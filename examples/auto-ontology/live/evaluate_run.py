"""Score one complete run by named, typed output columns; never rewrite responses."""
from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import re
import sys

from ask_questions import _gold_rows, _rows_from_payload


def value_key(value, kind):
    if kind == 'string':
        if not isinstance(value, str):
            raise ValueError('expected string')
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('expected numeric value')
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError('non-finite number')
    if kind == 'integer' and number != number.to_integral_value():
        raise ValueError('expected integer')
    return number


def score_record(record, reference, contract):
    event = next((e for e in record.get('events', []) if e.get('type') == 'result'), None)
    answer = (event or {}).get('answer') or {}
    rows = _rows_from_payload(answer.get('sql_response_from_db'))
    fields = contract['fields']
    names = [f['name'] for f in fields]
    schema = all(set(row) == set(names) for row in rows)
    issues = []
    got = []
    try:
        for row in rows:
            got.append(tuple(value_key(row[f['name']], f['type']) for f in fields))
    except (KeyError, ValueError) as error:
        schema = False
        issues.append(str(error))
    want = [tuple(value_key(v, f['type']) for v, f in zip(row, fields, strict=True))
            for row in _gold_rows(reference)]
    def equal(left, right):
        return all(abs(a - b) <= Decimal('0.000001') if f['type'] == 'number' else a == b
                   for a, b, f in zip(left, right, fields, strict=True))

    # Perfect bipartite matching preserves duplicate multiplicity under tolerance.
    # Greedy matching can reject overlapping numeric neighborhoods incorrectly.
    assigned = {}

    def match(index, seen):
        for target, row in enumerate(want):
            if target not in seen and equal(got[index], row):
                seen.add(target)
                if target not in assigned or match(assigned[target], seen):
                    assigned[target] = index
                    return True
        return False

    values = schema and len(got) == len(want) and all(match(i, set()) for i in range(len(got)))
    order = values and (not contract.get('ordered') or all(equal(a, b) for a, b in zip(got, want)))
    prose = answer.get('response')
    prose_valid = isinstance(prose, str) and bool(prose.strip()) and not re.search(
        r'\b(PLACEHOLDER|TODO|TBD)\b|I[’\']?m sorry,? but I (?:can[’\']?t|cannot) help', prose, re.I)
    prose_valid = prose_valid and not re.fullmatch(r"\s*(test|n/a)\s*[.!]?\s*", prose or "", re.I)
    completed = event is not None and record.get('status') == 200 and not record.get('error')
    return {'question_id': int(reference['question_id']), 'completed': completed,
            'schema_complete': schema, 'values_match': values, 'order_matches': order,
            'prose_present': prose_valid, 'strict_rows_pass': bool(completed and order),
            'pass': bool(completed and order and prose_valid),
            'agent_rows': len(rows), 'reference_rows': len(want), 'issues': issues}


def evaluate(directory, evaluation, contracts):
    references = {int(q['question_id']): q for q in json.loads(evaluation.read_text())}
    policy = json.loads(contracts.read_text())
    results = []
    for qid, reference in references.items():
        path = directory / f'ask_q{qid}.json'
        if not path.exists():
            results.append({'question_id': qid, 'pass': False, 'strict_rows_pass': False,
                            'issues': ['missing response']})
        else:
            results.append(score_record(json.loads(path.read_text()), reference, policy['questions'][str(qid)]))
    return {'protocol': policy['protocol'], 'questions': len(references),
            'strict_rows_pass': sum(r['strict_rows_pass'] for r in results),
            'pass': sum(r['pass'] for r in results), 'results': results,
            'prose_scope': 'Nonempty, non-placeholder and no generic unrelated refusal; semantic prose correctness requires manual review.'}


if __name__ == '__main__':
    directory, evaluation, contracts = map(Path, sys.argv[1:4])
    report = evaluate(directory, evaluation, contracts)
    (directory / 'strict_score.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
