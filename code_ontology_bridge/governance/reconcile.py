"""Reconcile several definitions of one term without silent renames.

Auto Ontology resolves a name clash by renaming: when another table already
owns a term name, ``upsert_table_term`` (``auto_ontology/dal/terms.py:417``)
tries ``name``, then ``name (db.schema.table)``, then ``name (table_id)``, and
keeps the first free one. Two meanings of "revenue" become two terms with
different names, and nobody is asked which "revenue" a question meant.

Here every definition is resolved in a fixed order, and a definition that the
order cannot place is returned as ``ambiguous`` with every candidate:

1. ``canonical_id`` on the definition;
2. canonical name: the definition's name equals the name of exactly one term
   that some definition declared with a ``canonical_id``;
3. declared resolution: an entry in the resolutions file keyed by
   ``source:name``, ``name``, ``source:alias`` or ``alias``, with
   ``resolved_to``, ``reason`` and ``decided_by``;
4. unique alias: the name or one alias matches the aliases of exactly one
   canonical term;
5. otherwise: a lone definition no other definition shares becomes a
   ``new_term`` proposal; several definitions sharing a name are ``ambiguous``.

A term's name changes only when a declared resolution supplies ``name``; the
change is recorded with its reason. Terms that still share a display name are
listed under ``name_collisions`` so an importer knows before Auto Ontology's
``(name, source)`` constraint renames one of them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _norm(text: str | None) -> str:
    return " ".join(str(text or "").lower().replace("_", " ").replace("-", " ").split())


def _validate_resolutions(raw: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    ok: dict[str, dict[str, Any]] = {}
    rejected: list[dict[str, Any]] = []
    for key, value in (raw or {}).items():
        missing = [k for k in ("resolved_to", "reason", "decided_by") if not (isinstance(value, dict) and value.get(k))]
        if missing:
            rejected.append({"key": key, "missing": missing})
            continue
        ok[_res_key(key)] = {**value, "key": key}
    return ok, rejected


def _res_key(key: str) -> str:
    if ":" in key:
        source, _, name = key.rpartition(":")
        return f"{source.strip()}:{_norm(name)}"
    return _norm(key)


def _lookup_resolution(defn: dict[str, Any], resolutions: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    source = str(defn.get("source", "")).strip()
    names = [defn.get("name")] + list(defn.get("aliases") or [])
    for name in names:
        for key in (f"{source}:{_norm(name)}", _norm(name)):
            if key in resolutions:
                return resolutions[key]
    return None


def reconcile(definitions: list[dict[str, Any]], resolutions: dict[str, Any] | None = None) -> dict[str, Any]:
    declared, rejected = _validate_resolutions(resolutions or {})

    # Canonical terms are those some definition names with a canonical_id.
    canonical: dict[str, dict[str, Any]] = {}
    for d in definitions:
        cid = d.get("canonical_id")
        if cid:
            entry = canonical.setdefault(cid, {"names": set(), "aliases": set()})
            entry["names"].add(_norm(d.get("name")))
            entry["aliases"].update(_norm(a) for a in d.get("aliases") or [])

    def by_name(name: str) -> list[str]:
        return sorted(cid for cid, e in canonical.items() if name in e["names"])

    def by_alias(names: list[str]) -> list[str]:
        return sorted({cid for cid, e in canonical.items() for n in names if n in e["aliases"]})

    placed: list[tuple[str, dict[str, Any], dict[str, Any]]] = []  # (term_id, defn, how)
    pending: list[tuple[dict[str, Any], list[str], str]] = []  # (defn, candidates, why)

    for d in definitions:
        name = _norm(d.get("name"))
        if d.get("canonical_id"):
            placed.append((d["canonical_id"], d, {"step": "canonical_id"}))
            continue
        name_hits = by_name(name)
        if len(name_hits) == 1:
            placed.append((name_hits[0], d, {"step": "canonical_name"}))
            continue
        res = _lookup_resolution(d, declared)
        if res is not None:
            placed.append(
                (
                    res["resolved_to"],
                    d,
                    {"step": "declared_resolution", "key": res["key"], "reason": res["reason"], "decided_by": res["decided_by"]},
                )
            )
            continue
        if name_hits:
            pending.append((d, name_hits, "name matches several canonical terms"))
            continue
        alias_hits = by_alias([name] + [_norm(a) for a in d.get("aliases") or []])
        if len(alias_hits) == 1:
            placed.append((alias_hits[0], d, {"step": "unique_alias"}))
            continue
        if alias_hits:
            pending.append((d, alias_hits, "aliases match several canonical terms"))
            continue
        pending.append((d, [], "no canonical candidate"))

    # Step 5: split what is left into lone proposals and shared-name ambiguity.
    ambiguous: list[dict[str, Any]] = []
    new_terms: list[dict[str, Any]] = []
    leftover_names: dict[str, list[dict[str, Any]]] = {}
    for d, cands, why in pending:
        if not cands:
            leftover_names.setdefault(_norm(d.get("name")), []).append(d)
    for d, cands, why in pending:
        name = _norm(d.get("name"))
        if cands:
            ambiguous.append(
                {
                    "name": d.get("name"),
                    "definition": _def_view(d),
                    "reason": why,
                    "candidates": [{"kind": "canonical_term", "term_id": c} for c in cands],
                }
            )
        elif len(leftover_names[name]) == 1:
            new_terms.append({"proposed_id": f"{d.get('source')}:{d.get('name')}", "definition": _def_view(d), "step": "sole_definition"})
    for name, group in sorted(leftover_names.items()):
        if len(group) > 1:
            texts = {_norm(g.get("definition")) for g in group}
            ambiguous.append(
                {
                    "name": group[0].get("name"),
                    "reason": f"{len(group)} definitions share this name and none is placed by canonical id, canonical name, declared resolution or alias",
                    "definitions_identical": len(texts) == 1,
                    "candidates": [{"kind": "definition", **_def_view(g)} for g in group],
                    "to_resolve": "add an entry keyed 'source:name' per definition to the resolutions file, with resolved_to, reason and decided_by",
                }
            )

    terms: dict[str, dict[str, Any]] = {}
    for term_id, d, how in placed:
        term = terms.setdefault(term_id, {"id": term_id, "name": None, "aliases": [], "definitions": [], "renames": []})
        term["definitions"].append({**_def_view(d), "resolution": how})
        for a in [d.get("name")] + list(d.get("aliases") or []):
            if a and a not in term["aliases"]:
                term["aliases"].append(a)
    for term_id, term in terms.items():
        canon_defs = [x for x in term["definitions"] if x["resolution"]["step"] == "canonical_id"]
        base = (canon_defs or term["definitions"])[0]["name"]
        declared_names = {
            (x["resolution"]["key"], declared[_res_key(x["resolution"]["key"])].get("name"))
            for x in term["definitions"]
            if x["resolution"]["step"] == "declared_resolution" and declared[_res_key(x["resolution"]["key"])].get("name")
        }
        term["name"] = base
        for key, new_name in sorted(declared_names):
            if new_name != term["name"]:
                res = declared[_res_key(key)]
                term["renames"].append(
                    {"from": term["name"], "to": new_name, "declared_by_key": key, "reason": res["reason"], "decided_by": res["decided_by"]}
                )
                term["name"] = new_name
        term["aliases"] = [a for a in term["aliases"] if a != term["name"]]
        term["definitions_differ"] = len({_norm(x["definition"]) for x in term["definitions"]}) > 1

    by_display: dict[str, list[str]] = {}
    for term in terms.values():
        by_display.setdefault(_norm(term["name"]), []).append(term["id"])
    collisions = [
        {
            "name": n,
            "term_ids": sorted(ids),
            "note": "Auto Ontology's (name, source) constraint would make its compiler rename one of these (dal/terms.py:417); declare a 'name' in the resolution to choose the names yourself",
        }
        for n, ids in sorted(by_display.items())
        if len(ids) > 1
    ]

    return {
        "terms": [terms[k] for k in sorted(terms)],
        "new_terms": new_terms,
        "ambiguous": ambiguous,
        "name_collisions": collisions,
        "rejected_resolutions": rejected,
        "order": ["canonical_id", "canonical_name", "declared_resolution", "unique_alias", "ambiguous"],
    }


def _def_view(d: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": d.get("source"),
        "name": d.get("name"),
        "definition": d.get("definition"),
        **({"canonical_id": d["canonical_id"]} if d.get("canonical_id") else {}),
    }


def load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))
