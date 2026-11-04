"""Certification history for Auto Ontology flags.

Auto Ontology stores certification as bare booleans (``term.name_certified``,
``term.description_certified``, ``column_attribute.certified``,
``sql_attribute.certified`` in ``auto_ontology/dal/schema.py``) and its own
skill says they are "not an atomic review/promotion system". This module keeps
the history those booleans lack:

- an append-only JSONL log of certification events (who, which check, what it
  returned, against which source fingerprint and commit, and what a revoke
  rolls back);
- pluggable checks, with two real ones for a code ontology;
- ``status``: current state recomputed from the events plus the files as they
  are now (certified / stale / failed / revoked / never);
- a planner that turns current state into requests for Auto Ontology's existing
  PATCH routes, sending them only on request.

A flag is only as strong as its receipt: the planner sets ``true`` only for a
target whose latest effective event is a passing check whose fingerprint still
matches the files.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import json
import os
import subprocess
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .fingerprint import compute_source_fingerprint, resolve

TOKEN_ENV = "AUTO_ONTOLOGY_API_TOKEN"

REQUIRED_EVENT_KEYS = (
    "event_id",
    "target_kind",
    "target_imported_id",
    "field",
    "decision",
    "actor",
    "check_id",
    "check_result",
    "source_fingerprint",
    "commit_sha",
    "at",
    "rollback_to_event_id",
)

# Which certification flags exist on which Auto Ontology entity
# (auto_ontology/dal/schema.py at cdaf61e: term 464-465, column_attribute 502,
# sql_attribute 607).
TARGET_FIELDS: dict[str, tuple[str, ...]] = {
    "term": ("name", "description"),
    "column_attribute": ("certified",),
    "sql_attribute": ("certified",),
}

STATES = ("certified", "stale", "failed", "revoked", "never")


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


@dataclass
class CheckOutcome:
    passed: bool
    detail: str
    source_paths: list[str] = field(default_factory=list)


CheckFn = Callable[[Path, dict[str, Any]], CheckOutcome]
CHECKS: dict[str, CheckFn] = {}


def register_check(check_id: str) -> Callable[[CheckFn], CheckFn]:
    """Register a check. Extra checks can live in any module loaded with
    ``load_check_module``; they receive the source root and the target's
    ``params`` and must name every file they read in ``source_paths``."""

    def wrap(fn: CheckFn) -> CheckFn:
        CHECKS[check_id] = fn
        return fn

    return wrap


def load_check_module(name: str) -> None:
    importlib.import_module(name)


def _normalise_ws(text: str) -> str:
    return " ".join(text.split())


def _docstring_for(tree: ast.Module, qualname: str | None) -> str | None:
    if not qualname:
        return ast.get_docstring(tree, clean=True)
    node: ast.AST = tree
    for part in qualname.split("."):
        body = getattr(node, "body", [])
        found = next(
            (
                child
                for child in body
                if isinstance(
                    child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                )
                and child.name == part
            ),
            None,
        )
        if found is None:
            return None
        node = found
    return ast.get_docstring(node, clean=True)  # type: ignore[arg-type]


@register_check("docstring_matches_description")
def check_docstring_matches_description(root: Path, params: dict[str, Any]) -> CheckOutcome:
    """The recorded description is verbatim text from the current docstring.

    params: ``path`` (repo-relative .py file), optional ``qualname`` (symbol;
    omit for the module docstring), ``description`` (the text being certified).
    Whitespace is normalised; anything else must match exactly. An empty
    description never passes: there is nothing to certify.
    """
    rel = str(params["path"])
    qualname = params.get("qualname")
    description = _normalise_ws(str(params.get("description") or ""))
    sources = [rel]
    if not description:
        return CheckOutcome(False, "empty description: nothing to certify", sources)
    try:
        tree = ast.parse(resolve(root, rel).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        return CheckOutcome(False, f"cannot parse {rel}: {exc.__class__.__name__}", sources)
    doc = _docstring_for(tree, qualname)
    where = f"{rel}::{qualname}" if qualname else rel
    if doc is None:
        return CheckOutcome(False, f"{where} has no docstring", sources)
    if description in _normalise_ws(doc):
        return CheckOutcome(True, f"description is verbatim from {where} docstring", sources)
    return CheckOutcome(False, f"description differs from current {where} docstring", sources)


def _norm_value(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 6)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _expected_rows(answer: Any, result_width: int) -> list[tuple[Any, ...]]:
    if not isinstance(answer, list):
        return [(answer,)]
    if all(isinstance(row, (list, tuple)) for row in answer):
        return [tuple(row) for row in answer]
    # A flat list is one column of many rows, or one row of many columns.
    return [(v,) for v in answer] if result_width == 1 else [tuple(answer)]


def _rows_key(rows: Iterable[Iterable[Any]]) -> list[tuple[str, ...]]:
    return sorted(tuple(json.dumps(_norm_value(v), sort_keys=True) for v in row) for row in rows)


def _recorded_answer(item: dict[str, Any]) -> Any:
    raw = item.get("answer_raw")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    elif isinstance(raw, list):
        return raw
    answer = item.get("answer")
    return answer if answer is not None else raw


@register_check("gold_sql_reproduces")
def check_gold_sql_reproduces(root: Path, params: dict[str, Any]) -> CheckOutcome:
    """Every gold SQL in an ontology-sql-eval ``evaluation.json`` still runs
    against the database and returns the recorded ``answer``.

    params: ``evaluation`` (path to evaluation.json), ``database`` (DuckDB
    file), optional ``question_ids`` to restrict the set. Rows compare as a
    multiset (order ignored), floats to 6 places. The recorded rows are
    ``answer_raw`` parsed as JSON (the dataset export writes the result rows
    there); ``answer``, a display string in that export, is used only when
    ``answer_raw`` is absent or is not JSON.
    """
    evaluation_rel = str(params["evaluation"])
    database_rel = str(params["database"])
    sources = [evaluation_rel, database_rel]
    try:
        import duckdb  # runtime dependency of the package
    except ImportError:
        return CheckOutcome(False, "duckdb is not installed", sources)
    try:
        items = json.loads(resolve(root, evaluation_rel).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return CheckOutcome(False, f"cannot read {evaluation_rel}: {exc.__class__.__name__}", sources)
    wanted = params.get("question_ids")
    if wanted is not None:
        wanted_set = {str(q) for q in wanted}
        items = [i for i in items if str(i.get("question_id")) in wanted_set]
    if not items:
        return CheckOutcome(False, "no gold questions selected", sources)
    failures: list[str] = []
    con = duckdb.connect(str(resolve(root, database_rel)), read_only=True)
    try:
        for item in items:
            qid = item.get("question_id")
            answer = _recorded_answer(item)
            try:
                cur = con.execute(item["SQL"])
                rows = cur.fetchall()
                width = len(cur.description or [])
            except Exception as exc:  # any engine error is a failed check
                failures.append(f"{qid}: error {exc.__class__.__name__}")
                continue
            if _rows_key(rows) != _rows_key(_expected_rows(answer, width)):
                failures.append(f"{qid}: answer differs")
    finally:
        con.close()
    if failures:
        return CheckOutcome(False, f"{len(failures)}/{len(items)} failed: " + "; ".join(failures), sources)
    return CheckOutcome(True, f"{len(items)}/{len(items)} gold queries reproduce", sources)


# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def git_commit_sha(root: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


class EventLog:
    """Append-only JSONL. Lines are never rewritten; a revoke is a new line."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events = []
        for n, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            event = json.loads(line)
            missing = [k for k in REQUIRED_EVENT_KEYS if k not in event]
            if missing:
                raise ValueError(f"{self.path}:{n}: event missing {missing}")
            events.append(event)
        return events

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        missing = [k for k in REQUIRED_EVENT_KEYS if k not in event]
        if missing:
            raise ValueError(f"event missing {missing}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return event


def _validate_target(target: dict[str, Any]) -> None:
    kind = target.get("target_kind")
    if kind not in TARGET_FIELDS:
        raise ValueError(f"target_kind must be one of {sorted(TARGET_FIELDS)}, got {kind!r}")
    if target.get("field") not in TARGET_FIELDS[kind]:
        raise ValueError(f"{kind} field must be one of {TARGET_FIELDS[kind]}, got {target.get('field')!r}")
    if not target.get("target_imported_id"):
        raise ValueError("target_imported_id is required")
    if kind == "column_attribute" and not target.get("parent_term_imported_id"):
        raise ValueError("column_attribute targets need parent_term_imported_id (the PATCH route is nested under the term)")


def certify(
    log: EventLog,
    target: dict[str, Any],
    *,
    root: Path,
    actor: str,
    commit_sha: str | None = None,
) -> dict[str, Any]:
    """Run the target's check and append the event, passed or failed.

    ``target``: ``{target_kind, target_imported_id, field, check_id, params,
    parent_term_imported_id?}``. A failed check is recorded too: a failed
    attempt displaces an earlier pass, because the current text did not pass.
    """
    _validate_target(target)
    if not actor:
        raise ValueError("actor is required")
    check_id = target["check_id"]
    if check_id not in CHECKS:
        raise KeyError(f"unknown check {check_id!r}; registered: {sorted(CHECKS)}")
    params = dict(target.get("params") or {})
    try:
        outcome = CHECKS[check_id](root, params)
    except Exception as exc:  # a crashing check is a failed check, never a pass
        outcome = CheckOutcome(False, f"check raised {exc.__class__.__name__}: {exc}", [])
    event = {
        "event_id": f"evt_{uuid.uuid4().hex}",
        "target_kind": target["target_kind"],
        "target_imported_id": target["target_imported_id"],
        "field": target["field"],
        "decision": "certify",
        "actor": actor,
        "check_id": check_id,
        "check_result": "passed" if outcome.passed else "failed",
        "source_fingerprint": compute_source_fingerprint(root, outcome.source_paths),
        "commit_sha": commit_sha if commit_sha is not None else git_commit_sha(root),
        "at": _now(),
        "rollback_to_event_id": None,
        # Extensions beyond the SPEC keys: what the fingerprint covers, why the
        # check said what it said, and the parent needed for nested routes.
        "source_paths": sorted(set(outcome.source_paths)),
        "check_detail": outcome.detail,
        "check_params": params,
        "parent_term_imported_id": target.get("parent_term_imported_id"),
    }
    return log.append(event)


def revoke(
    log: EventLog,
    event_id: str,
    *,
    actor: str,
    reason: str,
    commit_sha: str | None = None,
) -> dict[str, Any]:
    """Append a revoke reversing ``event_id``.

    ``event_id`` must be the target's current effective event. The target's
    state then falls back to whatever was effective before that event, so
    revoking a bad re-certification restores the earlier one (still subject to
    freshness); revoking the only certification leaves the target ``revoked``.
    """
    if not actor or not reason:
        raise ValueError("revoke needs an actor and a reason")
    events = log.read()
    prior = next((e for e in events if e["event_id"] == event_id), None)
    if prior is None or prior["decision"] != "certify":
        raise ValueError(f"{event_id} is not a certify event in {log.path}")
    key = _key(prior)
    stack = _effective_stacks(events).get(key, [])
    if not stack or stack[-1]["event_id"] != event_id:
        raise ValueError(f"{event_id} is not the current effective event for {key}; revoke that one first")
    event = {
        "event_id": f"evt_{uuid.uuid4().hex}",
        "target_kind": prior["target_kind"],
        "target_imported_id": prior["target_imported_id"],
        "field": prior["field"],
        "decision": "revoke",
        "actor": actor,
        "check_id": prior["check_id"],
        "check_result": "not_run",
        "source_fingerprint": prior["source_fingerprint"],
        "commit_sha": commit_sha if commit_sha is not None else prior.get("commit_sha"),
        "at": _now(),
        "rollback_to_event_id": event_id,
        "source_paths": prior.get("source_paths", []),
        "check_detail": reason,
        "parent_term_imported_id": prior.get("parent_term_imported_id"),
    }
    return log.append(event)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

Key = tuple[str, str, str]


def _key(event: dict[str, Any]) -> Key:
    return (event["target_kind"], event["target_imported_id"], event["field"])


def _effective_stacks(events: list[dict[str, Any]]) -> dict[Key, list[dict[str, Any]]]:
    stacks: dict[Key, list[dict[str, Any]]] = {}
    for event in events:
        stack = stacks.setdefault(_key(event), [])
        if event["decision"] == "certify":
            stack.append(event)
        elif event["decision"] == "revoke":
            target = event.get("rollback_to_event_id")
            if stack and stack[-1]["event_id"] == target:
                stack.pop()
            # A revoke naming anything else is ignored here and reported by
            # status() as an anomaly; it can never raise a target's state.
    return stacks


def status(events: list[dict[str, Any]], root: Path | None) -> list[dict[str, Any]]:
    """Current state per (kind, imported_id, field), recomputed from scratch.

    With ``root`` the stored fingerprint is compared against the files now;
    without it freshness is reported as ``unchecked`` and a passing target is
    not reported as certified.
    """
    stacks = _effective_stacks(events)
    revoked_keys = {_key(e) for e in events if e["decision"] == "revoke"}
    latest = {_key(e): e for e in events}
    anomalies: dict[Key, list[str]] = {}
    seen: dict[Key, list[str]] = {}
    for event in events:
        key = _key(event)
        if event["decision"] == "revoke" and event.get("rollback_to_event_id") not in seen.get(key, []):
            anomalies.setdefault(key, []).append(f"revoke {event['event_id']} names an unknown event")
        seen.setdefault(key, []).append(event["event_id"])

    rows = []
    for key in sorted(stacks):
        stack = stacks[key]
        row: dict[str, Any] = {
            "target_kind": key[0],
            "target_imported_id": key[1],
            "field": key[2],
            "event_count": len(seen.get(key, [])),
            "anomalies": anomalies.get(key, []),
        }
        if not stack:
            row["parent_term_imported_id"] = latest[key].get("parent_term_imported_id")
            row.update(state="revoked" if key in revoked_keys else "never", effective_event_id=None, freshness=None)
            rows.append(row)
            continue
        top = stack[-1]
        row["effective_event_id"] = top["event_id"]
        row["parent_term_imported_id"] = top.get("parent_term_imported_id")
        row["check_id"] = top["check_id"]
        row["check_detail"] = top.get("check_detail")
        row["certified_at"] = top["at"]
        row["actor"] = top["actor"]
        if top["check_result"] != "passed":
            row.update(state="failed", freshness=None)
        elif root is None:
            row.update(state="stale", freshness="unchecked")
        else:
            now = compute_source_fingerprint(root, top.get("source_paths", []))
            fresh = now == top["source_fingerprint"]
            row.update(
                state="certified" if fresh else "stale",
                freshness="current" if fresh else "changed",
                current_fingerprint=now,
                recorded_fingerprint=top["source_fingerprint"],
            )
        rows.append(row)
    return rows


def state_index(rows: list[dict[str, Any]]) -> dict[Key, dict[str, Any]]:
    return {(r["target_kind"], r["target_imported_id"], r["field"]): r for r in rows}


# ---------------------------------------------------------------------------
# PATCH planner
# ---------------------------------------------------------------------------

# Auto Ontology routes at cdaf61e (all mounted under /api by
# auto_ontology/server/__main__.py:102 and :110):
#   PATCH /api/terms/{term_id}                               TermUpdate
#       auto_ontology/server/terms/router.py:205, body model :34-39
#   PATCH /api/terms/{term_id}/column-attributes/{attr_id}  ColumnAttributeUpdate
#       auto_ontology/server/terms/router.py:116-119, body model :42-46
#   PATCH /api/sql-attributes/{attr_id}                      SqlAttributeMetadataPatch
#       auto_ontology/server/sql_attributes/router.py:193, body model :52-56
# Path ids are LIVE ids (uuid server default, dal/schema.py:105); the YAML id is
# stored separately as imported_id and is not returned by these routes.


def _route(kind: str, live: dict[str, str]) -> str:
    if kind == "term":
        return f"/api/terms/{live['term']}"
    if kind == "column_attribute":
        return f"/api/terms/{live['parent']}/column-attributes/{live['attr']}"
    return f"/api/sql-attributes/{live['attr']}"


def _body_key(kind: str, fld: str) -> str:
    if kind == "term":
        return f"{fld}_certified"
    return "certified"


def plan_patches(
    rows: list[dict[str, Any]],
    id_map: dict[str, str],
    *,
    unset_stale: bool = False,
) -> dict[str, Any]:
    """Requests that make Auto Ontology's flags match the receipts.

    - ``certified`` → ``true``.
    - ``revoked`` → ``false`` (an explicit decision by a named actor).
    - ``stale`` / ``failed`` → ``false`` only with ``unset_stale``; otherwise
      listed under ``withheld`` so a reviewer sees them.
    - ``never`` → nothing.

    ``id_map`` maps imported_id → live id. Unmapped ids leave a placeholder in
    the path and ``ready: false``; ``apply`` never sends those.
    """
    requests = []
    withheld = []
    for row in rows:
        state = row["state"]
        if state == "certified":
            value = True
        elif state == "revoked":
            value = False
        elif state in ("stale", "failed") and unset_stale:
            value = False
        else:
            if state in ("stale", "failed"):
                withheld.append({k: row.get(k) for k in ("target_kind", "target_imported_id", "field", "state", "check_detail")})
            continue
        kind, imported = row["target_kind"], row["target_imported_id"]

        def live(imported_id: str | None) -> str:
            if imported_id and imported_id in id_map:
                return id_map[imported_id]
            return f"{{live_id_of:{imported_id}}}"

        ids = {
            "term": live(imported),
            "attr": live(imported),
            "parent": live(row.get("parent_term_imported_id")),
        }
        path = _route(kind, ids)
        needed = [imported] + ([row.get("parent_term_imported_id")] if kind == "column_attribute" else [])
        requests.append(
            {
                "method": "PATCH",
                "path": path,
                "json": {_body_key(kind, row["field"]): value},
                "ready": all(i in id_map for i in needed),
                "target": {"target_kind": kind, "target_imported_id": imported, "field": row["field"]},
                "state": state,
                "because_event_id": row.get("effective_event_id"),
            }
        )
    return {"requests": requests, "withheld": withheld}


def apply_patches(
    plan: dict[str, Any],
    base_url: str,
    *,
    token: str | None = None,
    internal: bool = False,
    user_id: str | None = None,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    """Send ready requests. Through the public gateway the token comes from
    ``AUTO_ONTOLOGY_API_TOKEN`` unless passed; it goes only into the ``x-api-key``
    header (their documented ApiToken scheme) and never into a result or log line.

    ``internal=True`` targets the FastAPI service directly, which Auto Ontology
    treats as a trusted internal boundary and does not authenticate; no token is
    sent. ``user_id`` is forwarded as ``x-auto-ontology-user-id`` so their
    ``modified_by`` records the actor; it must be an existing Auto Ontology user."""
    headers = {"content-type": "application/json"}
    if internal:
        if user_id:
            headers["x-auto-ontology-user-id"] = user_id
    else:
        token = token if token is not None else os.environ.get(TOKEN_ENV)
        if not token:
            raise RuntimeError(f"set {TOKEN_ENV} to apply through the gateway, or pass internal=True; nothing was sent")
        headers["x-api-key"] = token
    results = []
    for req in plan["requests"]:
        if not req["ready"]:
            results.append({"path": req["path"], "sent": False, "reason": "unmapped live id"})
            continue
        http_req = urllib.request.Request(
            base_url.rstrip("/") + req["path"],
            data=json.dumps(req["json"]).encode("utf-8"),
            method="PATCH",
            headers=headers,
        )
        try:
            with urllib.request.urlopen(http_req, timeout=timeout) as resp:
                results.append({"path": req["path"], "sent": True, "status": resp.status})
        except urllib.error.HTTPError as exc:
            results.append({"path": req["path"], "sent": True, "status": exc.code})
        except urllib.error.URLError as exc:
            results.append({"path": req["path"], "sent": False, "reason": str(exc.reason)})
    return results


def load_targets(path: Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data["targets"]


def check_ids() -> list[str]:
    return sorted(CHECKS)


def describe_check(check_id: str) -> str:
    return inspect.getdoc(CHECKS[check_id]) or ""
