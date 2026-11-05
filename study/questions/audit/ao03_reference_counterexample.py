"""Reproduce the ao-03 reference/question mismatch without external dependencies.

The supplied reference SQL uses standard SQL, so SQLite is sufficient to expose
the missing kind restrictions. This is an oracle counterexample, not a rerun of
the saved DuckDB study and not an estimate of the effect on its scores.
"""

import json
from pathlib import Path
import sqlite3

questions_file = Path(__file__).with_name("ao03-question.json")
question = json.loads(questions_file.read_text())

con = sqlite3.connect(":memory:")
con.execute("ATTACH DATABASE ':memory:' AS code")
con.executescript("""
CREATE TABLE code.files(file_id TEXT PRIMARY KEY, is_test BOOL);
CREATE TABLE code.symbols(symbol_id TEXT PRIMARY KEY, file_id TEXT, kind TEXT);
CREATE TABLE code.calls(caller_symbol_id TEXT, callee_symbol_id TEXT, call_kind TEXT);
""")
con.execute("INSERT INTO code.files VALUES ('example.py', false)")
target = "auto_ontology/utils/llm_invoke.py::invoke_with_structured_output"
symbols = [
    (target, "function"),
    ("middle_function", "function"),
    ("good_function", "function"),
    ("wrong_class_result", "class"),
    ("class_intermediate", "class"),
    ("function_via_class", "function"),
]
con.executemany("INSERT INTO code.symbols VALUES (?, 'example.py', ?)", symbols)
con.executemany("INSERT INTO code.calls VALUES (?, ?, 'direct')", [
    ("middle_function", target),
    ("good_function", "middle_function"),
    ("wrong_class_result", "middle_function"),
    ("class_intermediate", target),
    ("function_via_class", "class_intermediate"),
])

reference = question["reference_sql"]
corrected = reference.replace(
    "SELECT DISTINCT caller_symbol_id AS s FROM code.calls WHERE",
    "SELECT DISTINCT caller_symbol_id AS s FROM code.calls "
    "JOIN code.symbols ds ON ds.symbol_id = caller_symbol_id "
    "WHERE ds.kind IN ('function', 'method') AND",
).replace(
    "AND NOT f.is_test",
    "AND NOT f.is_test AND x.kind IN ('function', 'method')",
)

original_rows = con.execute(reference).fetchall()
corrected_rows = con.execute(corrected).fetchall()
assert original_rows == [("function_via_class",), ("good_function",), ("wrong_class_result",)]
assert corrected_rows == [("good_function",)]

print("Source: supplied ao03-question.json, copied from study/questions/questions.json")
print("Question requires both result and intermediate to be a function or method.")
print("Original reference:", original_rows)
print("Reference with the two required kind constraints:", corrected_rows)
print("Expected by the question: good_function only.")
print("The study fuzzer permits class symbols to be callers and callees.")
print("Saved-run score impact is not measured by this counterexample.")
