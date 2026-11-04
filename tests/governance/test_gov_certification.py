from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from code_ontology_bridge.governance import certification as cert

DESC = "Load files and compute their fingerprints."


def term_target(description: str = DESC, field: str = "description", tid: str = "term_file") -> dict:
    return {
        "target_kind": "term",
        "target_imported_id": tid,
        "field": field,
        "check_id": "docstring_matches_description",
        "params": {"path": "pkg/files.py", "description": description},
    }


def only(rows, tid="term_file", field="description"):
    return next(r for r in rows if r["target_imported_id"] == tid and r["field"] == field)


def test_event_has_every_spec_key_and_log_is_append_only(tmp_path, src_root):
    log = cert.EventLog(tmp_path / "events.jsonl")
    e1 = cert.certify(log, term_target(), root=src_root, actor="will", commit_sha="abc")
    for key in cert.REQUIRED_EVENT_KEYS:
        assert key in e1
    assert e1["check_result"] == "passed" and e1["decision"] == "certify"
    assert e1["source_paths"] == ["pkg/files.py"]
    first = log.path.read_text()
    cert.certify(log, term_target(), root=src_root, actor="will", commit_sha="abc")
    assert log.path.read_text().startswith(first)  # earlier lines untouched
    assert len(log.read()) == 2


def test_log_rejects_events_missing_spec_keys(tmp_path):
    log = cert.EventLog(tmp_path / "e.jsonl")
    with pytest.raises(ValueError):
        log.append({"event_id": "x"})
    log.path.write_text(json.dumps({"event_id": "x"}) + "\n")
    with pytest.raises(ValueError):
        log.read()


def test_docstring_check_symbol_and_failures(src_root):
    ok = cert.CHECKS["docstring_matches_description"](
        src_root, {"path": "pkg/files.py", "qualname": "fingerprint", "description": "Return the SHA-256 of one file."}
    )
    assert ok.passed
    none = cert.CHECKS["docstring_matches_description"](
        src_root, {"path": "pkg/files.py", "qualname": "undocumented", "description": "x"}
    )
    assert not none.passed and "no docstring" in none.detail
    empty = cert.CHECKS["docstring_matches_description"](src_root, {"path": "pkg/files.py", "description": ""})
    assert not empty.passed
    wrong = cert.CHECKS["docstring_matches_description"](
        src_root, {"path": "pkg/files.py", "description": "Something an LLM wrote."}
    )
    assert not wrong.passed


def test_states_certified_stale_failed_revoked_never(tmp_path, src_root):
    log = cert.EventLog(tmp_path / "events.jsonl")
    e1 = cert.certify(log, term_target(), root=src_root, actor="will", commit_sha="abc")
    assert only(cert.status(log.read(), src_root))["state"] == "certified"

    # Without a root, freshness cannot be shown, so nothing is reported certified.
    assert only(cert.status(log.read(), None))["state"] == "stale"

    # Edit the file: the stored fingerprint no longer matches.
    f = src_root / "pkg" / "files.py"
    original = f.read_text()
    f.write_text(original + "\n# edited\n")
    row = only(cert.status(log.read(), src_root))
    assert row["state"] == "stale" and row["freshness"] == "changed"
    f.write_text(original)
    assert only(cert.status(log.read(), src_root))["state"] == "certified"

    # A failed attempt displaces the pass.
    e2 = cert.certify(log, term_target("A different description."), root=src_root, actor="will", commit_sha="abc")
    assert e2["check_result"] == "failed"
    assert only(cert.status(log.read(), src_root))["state"] == "failed"

    # Rolling back the failed attempt restores the earlier certification.
    r = cert.revoke(log, e2["event_id"], actor="will", reason="bad edit reverted")
    assert r["decision"] == "revoke" and r["rollback_to_event_id"] == e2["event_id"]
    row = only(cert.status(log.read(), src_root))
    assert row["state"] == "certified" and row["effective_event_id"] == e1["event_id"]

    # Revoking the only remaining certification leaves it revoked, not never.
    cert.revoke(log, e1["event_id"], actor="will", reason="owner withdrew it")
    assert only(cert.status(log.read(), src_root))["state"] == "revoked"


