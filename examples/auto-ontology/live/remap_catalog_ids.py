"""Rewrite the model YAML so its catalog ids are the live ids of an already ingested catalog.

G10 test helper. Auto Ontology's import resolves each YAML id against
`imported_id OR id` (dal/model_interchange.py). After catalog ingestion the
database, schema, table and column rows already exist with server UUIDs and
no imported_id, so our `cob:` ids match nothing, the import tries to insert,
and the unique name constraints fail. This replaces every catalog id (database,
schema, table, column) with the live id found by name in Postgres, everywhere it
appears (pk lists, foreign keys, column_id, represents, semantic FKs). Term,
attribute and analysis ids are left as `cob:` ids.

Usage: python remap_catalog_ids.py MODEL.yaml LIVE_IDS.json OUT.yaml
LIVE_IDS.json: {"database": {name: id}, "schema": {"db.schema": id},
                "table": {"schema.table": id}, "column": {"schema.table.column": id}}
Prints a JSON summary: how many ids were mapped and which were not found.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml


def main() -> int:
    model = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))
    live = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    mapping: dict[str, str] = {}
    missing: list[str] = []
    for db in model["data_layer"]["databases"]:
        for schema in db["schemas"]:
            db_name = schema["database_name"]
            if db["id"] not in mapping:
                if db_name in live["database"]:
                    mapping[db["id"]] = live["database"][db_name]
                else:
                    missing.append(db["id"])
            key = f"{db_name}.{schema['name']}"
            (mapping.__setitem__(schema["id"], live["schema"][key]) if key in live["schema"] else missing.append(schema["id"]))
            for table in schema["tables"]:
                tkey = f"{schema['name']}.{table['name']}"
                (mapping.__setitem__(table["id"], live["table"][tkey]) if tkey in live["table"] else missing.append(table["id"]))
                for col in table["columns"]:
                    ckey = f"{tkey}.{col['name']}"
                    (mapping.__setitem__(col["id"], live["column"][ckey]) if ckey in live["column"] else missing.append(col["id"]))

    replaced = 0

    def walk(node: object) -> object:
        nonlocal replaced
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, str) and node in mapping:
            replaced += 1
            return mapping[node]
        return node

    out = walk(model)
    Path(sys.argv[3]).write_text(yaml.safe_dump(out, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(json.dumps({"mapped_ids": len(mapping), "replaced_references": replaced, "missing": missing}, indent=2))
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
