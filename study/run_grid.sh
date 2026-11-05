#!/bin/sh
# Arms A, B, V and S: every arm, model, repository and repetition, two runs at a time (study/PROTOCOL.md).
# Usage: sh study/run_grid.sh OUT_ROOT REPETITIONS
set -u
cd "$(dirname "$0")/.."
OUT=$1; REPS=$2
for rep in $(seq 1 "$REPS"); do for model in deepseek nemotron; do for arm in A B V S; do for repo in auto_ontology click httpx rich; do
  echo "$OUT/$model/$arm/$repo/r$rep $arm $repo $model"
done; done; done; done | xargs -P 2 -L 1 sh -c '[ -e "$0/complete.json" ] || { rm -rf "$0"; mkdir -p "$(dirname "$0")"; .venv/bin/python study/run_direct.py "$1" "$2" "$3" "$0" > /dev/null 2>"$0.err" && rm -f "$0.err"; echo "$(date -u +%H:%M:%S) $0"; }'
echo "grid done $(date -u +%H:%M:%S)"