def test_revoke_must_name_current_effective_event(tmp_path, src_root):
    log = cert.EventLog(tmp_path / "events.jsonl")
    e1 = cert.certify(log, term_target(), root=src_root, actor="will", commit_sha="abc")
    cert.certify(log, term_target(), root=src_root, actor="will", commit_sha="abc")
    with pytest.raises(ValueError):
        cert.revoke(log, e1["event_id"], actor="will", reason="out of order")
    with pytest.raises(ValueError):
        cert.revoke(log, "evt_missing", actor="will", reason="x")


def test_crashing_check_is_recorded_as_failed(tmp_path, src_root):
    @cert.register_check("boom")
    def boom(root, params):
        raise RuntimeError("nope")

    log = cert.EventLog(tmp_path / "events.jsonl")
    t = term_target()
    t["check_id"] = "boom"
    e = cert.certify(log, t, root=src_root, actor="will", commit_sha="abc")
    assert e["check_result"] == "failed" and "RuntimeError" in e["check_detail"]
    del cert.CHECKS["boom"]


def test_target_validation(tmp_path, src_root):
    log = cert.EventLog(tmp_path / "events.jsonl")
    with pytest.raises(ValueError):
        cert.certify(log, {**term_target(), "field": "certified"}, root=src_root, actor="w")
    with pytest.raises(ValueError):
        cert.certify(
            log,
            {"target_kind": "column_attribute", "target_imported_id": "ca", "field": "certified", "check_id": "x"},
            root=src_root,
            actor="w",
        )


def test_gold_sql_check(tmp_path, src_root, code_db):
    params = {"evaluation": "evaluation.json", "database": "codemap.duckdb"}
    out = cert.CHECKS["gold_sql_reproduces"](src_root, params)
    assert out.passed, out.detail
    assert sorted(out.source_paths) == ["codemap.duckdb", "evaluation.json"]

    items = json.loads((src_root / "evaluation.json").read_text())
    # answer_raw (JSON rows) is what the check compares; q2's answer_raw is empty, so its answer is used.
    items[0]["answer_raw"] = "[[99]]"
    items[0]["answer"] = "1"
    items.append({**items[1], "question_id": "q3", "SQL": "select nope from code.files"})
    (src_root / "evaluation.json").write_text(json.dumps(items))
    out = cert.CHECKS["gold_sql_reproduces"](src_root, params)
    assert not out.passed
    assert "q1: answer differs" in out.detail and "q3: error" in out.detail

    only_q2 = cert.CHECKS["gold_sql_reproduces"](src_root, {**params, "question_ids": ["q2"]})
    assert only_q2.passed


def test_plan_patches_routes_and_payloads(tmp_path, src_root):
    log = cert.EventLog(tmp_path / "events.jsonl")
    cert.certify(log, term_target(), root=src_root, actor="w", commit_sha="a")
    cert.certify(
        log,
        {
            "target_kind": "column_attribute",
            "target_imported_id": "ca_file_package",
            "parent_term_imported_id": "term_file",
            "field": "certified",
            "check_id": "docstring_matches_description",
            "params": {"path": "pkg/files.py", "description": DESC},
        },
        root=src_root,
        actor="w",
        commit_sha="a",
    )
    e3 = cert.certify(
        log,
        {
            "target_kind": "sql_attribute",
            "target_imported_id": "sa_count",
            "field": "certified",
            "check_id": "docstring_matches_description",
            "params": {"path": "pkg/files.py", "description": DESC},
        },
        root=src_root,
        actor="w",
        commit_sha="a",
    )
    cert.revoke(log, e3["event_id"], actor="w", reason="query changed meaning")
    cert.certify(log, term_target("wrong", field="name"), root=src_root, actor="w", commit_sha="a")

    rows = cert.status(log.read(), src_root)
    id_map = {"term_file": "11111111-live", "ca_file_package": "22222222-live", "sa_count": "33333333-live"}
    plan = cert.plan_patches(rows, id_map)
    by_path = {r["path"]: r for r in plan["requests"]}
    assert by_path["/api/terms/11111111-live"]["json"] == {"description_certified": True}
    assert by_path["/api/terms/11111111-live/column-attributes/22222222-live"]["json"] == {"certified": True}
    assert by_path["/api/sql-attributes/33333333-live"]["json"] == {"certified": False}
    assert all(r["method"] == "PATCH" and r["ready"] for r in plan["requests"])
    # The failed name check is withheld, not silently unset.
    assert [w["field"] for w in plan["withheld"]] == ["name"]
    unset = cert.plan_patches(rows, id_map, unset_stale=True)
    assert {"name_certified": False} in [r["json"] for r in unset["requests"]]

    partial = cert.plan_patches(rows, {})
    assert all(not r["ready"] for r in partial["requests"])
    assert "/api/terms/{live_id_of:term_file}" in [r["path"] for r in partial["requests"]]


