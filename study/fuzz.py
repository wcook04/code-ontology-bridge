"""Build counterfactual databases for test-suite scoring.

A query can return the right rows on one database by coincidence: a missing "direct calls only"
filter changes nothing if no callback reference happens to touch the target. Following test-suite
accuracy (Zhong, Yu and Klein, EMNLP 2020), each repository's database is copied and its base
rows are perturbed in ways that keep the data valid: new files, functions, methods and classes
(some reusing existing names), new direct calls and callback references, removed calls, new
imports, bases and test links, and toggled docstrings. Perturbations are random, but new edges
are biased towards the symbols and files each question names, so that wrong interpretations of a
question have a chance to change its answer. The semantics-layer views are views, so they follow
the perturbed rows automatically.

usage: python study/fuzz.py REPO OUT_DIR [--variants 8] [--seed 0]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import shutil
from pathlib import Path

import duckdb

from code_ontology_bridge.codemap.resolve import is_test_path

ROOT = Path(__file__).resolve().parents[1]


def targets(con, questions) -> tuple[list[str], list[str]]:
    """Symbols and files named by any question's text, reference SQL or reference answer."""
    syms = {r[0]: r[1] for r in con.execute("SELECT symbol_id, name FROM code.symbols").fetchall()}
    files = {r[0] for r in con.execute("SELECT file_id FROM code.files").fetchall()}
    names = {}
    for sid, n in syms.items():
        names.setdefault(n, []).append(sid)
    t_syms, t_files = set(), set()
    for q in questions:
        text = q["question"] + " " + q["reference_sql"]
        for lit in re.findall(r"'([^']+)'", q["reference_sql"]) + re.findall(r"`([^`]+)`", q["question"]):
            if lit in syms:
                t_syms.add(lit)
            if lit in files:
                t_files.add(lit)
            for sid in names.get(lit.split(".")[-1].rstrip("()"), [])[:5]:
                t_syms.add(sid)
        for word in re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", text):
            if word in names and len(names[word]) <= 3:
                t_syms.update(names[word])
        try:
            for row in con.execute(q["reference_sql"]).fetchall()[:40]:
                for v in row:
                    if v in syms:
                        t_syms.add(v)
                    if v in files:
                        t_files.add(v)
        except duckdb.Error:
            pass
    t_files |= {s.split("::")[0] for s in t_syms}
    return sorted(t_syms), sorted(t_files)


