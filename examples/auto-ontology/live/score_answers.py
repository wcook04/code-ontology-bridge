"""Score Auto Ontology's answers against our reference answers, two ways.

exact:      the same values, in the same column and row order, with no normalisation.
equivalent: the same rows after normalising each value. A symbol id
            ``path/to/file.py::Qualified.name`` and the bare ``Qualified.name`` count as the
            same value; strings compare case-insensitively; numbers compare after rounding to
            1 decimal place. Rows are compared as a multiset of value tuples, ignoring column
            names, column order and row order.
items:      not equivalent, but the same number of rows and each row's values are
            contained in the reference row at the same position: the right items in
            the right order with a value column (usually a count) left out.

Usage: python score_answers.py ASK_DIR EVALUATION_JSON
Prints a table and writes ASK_DIR/score.json.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ask_questions import _rows_from_payload  # noqa: E402


def _value(v: Any) -> Any:
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return round(float(v), 1)
    s = str(v).strip()
    try:
        return round(float(s), 1)
    except ValueError:
        pass
    if "::" in s:
        s = s.split("::", 1)[1]
    return s.lower()


def _canon(rows: list[Any]) -> Counter:
    """Rows may be dicts (agent answers) or lists of values (reference answers)."""
    return Counter(
        tuple(sorted(repr(_value(v)) for v in (row.values() if isinstance(row, dict) else row)))
        for row in rows
    )


def _subset_rows(got: list[dict[str, Any]], want: list[Any]) -> bool:
    """Same row count, and each agent row's values are contained in the reference row
    at the same position: the right items in the right order, with a value column
    (usually a count) left out."""
    if not got or len(got) != len(want):
        return False
    for g, w in zip(got, want):
        have = Counter(repr(_value(v)) for v in g.values())
        need = Counter(repr(_value(v)) for v in (w.values() if isinstance(w, dict) else w))
        if have - need:
            return False
    return True


def main() -> int:
    ask_dir, evaluation = Path(sys.argv[1]), Path(sys.argv[2])
    gold = {int(q["question_id"]): q for q in json.loads(evaluation.read_text(encoding="utf-8"))}
    out = []
    for path in sorted(ask_dir.glob("ask_q*.json"), key=lambda p: int(p.stem.removeprefix("ask_q"))):
        qid = int(path.stem.removeprefix("ask_q"))
        rec = json.loads(path.read_text(encoding="utf-8"))
        result = next((e["answer"] for e in rec.get("events", []) if e.get("type") == "result"), {})
        got = _rows_from_payload(result.get("sql_response_from_db"))
        want = json.loads(gold[qid]["answer_raw"])
        out.append(
            {
                "question_id": qid,
                "difficulty": gold[qid]["difficulty"],
                "seconds": rec.get("elapsed_s"),
                "agent_rows": len(got),
                "gold_rows": len(want),
                "exact": bool(got) and [list(r.values()) for r in got] == want,
                "equivalent": bool(got) and _canon(got) == _canon(want),
                "items_without_values": _subset_rows(got, want),
                "question": gold[qid]["question"],
            }
        )
    (ask_dir / "score.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    for r in out:
        verdict = "equivalent" if r["equivalent"] else "items, no values" if r["items_without_values"] else "wrong or empty"
        print(f"Q{r['question_id']:>2} {r['difficulty']:<11} {verdict:<17} exact={r['exact']!s:<5} rows {r['agent_rows']}/{r['gold_rows']} {r['seconds']}s")
    n = len(out)
    eq = sum(r["equivalent"] for r in out)
    items = sum(r["items_without_values"] and not r["equivalent"] for r in out)
    print(f"exact {sum(r['exact'] for r in out)}/{n}; equivalent {eq}/{n}; right items without a value column {items}/{n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
