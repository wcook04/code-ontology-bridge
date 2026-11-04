"""OpenAPI document derived from the extractor's table and column definitions."""
from .api import API_SCHEMA, PREFIX
from ..codemap.schema import TABLES


def openapi_document():
    record = {"type": "object", "additionalProperties": True}
    text = {"type": "string"}
    integer = {"type": "integer"}

    def parameter(name, schema, required=False, description=""):
        return {"name": name, "in": "query", "required": required,
                "description": description, "schema": schema}

    def operation(summary, parameters, data_schema):
        envelope = {"type": "object", "required": ["schema_version", "revision", "data"],
                    "properties": {"schema_version": {"const": API_SCHEMA},
                                   "revision": text, "data": data_schema}}
        return {"summary": summary, "parameters": parameters, "responses": {
            "200": {"description": "Snapshot data", "content": {"application/json": {"schema": envelope}}},
            "304": {"description": "Representation unchanged"},
            "400": {"description": "Invalid or unknown query parameter", "content": {"application/json": {"schema": ref("Error")}}},
            "404": {"description": "Unknown route or identity", "content": {"application/json": {"schema": ref("Error")}}},
            "405": {"description": "Method not allowed", "content": {"application/json": {"schema": ref("Error")}}}}}

    def page(items):
        return {"type": "object", "required": ["items", "total", "limit", "offset", "next_offset"],
                "properties": {"items": {"type": "array", "items": items}, "total": integer,
                               "limit": integer, "offset": integer,
                               "next_offset": {"type": ["integer", "null"]}}}

    paging = [parameter("limit", {"type": "integer", "default": 25, "minimum": 1, "maximum": 100}),
              parameter("offset", {"type": "integer", "default": 0, "minimum": 0, "maximum": 999999999})]
    paths = {}
    schemas = resource_schemas()
    ref = lambda name: {"$ref": "#/components/schemas/" + name}

    def add(path, summary, params, schema):
        get = operation(summary, params, schema)
        paths[PREFIX + path] = {"get": get, "head": {
            "summary": "Headers for: " + summary, "parameters": params,
            "responses": {key: {"description": value["description"]} for key, value in get["responses"].items()}}}

    add("", "Snapshot identity and available routes", [], record)
    add("/overview", "Counts, packages, provenance and evaluation limits", [], ref("Overview"))
    add("/models", "Frozen model input and explicitly distinguished readback stages", [], ref("Models"))
    add("/cases", "Authored reading paths resolved against saved evidence", [], {"type": "array", "items": ref("Case")})
    add("/source-spans", "Selected build-time source locations and verified excerpts", [], {"type": "array", "items": ref("SourceSpan")})
    add("/schema", "Source table and join definitions", [], {"type": "array", "items": record})
    add("/bundle", "Complete portable snapshot", [], record)
    for table in TABLES:
        properties, params = {}, list(paging)
        for col in table.columns:
            kind = {"TEXT": "string", "INTEGER": "integer", "BOOLEAN": "boolean"}[col.sql_type]
            schema = {"type": [kind, "null"] if col.nullable else kind, "description": col.description}
            if col.allowed:
                schema["enum"] = list(col.allowed)
            properties[col.name] = schema
            params.append(parameter(col.name, {"type": kind}, description="Exact equality filter. " + col.description))
        params.append(parameter("q", {"type": "string", "minLength": 1, "maxLength": 160},
                                description="Case-insensitive literal substring across row values; nonblank."))
        if table.name == "calls":
            params.append(parameter("target", {"enum": ["all", "resolved", "null"], "default": "all"},
                                    description="Filter by presence of an internal callee, independently of resolution category."))
        if table.name in ("files", "symbols"):
            properties["source_url"] = {"type": ["string", "null"]}
        add("/tables/" + table.name, table.description, params,
            page({"type": "object", "required": table.column_names, "properties": properties}))
    add("/questions", "Recorded questions with automatic scores and separate review findings", paging, page(ref("QuestionSummary")))
    add("/questions/{id}", "Exact request, generated SQL, returned tables, reference and review", [], ref("RecordedQuestion"))
    for method in ("get", "head"):
        paths[PREFIX + "/questions/{id}"][method]["parameters"] = [
            {"name": "id", "in": "path", "required": True, "schema": {"type": "integer", "minimum": 1}}]
    add("/graph", "Bounded resolved call neighborhood; static relationships, not execution", [
        parameter("symbol_id", text, True),
        parameter("direction", {"enum": ["callers", "callees"], "default": "callers"}),
        parameter("call_kind", {"enum": ["all", "direct", "callback"], "default": "all"}),
        parameter("include_tests", {"type": "boolean", "default": True}),
        parameter("depth", {"type": "integer", "minimum": 1, "maximum": 5, "default": 1}),
        parameter("max_nodes", {"type": "integer", "minimum": 1, "maximum": 200, "default": 100}),
        parameter("max_edges", {"type": "integer", "minimum": 1, "maximum": 500, "default": 200}),
    ], ref("Graph"))
    return {"openapi": "3.1.0", "info": {"title": "Code Ontology Bridge inspection API", "version": "1.0.0"},
            "paths": paths, "components": {"schemas": schemas}}


