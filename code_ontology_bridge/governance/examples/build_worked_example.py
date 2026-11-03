"""Regenerate ``worked_example.json`` from the inputs in this folder.

    python -m code_ontology_bridge.governance.examples.build_worked_example

The output puts our result next to what Auto Ontology's compiler does with the
same names, so the difference is visible without running their server.
"""

from __future__ import annotations

import json
from pathlib import Path

from code_ontology_bridge.governance.reconcile import load_json, reconcile

HERE = Path(__file__).parent

AUTO_ONTOLOGY_BEHAVIOUR = {
    "where": "auto_ontology/dal/terms.py:417 upsert_table_term (upstream cdaf61e)",
    "what_it_does": (
        "A compilation term owned by one table keeps its proposed name unless another "
        "table already owns that name; it then tries 'name (db.schema.table)' and "
        "'name (table_id)' and inserts the first free candidate. No reason is recorded "
        "and no one is asked which meaning an unqualified question refers to."
    ),
    "revenue_case": [
        "the first table compiled keeps the name 'revenue'",
        "the second becomes 'revenue (<db>.finance.ledger)' or 'revenue (<db>.sales.orders)', whichever compiled second",
        "which one keeps the bare name depends on compile order",
    ],
    "utils_case": (
        "Auto Ontology has no code ontology, so there is no direct counterpart; under the same rule "
        "the second 'utils' would be renamed after its location rather than reported."
    ),
}


def build() -> dict:
    revenue_defs = load_json(HERE / "revenue_definitions.json")["definitions"]
    code_defs = load_json(HERE / "code_utils_definitions.json")["definitions"]
    resolutions = load_json(HERE / "revenue_resolutions.json")
    return {
        "generated_by": "code_ontology_bridge.governance.examples.build_worked_example",
        "revenue_without_resolutions": reconcile(revenue_defs, {}),
        "revenue_with_resolutions": reconcile(revenue_defs, resolutions),
        "code_modules": reconcile(code_defs, {}),
        "auto_ontology_behaviour_for_contrast": AUTO_ONTOLOGY_BEHAVIOUR,
    }


def main() -> None:
    (HERE / "worked_example.json").write_text(json.dumps(build(), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
