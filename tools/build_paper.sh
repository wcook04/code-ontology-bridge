#!/bin/sh
# Requires Python 3, Pandoc and Tectonic. Run from any directory.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$ROOT/tools/build_paper.py"
