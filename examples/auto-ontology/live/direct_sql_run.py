"""Arms A and B of the comparison: the same language model writes SQL directly, without Auto Ontology.

Arm A ("schema") sees the physical schema: tables, columns and their types.
Arm B ("schema_model") also sees what the exported semantic model says: each table's and
column's description, the primary keys and the declared joins. Auto Ontology (arm C) is run
separately by fresh_run.py; these arms isolate what the exported descriptions are worth and
what Auto Ontology's own pipeline adds.

Each question gets the same request text as arm C: the question, its hint if it has one and
the output contract. The model returns JSON with "sql" and "explanation". The SQL runs
read-only on the exported DuckDB file. After an error the model sees the error and may try
again, up to MAX_ATTEMPTS runs in all. Responses are written in the shape evaluate_run.py
scores, so all three arms use one scorer.

usage:
  python direct_sql_run.py ARM OUT_DIR EVALUATION CONTRACTS DUCKDB MODEL_YAML \\
      --endpoint URL --model NAME --env-file PATH --key-name VAR [--workers 3]
  python direct_sql_run.py ARM OUT_DIR EVALUATION CONTRACTS DUCKDB MODEL_YAML --dry-run-reference
      (uses each question's reference SQL as the "model", to check the harness scores it fully)
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import time
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path

import duckdb
import yaml

MAX_ATTEMPTS = 3
ARMS = ("schema", "schema_model")


def physical_schema(con: duckdb.DuckDBPyConnection) -> str:
    lines = []
    tables = con.execute(
        "SELECT table_name, table_type FROM information_schema.tables WHERE table_schema = 'code' ORDER BY table_name").fetchall()
    for name, kind in tables:
        cols = con.execute(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = 'code' AND table_name = ? ORDER BY ordinal_position",
            [name]).fetchall()
        label = "view" if kind == "VIEW" else "table"
        lines.append(f"{label} code.{name}(" + ", ".join(f"{c} {t}" for c, t in cols) + ")")
    return "\n".join(lines)


def model_context(model_yaml: Path) -> str:
    """The exported model's descriptions, keys and joins, as plain text."""
    model = yaml.safe_load(model_yaml.read_text())
    col_names: dict[str, str] = {}
    out = []
    for db in model["data_layer"]["databases"]:
        for schema in db["schemas"]:
            for table in schema.get("tables", []) + schema.get("views", []):
                qual = f"{schema['name']}.{table['name']}"
                for c in table.get("columns", []):
                    col_names[c["id"]] = f"{qual}.{c['name']}"
                pk = ", ".join(col_names.get(i, i).split(".")[-1] for i in table.get("pk") or [])
                out.append(f"\n{qual}: {table.get('description', '').strip()}" + (f" Primary key: {pk}." if pk else ""))
                for c in table.get("columns", []):
                    out.append(f"  {c['name']} ({c.get('type', '')}): {c.get('description', '').strip()}")
    attr_to_col = {}
    for term in model.get("semantic_layer", {}).get("terms", []):
        for a in term.get("columns_attributes", []):
            attr_to_col[a["id"]] = col_names.get(a["column_id"], a["column_id"])
    joins = [f"  {col_names.get(fk['column_id'], fk['column_id'])} -> {attr_to_col.get(fk['column_attribute_id'], fk['column_attribute_id'])}"
             for fk in model.get("semantic_layer", {}).get("semantic_fks", [])]
    if joins:
        out.append("\nJoins:")
        out.extend(joins)
    return "\n".join(out)


def build_prompt(arm: str, schema: str, context: str, instruction: str) -> str:
    parts = [
        "You answer questions about a Python code base by writing one DuckDB SQL query over the database described below. "
        "Tables are in the schema named code; always qualify them, as in code.calls.",
        "Reply with a JSON object only: {\"sql\": \"<one SELECT statement>\", \"explanation\": \"<2-4 sentences on what the query computes>\"}.",
        instruction,
        "Schema:\n" + schema,
    ]
    if arm == "schema_model":
        parts.append("What the tables and columns mean:" + context)
    return "\n\n".join(parts)


def contract_text(contract: dict) -> str:
    fields = ", ".join(f"{f['name']} ({f['type']})" for f in contract["fields"])
    order = " Order the rows as the question asks." if contract.get("ordered") else ""
    return f"Requested output columns: {fields}.{order}"


def jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


def run_sql(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    cur = con.execute(sql)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, map(jsonable, row))) for row in cur.fetchall()]


