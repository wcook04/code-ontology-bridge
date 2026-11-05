"""The study scorer: evaluator versions, accepted readings and the incomplete-suite guard."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "study"))
import score  # noqa: E402


def test_frozen_evaluator_uses_the_committed_references():
    frozen = score.load_questions("frozen")
    committed = {q["id"]: q["reference_sql"] for q in json.loads((ROOT / "study/questions/questions.json").read_text())}
    assert {k: q["reference_sql"] for k, q in frozen.items()} == committed
    assert all(q["accepted_sql"] == [q["reference_sql"]] for q in frozen.values())


def test_corrected_evaluator_applies_every_correction_and_reading():
    doc = json.loads((ROOT / "study/questions/corrections.json").read_text())
    corrected = score.load_questions("corrected")
    frozen = score.load_questions("frozen")
    for c in doc["corrections"]:
        assert c["frozen_reference_sql"] == frozen[c["id"]]["reference_sql"]
        assert corrected[c["id"]]["reference_sql"] == c["reference_sql"] != c["frozen_reference_sql"]
    for r in doc["accepted_readings"]:
        assert corrected[r["id"]]["accepted_sql"][1:] == r["accepted_sql"]
    changed = {c["id"] for c in doc["corrections"]}
    assert all(corrected[k]["reference_sql"] == q["reference_sql"] for k, q in frozen.items() if k not in changed)


def test_suite_scoring_refuses_missing_counterfactual_databases(tmp_path):
    with pytest.raises(SystemExit, match="expected 8"):
        score.databases("click", tmp_path)


def test_rows_match_is_a_typed_multiset_comparison():
    fields = [{"name": "symbol_id", "type": "string"}, {"name": "n", "type": "integer"}]
    want = [("a", 1), ("b", 2)]
    assert score.rows_match([{"symbol_id": "b", "n": 2}, {"symbol_id": "a", "n": 1}], want, fields, ordered=False)
    assert not score.rows_match([{"symbol_id": "b", "n": 2}, {"symbol_id": "a", "n": 1}], want, fields, ordered=True)
    assert not score.rows_match([{"symbol_id": "a", "n": 1}], want, fields, ordered=False)
    assert not score.rows_match([{"symbol_id": "a", "n": "1"}, {"symbol_id": "b", "n": 2}], want, fields, ordered=False)
