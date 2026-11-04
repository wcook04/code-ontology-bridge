"""Exercise the real saved example and the read-only website contract."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import threading
from urllib.parse import urlencode
from urllib.request import urlopen
from wsgiref.simple_server import make_server

import pytest

from code_ontology_bridge.cli import main
from code_ontology_bridge.inspection.api import APIError, Inspector
from code_ontology_bridge.inspection.bundle import build_bundle, encode, load_bundle, load_dataset, load_evidence
from code_ontology_bridge.inspection.http import Application

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples/auto-ontology"


@pytest.fixture(scope="module")
def bundle():
    return build_bundle(load_dataset(EXAMPLE / "auto_ontology_code"), EXAMPLE / "live/current")


@pytest.fixture(scope="module")
def api(bundle):
    return Inspector(bundle)


def request(app, path="/api/v1", query="", method="GET", **extra):
    result = {}
    def start(status, headers):
        result.update(status=int(status.split()[0]), headers=dict(headers))
    result["body"] = b"".join(app({"PATH_INFO": path, "QUERY_STRING": query,
                                  "REQUEST_METHOD": method, **extra}, start))
    return result


def test_retained_example_joins_and_review(api):
    overview = api.query("/api/v1/overview", {})
    assert overview["summary"]["row_counts"]["files"] == 473
    assert overview["summary"]["row_counts"]["symbols"] == 5319
    assert overview["evidence"]["review"]["rows_and_substantive_prose"] == 20
    q11 = api.query("/api/v1/questions/11", {})
    assert "backwards" in q11["request"]["evidence"]
    assert "Requested output columns" in q11["request"]["question"]
    assert len(q11["result_tables"][0]) == 4
    assert "thoughts" not in q11 and "events" not in q11
    assert api.query("/api/v1/questions/14", {})["review_finding"]["prose"] == "fail"


def test_graph_matches_saved_q11_and_keeps_callback(api):
    root = api.table("symbols", {"name": "resolve_semantic_fks"})["items"][0]["symbol_id"]
    graph = api.graph({"symbol_id": root, "depth": "5", "include_tests": "false"})
    actual = [{"symbol_id": n["symbol_id"], "depth": n["depth"]} for n in graph["nodes"] if n["depth"]]
    assert actual == api.questions["11"]["result_tables"][0]
    assert [e["call_kind"] for e in graph["edges"]].count("callback") == 1
    assert not graph["truncated"] and not graph["depth_limited"]
    bounded = api.graph({"symbol_id": root, "depth": "5", "max_nodes": "2"})
    assert len(bounded["nodes"]) == 2 and bounded["truncated"]
    assert api.graph({"symbol_id": root})["depth_limited"]


def test_search_pagination_filters_and_source_links(api):
    page = api.table("symbols", {"q": "resolve_semantic_fks", "limit": "1"})
    assert page["items"][0]["source_url"].startswith("https://github.com/NVIDIA/auto-ontology/blob/cdaf61e")
    first = api.table("symbols", {"kind": "method", "limit": "2"})
    second = api.table("symbols", {"kind": "method", "limit": "2", "offset": str(first["next_offset"])})
    assert first["total"] == 676
    assert {r["symbol_id"] for r in first["items"]}.isdisjoint(r["symbol_id"] for r in second["items"])
    assert api.table("files", {"is_test": "false"})["total"] == 305
    assert api.table("files", {"q": "'; DROP TABLE files; --"})["items"] == []
    assert api.table("files", {"offset": "999999999"})["next_offset"] is None


@pytest.mark.parametrize("path,params,status", [
    ("/api/v1/tables/symbols", {"limit": "101"}, 400),
    ("/api/v1/tables/symbols", {"offset": "-1"}, 400),
    ("/api/v1/tables/files", {"is_test": "yes"}, 400),
    ("/api/v1/tables/files", {"q": " "}, 400),
    ("/api/v1/overview", {"root": "/etc"}, 400),
    ("/api/v1/tables/missing", {}, 404),
    ("/api/v1/questions/999", {}, 404),
    ("/api/v1/../../etc/passwd", {}, 404),
])
def test_invalid_requests(api, path, params, status):
    with pytest.raises(APIError) as error:
        api.query(path, params)
    assert error.value.status == status


def test_http_head_etag_errors_and_no_mutation(bundle):
    app = Application(bundle)
    get = request(app)
    assert get["status"] == 200
    head = request(app, method="HEAD")
    assert head["body"] == b"" and head["headers"] == get["headers"]
    cached = request(app, HTTP_IF_NONE_MATCH="W/" + get["headers"]["ETag"])
    assert cached["status"] == 304 and not cached["body"]
    assert request(app, method="POST")["status"] == 405
    assert request(app, query="q=1&q=2")["status"] == 400
    for query in ("q=%ZZ", "q=%FF", "x=" + "a" * 4096):
        assert request(app, query=query)["status"] == 400
    assert "Access-Control-Allow-Origin" not in get["headers"]
    bundle_copy = copy.deepcopy(bundle)
    isolated = Application(bundle_copy)
    bundle_copy["snapshot"]["repo_url"] = "changed"
    assert request(isolated)["body"] == get["body"]


def test_real_http_roundtrip(bundle):
    with make_server("127.0.0.1", 0, Application(bundle)) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            query = urlencode({"name": "resolve_semantic_fks"})
            with urlopen(f"http://127.0.0.1:{server.server_port}/api/v1/tables/symbols?{query}", timeout=5) as response:
                assert json.load(response)["data"]["total"] == 1
        finally:
            server.shutdown()
            worker.join(timeout=5)


def test_openapi_uses_table_owner_and_real_routes(bundle):
    app = Application(bundle)
    response = request(app, "/api/v1/openapi.json")
    contract = json.loads(response["body"])
    assert contract["openapi"] == "3.1.0"
    assert "/api/v1/tables/calls" in contract["paths"]
    assert contract["paths"]["/api/v1/graph"]["get"]["parameters"][0]["required"]
    for path in contract["paths"]:
        path = path.replace("{id}", "11")
        query = ""
        if path.endswith("/graph"):
            query = urlencode({"symbol_id": next(iter(app.inspector.symbols))})
        assert request(app, path, query)["status"] == 200


def test_digest_roundtrip_and_modified_bundle(tmp_path, bundle):
    path = tmp_path / "bundle.json"
    path.write_bytes(encode(bundle))
    assert load_bundle(path) == bundle
    modified = copy.deepcopy(bundle)
    modified["snapshot"]["repo_url"] = "changed"
    path.write_bytes(encode(modified))
    with pytest.raises(ValueError, match="modified"):
        load_bundle(path)


def test_valid_hash_does_not_admit_broken_foreign_keys(tmp_path, bundle):
    modified = copy.deepcopy(bundle)
    del modified["revision"]
    modified["tables"]["calls"][0]["caller_symbol_id"] = "absent"
    modified["revision"] = hashlib.sha256(encode(modified)).hexdigest()
    path = tmp_path / "broken.json"
    path.write_bytes(encode(modified))
    with pytest.raises(ValueError, match="broken reference"):
        load_bundle(path)


def test_evidence_revision_and_tamper(tmp_path, bundle):
    with pytest.raises(ValueError, match="revisions differ"):
        load_evidence(EXAMPLE / "live/current", "wrong")
    folder = tmp_path / "evidence"
    folder.mkdir()
    for name in ("manifest.json", "artifacts.json"):
        shutil.copy(EXAMPLE / "live/current" / name, folder / name)
    with (folder / "manifest.json").open("a") as stream:
        stream.write(" ")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_evidence(folder, bundle["snapshot"]["commit_sha"])


def test_local_cli_no_evidence_cycles_and_determinism(tmp_path):
    src = tmp_path / "source"
    src.mkdir()
    (src / "example.py").write_text('def first():\n    second()\ndef second():\n    first()\n')
    codemap = tmp_path / "map.json"
    out = tmp_path / "bundle.json"
    assert main(["build", str(src), "--out", str(codemap)]) == 0
    assert main(["inspect-export", "--codemap", str(codemap), "--out", str(out)]) == 0
    before = out.read_bytes()
    main(["inspect-export", "--codemap", str(codemap), "--out", str(out)])
    assert out.read_bytes() == before
    api = Inspector(load_bundle(out))
    assert api.bundle["evidence"]["status"] == "not_supplied"
    root = next(iter(api.symbols))
    graph = api.graph({"symbol_id": root, "direction": "callees", "depth": "5"})
    assert len(graph["nodes"]) == 2 and len(graph["edges"]) == 2
    assert not graph["truncated"] and not graph["depth_limited"]
    assert all(n["source_url"] is None for n in graph["nodes"])
