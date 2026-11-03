"""``cob`` subcommands for the governance layer.

``register(subparsers)`` adds ``certify``, ``cert-status``, ``enrich-answer``
and ``reconcile`` to the main ``cob`` parser. Each handler is stored as the
``func`` default and takes the parsed namespace; it returns a process exit code.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import certification as cert
from . import evidence, reconcile


def _emit(payload: Any, out: str | None) -> None:
    text = json.dumps(payload, indent=2, sort_keys=False, default=str) + "\n"
    if out:
        Path(out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def _load_checks(modules: list[str] | None) -> None:
    for name in modules or []:
        cert.load_check_module(name)


def cmd_certify(args: argparse.Namespace) -> int:
    _load_checks(args.checks_module)
    log = cert.EventLog(Path(args.log))
    root = Path(args.root)
    if args.list_checks:
        _emit({cid: cert.describe_check(cid) for cid in cert.check_ids()}, None)
        return 0
    if args.revoke:
        if not args.reason:
            print("--revoke needs --reason", file=sys.stderr)
            return 2
        event = cert.revoke(log, args.revoke, actor=args.actor, reason=args.reason, commit_sha=args.commit_sha)
        _emit({"appended": [event]}, args.out)
        return 0
    if not args.targets:
        print("certify needs --targets (or --revoke / --list-checks)", file=sys.stderr)
        return 2
    events = [
        cert.certify(log, target, root=root, actor=args.actor, commit_sha=args.commit_sha)
        for target in cert.load_targets(Path(args.targets))
    ]
    _emit(
        {
            "appended": events,
            "passed": sum(e["check_result"] == "passed" for e in events),
            "failed": sum(e["check_result"] != "passed" for e in events),
        },
        args.out,
    )
    return 0 if all(e["check_result"] == "passed" for e in events) else 1


def cmd_cert_status(args: argparse.Namespace) -> int:
    events = cert.EventLog(Path(args.log)).read()
    rows = cert.status(events, Path(args.root) if args.root else None)
    counts: dict[str, int] = {s: 0 for s in cert.STATES}
    for row in rows:
        counts[row["state"]] += 1
    payload: dict[str, Any] = {"log": args.log, "counts": counts, "targets": rows}
    if args.plan_patches or args.apply:
        id_map = json.loads(Path(args.id_map).read_text(encoding="utf-8")) if args.id_map else {}
        plan = cert.plan_patches(rows, id_map, unset_stale=args.unset_stale)
        payload["patch_plan"] = plan
        payload["mode"] = "dry_run"
        if args.apply:
            if not args.base_url:
                print("--apply needs --base-url", file=sys.stderr)
                return 2
            try:
                payload["applied"] = cert.apply_patches(plan, args.base_url)
            except RuntimeError as exc:
                print(str(exc), file=sys.stderr)
                return 2
            payload["mode"] = "applied"
    _emit(payload, args.out)
    return 0


def cmd_enrich_answer(args: argparse.Namespace) -> int:
    raw = json.loads(Path(args.answer).read_text(encoding="utf-8")) if args.answer != "-" else json.load(sys.stdin)
    events = cert.EventLog(Path(args.log)).read() if args.log else []
    result = evidence.enrich_answer(
        raw,
        model_path=Path(args.model),
        events=events,
        root=Path(args.root) if args.root else None,
        snapshot_path=Path(args.snapshot) if args.snapshot else None,
    )
    _emit(result, args.out)
    return 0


def cmd_reconcile(args: argparse.Namespace) -> int:
    defs = reconcile.load_json(Path(args.definitions))
    if isinstance(defs, dict):
        defs = defs["definitions"]
    res = reconcile.load_json(Path(args.resolutions)) if args.resolutions else {}
    result = reconcile.reconcile(defs, res)
    _emit(result, args.out)
    return 0 if not result["ambiguous"] or not args.fail_on_ambiguous else 3


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("certify", help="run checks and append certification events (or --revoke one)")
    p.add_argument("--log", required=True, help="certification events JSONL (append-only)")
    p.add_argument("--targets", help="JSON list of {target_kind, target_imported_id, field, check_id, params, parent_term_imported_id?}")
    p.add_argument("--root", default=".", help="source root the checks read and fingerprint")
    p.add_argument("--actor", required=False, default=None, help="who is certifying (recorded on every event)")
    p.add_argument("--commit-sha", default=None, help="override the commit recorded (default: git rev-parse HEAD in --root)")
    p.add_argument("--revoke", metavar="EVENT_ID", help="append a revoke that rolls back this event")
    p.add_argument("--reason", help="why, for --revoke")
    p.add_argument("--checks-module", action="append", help="import a module that registers more checks")
    p.add_argument("--list-checks", action="store_true")
    p.add_argument("--out")
    p.set_defaults(func=_require_actor(cmd_certify))

    p = subparsers.add_parser("cert-status", help="recompute certification state; optionally plan or send PATCH requests")
    p.add_argument("--log", required=True)
    p.add_argument("--root", default=".", help="source root for freshness (pass '' to skip; passing targets are then reported stale/unchecked)")
    p.add_argument("--plan-patches", action="store_true", help="emit PATCH requests for Auto Ontology's existing routes")
    p.add_argument("--id-map", help="JSON {imported_id: live_id}; unmapped targets get a placeholder and are never sent")
    p.add_argument("--unset-stale", action="store_true", help="also plan certified=false for stale and failed targets")
    p.add_argument("--apply", action="store_true", help="send ready requests (token from AUTO_ONTOLOGY_API_TOKEN)")
    p.add_argument("--base-url", help="Auto Ontology server, e.g. http://localhost:3001")
    p.add_argument("--out")
    p.set_defaults(func=cmd_cert_status)

    p = subparsers.add_parser("enrich-answer", help="wrap an MCP DataAnswer with tables, columns, terms and certification state")
    p.add_argument("--answer", required=True, help="DataAnswer JSON file, or - for stdin")
    p.add_argument("--model", required=True, help="model import YAML (the one imported into Auto Ontology)")
    p.add_argument("--log", help="certification events JSONL")
    p.add_argument("--root", default=".", help="source root for freshness")
    p.add_argument("--snapshot", help="snapshot JSON, or the code.duckdb holding code.snapshot")
    p.add_argument("--out")
    p.set_defaults(func=cmd_enrich_answer)

    p = subparsers.add_parser("reconcile", help="resolve several definitions of a term in a fixed order")
    p.add_argument("--definitions", required=True, help="JSON list of {source, name, aliases, definition, canonical_id?}")
    p.add_argument("--resolutions", help="JSON {alias_or_name | source:name: {resolved_to, reason, decided_by, name?}}")
    p.add_argument("--fail-on-ambiguous", action="store_true", help="exit 3 when anything is ambiguous")
    p.add_argument("--out")
    p.set_defaults(func=cmd_reconcile)


def _require_actor(fn):
    def wrapped(args: argparse.Namespace) -> int:
        if not args.list_checks and not args.actor:
            print("certify needs --actor", file=sys.stderr)
            return 2
        return fn(args)

    return wrapped


def main(argv: list[str] | None = None) -> int:
    """Standalone entry for the governance commands (the package CLI ``cob``
    mounts the same subcommands through ``register``)."""
    parser = argparse.ArgumentParser(prog="cob-governance")
    register(parser.add_subparsers(dest="command", required=True))
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
