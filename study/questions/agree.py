"""Compare each author's reference rows with the independent annotator's rows, question by question.

usage: python study/questions/agree.py REPO   (reads build/study/authoring/REPO.draft.json and REPO.annot.json)
"""
import json
import sys
from collections import Counter
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
repo = sys.argv[1]
auth = ROOT / "build/study/authoring"
draft = {q["id"]: q for q in json.loads((auth / f"{repo}.draft.json").read_text())}
annot = {a["id"]: a for a in json.loads((auth / f"{repo}.annot.json").read_text())}
con = duckdb.connect(str(ROOT / "build/study/base" / f"{repo}_code.duckdb"), read_only=True)


def rows(sql):
    def norm(v):
        return round(float(v), 6) if isinstance(v, (int, float)) and not isinstance(v, bool) else v
    return [tuple(map(norm, r)) for r in con.execute(sql).fetchall()]


out = []
for qid, q in draft.items():
    a = annot.get(qid)
    ref = rows(q["reference_sql"])
    try:
        got = rows(a["sql"]) if a else None
    except duckdb.Error as e:
        got = f"error: {e}"
    same = isinstance(got, list) and (got == ref if q["ordered"] else Counter(got) == Counter(ref))
    out.append({"id": qid, "agree": same, "reference_rows": len(ref), "annotator_rows": len(got) if isinstance(got, list) else got,
                "flagged": [x["issue"] for x in (a or {}).get("ambiguities", [])]})
    print(f"{qid}: {'AGREE' if same else 'DISAGREE'} ref={len(ref)} annot={len(got) if isinstance(got, list) else got} flags={len((a or {}).get('ambiguities', []))}")
(auth / f"{repo}.agreement.json").write_text(json.dumps(out, indent=2))
