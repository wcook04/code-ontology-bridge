"""Check every reference reading of the chosen evaluator before scoring with it.

For each question and each accepted reading: the SQL runs on the real database and on all eight
counterfactual databases, and its rows on the real database are compared with the frozen
reference's. Exits non-zero if any reading fails to run.

usage: python study/check_references.py [--evaluator corrected|frozen]
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "study"))
from score import FUZZ_DIRS, databases, execute, load_questions  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--evaluator", choices=["frozen", "corrected"], default="corrected")
p.add_argument("--out", type=Path)
a = p.parse_args()
frozen = load_questions("frozen")
report, failures = {}, 0
for qid, q in load_questions(a.evaluator).items():
    dbs = databases(q["repo"], FUZZ_DIRS[a.evaluator])
    frozen_real = Counter(map(tuple, execute(dbs[0], frozen[qid]["reference_sql"])[1]))
    rows = []
    for sql in q["accepted_sql"]:
        try:
            real = Counter(map(tuple, execute(dbs[0], sql)[1]))
            for db in dbs[1:]:
                execute(db, sql)
            rows.append({"runs_on_all_9": True, "real_rows": sum(real.values()),
                         "same_real_rows_as_frozen": real == frozen_real})
        except Exception as e:  # noqa: BLE001
            failures += 1
            rows.append({"runs_on_all_9": False, "error": str(e)[:200]})
    report[qid] = rows
changed = [k for k, v in report.items() if any(not r.get("same_real_rows_as_frozen", True) for r in v)]
print(f"{a.evaluator}: {sum(len(v) for v in report.values())} readings, {failures} failed to run; "
      f"real-database rows differ from the frozen reference for: {', '.join(changed) or 'none'}")
if a.out:
    a.out.write_text(json.dumps(report, indent=2) + "\n")
raise SystemExit(1 if failures else 0)
