#!/bin/sh
# Arm C-native: Auto Ontology with no imported model, three runs per model (protocol amendment).
# Usage: sh study/run_c_native.sh OUT_ROOT UPSTREAM
set -u
cd "$(dirname "$0")/.."
OUT=$1; UP=$2
export UV_CACHE_DIR="$PWD/build/uv-cache"
for model in deepseek nemotron; do for rep in 1 2 3; do
  dir="$OUT/$model-native-$rep"
  [ -e "$dir/complete.json" ] && continue
  rm -rf "$dir"
  .venv/bin/python study/run_auto_ontology.py native "$model" "$dir" "$UP" --workers 3 > "$dir.log" 2>&1
  echo "$(date -u +%H:%M:%S) $dir exit $?"
  rm -rf "$dir/run/.pgdata"
done; done
echo "c native done $(date -u +%H:%M:%S)"