class _Recorder(BaseHTTPRequestHandler):
    seen: list = []

    def do_PATCH(self):  # noqa: N802
        body = self.rfile.read(int(self.headers["content-length"]))
        _Recorder.seen.append((self.path, json.loads(body), self.headers.get("x-api-key")))
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


def test_apply_sends_only_ready_requests_and_never_returns_the_token(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), _Recorder)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        plan = {
            "requests": [
                {"method": "PATCH", "path": "/api/terms/t1", "json": {"description_certified": True}, "ready": True},
                {"method": "PATCH", "path": "/api/terms/{live_id_of:x}", "json": {"name_certified": True}, "ready": False},
            ]
        }
        monkeypatch.delenv(cert.TOKEN_ENV, raising=False)
        with pytest.raises(RuntimeError):
            cert.apply_patches(plan, f"http://127.0.0.1:{server.server_port}")
        assert _Recorder.seen == []

        monkeypatch.setenv(cert.TOKEN_ENV, "auto_ontology_test_token")
        results = cert.apply_patches(plan, f"http://127.0.0.1:{server.server_port}")
        assert _Recorder.seen == [("/api/terms/t1", {"description_certified": True}, "auto_ontology_test_token")]
        assert results[0] == {"path": "/api/terms/t1", "sent": True, "status": 200}
        assert results[1]["sent"] is False
        assert "auto_ontology_test_token" not in json.dumps(results)
    finally:
        server.shutdown()


def test_internal_apply_sends_no_token_and_forwards_the_user(monkeypatch):
    class _UserRecorder(_Recorder):
        def do_PATCH(self):  # noqa: N802
            self.rfile.read(int(self.headers["content-length"]))
            _UserRecorder.seen.append((self.headers.get("x-api-key"), self.headers.get("x-auto-ontology-user-id")))
            self.send_response(200)
            self.end_headers()

    _UserRecorder.seen = []
    server = HTTPServer(("127.0.0.1", 0), _UserRecorder)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        plan = {"requests": [{"method": "PATCH", "path": "/api/terms/t1", "json": {"name_certified": True}, "ready": True}]}
        monkeypatch.setenv(cert.TOKEN_ENV, "auto_ontology_test_token")
        url = f"http://127.0.0.1:{server.server_port}"
        assert cert.apply_patches(plan, url, internal=True)[0]["status"] == 200
        cert.apply_patches(plan, url, internal=True, user_id="user-1")
        assert _UserRecorder.seen == [(None, None), (None, "user-1")]
    finally:
        server.shutdown()


REPO = Path(__file__).resolve().parents[2]
CLONE = Path(os.environ["AUTO_ONTOLOGY_CLONE"]) if os.environ.get("AUTO_ONTOLOGY_CLONE") else None


def _openapi() -> dict:
    path = CLONE / "docs" / "openapi" / "auto-ontology-api.json" if CLONE else None
    if path is None or not path.is_file():
        pytest.skip("needs AUTO_ONTOLOGY_CLONE with docs/openapi/auto-ontology-api.json")
    return json.loads(path.read_text(encoding="utf-8"))


def _template_for(path: str, templates: list[str]) -> str | None:
    parts = path.strip("/").split("/")
    for template in templates:
        tparts = template.strip("/").split("/")
        if len(tparts) == len(parts) and all(t == p or (t.startswith("{") and t.endswith("}")) for t, p in zip(tparts, parts)):
            return template
    return None


