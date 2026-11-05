"""For each question, count the counterfactual databases on which the reference answer differs from the real one.

usage: python study/suite_power.py [--evaluator corrected|frozen] [--fuzz-dir build/study/fuzz] [--out study/results/suite_power.json]
"""
import argparse
import glob
import json
from collections import Counter
from pathlib import Path

import sys

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "study"))
from score import FUZZ_DIRS, load_questions  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--evaluator", choices=["frozen", "corrected"], default="corrected")
p.add_argument("--fuzz-dir", type=Path)
p.add_argument("--out", type=Path)
a = p.parse_args()
a.fuzz_dir = a.fuzz_dir or FUZZ_DIRS[a.evaluator]
res = {}
for q in load_questions(a.evaluator).values():
    base = duckdb.connect(str(ROOT / f"study/data/{q['repo']}/{q['repo']}_code.duckdb"), read_only=True)
    ref = Counter(base.execute(q["reference_sql"]).fetchall())
    n = 0
    for path in sorted(glob.glob(str(a.fuzz_dir / f"{q['repo']}_v*.duckdb"))):
        c = duckdb.connect(path, read_only=True)
        n += Counter(c.execute(q["reference_sql"]).fetchall()) != ref
        c.close()
    res[q["id"]] = n
print(" ".join(f"{k}:{v}" for k, v in res.items()))
print(f"answer changes on at least one variant: {sum(v > 0 for v in res.values())}/{len(res)}")
if a.out:
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=2) + "\n")
