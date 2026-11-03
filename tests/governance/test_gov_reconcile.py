from __future__ import annotations

import json
from pathlib import Path

from code_ontology_bridge.governance.examples import build_worked_example
from code_ontology_bridge.governance.reconcile import reconcile


def d(source, name, definition="", aliases=(), cid=None):
    out = {"source": source, "name": name, "aliases": list(aliases), "definition": definition}
    if cid:
        out["canonical_id"] = cid
    return out


def steps(result):
    return {t["id"]: [x["resolution"]["step"] for x in t["definitions"]] for t in result["terms"]}


def test_fixed_order_each_step():
    defs = [
        d("a", "Revenue", "gross", aliases=["turnover"], cid="rev"),
        d("b", "revenue", "net"),  # canonical name (case/space-insensitive)
        d("c", "turnover", "sales"),  # unique alias
        d("e", "gm", "gross margin"),  # declared resolution
    ]
    res = {"gm": {"resolved_to": "gross_margin", "reason": "abbreviation", "decided_by": "owner"}}
    out = reconcile(defs, res)
    assert steps(out) == {"gross_margin": ["declared_resolution"], "rev": ["canonical_id", "canonical_name", "unique_alias"]}
    assert out["ambiguous"] == [] and out["new_terms"] == []
    rev = next(t for t in out["terms"] if t["id"] == "rev")
    assert rev["name"] == "Revenue" and rev["definitions_differ"] is True
    assert rev["renames"] == []


def test_canonical_name_outranks_declared_resolution():
    defs = [d("a", "revenue", cid="rev"), d("b", "revenue")]
    res = {"revenue": {"resolved_to": "other", "reason": "r", "decided_by": "x"}}
    assert steps(reconcile(defs, res)) == {"rev": ["canonical_id", "canonical_name"]}


def test_shared_name_without_rule_is_ambiguous_with_all_candidates():
    out = reconcile([d("a", "revenue", "gross"), d("b", "revenue", "net"), d("c", "orders", "x")])
    assert out["terms"] == []
    assert [n["proposed_id"] for n in out["new_terms"]] == ["c:orders"]
    amb = out["ambiguous"][0]
    assert amb["name"] == "revenue" and amb["definitions_identical"] is False
    assert [c["source"] for c in amb["candidates"]] == ["a", "b"]


def test_colliding_canonical_names_fall_to_declared_then_ambiguous():
    defs = [d("code", "utils", cid="a/utils.py"), d("code", "utils", cid="b/utils.py"), d("docs", "utils")]
    out = reconcile(defs)
    assert out["ambiguous"][0]["candidates"] == [
        {"kind": "canonical_term", "term_id": "a/utils.py"},
        {"kind": "canonical_term", "term_id": "b/utils.py"},
    ]
    assert out["name_collisions"][0]["term_ids"] == ["a/utils.py", "b/utils.py"]
    fixed = reconcile(defs, {"docs:utils": {"resolved_to": "b/utils.py", "reason": "docs page is in b", "decided_by": "w"}})
    assert fixed["ambiguous"] == []
    assert steps(fixed)["b/utils.py"] == ["canonical_id", "declared_resolution"]


def test_resolutions_without_reason_are_rejected_not_used():
    out = reconcile([d("a", "x"), d("b", "x")], {"x": {"resolved_to": "t"}})
    assert out["rejected_resolutions"] == [{"key": "x", "missing": ["reason", "decided_by"]}]
    assert out["ambiguous"]


def test_names_change_only_by_declaration_and_are_recorded():
    defs = [d("sales", "revenue", "gross"), d("ledger", "revenue", "net")]
    res = {
        "sales:revenue": {"resolved_to": "gross", "name": "gross revenue", "reason": "r1", "decided_by": "o"},
        "ledger:revenue": {"resolved_to": "net", "reason": "r2", "decided_by": "o"},
    }
    out = reconcile(defs, res)
    by_id = {t["id"]: t for t in out["terms"]}
    assert by_id["gross"]["name"] == "gross revenue"
    assert by_id["gross"]["renames"][0] == {"from": "revenue", "to": "gross revenue", "declared_by_key": "sales:revenue", "reason": "r1", "decided_by": "o"}
    assert "revenue" in by_id["gross"]["aliases"]
    assert by_id["net"]["name"] == "revenue" and by_id["net"]["renames"] == []


def test_result_does_not_depend_on_input_order():
    defs = [d("a", "Revenue", aliases=["turnover"], cid="rev"), d("b", "turnover"), d("c", "x"), d("d", "x")]
    def shape(result):
        return (
            {t["id"]: sorted(x["resolution"]["step"] for x in t["definitions"]) for t in result["terms"]},
            sorted(a["name"] for a in result["ambiguous"]),
            sorted(n["proposed_id"] for n in result["new_terms"]),
        )

    assert shape(reconcile(defs)) == shape(reconcile(list(reversed(defs))))


def test_worked_example_file_is_current():
    path = Path(build_worked_example.__file__).parent / "worked_example.json"
    assert json.loads(path.read_text()) == build_worked_example.build()
    built = build_worked_example.build()
    assert built["revenue_without_resolutions"]["ambiguous"]
    assert {t["id"] for t in built["revenue_with_resolutions"]["terms"]} == {"gross_order_revenue", "recognised_revenue"}
    assert built["code_modules"]["ambiguous"][0]["name"] == "utils"
