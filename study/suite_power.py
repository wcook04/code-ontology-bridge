"""For each question, count the counterfactual databases on which the reference answer differs from the real one.

usage: python study/suite_power.py [--questions ...] [--fuzz-dir build/study/fuzz] [--out study/results/suite_power.json]
"""
import argparse
import glob
import json
from collections import Counter
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument("--questions", type=Path, default=ROOT / "study/questions/questions.json")
p.add_argument("--fuzz-dir", type=Path, default=ROOT / "build/study/fuzz")
p.add_argument("--out", type=Path)
a = p.parse_args()
res = {}
for q in json.loads(a.questions.read_text()):
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
