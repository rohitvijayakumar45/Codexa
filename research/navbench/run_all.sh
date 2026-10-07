#!/bin/bash
# Full confirmatory run under the frozen configuration (FREEZE.md).
# Usage: run_all.sh <python> <out_dir>
set -u
PY=$1
OUT=$2
cd "$(dirname "$0")"
mkdir -p "$OUT"
export CODEXA_DATA_DIR=/work/nb

jobs_list=()
for d in /work/nb/repos/fx-*-heldout-*; do
  n=$(basename "$d"); l=$(echo "$n" | cut -d- -f2)
  jobs_list+=("$n $l fixture")
done
for r in more-itertools toolz marshmallow itsdangerous jinja attrs rich httpx boltons; do jobs_list+=("$r py natural"); done
for r in immer ky superstruct neverthrow ts-pattern commander.js redux dayjs; do jobs_list+=("$r ts natural"); done

printf '%s\n' "${jobs_list[@]}" | xargs -P 2 -L 1 bash -c 'timeout 7200 '"$PY"' -m nb.run "$0" "$1" "$2" '"$OUT"' >> '"$OUT"'/run.log 2>&1 || echo "FAILED $0" >> '"$OUT"'/run.log'
echo ALLDONE >> "$OUT/run.log"
