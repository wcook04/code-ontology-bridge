"""Copy our DuckDB file into a storage version Auto Ontology's DuckDB can read.

Our export runs under duckdb>=2.0.0 (our pyproject), which writes a storage
format that Auto Ontology's pinned duckdb 1.5.5 refuses ("version number 999,
but we can only read versions between 64 and 68"). This copies every schema,
table, view and constraint into a file written with STORAGE_VERSION 'v1.5.0'.
The file name is kept so `current_database()` stays `auto_ontology_code`.

Usage: python make_compat_duckdb.py SRC.duckdb OUT_DIR
Prints a JSON summary of what the copy holds.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb


def main() -> int:
    src = Path(sys.argv[1]).resolve()
    out_dir = Path(sys.argv[2]).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / src.name
    dst.unlink(missing_ok=True)
    con = duckdb.connect()
    con.execute(f"ATTACH '{src}' AS src (READ_ONLY)")
    con.execute(f"ATTACH '{dst}' AS dst (STORAGE_VERSION 'v1.5.0')")
    con.execute("COPY FROM DATABASE src TO dst")

    def q(sql: str) -> list:
        return con.execute(sql).fetchall()

    summary = {
        "source": str(src),
        "copy": str(dst),
        "writer_duckdb": duckdb.__version__,
        "storage_version": "v1.5.0",
        "tables": {db: q(f"select count(*) from duckdb_tables() where database_name='{db}'")[0][0] for db in ("src", "dst")},
        "views": {db: q(f"select count(*) from duckdb_views() where database_name='{db}' and not internal")[0][0] for db in ("src", "dst")},
        "pk_fk_constraints": {
            db: q(
                f"select count(*) from duckdb_constraints() where database_name='{db}' "
                "and constraint_type in ('PRIMARY KEY','FOREIGN KEY')"
            )[0][0]
            for db in ("src", "dst")
        },
    }
    con.close()
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
