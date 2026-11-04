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
            "400": {"description": "Invalid or unknown query parameter"},
            "404": {"description": "Unknown route or identity"}}}

    def page(items):
        return {"type": "object", "required": ["items", "total", "limit", "offset", "next_offset"],
                "properties": {"items": {"type": "array", "items": items}, "total": integer,
                               "limit": integer, "offset": integer,
                               "next_offset": {"type": ["integer", "null"]}}}

    paging = [parameter("limit", {"type": "integer", "default": 25, "minimum": 1, "maximum": 100}),
              parameter("offset", {"type": "integer", "default": 0, "minimum": 0, "maximum": 999999999})]
    paths = {}

    def add(path, summary, params, schema):
        get = operation(summary, params, schema)
        paths[PREFIX + path] = {"get": get, "head": {
            "summary": "Headers for: " + summary, "parameters": params,
            "responses": {key: {"description": value["description"]} for key, value in get["responses"].items()}}}

    add("", "Snapshot identity and available routes", [], record)
    add("/overview", "Counts, packages, provenance and evaluation limits", [], record)
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
        if table.name in ("files", "symbols"):
            properties["source_url"] = {"type": ["string", "null"]}
        add("/tables/" + table.name, table.description, params,
            page({"type": "object", "required": table.column_names, "properties": properties}))
    add("/questions", "Recorded questions with automatic scores and separate review findings", paging, page(record))
    add("/questions/{id}", "Exact request, generated SQL, returned tables, reference and review", [], record)
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
    ], {"type": "object", "required": ["root", "nodes", "edges", "truncated", "depth_limited"],
        "properties": {"root": text, "nodes": {"type": "array", "items": record},
                       "edges": {"type": "array", "items": record},
                       "truncated": {"type": "boolean"}, "depth_limited": {"type": "boolean"}}})
    return {"openapi": "3.1.0", "info": {"title": "Code Ontology Bridge inspection API", "version": "1.0.0"},
            "paths": paths}