# These are transport/resource schemas. Source row columns still have one owner: TABLES.
def resource_schemas():
    text, integer, boolean = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}
    nullable_text = {"type": ["string", "null"]}
    record = {"type": "object"}
    scalar = {"type": ["string", "integer", "number", "boolean", "null"]}
    ref = lambda name: {"$ref": "#/components/schemas/" + name}
    arr = lambda item: {"type": "array", "items": item}
    enum = lambda *values: {"enum": list(values)}
    def obj(props, required=None, extra=False):
        return {"type": "object", "properties": props, "required": list(props) if required is None else required,
                "additionalProperties": extra}
    def row(name, **extra):
        table = next(t for t in TABLES if t.name == name)
        props = {}
        for col in table.columns:
            kind = {"TEXT": "string", "INTEGER": "integer", "BOOLEAN": "boolean"}[col.sql_type]
            props[col.name] = {"type": [kind, "null"] if col.nullable else kind}
            if col.allowed:
                props[col.name]["enum"] = list(col.allowed) + ([None] if col.nullable else [])
        return obj(dict(props, **extra))
    schemas = {
        "Error": obj({"schema_version": {"const": API_SCHEMA}, "error": obj({"message": text})}),
        "Review": obj({"table_match": enum("pass", "fail"), "prose_review": enum("substantive", "fail", "unknown"),
                       "review_method": enum("author_review_not_blinded", "not_supplied"),
                       "review_basis": enum("individual_finding", "documented_aggregate", "not_supplied"),
                       "availability": {"const": "recorded"}}),
        "ResultTable": arr({"type": "object", "additionalProperties": scalar}),
        "GraphNode": row("symbols", depth=integer, source_url=nullable_text),
        "GraphEdge": row("calls", source_url=nullable_text),
        "Dataset": obj({"sha256": text, "algorithm": {"const": "cob_typed_tables_v1"}, "role": {"const": "publication_dataset"}}),
        "SourceSpan": obj({"id": text, "kind": enum("symbol", "call"), "record_id": text,
            "repository": text, "commit": nullable_text, "path": text, "line_start": integer, "line_end": integer,
            "file_sha256": text, "source_url": nullable_text, "excerpt": nullable_text,
            "excerpt_line_start": {"type": ["integer", "null"]}, "excerpt_status": enum("not_supplied", "verified_file_hash")}),
        "OutputContract": obj({"fields": arr(obj({"name": text, "type": enum("string", "integer", "number", "boolean")})),
                               "ordered": boolean, "guidance": text}),
    }
    score = obj({k: boolean for k in ("completed", "schema_complete", "values_match", "order_matches", "prose_present", "strict_rows_pass", "pass")} |
                {"question_id": integer, "agent_rows": integer, "reference_rows": integer, "issues": arr(text)})
    summary = {"question_id": integer, "question": text, "score": score,
               "review_finding": {"anyOf": [record, {"type": "null"}]}, "assessment": ref("Review")}
    schemas["QuestionSummary"] = obj(summary)
    schemas["RecordedQuestion"] = obj(dict(summary,
        request=obj({"question": text, "evidence": nullable_text, "calculation_only": boolean}, ["question", "calculation_only"]),
        output_contract=ref("OutputContract"), sql=nullable_text, answer=nullable_text,
        result_tables=arr(ref("ResultTable")), reference_sql=text, reference_rows={"type": ["string", "null"], "description": "Unmodified JSON-encoded reference rows from the frozen evaluation input."},
        artifact=text, sha256=text,
        display_annotations=obj({"method": {"const": "output_contract_identity_columns"}, "note": text,
            "links": arr(obj({"table_index": integer, "row_index": integer, "column": text,
                              "table": enum("files", "symbols"), "identity": text, "source_url": nullable_text}))})))
    schemas["Graph"] = obj({"root": text, "direction": enum("callers", "callees"), "depth": integer,
        "call_kind": enum("all", "direct", "callback"), "include_tests": boolean,
        "test_policy": enum("include", "exclude_from_traversal_except_root"), "max_nodes": integer, "max_edges": integer,
        "edge_semantics": {"const": "induced_call_occurrences"}, "availability": {"const": "computed_locally"},
        "truncated": boolean, "depth_limited": boolean, "omission_reasons": arr(enum("node_limit", "edge_limit", "depth_limit")),
        "counts": obj({k: integer for k in ("nodes", "call_occurrences", "unique_pairs", "eligible_call_occurrences")}),
        "nodes": arr(ref("GraphNode")), "edges": arr(ref("GraphEdge")), "semantics": text})
    column = obj({"id": text, "name": text, "description": text, "type": text,
                  "sample_values": arr(scalar), "is_nullable": boolean, "is_unique": boolean})
    table = obj({"id": text, "name": text, "description": text, "pk": arr(text), "type": text, "columns": arr(column)})
    attribute = obj({"id": text, "name": text, "description": text, "column_id": text})
    term = obj({"id": text, "name": text, "description": text, "represents": arr(text), "columns_attributes": arr(attribute)})
    native = obj({
        "data_layer": obj({"databases": arr(obj({"id": text, "dialect": text, "schemas": arr(obj({"id": text, "name": text, "database_name": text, "tables": arr(table)}))})),
                           "foreign_keys": arr(obj({"source_column_id": text, "target_column_id": text})), "joins": arr(record)}),
        "semantic_layer": obj({"terms": arr(term), "semantic_fks": arr(obj({"column_attribute_id": text, "column_id": text, "use_in_join_paths": boolean})),
            "sql_attributes": obj({k: arr(record) for k in ("manual", "table", "sql", "bridge_table")}),
            "custom_analyses": arr(obj({"id": text, "name": text, "description": text, "sql": text, "sql_column_is": arr(text)}))}), "zones": arr(record)})
    schemas["SemanticModel"] = obj({"status": enum("recorded", "computed_locally"), "role": enum("exported_input", "generated_export"),
        "format": {"const": "auto_ontology_native_yaml"}, "artifact": nullable_text, "sha256": text, "text": text,
        "document": native, "source_commit": nullable_text, "source_fingerprint": text})
    absent = obj({"status": enum("not_supplied", "not_captured")})
    schemas["Models"] = obj({
        "exported_input": {"anyOf": [absent, ref("SemanticModel")]}, "generated_export": ref("SemanticModel"),
        "submitted_import": absent, "catalog_id_mapping": absent, "compiled_model": absent, "retrieved_context": absent,
        "compiled_terms": {"anyOf": [absent, obj({"status": {"const": "recorded"}, "role": {"const": "partial_terms_readback"},
            "artifact": text, "sha256": text, "terms": arr(obj({"id": text, "name": text, "description": nullable_text}, ["id", "name"], True)), "note": text})]}},
        ["exported_input", "submitted_import", "catalog_id_mapping", "compiled_model", "compiled_terms", "retrieved_context"])
    counts = {"type": "object", "additionalProperties": integer}
    snapshot_summary = row("snapshot")
    del snapshot_summary["properties"]["known_limits"]
    snapshot_summary["required"].remove("known_limits")
    schemas["Summary"] = obj({
        "snapshot": snapshot_summary, "known_limits": arr(text),
        "omitted_files": arr({"type": "object", "additionalProperties": text}),
        "row_counts": obj({t.name: integer for t in TABLES}),
        "files": obj({"total": integer, "test_files": integer, "with_fixed_headings": integer,
                      "description_source": counts, "description_source_pct": {"type": "object", "additionalProperties": {"type": "number"}}}),
        "symbols": obj({"total": integer, "by_kind": counts, "public": integer, "with_summary": integer}),
        "calls": obj({"total": integer, "by_call_kind": counts, "direct_by_resolution": counts, "callback_by_resolution": counts}),
        "class_bases": obj({"total": integer, "resolved_to_internal_class": integer}),
        "imports": obj({"total": integer, "internal": integer, "resolved_to_file": integer}),
        "test_links": obj({"total": integer, "by_reason": counts})})
    schemas["Binding"] = obj({"source_commit": text, "dataset_match": enum("verified", "not_captured"),
        "run_dataset_sha256": nullable_text, "source_database_sha256": nullable_text,
        "artifact_manifest_sha256": text, "note": text})
    schemas["RunManifest"] = obj({"started_at": text, "bridge_commit": text, "upstream_commit": text,
        "chat_model": text, "embedding_model": text, "reranking_model": text, "protocol": text,
        "calculation_only": boolean, "attempts_per_question": integer, "custom_analyses_imported": integer,
        "input_sha256": {"type": "object", "additionalProperties": text}})
    schemas["Overview"] = obj({"snapshot": row("snapshot"), "summary": ref("Summary"),
        "packages": arr(obj({"package": text, "files": integer, "symbols": integer})),
        "dataset": {"anyOf": [ref("Dataset"), {"type": "null"}]}, "evidence": obj({
            "status": enum("recorded_run", "not_supplied"), "fresh_execution": {"const": False},
            "scope": text, "manifest": ref("RunManifest"), "score": record, "review": {"type": ["object", "null"]}, "binding": ref("Binding")},
            ["status", "fresh_execution"])})
    schemas["Case"] = obj({"id": text, "title": text, "short_question": text, "question_id": integer,
        "root_symbol_id": text, "semantic_term_ids": arr(text), "column_ids": arr(text), "call_ids": arr(text),
        "graph_presets": {"type": "object", "additionalProperties": {"type": "object", "additionalProperties": text}},
        "captions": arr(text), "editorial": {"const": True}, "recorded_response_ref": obj({"artifact": text, "sha256": text}),
        "source_span_ids": arr(text), "graphs": {"type": "object", "additionalProperties": ref("Graph")},
        "records": obj({"symbols": arr(row("symbols")), "calls": arr(row("calls"))}), "note": text})
    return schemas