def chat(endpoint: str, key: str, model: str, messages: list[dict], timeout: float = 300) -> tuple[str, dict]:
    body = json.dumps({"model": model, "messages": messages, "temperature": 0}).encode()
    req = urllib.request.Request(endpoint.rstrip("/") + "/chat/completions", data=body,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    for wait in (0, 5, 20):
        time.sleep(wait)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"] or "", data.get("usage", {})
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            last = error
    raise RuntimeError(f"model request failed: {last}")


def parse_reply(text: str) -> tuple[str, str]:
    match = re.search(r"\{.*\}", text, re.S)
    data = json.loads(match.group(0)) if match else {}
    return (data.get("sql") or "").strip(), (data.get("explanation") or "").strip()


def ask(question: dict, contract: dict, args, system: str, key: str | None) -> dict:
    con = duckdb.connect(str(args.duckdb), read_only=True)
    request = question["question"] + (f"\n\nHint: {question['evidence']}" if question.get("evidence") else "") + "\n\n" + contract_text(contract)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": request}]
    attempts, usage_total, started = [], {}, time.monotonic()
    rows, sql, explanation, error = None, "", "", None
    try:
        for _ in range(MAX_ATTEMPTS):
            if args.dry_run_reference:
                reply, usage = json.dumps({"sql": question["SQL"], "explanation": "Reference query."}), {}
            else:
                reply, usage = chat(args.endpoint, key, args.model, messages)
            for k, v in usage.items():
                if isinstance(v, (int, float)):
                    usage_total[k] = usage_total.get(k, 0) + v
            try:
                sql, explanation = parse_reply(reply)
            except json.JSONDecodeError:
                sql, explanation = "", ""
            if not sql:
                error = "the reply had no SQL"
            else:
                try:
                    rows = run_sql(con, sql)
                    error = None
                except duckdb.Error as exc:
                    error = str(exc).splitlines()[0]
            attempts.append({"sql": sql, "error": error})
            if error is None:
                break
            messages += [{"role": "assistant", "content": reply},
                         {"role": "user", "content": f"That query failed: {error}\nReply with corrected JSON."}]
    finally:
        con.close()
    answer = {"response": explanation, "sql_code": sql, "sql_response_from_db": rows if rows is not None else None}
    return {
        "question_id": question["question_id"], "status": 200, "error": error,
        "elapsed_s": round(time.monotonic() - started, 1), "attempts": attempts, "usage": usage_total,
        "request": {"question": request, "arm": args.arm, "model": args.model},
        "events": [{"type": "result", "answer": answer}],
    }


def read_key(env_file: Path, name: str) -> str:
    for line in env_file.read_text().splitlines():
        if line.strip().startswith(f"{name}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(f"{name} is not set in the env file")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("arm", choices=ARMS)
    p.add_argument("out", type=Path)
    p.add_argument("evaluation", type=Path)
    p.add_argument("contracts", type=Path)
    p.add_argument("duckdb", type=Path)
    p.add_argument("model_yaml", type=Path)
    p.add_argument("--endpoint")
    p.add_argument("--model", default="reference")
    p.add_argument("--env-file", type=Path)
    p.add_argument("--key-name")
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--dry-run-reference", action="store_true")
    args = p.parse_args()
    if args.out.exists():
        raise SystemExit(f"{args.out} exists; each run gets a new directory")
    key = None if args.dry_run_reference else read_key(args.env_file, args.key_name)
    questions = json.loads(args.evaluation.read_text())
    contracts = json.loads(args.contracts.read_text())
    con = duckdb.connect(str(args.duckdb), read_only=True)
    system = build_prompt(args.arm, physical_schema(con), model_context(args.model_yaml), contracts["instruction"])
    con.close()
    responses = args.out / "responses"
    responses.mkdir(parents=True)
    (args.out / "system_prompt.txt").write_text(system)
    (args.out / "manifest.json").write_text(json.dumps({
        "arm": args.arm, "model": args.model, "endpoint": args.endpoint, "workers": args.workers,
        "max_attempts": MAX_ATTEMPTS, "evaluation": str(args.evaluation), "contracts_protocol": contracts["protocol"],
        "duckdb": str(args.duckdb), "model_yaml": str(args.model_yaml), "dry_run_reference": args.dry_run_reference,
    }, indent=2) + "\n")
    with concurrent.futures.ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(ask, q, contracts["questions"][str(q["question_id"])], args, system, key): q for q in questions}
        for future in concurrent.futures.as_completed(futures):
            record = future.result()
            (responses / f"ask_q{record['question_id']}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
            print(f"q{record['question_id']}: {len(record['attempts'])} attempt(s), {'error' if record['error'] else 'ok'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
