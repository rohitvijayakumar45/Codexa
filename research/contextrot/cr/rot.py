"""Full-history claim tracking for one context file in one repository (RQ3, study S1).

Earlier work (Treude & Baltes 2026) compares two snapshots (the file's first commit and HEAD) and
only referential claims. Here every claim class is followed along the history:

  1. sample commits from the context file's first appearance to HEAD: every commit that changes the
     file, every `every`-th commit in between, and HEAD (capped at `max_points`);
  2. at each sampled commit, export the tree (git archive; the working tree is never touched),
     extract the file's claims as they stood *at that commit*, and check each claim against that
     commit's code (nb: claims and code move together in time);
  3. per claim (keyed by class + polarity + normalized text), derive its lifecycle:
       born_stale  false when first written
       rotted      true when written, later false while still in the file
       fixed       after rotting, true again or removed from the file
       censored    still true (or unknown) at its last observation

Outputs a JSONL of claim lifecycles plus a per-class summary with Kaplan–Meier survival (time to
rot, in commits and in days; claims removed or still valid are right-censored).
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import tarfile
import tempfile
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from cr.extract import CONTEXT_FILES, extract  # noqa: E402
from cr.oracles import Snapshot, check  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


def first_parent_history(repo: Path) -> list[tuple[str, int]]:
    """(sha, unix time) oldest first."""
    out = _git(repo, "log", "--first-parent", "--format=%H %ct", "HEAD")
    return [(l.split()[0], int(l.split()[1])) for l in reversed(out.splitlines()) if l.strip()]


def touching(repo: Path, path: str) -> set[str]:
    return set(_git(repo, "log", "--first-parent", "--format=%H", "--", path).split())


def file_at(repo: Path, sha: str, path: str) -> str | None:
    r = subprocess.run(["git", "-C", str(repo), "show", f"{sha}:{path}"], capture_output=True)
    return r.stdout.decode("utf-8", errors="replace") if r.returncode == 0 else None


def export(repo: Path, sha: str, dest: Path) -> Path:
    raw = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", sha], check=True, capture_output=True).stdout
    dest.mkdir(parents=True, exist_ok=True)
    try:
        tf = tarfile.open(fileobj=io.BytesIO(raw))
    except tarfile.ReadError:
        return dest
    with tf:
        for m in tf.getmembers():
            if m.issym() or m.islnk():
                continue
            try:
                tf.extract(m, dest, filter="data")
            except (OSError, tarfile.TarError):
                continue
    return dest


@dataclass
class Observation:
    idx: int          # position in first-parent history
    sha: str
    time: int
    status: str       # true | false | unknown | absent
    line: int | None = None
    evidence: str = ""


@dataclass
class Lifecycle:
    repo: str
    file: str
    key: str
    cls: str
    polarity: str
    text: str
    obs: list[Observation] = field(default_factory=list)
    outcome: str = ""          # born_stale | rotted | valid | unknown
    fixed: bool = False
    rot_commits: int | None = None     # commits from introduction to first false observation
    rot_days: float | None = None
    fix_commits: int | None = None
    censored_commits: int | None = None
    censored_days: float | None = None
    stale_at_head: bool = False


def sample_points(history: list[tuple[str, int]], changes: set[str], every: int, max_points: int) -> list[int]:
    start = next((i for i, (sha, _t) in enumerate(history) if sha in changes), None)
    if start is None:
        return []
    pts = {start, len(history) - 1}
    pts |= {i for i in range(start, len(history)) if history[i][0] in changes}
    pts |= set(range(start, len(history), max(1, every)))
    pts = sorted(pts)
    if len(pts) > max_points:  # keep every change point, thin the periodic ones
        must = {i for i in pts if history[i][0] in changes} | {start, len(history) - 1}
        rest = [i for i in pts if i not in must]
        keep = max(0, max_points - len(must))
        step = max(1, len(rest) // keep) if keep else len(rest) + 1
        pts = sorted(must | set(rest[::step][:keep]))
    return pts


def track(repo: Path, context_file: str, *, every: int = 10, max_points: int = 60,
          classes: tuple[str, ...] = ("path", "structure", "command", "symbol", "dependency")) -> list[Lifecycle]:
    repo = Path(repo).resolve()
    hist = first_parent_history(repo)
    pts = sample_points(hist, touching(repo, context_file), every, max_points)
    lifes: dict[str, Lifecycle] = {}
    with tempfile.TemporaryDirectory(prefix="cr-") as tmp:
        for idx in pts:
            sha, t = hist[idx]
            text = file_at(repo, sha, context_file)
            claims = [c for c in extract(text) if c.cls in classes] if text is not None else []
            present = {c.key for c in claims}
            snap = None
            if claims:
                try:
                    snap = Snapshot(export(repo, sha, Path(tmp) / sha[:12]))
                except subprocess.CalledProcessError:
                    continue  # tree not exportable (e.g. a blob missing from a partial clone): skip this point
            for c in claims:
                v = check(snap, c)
                lc = lifes.setdefault(c.key, Lifecycle(repo.name, context_file, c.key, c.cls, c.polarity, c.text))
                lc.obs.append(Observation(idx, sha, t, v.status, c.line, v.evidence))
            for key, lc in lifes.items():
                if key not in present and lc.obs and lc.obs[-1].status != "absent":
                    lc.obs.append(Observation(idx, sha, t, "absent"))
            if snap is not None:
                import shutil
                shutil.rmtree(snap.root, ignore_errors=True)
    for lc in lifes.values():
        _derive(lc, hist)
    return list(lifes.values())


def _derive(lc: Lifecycle, hist: list[tuple[str, int]]) -> None:
    obs = lc.obs
    first = obs[0]
    decided = [o for o in obs if o.status in ("true", "false")]
    if not decided:
        lc.outcome = "unknown"
        return
    if first.status == "false" or (first.status == "unknown" and decided[0].status == "false"):
        lc.outcome = "born_stale"
        rot_at = decided[0]
    else:
        rot_at = next((o for o in obs if o.status == "false"), None)
        lc.outcome = "rotted" if rot_at else "valid"
    if rot_at is not None and lc.outcome == "rotted":
        lc.rot_commits = rot_at.idx - first.idx
        lc.rot_days = (rot_at.time - first.time) / 86400
    if rot_at is not None:
        after = [o for o in obs if o.idx > rot_at.idx]
        fix = next((o for o in after if o.status in ("true", "absent")), None)
        if fix is not None:
            lc.fixed = True
            lc.fix_commits = fix.idx - rot_at.idx
    if lc.outcome == "valid":
        last = next((o for o in reversed(obs) if o.status != "absent"), obs[-1])
        end = next((o for o in obs if o.status == "absent"), None) or last
        lc.censored_commits = end.idx - first.idx
        lc.censored_days = (end.time - first.time) / 86400
    last_present = obs[-1]
    lc.stale_at_head = last_present.status == "false" and last_present.idx == len(hist) - 1


def kaplan_meier(durations: list[tuple[float, bool]]) -> list[tuple[float, float]]:
    """[(time, survival)] for (duration, event_observed) pairs; event = rotted."""
    pts, s = [(0.0, 1.0)], 1.0
    times = sorted({d for d, e in durations if e})
    for t in times:
        at_risk = sum(1 for d, _ in durations if d >= t)
        events = sum(1 for d, e in durations if e and d == t)
        if at_risk:
            s *= 1 - events / at_risk
            pts.append((t, s))
    return pts


def median_survival(km: list[tuple[float, float]]) -> float | None:
    return next((t for t, s in km if s <= 0.5), None)


def summarize(lifes: list[Lifecycle]) -> dict:
    by_cls: dict[str, list[Lifecycle]] = defaultdict(list)
    for lc in lifes:
        by_cls[lc.cls].append(lc)
    out = {}
    for cls, ls in sorted(by_cls.items()):
        decided = [l for l in ls if l.outcome != "unknown"]
        dur_c = [((l.rot_commits if l.outcome == "rotted" else l.censored_commits) or 0, l.outcome == "rotted")
                 for l in decided if l.outcome in ("rotted", "valid")]
        dur_d = [((l.rot_days if l.outcome == "rotted" else l.censored_days) or 0.0, l.outcome == "rotted")
                 for l in decided if l.outcome in ("rotted", "valid")]
        out[cls] = {
            "claims": len(ls), "decidable": len(decided),
            "born_stale": sum(l.outcome == "born_stale" for l in ls),
            "rotted": sum(l.outcome == "rotted" for l in ls),
            "valid": sum(l.outcome == "valid" for l in ls),
            "unknown": sum(l.outcome == "unknown" for l in ls),
            "fixed_after_stale": sum(l.fixed for l in ls),
            "stale_at_head": sum(l.stale_at_head for l in ls),
            "median_commits_to_rot_km": median_survival(kaplan_meier(dur_c)) if dur_c else None,
            "median_days_to_rot_km": median_survival(kaplan_meier(dur_d)) if dur_d else None,
        }
    return out


def find_context_files(repo: Path) -> list[str]:
    tracked = set(_git(repo, "ls-files").splitlines())
    return [f for f in CONTEXT_FILES if f in tracked]


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo", nargs="+")
    ap.add_argument("--every", type=int, default=10)
    ap.add_argument("--max-points", type=int, default=60)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    all_l = []
    for r in a.repo:
        for cf in find_context_files(Path(r)):
            ls = track(Path(r), cf, every=a.every, max_points=a.max_points)
            all_l += ls
            print(f"{Path(r).name}:{cf}: {len(ls)} claims", flush=True)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "lifecycles.jsonl", "w", encoding="utf-8") as fh:
        for l in all_l:
            fh.write(json.dumps(asdict(l)) + "\n")
    summ = summarize(all_l)
    (out / "summary.json").write_text(json.dumps(summ, indent=1))
    print(json.dumps(summ, indent=1))
