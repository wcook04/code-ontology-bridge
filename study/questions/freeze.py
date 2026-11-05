"""Apply the recorded rewordings and write the frozen question set study/questions/questions.json.

Copies each author's draft, annotation and agreement record into study/questions/authoring/ so
the full history of every question is published with it.
"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "build/study/authoring"
DST = ROOT / "study/questions/authoring"
REPOS = ["auto_ontology", "click", "httpx", "rich"]
edits = json.loads((ROOT / "study/questions/edits.json").read_text())
DST.mkdir(parents=True, exist_ok=True)
out = []
for repo in REPOS:
    for suffix in ("draft", "annot", "agreement"):
        shutil.copyfile(SRC / f"{repo}.{suffix}.json", DST / f"{repo}.{suffix}.json")
    for q in json.loads((SRC / f"{repo}.draft.json").read_text()):
        text = q["question"]
        e = edits.get(q["id"])
        if e:
            old, new = e["replace"]
            assert text.count(old) == 1, (q["id"], old)
            text = text.replace(old, new)
        out.append({"id": q["id"], "repo": repo, "question": text, "fields": q["fields"], "ordered": q["ordered"],
                    "reference_sql": q["reference_sql"], "difficulty": q["difficulty"], "topic": q["topic"],
                    "reworded": bool(e), "source_check": q["source_check"]})
missing = set(edits) - {q["id"] for q in out}
assert not missing, missing
(ROOT / "study/questions/questions.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
print(f"{len(out)} questions, {sum(q['reworded'] for q in out)} reworded")
