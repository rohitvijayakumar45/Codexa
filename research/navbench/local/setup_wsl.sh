#!/usr/bin/env bash
# One-command local setup for NavBench + agentbench on Ubuntu 24.04 (WSL2 on Windows, or native Linux).
# Reproduces the cloud environment the published results came from:
#   - Python 3.13, Node 22, ripgrep 14, gcc
#   - /work/nb as the data root
#   - pinned tool builds and corpus commits
#   - frozen package versions (local/envs/*.txt)
#
# Usage (from anywhere inside the Codexa checkout):
#   bash research/navbench/local/setup_wsl.sh            # everything (about 30–60 min, ~8 GB)
#   bash research/navbench/local/setup_wsl.sh --step corpus   # one step only
# Steps: system, data, tools, node, cbm, corpus, fixtures, venvs, traces, check
# Every step is idempotent: re-running skips what is already done.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAVBENCH="$(cd "$HERE/.." && pwd)"
CODEXA="$(cd "$NAVBENCH/../.." && pwd)"
NB=/work/nb
TOOLS_VENV="$NB/cxvenv"              # Python env for the harness + Codexa backend (name kept from the cloud run)
CBM_SRC="$NB/src/codebase-memory-mcp"
PY=${PYTHON:-python3.13}
ONLY=""
[[ "${1:-}" == "--step" ]] && ONLY="${2:?--step needs a name}"

log() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
want() { [[ -z "$ONLY" || "$ONLY" == "$1" ]]; }

# ------------------------------------------------------------------------------------------- system
if want system; then
  log "system packages (sudo)"
  if ! command -v $PY >/dev/null; then
    sudo apt-get update -y
    sudo apt-get install -y software-properties-common
    sudo add-apt-repository -y ppa:deadsnakes/ppa
  fi
  sudo apt-get update -y
  sudo apt-get install -y git curl ca-certificates build-essential zlib1g-dev ripgrep \
       python3.13 python3.13-venv python3.13-dev
  if ! command -v node >/dev/null || [[ "$(node -v)" != v22* ]]; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
    sudo apt-get install -y nodejs
  fi
  echo "python $($PY --version)  node $(node -v)  $(rg --version | head -1)  $(gcc --version | head -1)"
fi

# --------------------------------------------------------------------------------------------- data
if want data; then
  log "data root $NB"
  if [[ ! -d /work ]]; then sudo mkdir -p /work; fi
  sudo chown "$(id -u):$(id -g)" /work
  mkdir -p "$NB"/{repos,venvs,traces,bin,src}
fi

# -------------------------------------------------------------------------------------------- tools
if want tools; then
  log "harness + Codexa backend environment ($TOOLS_VENV)"
  [[ -x "$TOOLS_VENV/bin/python" ]] || $PY -m venv "$TOOLS_VENV"
  "$TOOLS_VENV/bin/python" -m pip install -q -U pip
  "$TOOLS_VENV/bin/python" -m pip install -q -r "$HERE/envs/codexa-tools.txt"
  "$TOOLS_VENV/bin/python" -m pip install -q -e "$CODEXA[dev]"
  "$TOOLS_VENV/bin/python" -m pip install -q python-dotenv litellm
fi

# --------------------------------------------------------------------------------------------- node
if want node; then
  log "pinned Node packages (pyright 1.1.414, typescript 5.9.3, gpt-tokenizer 4.0.0)"
  (cd "$NAVBENCH" && npm ci --no-audit --no-fund)
fi

# ---------------------------------------------------------------------------------------------- cbm
if want cbm; then
  log "codebase-memory-mcp builds: current bf93f0b7, v0.5.7, v0.5.5"
  [[ -d "$CBM_SRC/.git" ]] || git clone -q https://github.com/DeusData/codebase-memory-mcp "$CBM_SRC"
  for spec in "cur bf93f0b7" "057 v0.5.7" "055 v0.5.5"; do
    set -- $spec
    [[ -x "$NB/bin/cbm-$1" ]] && { echo "cbm-$1 present"; continue; }
    wt="$NB/src/cbm-$1"
    [[ -d "$wt" ]] || git -C "$CBM_SRC" worktree add -f "$wt" "$2" >/dev/null
    make -C "$wt" -f Makefile.cbm cbm CC=gcc CXX=g++ -j"$(nproc)" >"$NB/src/cbm-$1.build.log" 2>&1
    cp "$wt/build/c/codebase-memory-mcp" "$NB/bin/cbm-$1"
    echo "built cbm-$1"
  done
fi

# ------------------------------------------------------------------------------------------- corpus
if want corpus; then
  log "corpus at pinned commits (17 confirmatory + 3 pilot + 4 large)"
  "$TOOLS_VENV/bin/python" - "$NAVBENCH" "$NB" <<'PYEOF'
