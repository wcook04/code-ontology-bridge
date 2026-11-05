"""Score runs two ways: exact rows on the real database, and exact rows on every counterfactual database.

snapshot: the returned rows equal the reference rows on the repository's database (named columns,
          declared types, multiset equality, and order when the question asks for one).
suite:    the response's final SQL, run on the real database and on each counterfactual variant,
          returns the reference SQL's rows on every one of them. A response that fails snapshot
          fails suite.

Evaluator versions. "frozen" is the reference SQL committed before any model run
(study/questions/questions.json). "corrected" applies study/questions/corrections.json on top: reference
queries found, after the runs, not to express their own question's wording. The questions themselves and
every saved response are unchanged; only the reference rows a response is compared with differ.

usage: python study/score.py RUN_DIR [RUN_DIR ...] [--evaluator corrected] [--fuzz-dir build/study/fuzz] [--out scores.json]
"""
from __future__ import annotations

import argparse
import hashlib
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
    """Open a database under the real database's catalog name, so that every variant answers to
    the same names: Auto Ontology's agent qualifies tables as <repo>_code.code.<table>."""
    from run_direct import DB_CONFIG
    stem = Path(path).stem
    catalog = stem if stem.endswith("_code") else stem.rsplit("_v", 1)[0] + "_code"
    con = duckdb.connect(config=DB_CONFIG)
    con.execute(f"ATTACH '{path}' AS {catalog} (READ_ONLY)")
    con.execute(f"USE {catalog}")
    return con


def execute(path: str, sql: str):
    from run_direct import timed
    return timed(connect(path), sql)


@lru_cache(maxsize=None)
def reference(path: str, sql: str):
    return execute(path, sql)[1]


def as_dicts(names, rows):
    return [dict(zip(names, r)) for r in rows]


EXPECTED_VARIANTS = 8
EVALUATORS = ("frozen", "corrected")


def load_questions(evaluator: str = "corrected") -> dict:
    """The 48 questions with the reference SQL of the chosen evaluator version."""
    if evaluator not in EVALUATORS:
        raise ValueError(f"evaluator must be one of {EVALUATORS}")
    questions = {q["id"]: dict(q) for q in json.loads((ROOT / "study/questions/questions.json").read_text())}
    for q in questions.values():
        q["accepted_sql"] = [q["reference_sql"]]
    if evaluator == "corrected":
        doc = json.loads((ROOT / "study/questions/corrections.json").read_text())
        for c in doc["corrections"]:
            questions[c["id"]]["reference_sql"] = c["reference_sql"]
            questions[c["id"]]["accepted_sql"] = [c["reference_sql"]]
        for r in doc["accepted_readings"]:
            questions[r["id"]]["accepted_sql"] += r["accepted_sql"]
    return questions


FUZZ_DIRS = {"frozen": ROOT / "build/study/fuzz", "corrected": ROOT / "build/study/fuzz-corrected"}


@lru_cache(maxsize=None)
def sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def databases(repo: str, fuzz_dir: Path) -> list[str]:
    """The real database and its eight counterfactual variants. Refuses to return a shorter list:
    without the variants a suite score would silently equal the snapshot score."""
    real = str(ROOT / "study/data" / repo / f"{repo}_code.duckdb")
    variants = sorted(str(p) for p in fuzz_dir.glob(f"{repo}_v*.duckdb"))
    if len(variants) != EXPECTED_VARIANTS:
        raise SystemExit(f"{repo}: found {len(variants)} counterfactual databases in {fuzz_dir}, expected "
                         f"{EXPECTED_VARIANTS}. Build them with: python study/fuzz.py {repo} {fuzz_dir} --variants 8 --seed 0")
    return [real] + variants


def score_run(run: Path, questions: dict, fuzz_dir: Path) -> dict:
    manifest = json.loads((run / "manifest.json").read_text())
    dbs = databases(manifest["repo"], fuzz_dir)
    out = []
    for qid in manifest["question_ids"]:
        q = questions[qid]
        path = run / "responses" / f"{qid}.json"
        r = json.loads(path.read_text()) if path.exists() else None
        # A response passes suite when one accepted reading of the question gives its rows on every
        # database; snapshot needs one reading on the real database only.
        snapshot = suite = False
        failed_on = None
        if r and not r["error"]:
            for ref_sql in q["accepted_sql"]:
                if not rows_match(r["rows"], reference(dbs[0], ref_sql), q["fields"], q["ordered"]):
                    continue
                snapshot = True
                first_fail = None
                for db in dbs[1:]:
                    try:
                        names, rows = execute(db, r["sql"])
                        ok = rows_match(as_dicts(names, rows), reference(db, ref_sql), q["fields"], q["ordered"])
                    except duckdb.Error:
                        ok = False
                    if not ok:
                        first_fail = Path(db).name
                        break
                if first_fail is None:
                    suite, failed_on = True, None
                    break
                failed_on = failed_on or first_fail
        out.append({"id": qid, "answered": bool(r and not r["error"]), "snapshot": snapshot, "suite": suite,
                    "suite_failed_on": failed_on, "attempts": len(r["attempts"]) if r else 0,
                    "elapsed_s": r["elapsed_s"] if r else None,
                    "cost": (r or {}).get("usage", {}).get("cost"),
                    "prompt_tokens": (r or {}).get("usage", {}).get("prompt_tokens"),
                    "completion_tokens": (r or {}).get("usage", {}).get("completion_tokens")})
    return {"run": str(run), "arm": manifest["arm"],
            "databases": {Path(d).name: sha256(d) for d in dbs}, "model": manifest["model"], "repo": manifest["repo"],
            "n": len(out), "snapshot": sum(x["snapshot"] for x in out), "suite": sum(x["suite"] for x in out),
            "questions": out}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("runs", nargs="+", type=Path)
    p.add_argument("--evaluator", choices=EVALUATORS, default="corrected")
    p.add_argument("--fuzz-dir", type=Path)
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    args.fuzz_dir = args.fuzz_dir or FUZZ_DIRS[args.evaluator]
    questions = load_questions(args.evaluator)
    results = [score_run(r, questions, args.fuzz_dir) for r in args.runs if (r / "manifest.json").exists()]
    for s in results:
        print(f"{s['arm']} {s['model']:<40} {s['repo']:<14} snapshot {s['snapshot']}/{s['n']}  suite {s['suite']}/{s['n']}")
    if args.out:
        args.out.write_text(json.dumps(results, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
