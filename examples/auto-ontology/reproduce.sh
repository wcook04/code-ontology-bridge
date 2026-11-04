#!/bin/sh
# Rebuild every worked-example output from a clone of NVIDIA/auto-ontology.
# Usage: sh examples/auto-ontology/reproduce.sh /path/to/auto-ontology
#    or: AUTO_ONTOLOGY_CLONE=/path/to/auto-ontology sh examples/auto-ontology/reproduce.sh
# The committed example was built from commit cdaf61e1bd0cf3820d11d72b43bb460816aebbd3.
set -eu
CLONE="${1:-${AUTO_ONTOLOGY_CLONE:-}}"
if [ -z "$CLONE" ]; then
  echo "reproduce.sh: give the path to a clone of https://github.com/NVIDIA/auto-ontology" >&2
  echo "  as the first argument or in AUTO_ONTOLOGY_CLONE" >&2
  exit 2
fi
if [ ! -d "$CLONE/auto_ontology" ]; then
  echo "reproduce.sh: $CLONE is not an auto-ontology checkout (no auto_ontology/ directory)" >&2
  exit 2
fi
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
NAME=auto_ontology_code
SHA="$(git -C "$CLONE" rev-parse HEAD)"
# built_at is the commit time, so the CSV, JSON and YAML outputs are byte-identical across
# rebuilds; the DuckDB file holds identical rows but its bytes may differ.
SOURCE_DATE_EPOCH="$(git -C "$CLONE" log -1 --format=%ct HEAD)"
export SOURCE_DATE_EPOCH
cd "$REPO"
uv run cob build "$CLONE" --repo-url https://github.com/NVIDIA/auto-ontology --commit-sha "$SHA" \
  --out "$HERE/codemap.json" --summary "$HERE/summary.json"
uv run cob export-duckdb --codemap "$HERE/codemap.json" --out "$HERE/$NAME.duckdb"
uv run cob export-dataset --codemap "$HERE/codemap.json" --duckdb "$HERE/$NAME.duckdb" \
  --out "$HERE/$NAME" --questions eval/auto_ontology_questions.json --analyses eval/custom_analyses.json \
  --heldout eval/heldout_questions.json
uv run cob export-model --codemap "$HERE/codemap.json" --out "$HERE/$NAME.model.yaml" \
  --database "$NAME"
