"""S1 pilot: full-history claim tracking on a seeded random sample of repositories from the
Baltes et al. agent-configuration dataset (Zenodo 10.5281/zenodo.19375880, CC BY 4.0).

Usage: python pilot.py --n 20 --seed 20261008 [--every 20 --max-points 30]
Outputs work/pilot/{sample.json, lifecycles.jsonl, summary.json, verdicts_false.jsonl}
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from cr.extract import CONTEXT_FILES  # noqa: E402
from cr.rot import summarize, track  # noqa: E402

DATA = HERE / "data" / "context_files.csv"
WORK = HERE / "work"


def sample(n: int, seed: int) -> list[dict]:
    rows = list(csv.DictReader(open(DATA, encoding="utf-8")))
    elig = [r for r in rows if r["context_file"] in CONTEXT_FILES and r["is_empty"] == "False"
            and r["is_reference"] == "False" and int(r["#commits"] or 0) >= 3 and int(r["line_count"] or 0) >= 20]
    repos = sorted({r["repo_name"] for r in elig})
    rng = random.Random(seed)
    pick = set(rng.sample(repos, min(n, len(repos))))
    return [r for r in elig if r["repo_name"] in pick]


def clone(repo: str, branch: str) -> Path | None:
    dest = WORK / "repos" / repo.replace("/", "__")
    if (dest / ".git").exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    # blobs <512 KB come with the clone; exporting a historical tree from a blob:none partial clone
    # fetches blobs one by one and was ~100x slower
    base = ["git", "clone", "--quiet", "--filter=blob:limit=512k", "--single-branch"]
    for extra in (["--branch", branch], []):  # the dataset's branch may have been renamed/deleted
        if dest.exists():
            import shutil
            shutil.rmtree(dest, ignore_errors=True)
        try:
            r = subprocess.run(base + extra + [f"https://github.com/{repo}.git", str(dest)], capture_output=True,
                               text=True, timeout=900)
        except subprocess.TimeoutExpired:
            continue
        if r.returncode == 0:
            return dest
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=20261008)
    ap.add_argument("--every", type=int, default=20)
    ap.add_argument("--max-points", type=int, default=30)
    a = ap.parse_args()
    out = WORK / "pilot"
    out.mkdir(parents=True, exist_ok=True)
    rows = sample(a.n, a.seed)
    (out / "sample.json").write_text(json.dumps(rows, indent=1))
    lifes, status = [], []
    per_repo = out / "per_repo"  # one file per (repo, context file): resumable, nothing lost on a kill
    per_repo.mkdir(exist_ok=True)
    for r in rows:
        done_path = per_repo / (r["repo_name"].replace("/", "__") + "__" + r["context_file"].replace("/", "_") + ".json")
        if done_path.exists():
            d = json.loads(done_path.read_text())
            status.append(d["status"])
            from cr.rot import Lifecycle, Observation
            for x in d["lifecycles"]:
                obs = [Observation(**o) for o in x.pop("obs")]
                lifes.append(Lifecycle(**x, obs=obs))
            continue
        dest = clone(r["repo_name"], r["branch"] or "main")
        if dest is None:
            status.append({"repo": r["repo_name"], "file": r["context_file"], "status": "clone_failed"})
            print("clone failed", r["repo_name"], flush=True)
            continue
        try:
            ls = track(dest, r["context_file"], every=a.every, max_points=a.max_points)
        except Exception as e:  # noqa: BLE001 - one bad repository must not stop the pilot
            status.append({"repo": r["repo_name"], "file": r["context_file"], "status": f"error: {e}"[:200]})
            print("error", r["repo_name"], e, flush=True)
            continue
        for l in ls:
            l.repo = r["repo_name"]
        lifes += ls
        st_ = {"repo": r["repo_name"], "file": r["context_file"], "status": "ok", "claims": len(ls)}
        status.append(st_)
        done_path.write_text(json.dumps({"status": st_, "lifecycles": [asdict(l) for l in ls]}))
        print(f"{r['repo_name']}:{r['context_file']} -> {len(ls)} claims", flush=True)
    with open(out / "lifecycles.jsonl", "w", encoding="utf-8") as fh:
        for l in lifes:
            fh.write(json.dumps(asdict(l)) + "\n")
    with open(out / "verdicts_false.jsonl", "w", encoding="utf-8") as fh:  # audit sheet for oracle precision
        for l in lifes:
            for o in l.obs:
                if o.status == "false":
                    fh.write(json.dumps({"repo": l.repo, "file": l.file, "cls": l.cls, "polarity": l.polarity,
                                         "text": l.text, "sha": o.sha, "line": o.line, "evidence": o.evidence}) + "\n")
                    break
    summ = summarize(lifes)
    (out / "summary.json").write_text(json.dumps({"repos": status, "by_class": summ}, indent=1))
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
