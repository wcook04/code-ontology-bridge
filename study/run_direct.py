"""Ask one frozen question set with one model under one arm, and save every response.

Arms (all query the same DuckDB file; they differ only in what the model is told about it):
  A  schema       the physical schema of the base tables and the two base views
  B  base_model   A plus the base semantic model: table and column descriptions, keys and joins
  V  views        A plus the semantics-layer views listed physically, with no descriptions
  S  semantics    B plus the semantics layer: its views, their documented columns, keys, joins and definitions

The model returns JSON {"sql", "explanation"}. The SQL runs read-only. After an SQL error the model
sees the error and may try again, up to three runs in all. No question is ever rerun on its own.

usage: python study/run_direct.py ARM REPO MODEL OUT_DIR [--questions study/questions/questions.json]
       [--workers 8] [--env-file ~/.config/cob-eval/models.env] [--dry-run-reference]
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "examples/auto-ontology/live"))
from direct_sql_run import model_context  # noqa: E402

from code_ontology_bridge.semantics import LAYER_VIEWS, layer_context_text  # noqa: E402

ARMS = {"A": "schema", "B": "base_model", "V": "views", "S": "semantics"}
MODELS = {
    "deepseek": "deepseek/deepseek-v4.1-flash-1017",
    "nemotron": "nvidia/nemotron-3.5-lightning",
}
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
MAX_ATTEMPTS = 3
MAX_TOKENS = 4000
LAYER = {v.name for v in LAYER_VIEWS}

INSTRUCTION = (
    "Return exactly the requested output columns, using each requested name as the column alias, in the requested order. "
    "Return complete repository-relative file paths and complete symbol IDs exactly as stored. "
    "When the question asks which files, symbols or modules, return each distinct one once unless it asks for occurrences."
)


def physical_schema(con: duckdb.DuckDBPyConnection, include_layer: bool) -> str:
    lines = []
    for name, kind in con.execute(
            "SELECT table_name, table_type FROM information_schema.tables WHERE table_schema = 'code' ORDER BY table_name").fetchall():
        if name in LAYER and not include_layer:
            continue
        cols = con.execute(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = 'code' AND table_name = ? ORDER BY ordinal_position",
            [name]).fetchall()
        lines.append(f"{'view' if kind == 'VIEW' else 'table'} code.{name}(" + ", ".join(f"{c} {t}" for c, t in cols) + ")")
    return "\n".join(lines)


def system_prompt(arm: str, con, base_model: Path) -> str:
    parts = [
        "You answer questions about a Python code base by writing one DuckDB SQL query over the database described below. "
        "Tables are in the schema named code; always qualify them, as in code.calls.",
        'Reply with a JSON object only: {"sql": "<one SELECT statement>", "explanation": "<2-4 sentences on what the query computes>"}.',
        INSTRUCTION,
        "Schema:\n" + physical_schema(con, include_layer=arm in ("V", "S")),
    ]
    if arm in ("B", "S"):
        parts.append("What the tables and columns mean:" + model_context(base_model))
    if arm == "S":
        parts.append(layer_context_text())
    return "\n\n".join(parts)


def contract_text(q: dict) -> str:
    fields = ", ".join(f"{f['name']} ({f['type']})" for f in q["fields"])
    return f"Requested output columns: {fields}." + (" Order the rows as the question asks." if q["ordered"] else "")


def jsonable(v):
    return float(v) if isinstance(v, Decimal) else v


QUERY_TIMEOUT_S = 60


def timed(con, sql: str):
    """Execute and fetch, interrupting the query after QUERY_TIMEOUT_S (a recursive query without a cycle check can run forever)."""
    import threading
    timer = threading.Timer(QUERY_TIMEOUT_S, con.interrupt)
    timer.start()
    try:
        cur = con.execute(sql)
        return [d[0] for d in cur.description], cur.fetchall()
    except duckdb.InterruptException as e:
        raise duckdb.Error(f"query interrupted after {QUERY_TIMEOUT_S} s") from e
    finally:
        timer.cancel()


def run_sql(con, sql: str) -> list[dict]:
    names, rows = timed(con, sql)
    return [dict(zip(names, map(jsonable, r))) for r in rows]


def chat(key: str, model: str, messages: list[dict]) -> tuple[str, dict]:
    body = json.dumps({
        "model": model, "messages": messages, "temperature": 0, "max_tokens": MAX_TOKENS,
        "reasoning": {"enabled": False}, "usage": {"include": True},
    }).encode()
    last = None
    for wait in (0, 5, 15, 45, 90):
        time.sleep(wait)
        req = urllib.request.Request(ENDPOINT, data=body, headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/wcook04/code-ontology-bridge", "X-Title": "code-ontology-bridge study"})
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read())
            if "choices" not in data:
                last = RuntimeError(str(data)[:300])
                continue
            usage = data.get("usage", {})
            usage["provider"] = data.get("provider")
            usage["model_served"] = data.get("model")
            return data["choices"][0]["message"].get("content") or "", usage
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last = e
    raise RuntimeError(f"model request failed: {last}")


def parse_reply(text: str) -> tuple[str, str]:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return "", ""
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return "", ""
    return (d.get("sql") or "").strip(), (d.get("explanation") or "").strip()


def ask(q: dict, args, system: str, key: str | None) -> dict:
    con = duckdb.connect(str(args.db), read_only=True)
    request = q["question"] + "\n\n" + contract_text(q)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": request}]
    attempts, usage_total, started = [], {}, time.monotonic()
    rows, sql, explanation, error = None, "", "", None
    try:
        for _ in range(MAX_ATTEMPTS):
            if args.dry_run_reference:
                reply, usage = json.dumps({"sql": q["reference_sql"], "explanation": "reference"}), {}
            else:
                reply, usage = chat(key, MODELS[args.model], messages)
            for k, v in usage.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    usage_total[k] = usage_total.get(k, 0) + v
            usage_total.setdefault("providers", []).append(usage.get("provider"))
            sql, explanation = parse_reply(reply)
            if not sql:
                error = "the reply had no SQL"
            else:
                try:
                    rows = run_sql(con, sql)
                    error = None
                except duckdb.Error as e:
                    rows, error = None, str(e).splitlines()[0][:500]
            attempts.append({"sql": sql, "error": error})
            if error is None:
                break
            messages += [{"role": "assistant", "content": reply},
                         {"role": "user", "content": f"That query failed: {error}\nReply with corrected JSON."}]
    finally:
        con.close()
    return {"question_id": q["id"], "arm": args.arm, "model": MODELS[args.model], "error": error,
            "elapsed_s": round(time.monotonic() - started, 2), "attempts": attempts, "usage": usage_total,
            "request": request, "explanation": explanation, "sql": sql, "rows": rows}


def read_key(env_file: Path, name: str) -> str:
    for line in env_file.read_text().splitlines():
        if line.strip().startswith(f"{name}="):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise SystemExit(f"{name} not set")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("arm", choices=ARMS)
    p.add_argument("repo")
    p.add_argument("model", choices=list(MODELS) + ["reference"])
    p.add_argument("out", type=Path)
    p.add_argument("--questions", type=Path, default=ROOT / "study/questions/questions.json")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--env-file", type=Path, default=Path.home() / ".config/cob-eval/models.env")
    p.add_argument("--dry-run-reference", action="store_true")
    args = p.parse_args()
    if args.dry_run_reference:
        args.model = "reference"
        MODELS["reference"] = "reference"
    if args.out.exists():
        raise SystemExit(f"{args.out} exists; every run gets a new directory")
    data = ROOT / "study/data" / args.repo
    args.db = data / f"{args.repo}_code.duckdb"
    questions = [q for q in json.loads(args.questions.read_text()) if q["repo"] == args.repo]
    con = duckdb.connect(str(args.db), read_only=True)
    system = system_prompt(args.arm, con, data / "base.model.yaml")
    con.close()
    key = None if args.dry_run_reference else read_key(args.env_file, "OPENROUTER_API_KEY")
    (args.out / "responses").mkdir(parents=True)
    (args.out / "system_prompt.txt").write_text(system)
    manifest = {
        "arm": args.arm, "arm_name": ARMS[args.arm], "repo": args.repo, "model": MODELS[args.model],
        "endpoint": ENDPOINT, "temperature": 0, "reasoning": "disabled", "max_tokens": MAX_TOKENS,
        "max_attempts": MAX_ATTEMPTS, "workers": args.workers,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "bridge_commit": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        "questions_sha256": sha(args.questions), "database_sha256": sha(args.db),
        "system_prompt_sha256": hashlib.sha256(system.encode()).hexdigest(),
        "question_ids": [q["id"] for q in questions],
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with concurrent.futures.ThreadPoolExecutor(args.workers) as pool:
        futs = [pool.submit(ask, q, args, system, key) for q in questions]
        for f in concurrent.futures.as_completed(futs):
            r = f.result()
            (args.out / "responses" / f"{r['question_id']}.json").write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n")
    (args.out / "complete.json").write_text(json.dumps({"finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                                       "responses": len(questions)}) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
