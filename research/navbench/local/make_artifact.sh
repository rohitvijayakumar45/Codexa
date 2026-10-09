#!/usr/bin/env bash
# Build the anonymous review artifact for the FORGE submission as a standalone directory (and tarball).
# Contents:
#   - the NavBench harness and released results;
#   - the agentbench harness and tasks;
#   - G1's source (the evaluated prototype: backend/ + pyproject.toml), needed to reproduce its rows;
#   - setup and run scripts.
# Left out: paper drafts and reviews, personal setup notes, and the rest of the product repository.
#
# Usage: bash research/navbench/local/make_artifact.sh [OUT_DIR]   (default: ../navbench-artifact)
# Then push OUT_DIR to a new GitHub repository and anonymize it at https://anonymous.4open.science
# (terms to mask: see paper/forge/SUBMISSION_CHECKLIST.md).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODEXA="$(cd "$HERE/../../.." && pwd)"
OUT="${1:-$CODEXA/../navbench-artifact}"
rm -rf "$OUT"
mkdir -p "$OUT/research"

copy() {  # copy SRC_DIR (relative to the Codexa root) into OUT, excluding patterns
  local src=$1; shift
  local ex=(--exclude=node_modules --exclude=__pycache__ --exclude='*.pyc')
  for e in "$@"; do ex+=(--exclude="$e"); done
  tar -C "$CODEXA" -cf - "${ex[@]}" "$src" | tar -C "$OUT" -xf -
}
copy research/navbench 'research/navbench/paper' 'research/navbench/local/LOCAL_SETUP.md'
copy research/agentbench 'research/agentbench/PILOT_RQ4.md'
copy backend
cp "$CODEXA/pyproject.toml" "$OUT/"
mkdir -p "$OUT/tests"
cp "$CODEXA"/tests/test_agentbench*.py "$CODEXA"/tests/test_navbench_features.py "$OUT/tests/" 2>/dev/null || true

cat > "$OUT/README.md" <<'EOF'
# NavBench — artifact for "What Does 'N× Fewer Tokens' Measure?"

`G1` in the paper is the prototype in `backend/` (evaluated as frozen; see `research/navbench/FREEZE.md`).

- **Reproduce:**
  - on Ubuntu 24.04 or WSL2, run `bash research/navbench/local/setup_wsl.sh`, then
    `bash research/navbench/local/run_local.sh frozen`;
  - details: `research/navbench/REPRODUCE.md`.
- **Re-analyse without re-running:**
  - `research/navbench/results/main/scored.jsonl.gz` holds every scored row;
  - `nb.analyze`, `nb.robustness`, `nb.replicate_original` and `nb.figures` regenerate every number and figure.
- **Protocol:** `research/navbench/FREEZE.md` lists the frozen configuration and every post-freeze change, with
  before/after results.
- **Results:**
  - `results/main` (17 repositories, fixtures, traces);
  - `results/v2` (all adapters, T3, fresh split);
  - `results/large` (large-repository extension).
EOF
(cd "$(dirname "$OUT")" && tar czf "$(basename "$OUT").tar.gz" "$(basename "$OUT")")
du -sh "$OUT" "$OUT.tar.gz"
echo "artifact: $OUT"
