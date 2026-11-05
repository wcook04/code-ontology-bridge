"""Frozen native Auto Ontology inputs, validated without an upstream dependency."""
from __future__ import annotations

import hashlib
import yaml

from ..export.model_export import build_model_document, header_comment


def validate_model(document):
    """Check native references; this is not a replacement for upstream round trips."""
    if set(document) != {"data_layer", "semantic_layer", "zones"}:
        raise ValueError("expected native Auto Ontology model")
    data, semantic = document["data_layer"], document["semantic_layer"]
    tables, columns, attributes, identities = {}, {}, {}, set()

    def identity(obj):
        value = obj["id"]
        if not isinstance(value, str) or not value or value in identities:
            raise ValueError("duplicate or invalid model identity")
        identities.add(value)
        return value

    for db in data["databases"]:
        identity(db)
        for schema in db["schemas"]:
            identity(schema)
            for table in schema["tables"]:
                tables[identity(table)] = table
                local = set()
                for column in table["columns"]:
                    cid = identity(column)
                    columns[cid] = column
                    local.add(cid)
                if not set(table["pk"]) <= local:
                    raise ValueError("dangling model primary key")
    for term in semantic["terms"]:
        identity(term)
        if not set(term["represents"]) <= tables.keys():
            raise ValueError("dangling represented table")
        represented_columns = {c["id"] for tid in term["represents"] for c in tables[tid]["columns"]}
        for attr in term["columns_attributes"]:
            attributes[identity(attr)] = attr
            if attr["column_id"] not in represented_columns:
                raise ValueError("dangling model column")
    for fk in data["foreign_keys"]:
        if fk["source_column_id"] not in columns or fk["target_column_id"] not in columns:
            raise ValueError("dangling model foreign key")
    for fk in semantic["semantic_fks"]:
        if fk["column_id"] not in columns or fk["column_attribute_id"] not in attributes:
            raise ValueError("dangling semantic foreign key")
    for analysis in semantic["custom_analyses"]:
        identity(analysis)
    return document


def model_resource(raw, snapshot, *, role, artifact, expected_sha256=None):
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError("frozen model hash mismatch")
    text = raw.decode("utf-8")
    for key in ("commit_sha", "source_fingerprint", "snapshot_id"):
        if f"# {key}: {snapshot[key]}\n" not in text:
            raise ValueError(f"model snapshot binding differs: {key}")
    document = validate_model(yaml.safe_load(text))
    return {"status": "recorded" if role == "exported_input" else "computed_locally",
            "role": role, "format": "auto_ontology_native_yaml", "artifact": artifact,
            "sha256": digest, "text": text, "document": document,
            "source_commit": snapshot["commit_sha"], "source_fingerprint": snapshot["source_fingerprint"]}


def generated_model(code_map, database):
    document = build_model_document(code_map, database=database)
    raw = (header_comment(code_map, database) + yaml.safe_dump(document, sort_keys=False)).encode()
    return model_resource(raw, code_map.snapshot, role="generated_export", artifact=None)


def absent_models():
    return {name: {"status": "not_captured"} for name in
            ("submitted_import", "catalog_id_mapping", "compiled_model", "compiled_terms", "retrieved_context")}
