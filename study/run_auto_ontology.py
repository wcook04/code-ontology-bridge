"""Arm C: the same frozen questions asked through NVIDIA Auto Ontology's own SQL agent.

The agent, its retrieval, validation and repair steps, the database and the chat model are fixed;
only the imported semantic model differs:
  C-base       the base model (tables, columns, keys, joins)
  C-semantics  the same model extended with the semantics layer's views, columns, keys and joins

It drives examples/auto-ontology/live/run_live.sh (pinned Auto Ontology checkout with the
documented compatibility patch) and converts each saved answer into the response shape
study/score.py reads, without changing any SQL or row.

usage: python study/run_auto_ontology.py VARIANT MODEL OUT_DIR UPSTREAM [--workers 3]
       VARIANT is base or semantics; MODEL is deepseek or nemotron; only repo auto_ontology.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "study"))
from run_direct import INSTRUCTION, MODELS  # noqa: E402

REPO = "auto_ontology"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("variant", choices=["native", "base", "semantics"])
    p.add_argument("model", choices=list(MODELS))
    p.add_argument("out", type=Path)
    p.add_argument("upstream", type=Path)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--questions", type=Path, default=ROOT / "study/questions/questions.json")
    p.add_argument("--env-file", type=Path, default=Path.home() / ".config/cob-eval/models.env")
    p.add_argument("--port-offset", type=int, default=0)
    args = p.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    inputs = out / "inputs"
    inputs.mkdir()
    questions = [q for q in json.loads(args.questions.read_text()) if q["repo"] == REPO]
    ids = {i + 1: q["id"] for i, q in enumerate(questions)}
    evaluation = [{"question_id": i, "question": q["question"], "evidence": "", "SQL": q["reference_sql"], "difficulty": q["difficulty"]}
                  for i, q in zip(ids, questions)]
    contracts = {"protocol": "study-v1", "instruction": INSTRUCTION,
                 "questions": {str(i): {"fields": q["fields"], "ordered": q["ordered"],
                                        "guidance": "Order the rows as the question asks." if q["ordered"] else ""}
                               for i, q in zip(ids, questions)}}
    (inputs / "evaluation.json").write_text(json.dumps(evaluation, indent=2))
    (inputs / "contracts.json").write_text(json.dumps(contracts, indent=2))
    data = ROOT / "study/data" / REPO
    model_file = data / ("base.model.yaml" if args.variant == "base" else "semantic.model.yaml")
    db = data / f"{REPO}_code.duckdb"
    if args.variant in ("base", "native"):
        # The base and native variants' database holds no layer views, so the agent cannot find them by introspection.
        base_db = ROOT / "build/study/base" / f"{REPO}_code.duckdb"
        db = base_db
    manifest = {
        "arm": "C", "variant": args.variant, "repo": REPO, "model": MODELS[args.model], "endpoint": "https://openrouter.ai/api/v1",
        "workers": args.workers, "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "bridge_commit": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        "upstream_commit": subprocess.check_output(["git", "-C", str(args.upstream), "rev-parse", "HEAD"], text=True).strip(),
        "model_file": str(model_file.relative_to(ROOT)), "model_sha256": hashlib.sha256(model_file.read_bytes()).hexdigest(),
        "questions_sha256": hashlib.sha256(args.questions.read_bytes()).hexdigest(),
        "question_ids": [q["id"] for q in questions], "id_map": ids,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    env = os.environ.copy()
    o = args.port_offset
    env.update({
        "AUTO_ONTOLOGY_CLONE": str(args.upstream.resolve()), "AO_RUN_DIR": str(out / "run"),
        "PG_PORT": str(54339 + o), "AO_BACKEND_PORT": str(3111 + o), "AO_KEYLESS_PORT": str(3101 + o), "AO_INGEST_PORT": str(3102 + o),
        "AO_CHAT_ENDPOINT": "https://openrouter.ai/api/v1", "AO_CHAT_KEY_VAR": "OPENROUTER_API_KEY", "AO_CHAT_MODEL": MODELS[args.model],
        "AO_CALCULATION_ONLY": "1", "AO_QIDS": " ".join(map(str, ids)), "KEYED_ONLY": "1",
        "AO_CONTRACTS": str(inputs / "contracts.json"), "AO_MODEL_FILE": str(model_file),
        "AO_EVALUATION_FILE": str(inputs / "evaluation.json"), "AO_WORKERS": str(args.workers),
        "AO_DUCKDB_FILE": str(db), "AO_SKIP_SYNC": "1", "UV_CACHE_DIR": str(ROOT / "build/uv-cache"), "PYTHONUNBUFFERED": "1",
    })
    script = ROOT / "examples/auto-ontology/live/run_live.sh"
    if args.variant == "native":
        # Same script with the model import removed: the agent sees only the catalog Auto Ontology builds itself.
        # Written next to run_live.sh (it finds its helpers from its own directory) and removed afterwards.
        text = script.read_text()
        start = text.index('  psql_db $DB3 -At -f "$HERE/sql/live_catalog_ids.sql"')
        end = text.index("  psql_db $DB3 -q -f \"$HERE/sql/frontend_configurations.sql\"\n  : > \"$LOGS/ingestion_keyed.compile_marker\"")
        native = script.with_name(f".run_live_native_{os.getpid()}.sh")
        native.write_text(text[:start] + '  echo "model import skipped (C-native)" > "$RESP/10c_model_import_skipped.txt"\n' + text[end:])
        (inputs / "run_live_native.sh").write_text(native.read_text())
        script = native
    try:
        with (out / "runner.log").open("w") as log:
            code = subprocess.call(["sh", str(script), "--with-key", str(args.env_file)],
                                   cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    finally:
        if args.variant == "native":
            script.unlink(missing_ok=True)
    responses = out / "responses"
    responses.mkdir()
    for i, qid in ids.items():
        src = out / "run/responses/10i_ask_with_key" / f"ask_q{i}.json"
        if not src.exists():
            continue
        rec = json.loads(src.read_text())
        ev = next((e for e in rec.get("events", []) if e.get("type") == "result"), {})
        ans = ev.get("answer") or {}
        rows = ans.get("sql_response_from_db")
        if isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], str):
            try:
                rows = json.loads(rows[0])
            except json.JSONDecodeError:
                pass
        if isinstance(rows, dict):
            rows = [rows]
        failed = rec.get("status") != 200 or rec.get("error") or not ev
        (responses / f"{qid}.json").write_text(json.dumps({
            "question_id": qid, "arm": f"C-{args.variant}", "model": MODELS[args.model],
            "error": rec.get("error") or (None if not failed else "no result"),
            "elapsed_s": rec.get("elapsed_s"), "attempts": [{"sql": ans.get("sql_code")}], "usage": {},
            "request": rec.get("request", {}).get("question") if isinstance(rec.get("request"), dict) else None,
            "explanation": ans.get("response"), "sql": ans.get("sql_code") or "", "rows": rows if not failed else None,
            "source_record": str(src.relative_to(out))}, indent=2, ensure_ascii=False) + "\n")
    (out / "complete.json").write_text(json.dumps({"exit_code": code, "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
