#!/usr/bin/env bash
# Run NavBench / agentbench stages locally after setup_wsl.sh. Repositories are processed one at a time
# (parallel runs sharing a codebase-memory cache directory can hang).
#
#   bash research/navbench/local/run_local.sh frozen        # 17-repo confirmatory run + full analysis (~30 min)
#   bash research/navbench/local/run_local.sh v2            # all adapters, T1-T3, held-out + fresh fixtures (~2 h)
#   bash research/navbench/local/run_local.sh large         # large-repository extension (networkx, sqlalchemy, typeorm, nest)
#   bash research/navbench/local/run_local.sh retrace       # re-trace the Python test suites (layer C) instead of the released traces
#   bash research/navbench/local/run_local.sh selftest      # agentbench natural tasks: grader + navigation check, no model calls
#   bash research/navbench/local/run_local.sh agent MODEL [CONDITIONS] [REPS]
#                                                           # RQ4 agent study on tasks/natural_v1.json; keys from Codexa/.env
# Outputs go to /work/nb/out-<stage> (and /work/ab for agent runs); each stage prints where.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAVBENCH="$(cd "$HERE/.." && pwd)"
AB="$(cd "$NAVBENCH/../agentbench" && pwd)"
NB=/work/nb
PY="$NB/cxvenv/bin/python"
export CODEXA_DATA_DIR=$NB
cd "$NAVBENCH"

FIXTURES_HELDOUT=$(ls -d $NB/repos/fx-*-heldout-* | xargs -n1 basename)
FIXTURES_FRESH=$(ls -d $NB/repos/fx-*-fresh-* 2>/dev/null | xargs -n1 basename || true)
PY_REPOS="more-itertools toolz marshmallow itsdangerous jinja attrs rich httpx boltons"
TS_REPOS="immer ky superstruct neverthrow ts-pattern commander.js redux dayjs"

lang_of() { case "$1" in fx-py-*) echo py;; fx-ts-*) echo ts;; networkx|sqlalchemy) echo py;; typeorm|nest) echo ts;;
            *) [[ " $PY_REPOS click " == *" $1 "* ]] && echo py || echo ts;; esac; }
layer_of() { [[ "$1" == fx-* ]] && echo fixture || echo natural; }

run_repos() {  # run_repos OUT "extra nb.run args" repo...
  local out=$1 extra=$2; shift 2
  mkdir -p "$out"
  for r in "$@"; do
    if [[ -f "$out/$r.meta.json" ]] && grep -q '"finished"' "$out/$r.meta.json"; then continue; fi
    echo "[$(date +%T)] $r"
    timeout 10800 "$PY" -m nb.run "$r" "$(lang_of "$r")" "$(layer_of "$r")" "$out" $extra >> "$out/run.log" 2>&1 \
      || echo "FAILED $r (see $out/run.log)"
  done
}

stage=${1:-help}; shift || true
case "$stage" in
  frozen)
    OUT=$NB/out-main-local
    run_repos "$OUT" "" $FIXTURES_HELDOUT $PY_REPOS $TS_REPOS
    "$PY" -m nb.score "$OUT"
    "$PY" -m nb.analyze "$OUT/scored.jsonl" "$OUT/analysis"
    "$PY" -m nb.replicate_original "$OUT/scored.jsonl" "$OUT/analysis/original_method.json" >/dev/null
    "$PY" -m nb.figures "$OUT/scored.jsonl" "$OUT/figs"
    "$PY" -m nb.taxonomy "$OUT" >/dev/null
    "$PY" -m nb.robustness "$OUT" "$OUT/scored.jsonl" "$OUT/analysis" >/dev/null
    mkdir -p $NB/out-main-released && tar xzf results/main/raw_results.tar.gz -C $NB/out-main-released
    echo "--- reproduction of the released frozen run (expect identical facts except codebase-memory run-to-run noise"
    echo "    and G1 rows truncated at its output caps; see results/v2/RESULTS_V2.md)"
    "$PY" -m nb.equivalence $NB/out-main-released "$OUT" "$OUT/equivalence.json"
    echo "report: $OUT/analysis/report.md  robustness: $OUT/analysis/robustness.md"
    ;;
  v2)
    OUT=$NB/out-v2-local
    run_repos "$OUT" "--arms rg0,rg3,lsp,codexa,codexa2,cbm_cur,cbm_057 --tasks T1,T2,T3" \
      $FIXTURES_HELDOUT $FIXTURES_FRESH $PY_REPOS $TS_REPOS
    "$PY" -m nb.score "$OUT"
    "$PY" -m nb.leaderboard "$OUT/scored.jsonl" "$OUT/lb"
    "$PY" -m nb.policy "$OUT/scored.jsonl" "$OUT/policy" --layer A --token-key tok_msa_cl100k
    "$PY" -m nb.policy "$OUT/scored.jsonl" "$OUT/policy" --layer C --token-key tok_msa_cl100k
    echo "leaderboard: $OUT/lb/leaderboard.md  policies: $OUT/policy/"
    ;;
  large)
    OUT=$NB/out-large-local
    for r in networkx sqlalchemy; do
      [[ -f $NB/traces/$r.json ]] || "$PY" -m nb.trace_repo $r 300 900
    done
    run_repos "$OUT" "" networkx sqlalchemy typeorm nest
    "$PY" -m nb.score "$OUT"
    "$PY" -m nb.analyze "$OUT/scored.jsonl" "$OUT/analysis"
    echo "report: $OUT/analysis/report.md"
    ;;
  retrace)
    for r in $PY_REPOS ${@:-}; do "$PY" -m nb.trace_repo "$r" 300 900; done
    ;;
  selftest)
    cd "$AB"
    CODEXA_DATA_DIR=/work/ab "$PY" -m ab.natural selftest tasks/natural_v1.json tasks/natural_v1_validation.jsonl --n 40
    ;;
  agent)
    MODEL=${1:?usage: run_local.sh agent MODEL [CONDITIONS] [REPS]}
    COND=${2:-rg,lsp,codexa,codexa2,routed,cbm_cur}
    REPS=${3:-3}
    [[ -f "$NAVBENCH/../../.env" ]] || echo "WARNING: no Codexa/.env found; provider keys must be in the environment"
    cd "$AB"
    mkdir -p /work/ab
    CODEXA_DATA_DIR=/work/ab "$PY" -m ab.run --tasks-file tasks/natural_v1.json --n-tasks 40 --conditions "$COND" \
      --model "$MODEL" --reps "$REPS" --max-steps 40 --token-budget 200000 --min-interval 2 --out /work/ab/natural-run
    "$PY" -m ab.analyze /work/ab/natural-run/results.jsonl --out /work/ab/natural-run/report.md || true
    echo "results: /work/ab/natural-run/results.jsonl  report: /work/ab/natural-run/report.md"
    ;;
  *)
    sed -n 2,14p "$0"; exit 1;;
esac
