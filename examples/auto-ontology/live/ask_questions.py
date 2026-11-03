"""Ask Auto Ontology's agent our benchmark questions and compare its rows to our gold answers.

Calls `POST /api/chat/completions` (the route their MCP `ask_question` tool
streams from, mcp/auto_ontology_mcp/chat.py) on the internal FastAPI service,
parses the SSE stream the same way that tool does, and compares the returned
rows to the `answer_raw` rows recorded in our evaluation.json. Rows compare as
a multiset of value tuples (column names ignored, order ignored, floats to 6
places), the same rule as our `gold_sql_reproduces` check.

Usage: python ask_questions.py BASE_URL EVALUATION.json OUT_DIR QID [QID ...]
Writes OUT_DIR/ask_q<QID>.json per question and OUT_DIR/ask_summary.json.
Sends no credential: the model key lives only in the backend's environment.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _norm(v: Any) -> Any:
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return round(float(v), 6)
    return str(v)


def _key(rows: list[list[Any]]) -> list[tuple[str, ...]]:
    return sorted(tuple(json.dumps(_norm(x)) for x in r) for r in rows)


def _rows_from_payload(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list) and len(raw) == 1 and isinstance(raw[0], str):
        try:
            raw = json.loads(raw[0])
        except json.JSONDecodeError:
            return []
    if isinstance(raw, dict):
        raw = [raw]
    return [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []


def _gold_rows(item: dict[str, Any]) -> list[list[Any]]:
    raw = item.get("answer_raw")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = None
    if raw is None:
        raw = item.get("answer")
    if not isinstance(raw, list):
        return [[raw]]
    return [list(r) if isinstance(r, (list, tuple)) else [r] for r in raw]


def ask(base_url: str, question: str, evidence: str | None, timeout: float) -> dict[str, Any]:
    body: dict[str, Any] = {"question": question}
    if evidence:
        body["evidence"] = evidence
    if os.environ.get("AO_CALCULATION_ONLY") == "1":
        # Needs the patched Auto Ontology in upstream-fix/; skips their metadata route.
        body["calculation_only"] = True
    req = urllib.request.Request(
        base_url.rstrip("/") + "/api/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"content-type": "application/json", "accept": "text/event-stream"},
    )
    events: list[dict[str, Any]] = []
    status: int | None = None
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            for raw_line in resp:
                line = raw_line.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    ev = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if isinstance(ev, dict):
                    events.append(ev)
    except urllib.error.HTTPError as exc:
        status = exc.code
        events.append({"type": "http_error", "status": exc.code, "body": exc.read().decode("utf-8", "replace")[:2000]})
    except Exception as exc:  # timeouts, resets
        events.append({"type": "client_error", "message": f"{exc.__class__.__name__}: {exc}"})
    return {"request": body, "status": status, "elapsed_s": round(time.time() - started, 1), "events": events}


def main() -> int:
    base_url, evaluation, out_dir = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    qids = [int(q) for q in sys.argv[4:]]
    items = {int(i["question_id"]): i for i in json.loads(evaluation.read_text(encoding="utf-8"))}
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = []
    for qid in qids:
        item = items[qid]
        rec = ask(base_url, item["question"], item.get("evidence"), timeout=900)
        result = next((e for e in rec["events"] if e.get("type") == "result"), None)
        error = next((e for e in rec["events"] if e.get("type") in ("error", "http_error", "client_error")), None)
        answer = (result or {}).get("answer") or {}
        rows = _rows_from_payload(answer.get("sql_response_from_db") or answer.get("result"))
        got = [list(r.values()) for r in rows]
        gold = _gold_rows(item)
        correct = bool(result) and _key(got) == _key(gold)
        rec.update(
            {
                "question_id": qid,
                "gold_sql": item["SQL"],
                "gold_row_count": len(gold),
                "agent_sql": answer.get("sql_code"),
                "agent_answer": answer.get("response"),
                "agent_row_count": len(got),
                "correct_rows": correct,
                "error": error,
            }
        )
        (out_dir / f"ask_q{qid}.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
        line = {"question_id": qid, "status": rec["status"], "correct_rows": correct, "agent_rows": len(got), "gold_rows": len(gold), "error": (error or {}).get("message") or (error or {}).get("body")}
        summary.append(line)
        print(json.dumps(line, default=str))
    (out_dir / "ask_summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
