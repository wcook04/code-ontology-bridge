#!/usr/bin/env python3
"""Make one complete fresh_run.py job the published record in examples/auto-ontology/live/current/.

usage: uv run python tools/promote_run.py JOB_DIR

The job must have finished with state "complete". Its manifest, status, score, frozen inputs,
responses and logs replace the folder's contents, and artifacts.json is rewritten with the
SHA-256 of every file copied. The publication (tools/build_publication.py) reads this folder.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys

REPO = Path(__file__).resolve().parents[1]
CURRENT = REPO / "examples/auto-ontology/live/current"


def main() -> int:
    job = Path(sys.argv[1]).resolve()
    status = json.loads((job / "status.json").read_text())
    if status.get("state") != "complete":
        raise SystemExit(f"{job} did not complete: {status.get('state')}")
    if CURRENT.exists():
        shutil.rmtree(CURRENT)
    CURRENT.mkdir(parents=True)
    for name in ("manifest.json", "status.json", "score.json"):
        shutil.copyfile(job / name, CURRENT / name)
    for src, dest in ((job / "inputs", "inputs"), (job / "run/responses", "responses"), (job / "run/logs", "logs")):
        shutil.copytree(src, CURRENT / dest)
    files = sorted(p for p in CURRENT.rglob("*") if p.is_file())
    hashes = {str(p.relative_to(CURRENT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (CURRENT / "artifacts.json").write_text(json.dumps({"algorithm": "sha256", "source_job": job.name, "files": hashes}, indent=2) + "\n")
    print(f"promoted {job} -> {CURRENT.relative_to(REPO)}: {len(hashes)} files, {status['strict_rows_pass']}/{status['questions']} expected rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
