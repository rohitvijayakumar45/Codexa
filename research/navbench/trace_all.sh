#!/bin/bash
# Layer C: trace every confirmatory Python repository's test suite within a fixed budget.
# Usage: trace_all.sh <python>   (plain-run budget 300 s, traced budget 900 s per repository)
set -u
PY=$1
cd "$(dirname "$0")"
export CODEXA_DATA_DIR=/work/nb
for r in more-itertools toolz marshmallow itsdangerous jinja attrs rich httpx boltons; do
  timeout 1800 "$PY" -m nb.trace_repo "$r" 300 900 >> /work/nb/traces/trace_all.log 2>&1 || echo "FAILED $r" >> /work/nb/traces/trace_all.log
done
echo ALLDONE >> /work/nb/traces/trace_all.log
