"""Score runs two ways: exact rows on the real database, and exact rows on every counterfactual database.

snapshot: the returned rows equal the reference rows on the repository's database (named columns,
          declared types, multiset equality, and order when the question asks for one).
suite:    the response's final SQL, run on the real database and on each counterfactual variant,
          returns the reference SQL's rows on every one of them. A response that fails snapshot
          fails suite.

usage: python study/score.py RUN_DIR [RUN_DIR ...] [--fuzz-dir build/study/fuzz] [--out scores.json]
"""
from __future__ import annotations

import argparse
import json
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402
sys.path.insert(0, str(ROOT / "study"))


def key(value, kind):
    if value is None:
        return None
    if kind == "string":
        if not isinstance(value, str):
            raise ValueError("expected string")
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("expected number")
    n = Decimal(str(value))
    if kind == "integer" and n != n.to_integral_value():
        raise ValueError("expected integer")
    return n


def rows_match(rows: list[dict] | None, want: list[tuple], fields: list[dict], ordered: bool) -> bool:
    if rows is None:
        return False
    names = [f["name"] for f in fields]
    try:
        if any(set(r) != set(names) for r in rows):
            return False
        got = [tuple(key(r[f["name"]], f["type"]) for f in fields) for r in rows]
        exp = [tuple(key(v, f["type"]) for v, f in zip(r, fields, strict=True)) for r in want]
    except (KeyError, ValueError):
        return False
    if len(got) != len(exp):
        return False

    def eq(a, b):
        return all((x is None and y is None) or (x is not None and y is not None and
                   (abs(x - y) <= Decimal("0.000001") if f["type"] == "number" else x == y))
                   for x, y, f in zip(a, b, fields))
    if ordered:
        return all(eq(a, b) for a, b in zip(got, exp))
    assigned: dict[int, int] = {}

    def match(i, seen):
        for t, row in enumerate(exp):
            if t not in seen and eq(got[i], row):
                seen.add(t)
                if t not in assigned or match(assigned[t], seen):
                    assigned[t] = i
                    return True
        return False
    return all(match(i, set()) for i in range(len(got)))


@lru_cache(maxsize=None)
def connect(path: str):
    return duckdb.connect(path, read_only=True)


def execute(path: str, sql: str):
    from run_direct import timed
    return timed(connect(path), sql)


@lru_cache(maxsize=None)
def reference(path: str, sql: str):
    return execute(path, sql)[1]


def as_dicts(names, rows):
    return [dict(zip(names, r)) for r in rows]


def databases(repo: str, fuzz_dir: Path) -> list[str]:
    real = str(ROOT / "study/data" / repo / f"{repo}_code.duckdb")
    return [real] + sorted(str(p) for p in fuzz_dir.glob(f"{repo}_v*.duckdb"))


def score_run(run: Path, questions: dict, fuzz_dir: Path) -> dict:
    manifest = json.loads((run / "manifest.json").read_text())
    dbs = databases(manifest["repo"], fuzz_dir)
    out = []
    for qid in manifest["question_ids"]:
        q = questions[qid]
        path = run / "responses" / f"{qid}.json"
        r = json.loads(path.read_text()) if path.exists() else None
        snapshot = bool(r and not r["error"] and rows_match(r["rows"], reference(dbs[0], q["reference_sql"]), q["fields"], q["ordered"]))
        suite, failed_on = snapshot, None
        if snapshot:
            for db in dbs[1:]:
                try:
                    names, rows = execute(db, r["sql"])
                    ok = rows_match(as_dicts(names, rows), reference(db, q["reference_sql"]), q["fields"], q["ordered"])
                except duckdb.Error:
                    ok = False
                if not ok:
                    suite, failed_on = False, Path(db).name
                    break
        out.append({"id": qid, "answered": bool(r and not r["error"]), "snapshot": snapshot, "suite": suite,
                    "suite_failed_on": failed_on, "attempts": len(r["attempts"]) if r else 0,
                    "elapsed_s": r["elapsed_s"] if r else None,
                    "cost": (r or {}).get("usage", {}).get("cost"),
                    "prompt_tokens": (r or {}).get("usage", {}).get("prompt_tokens"),
                    "completion_tokens": (r or {}).get("usage", {}).get("completion_tokens")})
    return {"run": str(run), "arm": manifest["arm"], "model": manifest["model"], "repo": manifest["repo"],
            "n": len(out), "snapshot": sum(x["snapshot"] for x in out), "suite": sum(x["suite"] for x in out),
            "questions": out}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("runs", nargs="+", type=Path)
    p.add_argument("--questions", type=Path, default=ROOT / "study/questions/questions.json")
    p.add_argument("--fuzz-dir", type=Path, default=ROOT / "build/study/fuzz")
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    questions = {q["id"]: q for q in json.loads(args.questions.read_text())}
    results = [score_run(r, questions, args.fuzz_dir) for r in args.runs if (r / "manifest.json").exists()]
    for s in results:
        print(f"{s['arm']} {s['model']:<40} {s['repo']:<14} snapshot {s['snapshot']}/{s['n']}  suite {s['suite']}/{s['n']}")
    if args.out:
        args.out.write_text(json.dumps(results, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
