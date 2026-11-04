#!/usr/bin/env python3
"""Record how the current extractor's output differs from the frozen worked example.

The committed example under examples/auto-ontology/auto_ontology_code is the
input the recorded Auto Ontology run used, so it stays as it was. When the
extractor is corrected, this tool rebuilds the example from a clone of
NVIDIA/auto-ontology at the pinned commit and writes every difference to
examples/auto-ontology/auto_ontology_code/extractor-corrections.json: the call
rows removed and added, the changed snapshot text, the changed summary
statistics and the questions whose reference answers change. The reproducibility
tests require a fresh build to differ from the committed example by exactly that
record.

usage: AUTO_ONTOLOGY_CLONE=/path/to/clone uv run python tools/record_extractor_corrections.py
"""
from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from code_ontology_bridge.codemap import build_code_map  # noqa: E402
from code_ontology_bridge.export import export_dataset, export_duckdb  # noqa: E402

PINNED_SHA = "cdaf61e1bd0cf3820d11d72b43bb460816aebbd3"
EXAMPLE = REPO / "examples" / "auto-ontology"
NAME = "auto_ontology_code"
OUT = EXAMPLE / NAME / "extractor-corrections.json"


def csv_rows(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text)))


def build(clone: Path, out: Path):
    epoch = subprocess.run(["git", "-C", str(clone), "log", "-1", "--format=%ct", "HEAD"], capture_output=True, text=True).stdout.strip()
    os.environ["SOURCE_DATE_EPOCH"] = epoch
    code_map = build_code_map(clone, repo_url="https://github.com/NVIDIA/auto-ontology", commit_sha=PINNED_SHA)
    questions = json.loads((REPO / "eval" / "auto_ontology_questions.json").read_text())
    analyses = json.loads((REPO / "eval" / "custom_analyses.json").read_text())
    db = export_duckdb(code_map, out / f"{NAME}.duckdb")
    dataset = export_dataset(code_map, out / NAME, duckdb_path=db, questions=questions, analyses=analyses)
    return code_map, dataset


def diff_rows(committed: Path, fresh: Path) -> dict[str, list[list[str]]]:
    old, new = csv_rows(committed.read_text()), csv_rows(fresh.read_text())
    assert old[0] == new[0], "header changed"
    old_set, new_set = {tuple(r) for r in old[1:]}, {tuple(r) for r in new[1:]}
    return {"header": old[0], "removed": sorted(map(list, old_set - new_set)), "added": sorted(map(list, new_set - old_set))}


def main() -> int:
    clone = Path(os.environ.get("AUTO_ONTOLOGY_CLONE", ""))
    head = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if head != PINNED_SHA:
        print(f"AUTO_ONTOLOGY_CLONE must be a clone at {PINNED_SHA}", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory() as tmp:
        code_map, dataset = build(clone, Path(tmp))
        committed = EXAMPLE / NAME
        tables = {}
        for csv_path in sorted((committed / "data").glob("*.csv")):
            fresh = dataset / "data" / csv_path.name
            if csv_path.read_bytes() != fresh.read_bytes():
                tables[csv_path.name] = diff_rows(csv_path, fresh)
        old_eval = {q["question_id"]: q for q in json.loads((committed / "evaluation.json").read_text())}
        new_eval = {q["question_id"]: q for q in json.loads((dataset / "evaluation.json").read_text())}
        changed_questions = {str(i): {"committed": old_eval[i], "fresh": new_eval[i]} for i in old_eval if old_eval[i] != new_eval[i]}
        old_summary = json.loads((EXAMPLE / "summary.json").read_text())
        summary_changes = {k: {"committed": old_summary.get(k), "fresh": v} for k, v in code_map.stats.items() if old_summary.get(k) != v}
    record = {
        "purpose": "Differences between the frozen worked example, which the recorded Auto Ontology run used, and the current extractor's output for the same source.",
        "auto_ontology_commit": PINNED_SHA,
        "extractor_change": "Imports bind only in the function, method or class that contains them; calls inside a nested function count for the enclosing function only when it calls the nested function or passes it on by name, directly or through other nested functions.",
        "tables": tables,
        "evaluation_changes": changed_questions,
        "summary_changes": summary_changes,
    }
    OUT.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n")
    calls = tables.get("code.calls.csv", {})
    print(f"wrote {OUT.relative_to(REPO)}: {len(calls.get('removed', []))} call rows removed, {len(calls.get('added', []))} added; "
          f"tables changed: {sorted(tables)}; reference answers changed: {sorted(changed_questions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
