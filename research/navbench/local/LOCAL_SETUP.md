# Running NavBench and agentbench on your own PC (Windows → WSL2)

Everything in `research/navbench` and `research/agentbench` runs locally under **WSL2 with Ubuntu 24.04**.
That is the same OS the published results were produced on. Native Windows is not supported: the pipeline
needs bash, gcc (to build codebase-memory-mcp), and Linux paths. Expect:
- disk: about 10 GB;
- RAM: 8 GB or more (16 GB recommended);
- setup time: 30–60 minutes, mostly unattended.

## 1. Install WSL2 + Ubuntu 24.04 (once, PowerShell as Administrator)

```powershell
wsl --install -d Ubuntu-24.04
```

Reboot if asked, open **Ubuntu 24.04** from the Start menu, and create your Linux user.

Optional: give WSL more memory by putting this in `C:\Users\<you>\.wslconfig`:

```
[wsl2]
memory=12GB
processors=4
```

Then run `wsl --shutdown` in PowerShell and reopen Ubuntu.

## 2. Clone the repository *inside* WSL (not under `/mnt/c` or OneDrive)

The Windows filesystem is much slower from WSL and breaks file watching, so keep the checkout in your
Linux home:

```bash
cd ~
git clone https://github.com/rohitvijayakumar45/Codexa.git
cd Codexa
git checkout claude/upbeat-hamilton-zhq0os      # or main, once merged
```

Copy your API keys for the agent study (the `.env` is gitignored, so it is not in the clone):

```bash
cp /mnt/c/Users/rohit/OneDrive/Documents/Codexa/.env ~/Codexa/.env
```

## 3. One-command setup

```bash
bash research/navbench/local/setup_wsl.sh
```

It asks for your sudo password (apt packages, creating `/work`). Steps, each idempotent:

| step | what it does |
|---|---|
| `system` | Python 3.13 (deadsnakes PPA), Node 22, ripgrep, gcc, zlib |
| `data` | creates `/work/nb`, the data root every script expects |
| `tools` | harness + Codexa backend environment, frozen versions (`local/envs/codexa-tools.txt`) |
| `node` | pinned pyright 1.1.414, TypeScript 5.9.3, gpt-tokenizer 4.0.0 (`npm ci`) |
| `cbm` | builds codebase-memory-mcp at current `bf93f0b7`, v0.5.7 and v0.5.5 |
| `corpus` | clones all 24 repositories at their pinned commits |
| `fixtures` | generates the held-out, calibration and fresh fixtures and runs the fixture gate |
| `venvs` | per-repository test environments with frozen versions (`local/envs/<repo>.txt`) |
| `traces` | unpacks the released layer-C traces |
| `check` | runs one fixture end to end and compares it with the released raw results; prints `SETUP OK` |

If a step fails, fix the cause and re-run only that step, e.g.
`bash research/navbench/local/setup_wsl.sh --step cbm`.

## 4. Run

```bash
R=research/navbench/local/run_local.sh
bash $R frozen     # the paper's confirmatory run on 17 repositories + full analysis   (~30 min)
bash $R large      # large-repository extension: networkx, sqlalchemy, typeorm, nest (~1–2 h)
bash $R v2         # all adapters incl. G1-v2, multi-hop T3, routing policies           (~2 h)
bash $R selftest   # agent tasks: grader and navigation check, no model calls          (~1 h)
bash $R agent nvidia_nim/z-ai/glm-5.3 rg,lsp,codexa,codexa2,routed,cbm_cur 3
                   # agent study on tasks/natural_v1.json (paid model calls; keys from .env)
```

What each run produces:
- `frozen` checks itself against the released results (`nb.equivalence`). Facts should be identical, except for:
  - codebase-memory run-to-run noise (about 5% of natural-code queries for v0.5.x, 0.4% for current);
  - G1 answers truncated at its output caps.
  
  Token counts depend on the absolute path only in the LSP-JSON form; `/work/nb` keeps it identical.
- `agent` resumes automatically: re-running it skips finished runs and repeats runs that hit provider errors.
  Before the full 40 × 6 × 3 = 720 runs, try a smoke test: `... agent <model> rg,lsp 1`.
- Outputs go to `/work/nb/out-*-local/` and `/work/ab/natural-run/`. From Windows, open them as
  `\\wsl$\Ubuntu-24.04\work\nb\...`.

## 5. Bring results back

Copy the outputs you want under `research/navbench/results/` (or `research/agentbench/`), then
`git add`, `commit` and `push` from WSL as usual. Raw run directories are large; commit the scored and
analysis files, as `results/main/` and `results/v2/` do.

## Troubleshooting

| symptom | fix |
|---|---|
| `python3.13: command not found` after `system` | `sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install python3.13 python3.13-venv` |
| a run hangs on codebase-memory | never run two `run_local.sh` stages at once; they share `/work/nb/cbmhome-*` |
| pyright results empty or tiny | the harness waits until pyright has indexed (`nb/lsp.py warm`); give WSL more memory |
| `zenodo.org` downloads (context-rot study) | work locally; only the cloud sandbox blocks that host |
| everything is slow | the checkout or `/work` is on `/mnt/c`; move both into the Linux filesystem |
