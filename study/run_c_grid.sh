#!/bin/sh
# Arm C: Auto Ontology's agent with the base model and with the semantics-layer model, three runs each,
# DeepSeek then Nemotron, variants interleaved so time-of-day effects fall on both (study/PROTOCOL.md).
# Usage: sh study/run_c_grid.sh OUT_ROOT UPSTREAM
set -u
cd "$(dirname "$0")/.."
OUT=$1; UP=$2
export UV_CACHE_DIR="$PWD/build/uv-cache"
for model in deepseek nemotron; do for rep in 1 2 3; do for variant in base semantics; do
  dir="$OUT/$model-$variant-$rep"
  [ -e "$dir/complete.json" ] && continue
  rm -rf "$dir"
  .venv/bin/python study/run_auto_ontology.py "$variant" "$model" "$dir" "$UP" --workers 3 > "$dir.log" 2>&1
  echo "$(date -u +%H:%M:%S) $dir exit $?"
  rm -rf "$dir/run/.pgdata"
done; done; done
echo "c grid done $(date -u +%H:%M:%S)"
