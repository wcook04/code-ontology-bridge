"""Build a portable website dataset from existing exports, without model calls."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import duckdb

from ..codemap.builder import CodeMap, summarise
from ..codemap.schema import TABLES
from ..export.csvio import csv_name
from ..export.duckdb_export import copy_sql, ddl_statements

BUNDLE_SCHEMA = "cob_inspection_bundle_v1"
MAX_BUNDLE_BYTES = 64 * 1024 * 1024


def encode(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode()


def validate_tables(rows, snapshot):
    """Reject invalid identities and joins before constructing the graph indexes."""
    if not isinstance(rows, dict) or set(rows) != {t.name for t in TABLES}:
        raise ValueError("inspection input must contain the eight source tables")
    keys = {}
    for table in TABLES:
        if not isinstance(rows[table.name], list):
            raise ValueError("table rows must be a list")
        keys[table.name] = set()
        for row in rows[table.name]:
            if not isinstance(row, dict) or set(row) != set(table.column_names):
                raise ValueError(f"invalid columns in {table.name}")
            for col in table.columns:
                value = row[col.name]
                if value is None and col.nullable:
                    continue
                expected = {"TEXT": str, "INTEGER": int, "BOOLEAN": bool}[col.sql_type]
                if type(value) is not expected or (col.allowed and value not in col.allowed):
                    raise ValueError(f"invalid value in {table.name}.{col.name}")
            key = tuple(row[k] for k in table.primary_key)
            if key in keys[table.name]:
                raise ValueError(f"duplicate identity in {table.name}")
            keys[table.name].add(key)
    for table in TABLES:
        for row in rows[table.name]:
            for fk in table.foreign_keys:
                key = tuple(row[k] for k in fk.columns)
                if None not in key and key not in keys[fk.ref_table]:
                    raise ValueError(f"broken reference in {table.name}")
    if rows["snapshot"] != [snapshot] or snapshot["file_count"] != len(rows["files"]):
        raise ValueError("source snapshot and file rows differ")


def load_dataset(folder: Path) -> CodeMap:
    """Read our CSV format through the same schema and COPY rules as export."""
    with duckdb.connect() as con:
        for statement in ddl_statements():
            con.execute(statement)
        rows = {}
        for table in TABLES:
            con.execute(copy_sql(table.qualified, folder / "data" / csv_name(table)))
            values = con.execute(f"SELECT * FROM {table.qualified} ORDER BY {', '.join(table.primary_key)}").fetchall()
            rows[table.name] = [dict(zip(table.column_names, row)) for row in values]
    if len(rows["snapshot"]) != 1:
        raise ValueError("expected exactly one source snapshot")
    return CodeMap(rows=rows, snapshot=rows["snapshot"][0], omitted_files=[])


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_evidence(folder: Path, source_commit: str | None) -> dict:
    """Select public final answers, never service logs or intermediate thoughts."""
    hashes = _read_json(folder / "artifacts.json")["files"]

    def checked(name):
        data = (folder / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != hashes.get(name):
            raise ValueError(f"saved artifact hash mismatch: {name}")
        return json.loads(data)

    manifest = checked("manifest.json")
    if not source_commit or manifest["upstream_commit"] != source_commit:
        raise ValueError("saved run and source snapshot revisions differ")
    score = checked("score.json")
    review = checked("review.json")
    evaluation = checked("inputs/evaluation.json")
    questions = {q["question_id"]: q for q in evaluation}
    scores = {q["question_id"]: q for q in score["results"]}
    findings = {q["question_id"]: q for q in review["findings"]}
    result = []
    for qid in manifest["question_ids"]:
        if type(qid) is not int or qid not in questions or qid not in scores:
            raise ValueError("incomplete saved question set")
        artifact = f"responses/10i_ask_with_key/ask_q{qid}.json"
        response = checked(artifact)
        final = [e["answer"] for e in response["events"] if e.get("type") == "result"]
        if len(final) != 1:
            raise ValueError("expected one retained final answer per question")
        answer = final[0]
        result.append({
            "question_id": qid, "question": questions[qid]["question"],
            "request": {k: response["request"].get(k) for k in ("question", "evidence", "calculation_only")},
            "sql": answer.get("sql_code"), "answer": answer.get("response"),
            "result_tables": [json.loads(t) for t in answer.get("sql_response_from_db", [])],
            "reference_sql": questions[qid]["SQL"], "reference_rows": questions[qid].get("answer_raw"),
            "score": scores[qid], "review_finding": findings.get(qid),
            "artifact": artifact, "sha256": hashes[artifact],
        })
    return {
        "status": "recorded_run", "fresh_execution": False,
        "scope": "Author-written development questions; no held-out set or schema-only control.",
        "manifest": {k: manifest[k] for k in (
            "started_at", "bridge_commit", "upstream_commit", "chat_model",
            "embedding_model", "reranking_model", "protocol", "calculation_only",
            "attempts_per_question", "custom_analyses_imported", "input_sha256")},
        "score": score, "review": review, "questions": result,
        "binding": "Selected saved artifacts verified against artifacts.json; not an independent attestation.",
    }


def build_bundle(code_map: CodeMap, evidence: Path | None = None) -> dict:
    validate_tables(code_map.rows, code_map.snapshot)
    rows = {t.name: sorted(code_map.rows[t.name], key=lambda r: tuple(r[k] for k in t.primary_key)) for t in TABLES}
    payload = {
        "schema_version": BUNDLE_SCHEMA, "snapshot": code_map.snapshot,
        "summary": summarise(code_map), "tables": rows,
        "schema": json.loads(encode([asdict(t) for t in TABLES])),
        "evidence": load_evidence(evidence, code_map.snapshot.get("commit_sha")) if evidence else {
            "status": "not_supplied", "fresh_execution": False, "questions": []},
    }
    payload["revision"] = hashlib.sha256(encode(payload)).hexdigest()
    if len(encode(payload)) > MAX_BUNDLE_BYTES:
        raise ValueError("inspection bundle exceeds 64 MiB")
    return payload


def load_bundle(path: Path) -> dict:
    with path.open("rb") as stream:
        data = stream.read(MAX_BUNDLE_BYTES + 1)
    if len(data) > MAX_BUNDLE_BYTES:
        raise ValueError("inspection bundle exceeds 64 MiB")
    bundle = json.loads(data)
    revision = bundle.pop("revision")
    if bundle.get("schema_version") != BUNDLE_SCHEMA or hashlib.sha256(encode(bundle)).hexdigest() != revision:
        raise ValueError("unsupported or modified inspection bundle")
    bundle["revision"] = revision
    validate_tables(bundle["tables"], bundle["snapshot"])
    if bundle["schema"] != json.loads(encode([asdict(t) for t in TABLES])):
        raise ValueError("inspection schema differs from the installed extractor")
    return bundle