def test_planned_patches_match_their_openapi(tmp_path, src_root):
    """Every planned request hits a PATCH route in their OpenAPI file, sends only
    fields of that route's request-body schema, and the route takes the
    x-api-key ApiToken we send."""
    spec = _openapi()
    log = cert.EventLog(tmp_path / "events.jsonl")
    for target in (
        term_target(),
        term_target(field="name", description="Load files and compute their fingerprints."),
        {**term_target(), "target_kind": "column_attribute", "target_imported_id": "ca", "parent_term_imported_id": "term_file", "field": "certified"},
        {**term_target(), "target_kind": "sql_attribute", "target_imported_id": "sa", "field": "certified"},
    ):
        cert.certify(log, target, root=src_root, actor="w", commit_sha="a")
    plan = cert.plan_patches(cert.status(log.read(), src_root), {"term_file": "t-live", "ca": "c-live", "sa": "s-live"})
    assert len(plan["requests"]) == 4
    assert spec["components"]["securitySchemes"]["ApiToken"] == {
        **spec["components"]["securitySchemes"]["ApiToken"],
        "type": "apiKey",
        "in": "header",
        "name": "x-api-key",
    }
    seen_templates = set()
    for req in plan["requests"]:
        template = _template_for(req["path"], list(spec["paths"]))
        assert template, req["path"]
        operation = spec["paths"][template].get(req["method"].lower())
        assert operation, (template, req["method"])
        assert {"ApiToken": []} in operation.get("security", [])
        ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        properties = spec["components"]["schemas"][ref.rsplit("/", 1)[-1]]["properties"]
        assert set(req["json"]) <= set(properties), (template, req["json"])
        seen_templates.add(template)
    assert seen_templates == {
        "/api/terms/{term_id}",
        "/api/terms/{term_id}/column-attributes/{attr_id}",
        "/api/sql-attributes/{attr_id}",
    }


def test_cli_apply_never_prints_the_token(tmp_path, src_root):
    """Run ``cob cert-status --apply`` as a process against a stub server and
    check its stdout and stderr, for a successful send and for an HTTP error."""
    log = cert.EventLog(tmp_path / "events.jsonl")
    cert.certify(log, term_target(), root=src_root, actor="w", commit_sha="a")
    cert.certify(log, term_target(tid="term_other"), root=src_root, actor="w", commit_sha="a")
    id_map = tmp_path / "ids.json"
    id_map.write_text(json.dumps({"term_file": "t1", "term_other": "missing"}))
    token = "auto_ontology_secret_token_0123456789"

    class _Handler(_Recorder):
        def do_PATCH(self):  # noqa: N802
            self.rfile.read(int(self.headers["content-length"]))
            _Recorder.seen.append((self.path, self.headers.get("x-api-key")))
            self.send_response(200 if self.path.endswith("/t1") else 404)
            self.end_headers()

    _Recorder.seen = []
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = {**os.environ, cert.TOKEN_ENV: token}
        proc = subprocess.run(
            [sys.executable, "-m", "code_ontology_bridge.cli", "cert-status", "--log", str(log.path), "--root", str(src_root),
             "--id-map", str(id_map), "--apply", "--base-url", f"http://127.0.0.1:{server.server_port}"],
            capture_output=True, text=True, env=env, cwd=REPO, timeout=60,
        )
    finally:
        server.shutdown()
    assert proc.returncode == 0, proc.stderr
    assert sorted(_Recorder.seen) == [("/api/terms/missing", token), ("/api/terms/t1", token)]
    assert token not in proc.stdout and token not in proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["mode"] == "applied"
    assert sorted(r["status"] for r in payload["applied"]) == [200, 404]


def test_revoked_column_attribute_keeps_parent_route(tmp_path, src_root):
    log = cert.EventLog(tmp_path / 'events.jsonl')
    target = {**term_target(), 'target_kind': 'column_attribute',
              'target_imported_id': 'attr', 'parent_term_imported_id': 'term',
              'field': 'certified'}
    event = cert.certify(log, target, root=src_root, actor='test')
    cert.revoke(log, event['event_id'], actor='test', reason='withdrawn')
    state = cert.status(log.read(), src_root)
    plan = cert.plan_patches(state, {'attr': 'live-attr', 'term': 'live-term'})
    assert plan['requests'][0]['ready']
    assert plan['requests'][0]['path'] == '/api/terms/live-term/column-attributes/live-attr'
    assert plan['requests'][0]['json'] == {'certified': False}
