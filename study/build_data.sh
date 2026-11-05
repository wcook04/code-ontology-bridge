#!/bin/sh
# Build the code map, DuckDB file, base model and semantic-layer model for each pinned repository.
# Usage: sh study/build_data.sh CLONES_DIR    (CLONES_DIR holds a checkout per entry in study/repos.json)
set -eu
CLONES="$1"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
for name in $(uv run python -c "import json;print(' '.join(r['name'] for r in json.load(open('study/repos.json'))))"); do
  url=$(uv run python -c "import json;print([r['url'] for r in json.load(open('study/repos.json')) if r['name']=='$name'][0])")
  sha=$(uv run python -c "import json;print([r['commit'] for r in json.load(open('study/repos.json')) if r['name']=='$name'][0])")
  src="$CLONES/$name"
  [ "$(git -C "$src" rev-parse HEAD)" = "$sha" ] || { echo "$src is not at $sha" >&2; exit 2; }
  out="study/data/$name"; mkdir -p "$out"
  SOURCE_DATE_EPOCH="$(git -C "$src" log -1 --format=%ct HEAD)"; export SOURCE_DATE_EPOCH
  db="${name}_code"
  uv run cob build "$src" --repo-url "$url" --commit-sha "$sha" --out "$out/codemap.json" --summary "$out/summary.json"
  uv run cob export-duckdb --codemap "$out/codemap.json" --out "$out/$db.duckdb"
  uv run cob export-model --codemap "$out/codemap.json" --out "$out/base.model.yaml" --database "$db"
  uv run cob semantics --duckdb "$out/$db.duckdb" --model "$out/base.model.yaml" --out-model "$out/semantic.model.yaml"
done
