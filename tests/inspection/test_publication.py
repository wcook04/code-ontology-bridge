"""Publication proof: real payload contracts, graph boundaries and evidence isolation."""
import copy
import hashlib
import json
from pathlib import Path
import shutil

import jsonschema
import pytest

from code_ontology_bridge.codemap.builder import build_code_map
from code_ontology_bridge.inspection.api import Inspector
from code_ontology_bridge.inspection.bundle import build_bundle, dataset_digest, encode, load_bundle, load_dataset, load_evidence
from code_ontology_bridge.inspection.contract import openapi_document
from code_ontology_bridge.inspection.http import Application
from code_ontology_bridge.inspection.publication import publish, source_span
from test_inspection import request

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples/auto-ontology"
EVIDENCE = EXAMPLE / "live/current"
CASE = EXAMPLE / "live/caller-chain-case.json"


@pytest.fixture(scope="module")
def bundle():
    return build_bundle(load_dataset(EXAMPLE / "auto_ontology_code"), EVIDENCE, case=CASE)


def validate_payload(contract, path, payload, status="200"):
    schema = dict(contract["paths"][path]["get"]["responses"][status]["content"]["application/json"]["schema"],
                  components=contract["components"])
    jsonschema.Draft202012Validator(schema).validate(payload)


def test_real_http_payloads_validate_and_negative_contract(bundle):
    contract = openapi_document()
    jsonschema.Draft202012Validator.check_schema({"components": contract["components"]})
    app = Application(bundle)
    for path in contract["paths"]:
        actual = path.replace("{id}", "11").replace("{case_id}", "caller-chain-q11").replace("{step_id}", "source")
        query = "symbol_id=" + bundle["cases"][0]["root_symbol_id"] if path.endswith("/graph") else ""
        response = request(app, actual, query)
        assert response["status"] == 200, actual
        validate_payload(contract, path, json.loads(response["body"]))
    for question in bundle["evidence"]["questions"]:
        payload = app.inspector.response(f"/api/v1/questions/{question['question_id']}", {})
        validate_payload(contract, "/api/v1/questions/{id}", payload)
    wrong = app.inspector.response("/api/v1/questions/11", {})
    wrong["data"]["assessment"]["prose_review"] = "passed_by_absence"
    with pytest.raises(jsonschema.ValidationError):
        validate_payload(contract, "/api/v1/questions/{id}", wrong)
    failure = request(app, "/api/v1/graph", "depth=999")
    validate_payload(contract, "/api/v1/graph", json.loads(failure["body"]), str(failure["status"]))


def test_frozen_model_readback_and_request_preserved(bundle):
    models = bundle["models"]
    assert models["exported_input"]["text"].encode() == (EVIDENCE / "inputs/model.yaml").read_bytes()
    assert len(models["exported_input"]["document"]["semantic_layer"]["terms"]) == 8
    assert models["compiled_terms"]["role"] == "partial_terms_readback"
    assert models["submitted_import"]["status"] == models["retrieved_context"]["status"] == "not_captured"
    for q in bundle["evidence"]["questions"]:
        original = json.loads((EVIDENCE / q["artifact"]).read_text())
        assert q["request"] == original["request"]
        final = next(e["answer"] for e in original["events"] if e.get("type") == "result")
        assert q["result_tables"] == [json.loads(t) for t in final["sql_response_from_db"]]
        assert "thoughts" not in encode(q).decode()
    assert bundle["evidence"]["binding"]["dataset_match"] == "verified"
    assert all(q["assessment"]["table_match"] == "pass" for q in bundle["evidence"]["questions"])


def test_q11_presets_links_and_occurrence_location(bundle):
    case = bundle["cases"][0]
    full, direct = case["graphs"]["all_relationships"], case["graphs"]["direct_only"]
    full_ids, direct_ids = ({n["symbol_id"] for n in g["nodes"]} for g in (full, direct))
    assert full_ids - direct_ids == {"auto_ontology/ingestion_service/semantic_scheduler.py::SemanticScheduler._run_once"}
    assert len(full_ids) == 5 and len(direct_ids) == 4
    callback = next(e for e in full["edges"] if e["call_kind"] == "callback")
    assert callback["source_url"].endswith("semantic_scheduler.py#L203")
    occurrence = next(s for s in bundle["source_spans"] if s["record_id"] == callback["call_id"])
    assert occurrence["line_start"] == occurrence["line_end"] == 203
    assert len(bundle["evidence"]["questions"][10]["display_annotations"]["links"]) == 4


