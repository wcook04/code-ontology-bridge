from __future__ import annotations

import json

import pytest

from code_ontology_bridge.governance import certification as cert
from code_ontology_bridge.governance import evidence as ev

DESC = "Load files and compute their fingerprints."


def test_tokenizer_skips_comments_and_strings():
    toks = ev.tokenize("select 'from x' -- from y\n /* join z */ from \"Code\".\"Files\"")
    words = [t.text for t in toks]
    assert "y" not in words and "z" not in words
    assert ("ident", "Code") in [(t.kind, t.text) for t in toks]
    refs = ev.extract_refs("select 'from x' -- from y\n from code.files")
    assert refs.tables == ["code.files"]


def test_aliases_joins_and_qualified_columns():
    sql = """
        SELECT f.file_id, s.name, count(*) AS n
        FROM code.files AS f
        LEFT JOIN code.symbols s ON s.file_id = f.file_id
        WHERE f.is_test = false
        GROUP BY 1, 2
    """
    refs = ev.extract_refs(sql)
    assert refs.tables == ["code.files", "code.symbols"]
    assert refs.aliases["f"] == "code.files" and refs.aliases["s"] == "code.symbols"
    assert set(refs.columns) == {
        ("code.files", "file_id"),
        ("code.symbols", "name"),
        ("code.symbols", "file_id"),
        ("code.files", "is_test"),
    }
    assert not any("not a known alias" in n for n in refs.notes)


def test_ctes_are_not_tables_and_comma_from_lists():
    sql = """
        with recursive pub as (select file_id from code.files where package = 'pkg'),
             syms(fid, nm) as (select file_id, name from code.symbols)
        select pub.file_id, syms.nm from pub, syms where pub.file_id = syms.fid
    """
    refs = ev.extract_refs(sql)
    assert refs.ctes == ["pub", "syms"]
    assert refs.tables == ["code.files", "code.symbols"]
    # CTE-qualified columns are not attributed to physical tables, and with
    # CTEs present unqualified columns are reported, not guessed.
    assert refs.columns == []
    assert "file_id" in refs.unattributed_columns and "package" in refs.unattributed_columns


def test_single_table_unqualified_columns_and_select_star_note():
    refs = ev.extract_refs("select package, count(*) as n from code.files group by package")
    assert ("code.files", "package") in refs.columns
    assert ("code.files", "n") not in refs.columns
    star = ev.extract_refs("select * from code.files")
    assert any("SELECT *" in n for n in star.notes)


def test_subquery_in_from_and_three_part_names():
    refs = ev.extract_refs("select x.c from (select file_id as c from main.code.files) x")
    assert refs.tables == ["code.files"]


def _answer(sql: str) -> dict:
    return {"answer": "There is 1 test file.", "sql": sql, "rows": [{"n": 1}], "row_count": 1, "truncated": False, "reasoning": "ran sql"}


def test_enrich_answer_verdicts(tmp_path, src_root, model_yaml, code_db):
    log = cert.EventLog(tmp_path / "events.jsonl")
    sql = "select f.package, count(*) as n from code.files f where f.is_test group by f.package"
    snap = src_root / "codemap.duckdb"

    out = ev.enrich_answer(_answer(sql), model_path=model_yaml, events=log.read(), root=src_root, snapshot_path=snap, now="T")
    assert out["provenance_verdict"] == "uncertified"
    assert out["term_ids"] == ["term_file"]
    assert {"table": "code.files", "column": "package", "in_model": True} in out["columns_used"]
    assert out["snapshot"]["status"] == "loaded" and out["snapshot"]["commit_sha"] == "abc123"
    assert out["data_answer"]["sql"] == sql and out["generated_at"] == "T"
    assert out["model"]["sha256"]

    target = {
        "target_kind": "term",
        "target_imported_id": "term_file",
        "field": "description",
        "check_id": "docstring_matches_description",
        "params": {"path": "pkg/files.py", "description": DESC},
    }
    cert.certify(log, target, root=src_root, actor="w", commit_sha="a")
    out = ev.enrich_answer(_answer(sql), model_path=model_yaml, events=log.read(), root=src_root)
    assert out["provenance_verdict"] == "partially_certified"  # column attribute still uncertified

    cert.certify(
        log,
        {**target, "target_kind": "column_attribute", "target_imported_id": "ca_file_package", "field": "certified", "parent_term_imported_id": "term_file"},
        root=src_root,
        actor="w",
        commit_sha="a",
    )
    out = ev.enrich_answer(_answer(sql), model_path=model_yaml, events=log.read(), root=src_root)
    assert out["provenance_verdict"] == "grounded_in_certified"
    term = out["certification_state"][0]
    assert term["certification"]["description"] == "certified"
    assert term["column_attributes"][0]["certification"] == "certified"

    (src_root / "pkg" / "files.py").write_text("'''changed'''\n")
    out = ev.enrich_answer(_answer(sql), model_path=model_yaml, events=log.read(), root=src_root)
    assert out["provenance_verdict"] == "stale"


def test_enrich_accepts_mcp_wrappers_and_json_snapshot(tmp_path, model_yaml):
    wrapped = {"content": [{"type": "text", "text": json.dumps(_answer("select name from code.symbols"))}]}
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps({"snapshot_id": "s", "commit_sha": "c"}))
    out = ev.enrich_answer(wrapped, model_path=model_yaml, events=[], root=None, snapshot_path=snap)
    assert out["term_ids"] == ["term_symbol"]
    assert out["snapshot"]["commit_sha"] == "c"
    assert ev.enrich_answer({"structuredContent": _answer("select 1")}, model_path=model_yaml, events=[], root=None)["provenance_verdict"] == "uncertified"
    with pytest.raises(ValueError):
        ev.unwrap_data_answer({"nothing": 1})


def test_verdict_function():
    assert ev.provenance_verdict([]) == "uncertified"
    assert ev.provenance_verdict(["certified", "certified"]) == "grounded_in_certified"
    assert ev.provenance_verdict(["certified", "never"]) == "partially_certified"
    assert ev.provenance_verdict(["certified", "stale"]) == "stale"
    assert ev.provenance_verdict(["revoked", "failed"]) == "uncertified"


def test_snapshot_reads_from_a_file_named_code_duckdb(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    path = tmp_path / "code.duckdb"  # catalog "code" == schema "code"
    con = duckdb.connect(str(path))
    con.execute("create schema code.code")
    con.execute("create table code.code.snapshot(snapshot_id text, commit_sha text)")
    con.execute("insert into code.code.snapshot values ('s1', 'abc')")
    con.close()
    snap = ev.load_snapshot(path)
    assert snap["status"] == "loaded" and snap["commit_sha"] == "abc"