def mutate(db: Path, k: int, seed: int, t_syms: list[str], t_files: list[str]) -> dict:
    rng = random.Random(seed * 1000 + k)
    con = duckdb.connect(str(db))
    files = [r[0] for r in con.execute("SELECT file_id FROM code.files").fetchall()]
    sym_rows = con.execute("SELECT symbol_id, file_id, name, qualname, kind FROM code.symbols").fetchall()
    names = [r[2] for r in sym_rows]
    classes = [r[0] for r in sym_rows if r[4] == "class"]
    stats = {"variant": k}

    # Files: one test file, one in an existing folder, one in a new folder.
    folder = rng.choice([f.rsplit("/", 1)[0] for f in files if "/" in f] or [""])
    new_files = [f"tests/test_fuzz{k}.py", f"{folder}/fuzz_mod{k}.py".lstrip("/"), f"fuzzpkg{k}/core.py"]
    for f in new_files:
        if f in files:
            continue
        doc = rng.random() < 0.5
        con.execute("INSERT INTO code.files VALUES (?, ?, ?, ?, ?, 'fuzz', ?, ?, false)", [
            f, f.rsplit("/", 1)[0].replace("/", ".") if "/" in f else "", f.removesuffix(".py").replace("/", "."),
            is_test_path(f), rng.randint(5, 400), "Fuzz module." if doc else "", "module_docstring" if doc else "none"])
        files.append(f)
    stats["files_added"] = len(new_files)

    # Symbols: some reuse existing names, in new and existing files (including target files).
    new_syms = []
    host_files = new_files + rng.sample(files, min(6, len(files))) + t_files[:6]
    for i in range(30):
        f = rng.choice(host_files)
        kind = rng.choice(["function", "function", "method", "class"])
        base = rng.choice(names) if rng.random() < 0.5 else f"fz{k}_{i}"
        if rng.random() < 0.25:
            base = "_" + base.lstrip("_")
        if kind == "method":
            cls = f"FzC{k}_{i}"
            con.execute("INSERT INTO code.symbols VALUES (?, ?, ?, ?, 'class', 1, 50, true, '', 'none')",
                        [f"{f}::{cls}", f, cls, cls])
            classes.append(f"{f}::{cls}")
            qual = f"{cls}.{base}"
        else:
            qual = base
        sid = f"{f}::{qual}"
        if con.execute("SELECT 1 FROM code.symbols WHERE symbol_id = ?", [sid]).fetchone():
            sid = f"{sid}@L{900 + i}"
        public = not base.startswith("_") and not qual.startswith("_")
        doc = rng.random() < 0.5
        con.execute("INSERT INTO code.symbols VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
            sid, f, base, qual, kind, 10 + i, 10 + i + rng.randint(1, 60), public,
            "Fuzz symbol." if doc else "", "docstring" if doc else "none"])
        new_syms.append(sid)
        if kind == "class":
            classes.append(sid)
    stats["symbols_added"] = len(new_syms)

    all_syms = [r[0] for r in sym_rows] + new_syms
    callers = new_syms + rng.sample(all_syms, min(40, len(all_syms))) + t_syms
    callees = t_syms * 3 + new_syms + rng.sample(all_syms, min(40, len(all_syms)))
    n = 0
    for i in range(160):
        a, b = rng.choice(callers), rng.choice(callees)
        kind = "direct" if rng.random() < 0.65 else "callback"
        res = rng.choice(["same_file", "imported", "method_on_self"])
        con.execute("INSERT INTO code.calls VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
            f"fuzz{k}:{i}", a, b, b.split("::")[-1].split(".")[-1], rng.randint(1, 500), res,
            "low" if kind == "callback" else "high", kind])
        n += 1
    for i in range(20):  # unlinked direct calls
        con.execute("INSERT INTO code.calls VALUES (?, ?, NULL, ?, 1, ?, 'low', 'direct')", [
            f"fuzzu{k}:{i}", rng.choice(callers), rng.choice(names), rng.choice(["builtin", "external", "dynamic_attribute", "unresolved"])])
    stats["calls_added"] = n + 20
    deleted = con.execute("SELECT call_id FROM code.calls WHERE callee_symbol_id IS NOT NULL AND call_id NOT LIKE 'fuzz%' "
                          "ORDER BY hash(call_id || ?) LIMIT (SELECT count(*) // 25 FROM code.calls)", [str(seed * 31 + k)]).fetchall()
    con.executemany("DELETE FROM code.calls WHERE call_id = ?", deleted)
    stats["calls_removed"] = len(deleted)

    for i in range(40):
        a = rng.choice(files + new_files)
        b = rng.choice(t_files + files) if rng.random() < 0.6 else None
        con.execute("INSERT INTO code.imports VALUES (?, ?, ?, ?, ?, ?)", [
            f"fuzz{k}:{i}", a, b, b.removesuffix(".py").replace("/", ".") if b else rng.choice(["os", "json", "typing"]),
            rng.randint(1, 30), b is not None])
    for i in range(20):  # imports made by the files questions name
        a = rng.choice(t_files or files)
        b = rng.choice(files)
        if a != b:
            con.execute("INSERT INTO code.imports VALUES (?, ?, ?, ?, ?, true)", [
                f"fuzzt{k}:{i}", a, b, b.removesuffix(".py").replace("/", "."), rng.randint(1, 30)])
    # Methods added to existing classes, some reusing names already defined elsewhere in the class hierarchy.
    method_names = [r[2] for r in sym_rows if r[4] == "method"] or names
    host_classes = [c for c in t_syms if c in classes] + rng.sample(classes, min(8, len(classes)))
    for i in range(12):
        c = rng.choice(host_classes)
        f, cq = c.split("::", 1)
        cq = cq.split("@")[0]
        m = rng.choice(method_names)
        sid = f"{f}::{cq}.{m}"
        if con.execute("SELECT 1 FROM code.symbols WHERE symbol_id = ?", [sid]).fetchone():
            sid = f"{sid}@L{800 + i}"
        con.execute("INSERT INTO code.symbols VALUES (?, ?, ?, ?, 'method', ?, ?, ?, '', 'none')", [
            sid, f, m, f"{cq}.{m}", 700 + i, 700 + i + rng.randint(1, 120), not m.startswith("_") and not cq.startswith("_")])
    # Sizes: change some files' line counts and some definitions' extents, favouring named files.
    for f in rng.sample(t_files, min(4, len(t_files))) + rng.sample(files, min(4, len(files))):
        con.execute("UPDATE code.files SET line_count = ? WHERE file_id = ?", [rng.randint(50, 6000), f])
    for sid in rng.sample(all_syms, min(10, len(all_syms))):
        con.execute("UPDATE code.symbols SET line_end = line_start + ? WHERE symbol_id = ?", [rng.randint(1, 200), sid])
    test_files = [f for f, in con.execute("SELECT file_id FROM code.files WHERE is_test").fetchall()]
    prod = [f for f, in con.execute("SELECT file_id FROM code.files WHERE NOT is_test").fetchall()]
    for i in range(10):
        con.execute("INSERT OR IGNORE INTO code.test_links VALUES (?, ?, ?)",
                    [rng.choice(test_files), rng.choice([f for f in t_files if f in prod] + prod), rng.choice(["imports_target", "name_match"])])
    target_classes = [c for c in t_syms if c in classes] or classes
    # New bases never create an inheritance cycle: Python rejects cyclic class hierarchies.
    parents = {}
    for c, b in con.execute("SELECT class_symbol_id, base_symbol_id FROM code.class_bases WHERE base_symbol_id IS NOT NULL").fetchall():
        parents.setdefault(c, set()).add(b)

    def ancestors(x):
        seen, stack = set(), [x]
        while stack:
            for b in parents.get(stack.pop(), ()):
                if b not in seen:
                    seen.add(b)
                    stack.append(b)
        return seen
    for i, c in enumerate(rng.sample(classes, min(12, len(classes)))):
        b = rng.choice(target_classes + classes)
        if b == c or c in ancestors(b):
            continue
        con.execute("INSERT INTO code.class_bases VALUES (?, ?, ?, ?)", [c, 90 + i, b.split("::")[-1], b])
        parents.setdefault(c, set()).add(b)
    # Toggle documentation on a few existing symbols and files.
    con.execute("UPDATE code.symbols SET summary = CASE WHEN summary_source = 'docstring' THEN '' ELSE 'Fuzz doc.' END, "
                "summary_source = CASE WHEN summary_source = 'docstring' THEN 'none' ELSE 'docstring' END "
                "WHERE hash(symbol_id || ?) % 20 = 0", [str(k)])
    con.execute("UPDATE code.files SET description = CASE WHEN description_source = 'none' THEN 'Fuzz.' ELSE '' END, "
                "description_source = CASE WHEN description_source = 'none' THEN 'module_docstring' ELSE 'none' END "
                "WHERE hash(file_id || ?) % 10 = 0", [str(k)])
    con.close()
    return stats


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("repo")
    p.add_argument("out", type=Path)
    p.add_argument("--variants", type=int, default=8)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--questions", type=Path, default=ROOT / "study/questions/questions.json")
    args = p.parse_args()
    src = ROOT / "study/data" / args.repo / f"{args.repo}_code.duckdb"
    questions = [q for q in json.loads(args.questions.read_text()) if q["repo"] == args.repo]
    con = duckdb.connect(str(src), read_only=True)
    t_syms, t_files = targets(con, questions)
    con.close()
    args.out.mkdir(parents=True, exist_ok=True)
    report = {"repo": args.repo, "seed": args.seed, "target_symbols": len(t_syms), "target_files": len(t_files), "variants": []}
    for k in range(args.variants):
        db = args.out / f"{args.repo}_v{k}.duckdb"
        shutil.copyfile(src, db)
        report["variants"].append(mutate(db, k, args.seed, t_syms, t_files))
    (args.out / f"{args.repo}_fuzz.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "variants"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
