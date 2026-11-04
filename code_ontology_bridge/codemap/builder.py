"""Build the code map of one repository: rows for every table of schema ``code``.

[PURPOSE]
- Teleology: Turn a Python checkout into the relational rows of schema ``code`` together with the snapshot identity (repository, commit, source fingerprint, builder) and the known limits of the analysis.
- Mechanism: List Python files (``git ls-files`` when the root is a git checkout, otherwise a directory walk), parse each with ``ast``, index modules, resolve imports and calls, link tests to targets, and sort every table by its primary key.
- Guarantee: The same checkout and options give byte-identical rows. A file that cannot be read or parsed is counted in ``omitted_file_count`` and named in ``omitted_files``; nothing is dropped silently.
- Fails: Raises ``FileNotFoundError`` when the root does not exist.
- Reads: The files under the root and, when present, git metadata of the checkout.
- Writes: Nothing.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .. import BUILDER_NAME, __version__
from . import docstrings
from .analyzer import analyse_source
from .resolve import FileContext, RepoIndex, is_test_path, module_name_for, name_match_targets
from .schema import TABLES

SKIP_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__", ".tox", ".mypy_cache", ".pytest_cache", "build", "dist"}

STATIC_KNOWN_LIMITS = (
    "Only Python files are analysed; other languages in the repository are not represented.",
    "Dynamic imports (importlib, __import__) and imports executed through strings are not resolved.",
    "Internal callees are resolved only through plain dotted names: same-file definitions, import bindings (following re-exports up to 3 levels), and self/cls methods of the enclosing class. Every other call keeps a null callee and is classified, never guessed: builtin (an unshadowed builtin name), external (rooted in a non-internal import or a module-level name assigned from one), dynamic_attribute (a method on an object whose type this analysis does not infer), or unresolved (parameters, local callables, super() and anything left).",
    "Functions passed by reference are recorded as call_kind callback (low confidence) only when a plain dotted name appears directly as a positional or keyword argument of a call inside a function and resolves, by the same rules, to an internal function or method: asyncio.to_thread(f, x), loop.run_in_executor(None, f), executor.submit(f), Thread(target=f), functools.partial(f), Depends(f). References held in lists, dicts, assignments, return values or decorators without a call are not recorded, a name the enclosing function binds locally is skipped, properties passed as values are skipped, arguments of inspect.* and of builtins that only examine a value (getattr, isinstance, print, repr and the like) are skipped, and every other receiving call is assumed, not proven, to invoke the reference.",
    "Builtin classification does not see local variables or parameters that shadow a builtin name.",
    "Inherited methods resolve only when the base class is statically resolvable to a definition in the repository; such calls are marked low confidence.",
    "Local variables that shadow a module-level name are not tracked, so a shadowed call may resolve to the module-level definition.",
    "Nested functions and classes defined inside a function are not symbols; their calls are attributed to the enclosing symbol.",
    "Test links are static: a test that exercises a file without importing it, and without a matching file name, is not linked.",
    "Descriptions and summaries are verbatim docstring text; no description is generated or inferred.",
)


@dataclass
class CodeMap:
    rows: dict[str, list[dict[str, Any]]]
    snapshot: dict[str, Any]
    omitted_files: list[dict[str, str]]
    stats: dict[str, Any] = field(default_factory=dict)


def compute_source_fingerprint(file_hashes: dict[str, str]) -> str:
    """16-hex SHA-256 over sorted ``path NUL sha256`` lines (same digest as the governance sidecars)."""
    digest = hashlib.sha256()
    for rel in sorted(file_hashes):
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hashes[rel].encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()[:16]


def _git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.decode("utf-8", "replace")


def discover_python_files(root: Path) -> list[str]:
    listed = _git(root, "ls-files", "-z", "--cached", "--", "*.py")
    if listed is not None:
        files = [f for f in listed.split("\0") if f]
        return sorted(f for f in files if (root / f).is_file())
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for name in filenames:
            if name.endswith(".py"):
                found.append((Path(dirpath) / name).relative_to(root).as_posix())
    return sorted(found)


def _built_at() -> str:
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    moment = datetime.fromtimestamp(int(epoch), UTC) if epoch else datetime.now(UTC)
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_code_map(
    root: str | Path,
    *,
    repo_url: str | None = None,
    commit_sha: str | None = None,
    exclude: list[str] | tuple[str, ...] = (),
) -> CodeMap:
    root = Path(root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)

    all_files = discover_python_files(root)
    omitted: list[dict[str, str]] = []
    candidates: list[str] = []
    for f in all_files:
        if any(fnmatch.fnmatch(f, pattern) for pattern in exclude):
            omitted.append({"file_id": f, "reason": "excluded"})
        else:
            candidates.append(f)

    package_dirs = {str(PurePosixPath(f).parent) for f in all_files if PurePosixPath(f).name == "__init__.py"}

    contexts: list[FileContext] = []
    file_meta: dict[str, dict[str, Any]] = {}
    for f in candidates:
        data = (root / f).read_bytes()
        try:
            facts = analyse_source(data.decode("utf-8"), filename=f)
        except (SyntaxError, ValueError, UnicodeDecodeError) as exc:
            omitted.append({"file_id": f, "reason": f"parse_error: {type(exc).__name__}"})
            continue
        module, package = module_name_for(f, package_dirs)
        contexts.append(FileContext(f, module, package, PurePosixPath(f).name == "__init__.py", facts))
        file_meta[f] = {"sha256": hashlib.sha256(data).hexdigest()}

    index = RepoIndex(contexts)

    files_rows, heading_rows, symbol_rows, call_rows, import_rows, link_rows = [], [], [], [], [], []
    base_rows: list[dict[str, Any]] = []
    module_level_calls = 0
    for ctx in contexts:
        facts = ctx.facts
        description, source = docstrings.module_description(facts.docstring)
        heads = docstrings.headings(facts.docstring)
        files_rows.append(
            {
                "file_id": ctx.file_id,
                "package": ctx.package,
                "module": ctx.module,
                "is_test": is_test_path(ctx.file_id),
                "line_count": facts.line_count,
                "sha256": file_meta[ctx.file_id]["sha256"],
                "description": description,
                "description_source": source,
                "has_fixed_headings": any(h.heading.startswith("[") for h in heads),
            }
        )
        for ordinal, h in enumerate(heads, start=1):
            heading_rows.append({"file_id": ctx.file_id, "heading": h.heading, "value": h.value, "ordinal": ordinal})
        for sym in facts.symbols:
            summary, summary_source = docstrings.symbol_summary(sym.docstring)
            symbol_rows.append(
                {
                    "symbol_id": ctx.definition_ids[(sym.qualname, sym.line_start)],
                    "file_id": ctx.file_id,
                    "name": sym.name,
                    "qualname": sym.qualname,
                    "kind": sym.kind,
                    "line_start": sym.line_start,
                    "line_end": sym.line_end,
                    "is_public": sym.is_public,
                    "summary": summary,
                    "summary_source": summary_source,
                }
            )
            for ordinal, (base_name, parts) in enumerate(sym.base_exprs, start=1):
                base_rows.append(
                    {
                        "class_symbol_id": ctx.definition_ids[(sym.qualname, sym.line_start)],
                        "ordinal": ordinal,
                        "base_name": base_name,
                        "base_symbol_id": index.resolve_base(ctx, parts),
                    }
                )
        module_level_calls += facts.module_level_calls
        seen: dict[tuple[int, int], int] = {}
        for call in facts.calls:
            res = index.resolve_callback(ctx, call) if call.is_callback else index.resolve_call(ctx, call)
            if res is None:
                continue
            key = (call.line, call.col)
            seq = seen.get(key, 0)
            seen[key] = seq + 1
            call_rows.append(
                {
                    "call_id": f"{ctx.file_id}:{call.line}:{call.col}:{seq}",
                    "caller_symbol_id": ctx.definition_ids[(call.caller, call.caller_line)],
                    "callee_symbol_id": res.callee_symbol_id,
                    "callee_name": call.callee_text,
                    "line": call.line,
                    "resolution": res.resolution,
                    "confidence": res.confidence,
                    "call_kind": "callback" if call.is_callback else "direct",
                }
            )
        for seq, (imp, module_name, target, internal) in enumerate(index.import_rows(ctx)):
            import_rows.append(
                {
                    "import_id": f"{ctx.file_id}:{imp.line}:{seq}",
                    "file_id": ctx.file_id,
                    "imported_file_id": target,
                    "module_name": module_name,
                    "line": imp.line,
                    "is_internal": internal,
                }
            )

    is_test = {r["file_id"]: r["is_test"] for r in files_rows}
    non_test = sorted(f for f, t in is_test.items() if not t)
    links: set[tuple[str, str, str]] = set()
    for row in import_rows:
        target = row["imported_file_id"]
        if is_test[row["file_id"]] and target and not is_test[target]:
            links.add((row["file_id"], target, "imports_target"))
    for test_file in (f for f, t in is_test.items() if t):
        for target in name_match_targets(test_file, non_test):
            links.add((test_file, target, "name_match"))
    link_rows = [{"test_file_id": a, "target_file_id": b, "reason": c} for a, b, c in links]

    file_hashes = {f: m["sha256"] for f, m in file_meta.items()}
    fingerprint = compute_source_fingerprint(file_hashes)
    commit = commit_sha or (_git(root, "rev-parse", "HEAD") or "").strip() or None
    url = repo_url or (_git(root, "remote", "get-url", "origin") or "").strip() or root.as_uri()

    known_limits = list(STATIC_KNOWN_LIMITS)
    known_limits.append(f"Calls at module level, outside any function or class, are not recorded ({module_level_calls} in this snapshot).")
    repeated = sum(len(c.definition_ids) - len(c.symbols) for c in contexts)
    if repeated:
        known_limits.append(f"{repeated} definitions share a qualified name. Their IDs include @L<definition-line>; ambiguous call targets are not resolved.")
    if index.ambiguous_modules:
        known_limits.append(
            f"{len(index.ambiguous_modules)} module names are shared by several files (e.g. top-level test modules); imports of those names are not resolved."
        )
    if omitted:
        known_limits.append(f"{len(omitted)} Python files were not analysed (excluded or unparseable).")
    if commit and _git(root, "status", "--porcelain", "--untracked-files=no", "--", "*.py"):
        known_limits.append("The working tree differs from the recorded commit; the source fingerprint identifies the analysed content.")

    snapshot = {
        "snapshot_id": f"{(commit or 'nocommit')[:12]}-{fingerprint[:12]}",
        "repo_url": url,
        "commit_sha": commit,
        "built_at": _built_at(),
        "builder_version": f"{BUILDER_NAME} {__version__}",
        "source_fingerprint": fingerprint,
        "file_count": len(files_rows),
        "omitted_file_count": len(omitted),
        "known_limits": json.dumps(known_limits),
    }

    rows = {
        "snapshot": [snapshot],
        "files": files_rows,
        "headings": heading_rows,
        "symbols": symbol_rows,
        "class_bases": base_rows,
        "calls": call_rows,
        "imports": import_rows,
        "test_links": link_rows,
    }
    for table in TABLES:
        rows[table.name].sort(key=lambda r, pk=table.primary_key: tuple(str(r[c]) for c in pk))
    code_map = CodeMap(rows=rows, snapshot=snapshot, omitted_files=sorted(omitted, key=lambda o: o["file_id"]))
    code_map.stats = summarise(code_map)
    return code_map


def summarise(code_map: CodeMap) -> dict[str, Any]:
    rows = code_map.rows
    by_kind: dict[str, dict[str, int]] = {"direct": {}, "callback": {}}
    for c in rows["calls"]:
        counts = by_kind[c["call_kind"]]
        counts[c["resolution"]] = counts.get(c["resolution"], 0) + 1
    by_source: dict[str, int] = {}
    for f in rows["files"]:
        by_source[f["description_source"]] = by_source.get(f["description_source"], 0) + 1
    n_files = len(rows["files"]) or 1
    symbols_by_kind: dict[str, int] = {}
    for s in rows["symbols"]:
        symbols_by_kind[s["kind"]] = symbols_by_kind.get(s["kind"], 0) + 1
    return {
        "snapshot": {k: v for k, v in code_map.snapshot.items() if k != "known_limits"},
        "known_limits": json.loads(code_map.snapshot["known_limits"]),
        "omitted_files": code_map.omitted_files,
        "row_counts": {name: len(r) for name, r in rows.items()},
        "files": {
            "total": len(rows["files"]),
            "test_files": sum(1 for f in rows["files"] if f["is_test"]),
            "with_fixed_headings": sum(1 for f in rows["files"] if f["has_fixed_headings"]),
            "description_source": dict(sorted(by_source.items())),
            "description_source_pct": {k: round(100 * v / n_files, 1) for k, v in sorted(by_source.items())},
        },
        "symbols": {
            "total": len(rows["symbols"]),
            "by_kind": dict(sorted(symbols_by_kind.items())),
            "public": sum(1 for s in rows["symbols"] if s["is_public"]),
            "with_summary": sum(1 for s in rows["symbols"] if s["summary_source"] == "docstring"),
        },
        "calls": {
            "total": len(rows["calls"]),
            "by_call_kind": {k: sum(v.values()) for k, v in by_kind.items()},
            "direct_by_resolution": dict(sorted(by_kind["direct"].items())),
            "callback_by_resolution": dict(sorted(by_kind["callback"].items())),
        },
        "class_bases": {
            "total": len(rows["class_bases"]),
            "resolved_to_internal_class": sum(1 for b in rows["class_bases"] if b["base_symbol_id"]),
        },
        "imports": {
            "total": len(rows["imports"]),
            "internal": sum(1 for i in rows["imports"] if i["is_internal"]),
            "resolved_to_file": sum(1 for i in rows["imports"] if i["imported_file_id"]),
        },
        "test_links": {
            "total": len(rows["test_links"]),
            "by_reason": {
                r: sum(1 for t in rows["test_links"] if t["reason"] == r) for r in ("imports_target", "name_match")
            },
        },
    }
