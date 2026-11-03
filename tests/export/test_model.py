import yaml

from code_ontology_bridge.codemap.schema import TABLES, VIEWS

from .conftest import PINNED_SHA, needs_clone


@needs_clone
def test_yaml_validates_against_their_pydantic_models(worked_example, their_schemas):
    text = worked_example.model.read_text()
    payload = yaml.safe_load(text)
    # Their import routes a document to the native reader only when a root key matches.
    assert set(payload) & set(their_schemas.AutoOntologyModelDocument.model_fields)
    document = their_schemas.AutoOntologyModelDocument.model_validate(payload)
    # Nothing we wrote is silently dropped by their models (extra keys would be ignored).
    assert document.model_dump(mode="json") == payload
    their_schemas.ImportRequest(replace=False)

    schema = document.data_layer.databases[0].schemas[0]
    assert schema.name == "code" and schema.database_name == "auto_ontology_code"
    assert {t.name for t in schema.tables} == {t.name for t in TABLES} | {v.name for v in VIEWS}
    files = next(t for t in schema.tables if t.name == "files")
    assert files.pk == ["cob:auto_ontology_code:column:code.files.file_id"]
    assert len(document.data_layer.foreign_keys) == sum(len(t.foreign_keys) for t in TABLES)
    assert {t.name for t in document.semantic_layer.terms} >= {"Source file", "Code symbol", "Call site"}
    assert len(document.semantic_layer.custom_analyses) >= 4


@needs_clone
def test_every_id_is_ours_unique_and_every_reference_resolves(worked_example):
    doc = yaml.safe_load(worked_example.model.read_text())
    ids = []

    def walk(node):
        if isinstance(node, dict):
            if "id" in node:
                ids.append(node["id"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(doc)
    assert ids and all(i.startswith("cob:auto_ontology_code:") for i in ids)
    assert len(ids) == len(set(ids))
    known = set(ids)
    for fk in doc["data_layer"]["foreign_keys"]:
        assert fk["source_column_id"] in known and fk["target_column_id"] in known
    for term in doc["semantic_layer"]["terms"]:
        assert set(term["represents"]) <= known
        for attr in term["columns_attributes"]:
            assert attr["column_id"] in known
    for sfk in doc["semantic_layer"]["semantic_fks"]:
        assert sfk["column_attribute_id"] in known and sfk["column_id"] in known


@needs_clone
def test_header_carries_snapshot_identity(worked_example):
    text = worked_example.model.read_text()
    assert f"commit_sha: {PINNED_SHA}" in text
    assert f"source_fingerprint: {worked_example.code_map.snapshot['source_fingerprint']}" in text
    assert "known_limits:" in text and "source: code_registry" in text
