"""``cob``: build a code map and export it to Auto Ontology's existing entry points.

Subcommands
- ``build ROOT --out codemap.json``: analyse a Python checkout.
- ``export-duckdb --codemap codemap.json --out code.duckdb``: for ``CONNECTION_STRINGS=duckdb:///...``.
- ``export-dataset --codemap ... --duckdb ... --out datasets/<name>``: ontology-sql-eval folder.
- ``export-model --codemap ... --out model.yaml --database <name>``: ``POST /api/model/import``.
Governance subcommands are registered from ``code_ontology_bridge.governance.cli`` when present.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .codemap.builder import CodeMap, build_code_map, summarise


def save_code_map(code_map: CodeMap, path: str | Path) -> None:
    payload = {"snapshot": code_map.snapshot, "omitted_files": code_map.omitted_files, "rows": code_map.rows}
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def load_code_map(path: str | Path) -> CodeMap:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    code_map = CodeMap(rows=payload["rows"], snapshot=payload["snapshot"], omitted_files=payload["omitted_files"])
    code_map.stats = summarise(code_map)
    return code_map


def cmd_build(args: argparse.Namespace) -> int:
    code_map = build_code_map(args.root, repo_url=args.repo_url, commit_sha=args.commit_sha, exclude=args.exclude or [])
    save_code_map(code_map, args.out)
    if args.summary:
        Path(args.summary).write_text(json.dumps(code_map.stats, indent=2) + "\n", encoding="utf-8")
    counts = code_map.stats["row_counts"]
    print(f"{args.out}: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


def cmd_export_duckdb(args: argparse.Namespace) -> int:
    from .export.duckdb_export import export_duckdb

    out = export_duckdb(load_code_map(args.codemap), args.out)
    print(f"wrote {out}  (CONNECTION_STRINGS=duckdb://{out})")
    return 0


def cmd_export_dataset(args: argparse.Namespace) -> int:
    from .export.dataset_export import export_dataset, load_json

    out = export_dataset(
        load_code_map(args.codemap),
        args.out,
        duckdb_path=args.duckdb,
        questions=load_json(args.questions),
        analyses=load_json(args.analyses),
        heldout=load_json(args.heldout),
        db_id=args.db_id,
    )
    print(f"wrote {out}")
    return 0


def cmd_export_model(args: argparse.Namespace) -> int:
    from .export.dataset_export import load_json
    from .export.model_export import export_model_yaml

    export_model_yaml(
        load_code_map(args.codemap),
        args.out,
        database=args.database,
        dialect=args.dialect,
        analyses=load_json(args.analyses),
    )
    print(f"wrote {args.out}")
    return 0


def cmd_inspect_export(args: argparse.Namespace) -> int:
    from .inspection.bundle import build_bundle, encode, load_dataset

    code_map = load_code_map(args.codemap) if args.codemap else load_dataset(Path(args.dataset))
    bundle = build_bundle(code_map, Path(args.evidence) if args.evidence else None,
                          model_database=args.model_database, case=Path(args.case) if args.case else None,
                          source_root=Path(args.source_root) if args.source_root else None)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(encode(bundle) + b"\n")
    print(f"wrote {out} (revision {bundle['revision']})")
    return 0


def cmd_inspect_publish(args: argparse.Namespace) -> int:
    from .inspection.bundle import load_bundle
    from .inspection.publication import publish

    manifest = publish(load_bundle(Path(args.bundle)), Path(args.out))
    print(f"wrote {args.out} ({len(manifest['resources'])} resources; {manifest['question_count']} recorded questions)")
    return 0


def cmd_inspect_serve(args: argparse.Namespace) -> int:
    from .inspection.bundle import load_bundle
    from .inspection.http import serve

    serve(load_bundle(Path(args.bundle)), args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cob", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("build", help="analyse a Python checkout into a code map JSON")
    p.add_argument("root")
    p.add_argument("--out", required=True)
    p.add_argument("--summary", help="also write a JSON summary of counts")
    p.add_argument("--repo-url", help="default: git remote origin, else the root's file URI")
    p.add_argument("--commit-sha", help="default: git rev-parse HEAD in ROOT")
    p.add_argument("--exclude", action="append", help="fnmatch pattern on repo-relative paths (repeatable); excluded files are counted as omitted")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("export-duckdb", help="write the DuckDB file (schema code, keys, views)")
    p.add_argument("--codemap", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_export_duckdb)

    p = sub.add_parser("export-dataset", help="write an ontology-sql-eval dataset folder")
    p.add_argument("--codemap", required=True)
    p.add_argument("--duckdb", required=True, help="DuckDB file of the same code map, used to compute gold answers")
    p.add_argument("--out", required=True, help="datasets/<name> folder")
    p.add_argument("--questions", help="JSON list of {question_id, question, evidence, SQL, difficulty}")
    p.add_argument("--analyses", help="JSON list of {name, description, sql}")
    p.add_argument("--heldout", help="JSON list of held-out questions; their reference answers go to heldout_evaluation.json")
    p.add_argument("--db-id", help="db_id recorded on each question (default: folder name upper-cased)")
    p.set_defaults(func=cmd_export_dataset)

    p = sub.add_parser("export-model", help="write an Auto Ontology model-import YAML")
    p.add_argument("--codemap", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--database", required=True, help="catalog database name (a DuckDB file's stem)")
    p.add_argument("--dialect", default="duckdb", choices=["duckdb", "postgres"])
    p.add_argument("--analyses", help="JSON list of {name, description, sql} to include as custom analyses")
    p.set_defaults(func=cmd_export_model)

    p = sub.add_parser("inspect-export", help="build a portable JSON dataset for a future website")
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--codemap", help="JSON produced by cob build")
    source.add_argument("--dataset", help="dataset directory produced by cob export-dataset")
    p.add_argument("--evidence", help="explicit saved live-run directory; optional")
    p.add_argument("--model-database", help="also expose a newly generated native model, labeled separately")
    p.add_argument("--case", help="authored case descriptor JSON")
    p.add_argument("--source-root", help="build-time snapshot directory; only case-selected, hash-checked source is read")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_inspect_export)

    p = sub.add_parser("inspect-publish", help="write static JSON resources into a new publication directory")
    p.add_argument("--bundle", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_inspect_publish)

    p = sub.add_parser("inspect-serve", help="serve an inspection bundle as a read-only local JSON API")
    p.add_argument("--bundle", required=True)
    p.add_argument("--port", type=int, default=8767)
    p.set_defaults(func=cmd_inspect_serve)

    # --- governance subcommands (registered by code_ontology_bridge/governance/cli.py) ---
    try:
        from .governance import cli as governance_cli
    except ImportError:
        governance_cli = None
    if governance_cli is not None and hasattr(governance_cli, "register"):
        governance_cli.register(sub)
    # --- end governance subcommands ---

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