def test_graph_cycles_duplicates_caps_and_tests(tmp_path):
    (tmp_path / "source.py").write_text("def a():\n    b()\n    b()\ndef b():\n    a()\n")
    api = Inspector(build_bundle(build_code_map(tmp_path)))
    params = {"symbol_id": "source.py::a", "direction": "callees", "depth": "1"}
    graph = api.graph(params)
    assert len(graph["edges"]) == 3
    assert graph["counts"]["unique_pairs"] == 2
    assert not graph["truncated"] and not graph["depth_limited"]
    limited = api.graph(dict(params, max_edges="1"))
    assert len(limited["nodes"]) == 2 and limited["omission_reasons"] == ["edge_limit"]
    assert limited["counts"]["eligible_call_occurrences"] == 3
    assert api.graph(dict(params, max_nodes="1"))["omission_reasons"] == ["node_limit"]
    # a -> test_bridge -> c: excluding tests removes the traversal path, not just its display.
    (tmp_path / "source.py").write_text("from test_bridge import middle\ndef a():\n    middle()\ndef c():\n    pass\n")
    (tmp_path / "test_bridge.py").write_text("from source import c\ndef middle():\n    c()\n")
    api = Inspector(build_bundle(build_code_map(tmp_path)))
    params["depth"] = "3"
    assert len(api.graph(params)["nodes"]) == 3
    assert len(api.graph(dict(params, include_tests="false"))["nodes"]) == 1


def test_null_target_is_not_resolution_enum(bundle):
    api = Inspector(bundle)
    nulls = api.table("calls", {"target": "null", "limit": "100"})
    assert all(r["callee_symbol_id"] is None for r in nulls["items"])
    assert nulls["total"] > api.table("calls", {"resolution": "unresolved"})["total"]
    assert nulls["total"] + api.table("calls", {"target": "resolved"})["total"] == len(api.tables["calls"])


def alter_artifact(folder, name, value):
    (folder / name).write_bytes(encode(value))
    hashes = json.loads((folder / "artifacts.json").read_text())
    hashes["files"][name] = hashlib.sha256((folder / name).read_bytes()).hexdigest()
    (folder / "artifacts.json").write_bytes(encode(hashes))


def test_missing_review_unknown_and_new_digest_binding(tmp_path, bundle):
    evidence = tmp_path / "run"
    shutil.copytree(EVIDENCE, evidence)
    hashes = json.loads((evidence / "artifacts.json").read_text())
    hashes["files"].pop("review.json", None)
    (evidence / "artifacts.json").write_bytes(encode(hashes))
    (evidence / "review.json").unlink(missing_ok=True)
    loaded = load_evidence(evidence, bundle["snapshot"]["commit_sha"], bundle["dataset"]["sha256"])
    assert all(q["assessment"]["prose_review"] == "unknown" for q in loaded["questions"])
    manifest = json.loads((evidence / "manifest.json").read_text())
    manifest["dataset_sha256"] = bundle["dataset"]["sha256"]
    manifest["dataset_digest_algorithm"] = "cob_typed_tables_v1"
    alter_artifact(evidence, "manifest.json", manifest)
    with pytest.raises(ValueError, match="digests differ"):
        load_evidence(evidence, bundle["snapshot"]["commit_sha"], "wrong")
    assert load_evidence(evidence, bundle["snapshot"]["commit_sha"], bundle["dataset"]["sha256"])["binding"]["dataset_match"] == "verified"


def test_verified_excerpts_and_stale_source_rejected(tmp_path):
    source = 'def example():\n    """<script>alert(1)</script>"""\n    return 1\n'
    (tmp_path / "example.py").write_text(source)
    api = Inspector(build_bundle(build_code_map(tmp_path), model_database="example"))
    span = source_span(api, "symbol", "example.py::example", tmp_path)
    assert span["excerpt_status"] == "verified_file_hash" and "<script>" in span["excerpt"]
    response = request(Application(api.bundle), "/api/v1/tables/symbols")
    assert response["headers"]["Content-Type"] == "application/json; charset=utf-8"
    assert response["headers"]["X-Content-Type-Options"] == "nosniff"
    assert "<script>" in json.loads(response["body"])["data"]["items"][0]["summary"]
    (tmp_path / "example.py").write_text(source + "# changed\n")
    with pytest.raises(ValueError, match="hash differs"):
        source_span(api, "symbol", "example.py::example", tmp_path)


