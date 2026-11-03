from __future__ import annotations

import argparse
import json

from code_ontology_bridge.governance import cli

DESC = "Load files and compute their fingerprints."


def run(argv):
    parser = argparse.ArgumentParser(prog="cob")
    cli.register(parser.add_subparsers(dest="command", required=True))
    args = parser.parse_args(argv)
    return args.func(args)


def test_register_adds_the_four_subcommands():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    cli.register(sub)
    assert {"certify", "cert-status", "enrich-answer", "reconcile"} <= set(sub.choices)


def test_certify_status_plan_round_trip(tmp_path, src_root, monkeypatch):
    targets = tmp_path / "targets.json"
    targets.write_text(
        json.dumps(
            [
                {
                    "target_kind": "term",
                    "target_imported_id": "term_file",
                    "field": "description",
                    "check_id": "docstring_matches_description",
                    "params": {"path": "pkg/files.py", "description": DESC},
                }
            ]
        )
    )
    log = tmp_path / "events.jsonl"
    assert run(["certify", "--log", str(log), "--targets", str(targets), "--root", str(src_root), "--commit-sha", "abc"]) == 2  # no actor
    assert run(["certify", "--log", str(log), "--targets", str(targets), "--root", str(src_root), "--actor", "will", "--commit-sha", "abc"]) == 0

    id_map = tmp_path / "ids.json"
    id_map.write_text(json.dumps({"term_file": "live-1"}))
    out = tmp_path / "status.json"
    assert run(["cert-status", "--log", str(log), "--root", str(src_root), "--plan-patches", "--id-map", str(id_map), "--out", str(out)]) == 0
    status = json.loads(out.read_text())
    assert status["counts"]["certified"] == 1 and status["mode"] == "dry_run"
    assert status["patch_plan"]["requests"][0]["path"] == "/api/terms/live-1"
    assert status["patch_plan"]["requests"][0]["json"] == {"description_certified": True}

    monkeypatch.delenv("AUTO_ONTOLOGY_API_TOKEN", raising=False)
    assert run(["cert-status", "--log", str(log), "--apply", "--base-url", "http://127.0.0.1:9", "--id-map", str(id_map)]) == 2

    event_id = json.loads(log.read_text().splitlines()[0])["event_id"]
    assert run(["certify", "--log", str(log), "--revoke", event_id, "--actor", "will", "--root", str(src_root)]) == 2  # no reason
    assert run(["certify", "--log", str(log), "--revoke", event_id, "--reason", "withdrawn", "--actor", "will", "--root", str(src_root)]) == 0
    assert run(["cert-status", "--log", str(log), "--root", str(src_root), "--out", str(out)]) == 0
    assert json.loads(out.read_text())["counts"]["revoked"] == 1


def test_reconcile_and_enrich_commands(tmp_path, model_yaml):
    defs = tmp_path / "defs.json"
    defs.write_text(json.dumps([{"source": "a", "name": "x", "aliases": [], "definition": "1"}, {"source": "b", "name": "x", "aliases": [], "definition": "2"}]))
    out = tmp_path / "r.json"
    assert run(["reconcile", "--definitions", str(defs), "--out", str(out)]) == 0
    assert run(["reconcile", "--definitions", str(defs), "--fail-on-ambiguous", "--out", str(out)]) == 3
    assert json.loads(out.read_text())["ambiguous"][0]["name"] == "x"

    answer = tmp_path / "a.json"
    answer.write_text(json.dumps({"answer": "a", "sql": "select s.name from code.symbols s", "rows": [], "row_count": 0, "truncated": False, "reasoning": ""}))
    eout = tmp_path / "e.json"
    assert run(["enrich-answer", "--answer", str(answer), "--model", str(model_yaml), "--out", str(eout)]) == 0
    enriched = json.loads(eout.read_text())
    assert enriched["term_ids"] == ["term_symbol"] and enriched["provenance_verdict"] == "uncertified"