import json, subprocess, sys
from pathlib import Path
nav, nb = Path(sys.argv[1]), Path(sys.argv[2])
c = json.loads((nav / "corpus.json").read_text())
shas = dict(l.split() for l in (nav / "results" / "corpus_shas.txt").read_text().splitlines() if l.strip())
repos = [(r["name"], r["url"], shas[r["name"]]) for r in c["python"] + c["typescript"]]
large = c.get("large_extension", {})
repos += [(r["name"], r["url"], r["sha"]) for r in large.get("python", []) + large.get("typescript", [])]
for name, url, sha in repos:
    d = nb / "repos" / name
    if not (d / ".git").exists():
        subprocess.run(["git", "clone", "-q", "--filter=blob:none", url, str(d)], check=True)
    have = subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if have != sha:
        subprocess.run(["git", "-C", str(d), "fetch", "-q", "origin", sha], check=False)
        subprocess.run(["git", "-C", str(d), "checkout", "-q", "--detach", sha], check=True)
    (d / ".codexa-repo.json").write_text(json.dumps({"url": url}))
    print(f"{name:16s} {sha[:10]}")
PYEOF
fi

# ----------------------------------------------------------------------------------------- fixtures
if want fixtures; then
  log "fixtures (held-out, calibration, fresh) and the fixture gate"
  cd "$NAVBENCH"
  CODEXA_DATA_DIR=$NB "$TOOLS_VENV/bin/python" -m nb.fixtures "$NB/repos"
  CODEXA_DATA_DIR=$NB "$TOOLS_VENV/bin/python" -m nb.fixtures "$NB/repos" --fresh
  CODEXA_DATA_DIR=$NB "$TOOLS_VENV/bin/python" -m nb.gate_fixtures "$NB/repos"
fi

# -------------------------------------------------------------------------------------------- venvs
if want venvs; then
  log "per-repository Python test environments (frozen versions)"
  for req in "$HERE"/envs/*.txt; do
    r="$(basename "$req" .txt)"
    [[ "$r" == codexa-tools ]] && continue
    [[ -d "$NB/repos/$r" ]] || continue
    v="$NB/venvs/$r"
    if [[ -x "$v/bin/python" ]] && "$v/bin/python" -c "import pytest" 2>/dev/null; then echo "$r present"; continue; fi
    $PY -m venv "$v"
    "$v/bin/python" -m pip install -q -U pip
    "$v/bin/python" -m pip install -q -r "$req"
    "$v/bin/python" -m pip install -q --no-deps -e "$NB/repos/$r"
    echo "$r ok"
  done
fi

# ------------------------------------------------------------------------------------------- traces
if want traces; then
  log "layer-C traces: unpack the released traces (re-trace with: run_local.sh retrace)"
  for f in "$NAVBENCH"/results/traces/*.json.gz; do
    r="$(basename "$f" .json.gz)"
    [[ -f "$NB/traces/$r.json" ]] || gunzip -c "$f" > "$NB/traces/$r.json"
    cp -f "$NAVBENCH/results/traces/$r.trace-meta.json" "$NB/traces/" 2>/dev/null || true
  done
  ls "$NB/traces" | grep -c '\.json$' | xargs echo "trace files:"
fi

# -------------------------------------------------------------------------------------------- check
if want check; then
  log "self-check"
  cd "$NAVBENCH"
  ok=1
  for b in cur 057 055; do [[ -x "$NB/bin/cbm-$b" ]] || { echo "MISSING cbm-$b"; ok=0; }; done
  [[ -d node_modules/pyright ]] || { echo "MISSING node_modules (step node)"; ok=0; }
  "$TOOLS_VENV/bin/python" -c "import psycopg, tree_sitter, numpy, matplotlib; print('python tools ok')" || ok=0
  CODEXA_DATA_DIR=$NB "$TOOLS_VENV/bin/python" -c "
from nb import tokens; print('tokenizer', tokens.count('hello world'))" || ok=0
  # one small fixture end to end, compared with the released raw results
  CODEXA_DATA_DIR=$NB "$TOOLS_VENV/bin/python" -m nb.run fx-py-heldout-100 py fixture "$NB/out-check" >/dev/null 2>&1 || ok=0
  mkdir -p "$NB/out-main-released" && tar xzf results/main/raw_results.tar.gz -C "$NB/out-main-released" 2>/dev/null || true
  cp -n results/main/*.targets.json results/main/*.meta.json "$NB/out-main-released/" 2>/dev/null || true
  "$TOOLS_VENV/bin/python" -m nb.equivalence "$NB/out-main-released" "$NB/out-check" || ok=0
  [[ $ok == 1 ]] && echo "SETUP OK" || { echo "SETUP INCOMPLETE (see messages above)"; exit 1; }
fi