@pytest.mark.parametrize("change", ["term", "column", "artifact", "span", "model"])
def test_resigned_dangling_resources_rejected(tmp_path, bundle, change):
    broken = copy.deepcopy(bundle)
    if change in ("term", "column"):
        broken["cases"][0]["semantic_term_ids" if change == "term" else "column_ids"] = ["missing"]
    elif change == "artifact":
        broken["cases"][0]["recorded_response_ref"]["sha256"] = "missing"
    elif change == "span":
        broken["source_spans"][0]["path"] = "missing.py"
    else:
        broken["models"]["exported_input"]["document"]["semantic_layer"]["terms"][0]["represents"] = ["missing"]
    broken.pop("revision")
    broken["revision"] = hashlib.sha256(encode(broken)).hexdigest()
    path = tmp_path / "bundle.json"
    path.write_bytes(encode(broken))
    with pytest.raises(ValueError):
        load_bundle(path)


def test_static_publication_complete_small_entry_and_no_capture_leak(tmp_path, bundle):
    manifest = publish(bundle, tmp_path / "publication")
    assert manifest["question_count"] == 22
    assert manifest["entry_cases"] == ["cases/caller-chain-q11.json"]
    assert (tmp_path / "publication/manifest.json").stat().st_size < 20000
    assert manifest["resources"]["cases/caller-chain-q11.json"]["bytes"] < 60000
    for name, metadata in manifest["resources"].items():
        data = (tmp_path / "publication" / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == metadata["sha256"]
        assert len(data) == metadata["bytes"]
    bad = copy.deepcopy(bundle)
    bad["evidence"]["questions"][0]["thoughts"] = "private intermediate capture"
    with pytest.raises(ValueError, match="forbidden"):
        publish(bad, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()
    with pytest.raises(ValueError, match="must not exist"):
        publish(bundle, tmp_path / "publication")


def test_dataset_digest_is_typed_and_order_independent(bundle):
    rows = copy.deepcopy(bundle["tables"])
    rows["calls"].reverse()
    assert dataset_digest(rows) == bundle["dataset"]["sha256"]
    rows["calls"][0]["line"] = str(rows["calls"][0]["line"])
    assert dataset_digest(rows) != bundle["dataset"]["sha256"]


def test_database_digest_matches_export_and_rejects_invalid_rows(tmp_path):
    from code_ontology_bridge.export.duckdb_export import export_duckdb
    from code_ontology_bridge.inspection.bundle import database_digest
    (tmp_path / "example.py").write_text("def example():\n    pass\n")
    source = build_code_map(tmp_path)
    path = tmp_path / "source.duckdb"
    export_duckdb(source, path)
    assert database_digest(path) == dataset_digest(source.rows)


@pytest.mark.parametrize("value", ["../../outside", "a/b", "/tmp/outside"])
def test_publication_rejects_unsafe_case_identifiers(tmp_path, bundle, value):
    altered = copy.deepcopy(bundle)
    altered["cases"][0]["id"] = value
    with pytest.raises(ValueError, match="case identities"):
        publish(altered, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_publication_rejects_credentials_and_logs(tmp_path, bundle):
    for key, value in [("logs", []), ("answer", "Bearer " + "a" * 30)]:
        altered = copy.deepcopy(bundle)
        altered["evidence"]["questions"][0][key] = value
        with pytest.raises(ValueError, match="forbidden|credential"):
            publish(altered, tmp_path / "output")


def test_generated_model_and_no_evidence_contract(tmp_path):
    (tmp_path / "example.py").write_text("def example():\n    pass\n")
    api = Inspector(build_bundle(build_code_map(tmp_path), model_database="local"))
    for path in ("/api/v1/overview", "/api/v1/models", "/api/v1/questions"):
        validate_payload(openapi_document(), path, api.response(path, {}))
    assert api.bundle["models"]["generated_export"]["status"] == "computed_locally"
    assert api.bundle["models"]["exported_input"]["status"] == "not_supplied"
