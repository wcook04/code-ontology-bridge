"""Regression checks for the public request contract and strict scoring."""
import importlib.util
from pathlib import Path
import sys

LIVE = Path(__file__).resolve().parents[1] / 'examples/auto-ontology/live'
sys.path.insert(0, str(LIVE))
from ask_questions import request_text
from evaluate_run import score_record


def record(rows, prose='Returned the requested rows.'):
    return {'status': 200, 'events': [{'type': 'result', 'answer': {
        'sql_response_from_db': rows, 'response': prose}}]}


def contract(ordered=False):
    return {'fields': [{'name': 'symbol_id', 'type': 'string'},
                       {'name': 'count', 'type': 'integer'}], 'ordered': ordered}


def test_request_excludes_gold_sql_and_values():
    item = {'question_id': 1, 'question': 'Which symbols?', 'SQL': 'GOLD_SQL_SECRET',
            'answer_raw': 'GOLD_VALUES_SECRET'}
    policy = {'instruction': 'Preserve IDs.', 'questions': {'1': contract()}}
    question = request_text(item, policy)
    assert 'symbol_id (string)' in question and 'count (integer)' in question
    assert 'GOLD_' not in question


def test_named_columns_full_ids_and_case_matter():
    gold = {'question_id': 1, 'answer_raw': '[["a.py::Thing", 2]]'}
    assert score_record(record([{'symbol_id': 'a.py::Thing', 'count': 2}]), gold, contract())['pass']
    for rows in ([{'symbol_id': 'Thing', 'count': 2}], [{'symbol_id': 'a.py::thing', 'count': 2}],
                 [{'symbol_id': 2, 'count': 'a.py::Thing'}], [{'symbol_id': 'a.py::Thing'}],
                 [{'symbol_id': 'a.py::Thing', 'count': '2'}]):
        assert not score_record(record(rows), gold, contract())['pass']


def test_empty_reference_duplicates_and_order():
    empty = {'question_id': 1, 'answer_raw': '[]'}
    assert score_record(record([]), empty, contract())['pass']
    gold = {'question_id': 1, 'answer_raw': '[["a",2],["b",1]]'}
    rows = [{'symbol_id': 'b', 'count': 1}, {'symbol_id': 'a', 'count': 2}]
    assert score_record(record(rows), gold, contract())['pass']
    assert not score_record(record(rows), gold, contract(True))['pass']
    assert not score_record(record(rows + rows), gold, contract())['pass']


def test_placeholder_is_separate_from_correct_rows():
    gold = {'question_id': 1, 'answer_raw': '[["a",2]]'}
    result = score_record(record([{'symbol_id': 'a', 'count': 2}], 'PLACEHOLDER'), gold, contract())
    assert result['strict_rows_pass'] and not result['pass']


def test_absolute_numeric_tolerance_and_multiplicity():
    policy = {'fields': [{'name': 'pct', 'type': 'number'}], 'ordered': False}
    gold = {'question_id': 1, 'answer_raw': '[[41.2]]'}
    assert score_record(record([{'pct': 41.2000007629}]), gold, policy)['pass']
    assert not score_record(record([{'pct': 41.200002}]), gold, policy)['pass']
    # One broad match must not consume the only neighbor of the next row.
    gold = {'question_id': 1, 'answer_raw': '[[1.000001], [1.0]]'}
    assert score_record(record([{'pct': 1.0}, {'pct': 1.000002}]), gold, policy)['pass']
    assert not score_record(record([{'pct': 1.0}]), gold, policy)['pass']


def test_correct_rows_with_unrelated_refusal_need_review():
    gold = {'question_id': 1, 'answer_raw': '[["a",2]]'}
    result = score_record(record([{'symbol_id': 'a', 'count': 2}], "I’m sorry, but I can’t help with that."), gold, contract())
    assert result['strict_rows_pass'] and not result['pass']
