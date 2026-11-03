from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

MODULE_SRC = textwrap.dedent(
    '''
    """Load files and compute their fingerprints.

    Second paragraph with more detail.
    """


    def fingerprint(path):
        """Return the SHA-256 of one file."""
        return path


    def undocumented():
        return 1
    '''
).lstrip()


@pytest.fixture()
def src_root(tmp_path: Path) -> Path:
    root = tmp_path / "src"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "files.py").write_text(MODULE_SRC, encoding="utf-8")
    return root


@pytest.fixture()
def code_db(src_root: Path) -> Path:
    duckdb = pytest.importorskip("duckdb")
    db = src_root / "codemap.duckdb"
    con = duckdb.connect(str(db))
    con.execute("create schema code")
    con.execute(
        "create table code.files(file_id text primary key, package text, line_count integer, is_test boolean)"
    )
    con.execute(
        "insert into code.files values ('pkg/files.py','pkg',14,false),('pkg/other.py','pkg',3,false),('tests/test_files.py','tests',9,true)"
    )
    con.execute(
        "create table code.symbols(symbol_id text primary key, file_id text, name text, kind text, is_public boolean)"
    )
    con.execute(
        "insert into code.symbols values ('pkg/files.py::fingerprint','pkg/files.py','fingerprint','function',true),"
        "('pkg/files.py::undocumented','pkg/files.py','undocumented','function',true)"
    )
    con.execute(
        "create table code.snapshot(snapshot_id text, repo_url text, commit_sha text, built_at text, builder_version text,"
        " source_fingerprint text, file_count integer, omitted_file_count integer, known_limits text)"
    )
    con.execute(
        "insert into code.snapshot values ('snap1','https://example.invalid/repo','abc123','2026-11-03T00:00:00Z','0.1.0','f00d',3,0,'[]')"
    )
    con.close()
    evaluation = [
        {
            "question_id": "q1",
            "db_id": "code",
            "question": "How many test files are there?",
            "evidence": "",
            "SQL": "select count(*) from code.files where is_test",
            "difficulty": "simple",
            "answer_raw": "[[1]]",
            "answer": [[1]],
        },
        {
            "question_id": "q2",
            "db_id": "code",
            "question": "Which files are in package pkg?",
            "evidence": "",
            "SQL": "select file_id from code.files where package = 'pkg' order by file_id",
            "difficulty": "simple",
            "answer_raw": "",
            "answer": ["pkg/other.py", "pkg/files.py"],
        },
    ]
    (src_root / "evaluation.json").write_text(json.dumps(evaluation), encoding="utf-8")
    return db


MODEL_YAML = textwrap.dedent(
    """
    data_layer:
      databases:
        - id: db_code
          dialect: duckdb
          schemas:
            - id: sch_code
              name: code
              tables:
                - id: tbl_files
                  name: files
                  columns:
                    - {id: col_files_file_id, name: file_id}
                    - {id: col_files_package, name: package}
                    - {id: col_files_is_test, name: is_test}
                - id: tbl_symbols
                  name: symbols
                  columns:
                    - {id: col_symbols_symbol_id, name: symbol_id}
                    - {id: col_symbols_file_id, name: file_id}
                    - {id: col_symbols_name, name: name}
    semantic_layer:
      terms:
        - id: term_file
          name: source file
          description: Load files and compute their fingerprints.
          represents: [tbl_files]
          columns_attributes:
            - {id: ca_file_package, name: package, column_id: col_files_package}
        - id: term_symbol
          name: symbol
          description: ""
          represents: [tbl_symbols]
          columns_attributes:
            - {id: ca_symbol_name, name: symbol name, column_id: col_symbols_name}
        - id: term_unused
          name: unused
          represents: []
    """
).lstrip()


@pytest.fixture()
def model_yaml(tmp_path: Path) -> Path:
    pytest.importorskip("yaml")
    path = tmp_path / "model.yaml"
    path.write_text(MODEL_YAML, encoding="utf-8")
    return path
