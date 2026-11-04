"""Resolve a small authored reading path and emit static, model-free JSON assets."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import tempfile

from .api import Inspector

# Exact output-contract field names, never guesses from path-shaped values.
IDENTITY_COLUMNS = {"symbol_id": "symbols", "caller_symbol_id": "symbols", "callee_symbol_id": "symbols",
                    "file_id": "files", "test_file_id": "files"}


def annotate_results(bundle):
    api = Inspector(dict(bundle, revision="building"))
    for question in bundle["evidence"]["questions"]:
        links = []
        fields = {f["name"] for f in question["output_contract"]["fields"] if f["type"] == "string"}
        for table_index, rows in enumerate(question["result_tables"]):
            for row_index, row in enumerate(rows):
                for column in sorted(fields & IDENTITY_COLUMNS.keys()):
                    value = row.get(column)
                    records = api.symbols if IDENTITY_COLUMNS[column] == "symbols" else api.files
                    if value in records:
                        links.append({"table_index": table_index, "row_index": row_index, "column": column,
                                      "table": IDENTITY_COLUMNS[column], "identity": value,
                                      "source_url": api.source_url(records[value])})
        question["display_annotations"] = {"method": "output_contract_identity_columns", "links": links,
            "note": "Deterministic display links; not source citations made by the model."}


def source_span(api, kind, identity, source_root):
    if kind not in ("symbol", "call"):
        raise ValueError("invalid source span kind")
    if kind == "symbol":
        row = api.symbols[identity]
        file_id, start, end = row["file_id"], row["line_start"], row["line_end"]
    else:
        row = next(r for r in api.tables["calls"] if r["call_id"] == identity)
        file_id = api.symbols[row["caller_symbol_id"]]["file_id"]
        start = end = row["line"]
    file = api.files[file_id]
    span = {"id": kind + ":" + identity, "kind": kind, "record_id": identity,
            "repository": api.bundle["snapshot"]["repo_url"], "commit": api.bundle["snapshot"]["commit_sha"],
            "path": file_id, "line_start": start, "line_end": end, "file_sha256": file["sha256"],
            "source_url": api.source_url({"file_id": file_id, "line_start": start}),
            "excerpt": None, "excerpt_line_start": None, "excerpt_status": "not_supplied"}
    if source_root:
        root = Path(source_root).resolve()
        path = root / file_id
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("source file escapes selected snapshot")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != file["sha256"]:
            raise ValueError("selected source file hash differs: " + file_id)
        lines = raw.decode("utf-8").splitlines()
        if start < 1 or end < start or end > len(lines):
            raise ValueError("source span is outside file")
        excerpt_start = max(1, start - 2)
        excerpt_end = min(len(lines), start + 7)
        span.update(excerpt="\n".join(lines[excerpt_start - 1:excerpt_end]),
                    excerpt_line_start=excerpt_start, excerpt_status="verified_file_hash")
    return span


def attach_case(bundle, descriptor, source_root=None):
    required = {"id", "title", "short_question", "question_id", "root_symbol_id", "semantic_term_ids",
                "column_ids", "call_ids", "graph_presets", "captions"}
    if set(descriptor) != required or not re.fullmatch(r"[a-z0-9-]+", descriptor["id"]):
        raise ValueError("invalid case descriptor")
    api = Inspector(dict(bundle, revision="building"))
    question = api.questions.get(str(descriptor["question_id"]))
    if question is None:
        raise ValueError("case question missing")
    graphs = {}
    for name, params in descriptor["graph_presets"].items():
        if not re.fullmatch(r"[a-z0-9_]+", name):
            raise ValueError("invalid graph preset name")
        graphs[name] = api.graph(dict(params, symbol_id=descriptor["root_symbol_id"]))
    symbols = {n["symbol_id"] for graph in graphs.values() for n in graph["nodes"]}
    calls = {e["call_id"] for graph in graphs.values() for e in graph["edges"]} | set(descriptor["call_ids"])
    known_calls = {r["call_id"] for r in api.tables["calls"]}
    if not calls <= known_calls:
        raise ValueError("case call reference missing")
    spans = [source_span(api, "symbol", identity, source_root) for identity in sorted(symbols)]
    spans += [source_span(api, "call", identity, source_root) for identity in sorted(calls)]
    case = dict(descriptor, editorial=True, recorded_response_ref={"artifact": question["artifact"], "sha256": question["sha256"]},
                source_span_ids=[s["id"] for s in spans], graphs=graphs,
                records={"symbols": [api.symbols[s] for s in sorted(symbols)],
                         "calls": [r for r in api.tables["calls"] if r["call_id"] in calls]},
                note="Graph presets are local computations. Test exclusion removes traversal nodes; recorded SQL filters final rows.")
    bundle["cases"].append(case)
    bundle["source_spans"].extend(spans)


def validate_resources(bundle):
    """Admit references again on load, even if a modified bundle has a valid hash."""
    from .models import model_resource
    models = bundle.get("models", {})
    for name in ("exported_input", "generated_export"):
        resource = models.get(name, {})
        if resource.get("document") is not None:
            checked = model_resource(resource["text"].encode(), bundle["snapshot"], role=resource["role"],
                                     artifact=resource["artifact"], expected_sha256=resource["sha256"])
            if checked != resource:
                raise ValueError("model document differs from retained YAML")
    questions = {q["question_id"]: q for q in bundle["evidence"]["questions"]}
    if len(questions) != len(bundle["evidence"]["questions"]) or any(type(qid) is not int or qid < 1 for qid in questions):
        raise ValueError("invalid publication question identities")
    api = Inspector(dict(bundle, revision=bundle.get("revision", "building")))
    spans = {s["id"]: s for s in bundle.get("source_spans", [])}
    if len(spans) != len(bundle.get("source_spans", [])):
        raise ValueError("duplicate source span")
    for span in spans.values():
        expected = source_span(api, span["kind"], span["record_id"], None)
        if any(span.get(k) != v for k, v in expected.items() if k not in ("excerpt", "excerpt_line_start", "excerpt_status")):
            raise ValueError("source span reference differs")
    case_ids = [c["id"] for c in bundle.get("cases", [])]
    if len(case_ids) != len(set(case_ids)) or any(not re.fullmatch(r"[a-z0-9-]+", cid) for cid in case_ids):
        raise ValueError("invalid publication case identities")
    for case in bundle.get("cases", []):
        if case["question_id"] not in questions or not set(case["source_span_ids"]) <= spans.keys():
            raise ValueError("dangling case reference")
        q = questions[case["question_id"]]
        if case["recorded_response_ref"] != {"artifact": q["artifact"], "sha256": q["sha256"]}:
            raise ValueError("case recorded artifact differs")
        model = models.get("exported_input", {}).get("document")
        if model is None:
            raise ValueError("case requires frozen model input")
        terms = {t["id"] for t in model["semantic_layer"]["terms"]}
        columns = {c["id"] for d in model["data_layer"]["databases"] for s in d["schemas"] for t in s["tables"] for c in t["columns"]}
        if not set(case["semantic_term_ids"]) <= terms or not set(case["column_ids"]) <= columns:
            raise ValueError("dangling case model reference")
        expected_symbols, expected_calls = set(), set(case["call_ids"])
        for name, params in case["graph_presets"].items():
            expected_symbols.update(n["symbol_id"] for n in case["graphs"][name]["nodes"])
            expected_calls.update(e["call_id"] for e in case["graphs"][name]["edges"])
            if case["graphs"][name] != api.graph(dict(params, symbol_id=case["root_symbol_id"])):
                raise ValueError("case graph preset differs")
        expected_records = {"symbols": [api.symbols[s] for s in sorted(expected_symbols)],
                            "calls": [r for r in api.tables["calls"] if r["call_id"] in expected_calls]}
        if case["records"] != expected_records or not expected_calls <= {r["call_id"] for r in api.tables["calls"]}:
            raise ValueError("case extracted records differ")
        if set(case["source_span_ids"]) != {"symbol:" + s for s in expected_symbols} | {"call:" + c for c in expected_calls}:
            raise ValueError("case source spans differ")
    for q in questions.values():
        for link in q.get("display_annotations", {}).get("links", []):
            record = q["result_tables"][link["table_index"]][link["row_index"]]
            if record[link["column"]] != link["identity"]:
                raise ValueError("result annotation differs")


def check_public(value):
    """Fail closed on forbidden capture fields; descriptions remain inert JSON text."""
    forbidden = {"thoughts", "events", "logs", "authorization", "api_key", "password", "headers"}
    if isinstance(value, dict):
        if forbidden & {k.lower() for k in value}:
            raise ValueError("forbidden captured material in public projection")
        for item in value.values():
            check_public(item)
    elif isinstance(value, list):
        for item in value:
            check_public(item)
    elif isinstance(value, str) and re.search(r"(?:nvapi-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{24,}|Bearer\s+[A-Za-z0-9._-]{20,}|/Users/[^/\s]+/|/home/[^/\s]+/)", value):
        raise ValueError("credential or private path in public projection")


def publish(bundle, out):
    """Write an immutable directory. No runtime, network, model calls or HTML."""
    from .bundle import encode
    from .contract import openapi_document
    validate_resources(bundle)
    check_public(bundle)
    api = Inspector(bundle)
    resources = {"overview.json": api.query("/api/v1/overview", {}), "schema.json": bundle["schema"],
                 "models.json": bundle.get("models", {}), "source-spans.json": bundle.get("source_spans", []),
                 "questions.json": api.query("/api/v1/questions", {"limit": "100"}),
                 "openapi.json": openapi_document(), "bundle.json": bundle}
    for question in bundle["evidence"]["questions"]:
        resources[f"questions/{question['question_id']}.json"] = question
    for case in bundle.get("cases", []):
        resources[f"cases/{case['id']}.json"] = case
    for name in ("score", "review", "contracts"):
        if name in bundle["evidence"]:
            resources[f"evidence/{name}.json"] = bundle["evidence"][name]
    manifest = {"schema_version": "cob_publication_v1", "revision": bundle["revision"],
                "dataset": bundle.get("dataset"), "source_snapshot": bundle["snapshot"],
                "entry_cases": [f"cases/{c['id']}.json" for c in bundle.get("cases", [])],
                "question_count": len(bundle["evidence"]["questions"]), "resources": {}}
    out = Path(out)
    if out.exists():
        raise ValueError("publication destination must not exist")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".cob-publication-", dir=out.parent) as temp:
        root = Path(temp) / "assets"
        root.mkdir()
        for name, value in sorted(resources.items()):
            raw = encode(value) + b"\n"
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            manifest["resources"][name] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "media_type": "application/json"}
        (root / "manifest.json").write_bytes(encode(manifest) + b"\n")
        root.rename(out)
    return manifest
