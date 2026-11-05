#!/usr/bin/env python3
"""Collect the comparison runs of docs/experiment-protocol.md into one results file.

For each model, arm and question set it copies the run's responses, manifest and score into
examples/auto-ontology/live/experiment/<model>/<arm>-<set>/ and writes
examples/auto-ontology/live/experiment/summary.json: per run, the questions with exactly the
expected rows, SQL runs, repairs, seconds per request and tokens; per question, each arm's result.

usage: uv run python tools/summarise_experiment.py RUNS_JSON
RUNS_JSON maps "<model>/<arm>/<set>" to a run directory.
"""
from __future__ import annotations

import json
import shutil
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "examples/auto-ontology/live"))
from evaluate_run import evaluate  # noqa: E402

OUT = REPO / "examples/auto-ontology/live/experiment"
DATA = REPO / "examples/auto-ontology/auto_ontology_code"
SETS = {
    "development": (DATA / "evaluation.json", REPO / "eval/answer_contracts.json"),
    "heldout": (DATA / "heldout_evaluation.json", REPO / "eval/heldout_contracts.json"),
}
MODELS = {"nemotron": "nvidia/nemotron-3.5-lightning-30b-a3b", "deepseek": "deepseek/deepseek-v4.1-flash-1017"}


def responses_dir(run: Path) -> Path:
    for candidate in (run / "responses", run / "run/responses/10i_ask_with_key"):
        if candidate.is_dir():
            return candidate
    raise SystemExit(f"no responses under {run}")


def sql_runs(record: dict) -> tuple[int, int]:
    """(SQL executions, repairs) for one response of any arm."""
    if "attempts" in record:
        return len(record["attempts"]), max(0, len(record["attempts"]) - 1)
    ends = [e for e in record.get("events", []) if e.get("phase") == "end"]
    runs = sum(1 for e in ends if e.get("node") == "execute_sql_query")
    repairs = sum(1 for e in ends if e.get("node") == "reconstruct_sql")
    return runs, repairs


def tokens(record: dict) -> int | None:
    usage = record.get("usage") or {}
    return usage.get("total_tokens")


def main() -> int:
    runs = json.loads(Path(sys.argv[1]).read_text())
    notes = runs.pop("_notes", {})
    if OUT.exists():
        shutil.rmtree(OUT)
    summary = {"protocol": "docs/experiment-protocol.md", "models": MODELS, "runs": [], "questions": {}, "notes": notes,
               "question_text": {qset: {str(q["question_id"]): q["question"] for q in json.loads(files[0].read_text())}
                                 for qset, files in SETS.items()}}
    for key, path in sorted(runs.items()):
        model, arm, qset = key.split("/")
        run = Path(path)
        evaluation, contracts = SETS[qset]
        report = evaluate(responses_dir(run), evaluation, contracts)
        dest = OUT / model / f"{arm}-{qset}"
        (dest / "responses").mkdir(parents=True)
        for f in sorted(responses_dir(run).glob("ask_q*.json")):
            shutil.copyfile(f, dest / "responses" / f.name)
        for name in ("manifest.json", "status.json", "system_prompt.txt"):
            if (run / name).is_file():
                shutil.copyfile(run / name, dest / name)
        (dest / "score.json").write_text(json.dumps(report, indent=2) + "\n")
        records = {int(f.stem[5:]): json.loads(f.read_text()) for f in (dest / "responses").glob("ask_q*.json")}
        elapsed = [r.get("elapsed_s") for r in records.values() if r.get("elapsed_s") is not None]
        counts = {q: sql_runs(r) for q, r in records.items()}
        toks = [t for t in (tokens(r) for r in records.values()) if t is not None]
        summary["runs"].append({
            "model": model, "arm": arm, "set": qset, "questions": report["questions"],
            "expected_rows": report["strict_rows_pass"],
            "median_seconds": round(statistics.median(elapsed), 1) if elapsed else None,
            "sql_runs": sum(c[0] for c in counts.values()),
            "requests_repaired": sum(1 for c in counts.values() if c[1]),
            "total_tokens": sum(toks) if len(toks) == len(records) else None,
            "path": str(dest.relative_to(REPO)),
        })
        for result in report["results"]:
            q = summary["questions"].setdefault(qset, {}).setdefault(str(result["question_id"]), {})
            q[f"{model}/{arm}"] = {"expected_rows": result["strict_rows_pass"], "rows": result.get("agent_rows"),
                                   "reference_rows": result.get("reference_rows"), "sql_runs": counts.get(result["question_id"], (0, 0))[0]}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    discarded = Path(sys.argv[1]).parent / "discarded/README.txt"
    if discarded.is_file():
        shutil.copyfile(discarded, OUT / "discarded.txt")
    for r in summary["runs"]:
        print(f"{r['model']:9} {r['arm']:14} {r['set']:12} {r['expected_rows']}/{r['questions']}  median {r['median_seconds']} s  repaired {r['requests_repaired']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
