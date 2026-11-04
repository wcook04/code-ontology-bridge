"""Fixtures: the worked example (a clone of NVIDIA/auto-ontology) and loaders for their code.

Set ``AUTO_ONTOLOGY_CLONE`` to point at a clone; tests that need it are skipped
when it is absent.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

from code_ontology_bridge.codemap import build_code_map
from code_ontology_bridge.export import export_dataset, export_duckdb, export_model_yaml

REPO = Path(__file__).resolve().parents[2]
# Unset or empty: every test that needs Auto Ontology's code is skipped.
CLONE = Path(os.environ["AUTO_ONTOLOGY_CLONE"]) if os.environ.get("AUTO_ONTOLOGY_CLONE") else None
PINNED_SHA = "cdaf61e1bd0cf3820d11d72b43bb460816aebbd3"
NAME = "auto_ontology_code"
QUESTIONS = json.loads((REPO / "eval" / "auto_ontology_questions.json").read_text())
ANALYSES = json.loads((REPO / "eval" / "custom_analyses.json").read_text())
EXAMPLE = REPO / "examples" / "auto-ontology"
# The committed example is the recorded run's input and stays frozen; every way the
# current extractor's output differs from it is listed here (tools/record_extractor_corrections.py).
CORRECTIONS_PATH = EXAMPLE / NAME / "extractor-corrections.json"
CORRECTIONS = json.loads(CORRECTIONS_PATH.read_text()) if CORRECTIONS_PATH.is_file() else {"tables": {}, "evaluation_changes": {}, "summary_changes": {}}


def _clone_at_pin() -> bool:
    if CLONE is None or not (CLONE / "auto_ontology").is_dir():
        return False
    head = subprocess.run(["git", "-C", str(CLONE), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    return head == PINNED_SHA


needs_clone = pytest.mark.skipif(not _clone_at_pin(), reason=f"needs a clone of NVIDIA/auto-ontology at {PINNED_SHA}")


@pytest.fixture(scope="session")
def worked_example(tmp_path_factory):
    """Build the worked example and exercise optional named-analysis export."""
    if not _clone_at_pin():
        pytest.skip("no auto-ontology clone at the pinned commit")
    epoch = subprocess.run(["git", "-C", str(CLONE), "log", "-1", "--format=%ct", "HEAD"], capture_output=True, text=True).stdout.strip()
    old = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = epoch
    try:
        code_map = build_code_map(CLONE, repo_url="https://github.com/NVIDIA/auto-ontology", commit_sha=PINNED_SHA)
    finally:
        if old is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = old
    out = tmp_path_factory.mktemp("worked")
    db = export_duckdb(code_map, out / f"{NAME}.duckdb")
    dataset = export_dataset(code_map, out / NAME, duckdb_path=db, questions=QUESTIONS, analyses=ANALYSES)
    model = out / f"{NAME}.model.yaml"
    export_model_yaml(code_map, model, database=NAME, analyses=ANALYSES)
    return types.SimpleNamespace(code_map=code_map, duckdb=db, dataset=dataset, model=model, out=out)


def load_by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def their_schemas():
    """Their pydantic models, loaded by file path (the module imports only pydantic)."""
    path = CLONE / "auto_ontology" / "server" / "model_interchange" / "schemas.py" if CLONE else None
    if path is None or not path.is_file():
        pytest.skip("no auto-ontology clone")
    saved = sys.modules.get("_ao_model_interchange_schemas")
    module = load_by_path("_ao_model_interchange_schemas", path)
    yield module
    if saved is None:
        sys.modules.pop("_ao_model_interchange_schemas", None)


@pytest.fixture()
def their_duckdb_connector():
    """``auto_ontology.connectors.duckdb.DuckDBDatabase`` loaded by path.

    Only one import is stubbed: ``auto_ontology.utils.sql_identifiers`` (it
    needs sqlglot), used by ``SQLDatabase.qualified_name``, which these tests
    do not call. Package modules are bare namespaces so their ``__init__``
    files, which import every connector, are not executed.
    """
    base_path = CLONE / "auto_ontology" / "connectors" / "base.py" if CLONE else None
    if base_path is None or not base_path.is_file():
        pytest.skip("no auto-ontology clone")
    names = ["auto_ontology", "auto_ontology.connectors", "auto_ontology.utils", "auto_ontology.utils.sql_identifiers",
             "auto_ontology.connectors.base", "auto_ontology.connectors.duckdb"]
    saved = {n: sys.modules.get(n) for n in names}
    for pkg in names[:3]:
        module = types.ModuleType(pkg)
        module.__path__ = []
        sys.modules[pkg] = module
    stub = types.ModuleType("auto_ontology.utils.sql_identifiers")

    def qualified_name(*_a, **_k):  # pragma: no cover - not reached by these tests
        raise NotImplementedError("stub: needs sqlglot")

    stub.qualified_name = qualified_name
    sys.modules["auto_ontology.utils.sql_identifiers"] = stub
    try:
        load_by_path("auto_ontology.connectors.base", base_path)
        module = load_by_path("auto_ontology.connectors.duckdb", base_path.with_name("duckdb.py"))
        yield module.DuckDBDatabase
    finally:
        for n, m in saved.items():
            if m is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = m
