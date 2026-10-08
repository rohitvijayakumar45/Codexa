"""Git-history replay benchmark for code-anchored memory invalidation.

Question it answers: when the code moves on, does a memory record about the code know it went stale —
without an LLM, and without throwing away every record that is still true?

Method
  1. Walk a repository's first-parent history. For each sampled pair of commits (t, t+k):
  2. Export both snapshots (git archive — the working tree is never touched) and parse each with the
     production tree-sitter analyzer.
  3. At t, extract ground-truth facts (anchoring_facts.py: signatures, callers, callees, imports, build
     scripts, dependencies) and, for each anchoring policy, the anchors a memory record stating
     that fact would carry.
  4. At t+k, the fact is ACTUALLY stale iff its recomputed value differs (or its subject is gone),
     and PREDICTED stale iff the policy says so — for anchor policies via the production
     `backend.memory.anchors.check_anchors`, the same code the live sweep runs.
  5. Score each (policy, fact type, k) as a binary classifier of staleness.

Policies
  A0_never          never invalidate (what memory did between reloads)
  A1_repo           invalidate everything whenever any file changed (what a reload did: wipe)
  A2_file           file anchors on the file(s) the fact was read from
  A3_symbol         symbol-content anchors for symbol facts, file anchors otherwise
  A4_neighborhood   A3 + file anchors on the fact's 1-hop graph neighbourhood (callers' files and
                    importers of the subject's file for F2, callees' files for F3, imported files for F4)
  A5_query          graph-query anchors: the hash of callers(X) / callees(X) / imports(f) for F2-F4
                    (exact by construction — the fact IS the query result), symbol anchors for F1
  TTL_<n>           invalidate once n or more commits have passed (time-based expiry baseline)

Metrics (positive class = stale)
  precision / recall / F1 of staleness detection
  false_invalidation_rate = FP / (FP + TN) — share of still-true facts thrown away
  stale_served_rate       = FN / (TP + FN) — share of stale facts still served as current

Usage
  python tests/benchmarks/memory_anchoring/replay.py --repo .codexa/repos/httpx --ks 1,5,20 \
      --pairs 12 --max-facts 300 --out tests/benchmarks/memory_anchoring/results/httpx.json
"""

from __future__ import annotations

import argparse
import io
import json
import random
import subprocess
import sys
import tarfile
import tempfile
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[3]
for _p in (ROOT, Path(__file__).resolve().parent):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from backend.memory.anchors import (  # noqa: E402
    QueryIndex, _LazyAnalysis, check_anchors, file_anchor, file_anchors, query_anchor, symbol_anchor,
)
from backend.repository.analyze import analyze_repo, symbol_key  # noqa: E402
from anchoring_facts import (  # noqa: E402
    FACT_TYPES, REPO_SUBJECT, Snapshot, snapshot, subjects,
)

ANCHOR_POLICIES = ("A0_never", "A1_repo", "A2_file", "A3_symbol", "A4_neighborhood", "A5_query")
_ROOT_MANIFESTS = ("package.json", "pyproject.toml", "requirements.txt", "requirements-dev.txt")


# --- git -----------------------------------------------------------------------------------------

def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, encoding="utf-8", errors="replace").stdout


def ensure_repo_root(repo: Path) -> None:
    """Refuse a directory that is not itself a repository root: git would silently resolve it to an
    enclosing repository and archive only this (possibly untracked) subdirectory — empty snapshots."""
    top = Path(_git(repo, "rev-parse", "--show-toplevel").strip()).resolve()
    if top != Path(repo).resolve():
        raise ValueError(f"{repo} is not a git repository root (enclosing repository: {top})")


def history(repo: Path) -> list[str]:
    """First-parent commits, oldest first."""
    return list(reversed(_git(repo, "rev-list", "--first-parent", "HEAD").split()))


def changed_files(repo: Path, a: str, b: str) -> list[str]:
    return [p for p in _git(repo, "diff", "--name-only", a, b).splitlines() if p.strip()]


def export(repo: Path, sha: str, dest: Path) -> Path:
    raw = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", sha],
                         check=True, capture_output=True).stdout
    dest.mkdir(parents=True, exist_ok=True)
    try:
        tar_file = tarfile.open(fileobj=io.BytesIO(raw))
    except tarfile.ReadError:
        return dest  # an empty tree (e.g. a history-only root commit) archives to a headerless tar
    with tar_file as tar:
        for member in tar.getmembers():
            if member.issym() or member.islnk():
                continue  # symlinks are irrelevant to parsing and fail on Windows
            try:
                tar.extract(member, dest, filter="data")
            except (OSError, tarfile.TarError):
                continue
    return dest


# --- anchoring policies -------------------------------------------------------------------------

def _manifest_anchor_files(snap: Snapshot) -> list[str]:
    return sorted(set(_ROOT_MANIFESTS) | set(snap.manifest_files))


def build_anchors(policy: str, fact_type: str, subject: str, snap: Snapshot,
                  rev_imports: dict[str, set[str]]) -> list[dict[str, Any]]:
    root = snap.root
    symbol_fact = fact_type in ("F1_signature", "F2_callers", "F3_callees")
    if fact_type in ("F5_scripts", "F6_deps"):
        return file_anchors(root, _manifest_anchor_files(snap))
    if symbol_fact:
        sym = snap_symbol(snap, subject)
        own_file = sym.file
    else:
        own_file = subject

    if policy == "A2_file":
        return [file_anchor(root, own_file)]
    if policy == "A3_symbol":
        return [symbol_anchor(sym)] if symbol_fact else [file_anchor(root, own_file)]
    if policy == "A4_neighborhood":
        if fact_type == "F1_signature":
            return [symbol_anchor(sym)]
        if fact_type == "F2_callers":
            files = {k.split("#", 1)[0] for k in snap.callers.get(subject, ())}
            files |= rev_imports.get(own_file, set())
            files.add(own_file)  # same-file callers
            return [symbol_anchor(sym)] + file_anchors(root, sorted(files))
        if fact_type == "F3_callees":
            files = {k.split("#", 1)[0] for k in snap.callees.get(subject, ())}
            return [symbol_anchor(sym)] + file_anchors(root, sorted(files))
        if fact_type == "F4_imports":
            return file_anchors(root, [own_file, *sorted(snap.imports.get(subject, ()))])
    if policy == "A5_query":
        query = {"F2_callers": "callers", "F3_callees": "callees", "F4_imports": "imports"}.get(fact_type)
        if query is None:
            return [symbol_anchor(sym)]
        index = _QUERY_INDEX.get(id(snap))
        if index is None:
            index = _QUERY_INDEX[id(snap)] = QueryIndex(snap.analysis)
        return [query_anchor(snap.analysis, query, subject, index=index)]
    raise ValueError(f"{policy} has no anchors for {fact_type}")


_SYMBOL_INDEX: dict[int, dict[str, Any]] = {}
_QUERY_INDEX: dict[int, QueryIndex] = {}


def snap_symbol(snap: Snapshot, key: str):
    index = _SYMBOL_INDEX.get(id(snap))
    if index is None:
        index = {symbol_key(s): s for s in snap.analysis.symbols}
        _SYMBOL_INDEX[id(snap)] = index
    return index[key]


# --- scoring ------------------------------------------------------------------------------------

@dataclass
class Confusion:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    anchors: int = 0  # total anchors carried (storage/check cost proxy)

    def add(self, predicted: bool, actual: bool, n_anchors: int = 0) -> None:
        if predicted and actual:
            self.tp += 1
        elif predicted:
            self.fp += 1
        elif actual:
            self.fn += 1
        else:
            self.tn += 1
        self.anchors += n_anchors

    def merge(self, other: "Confusion") -> None:
        self.tp += other.tp
        self.fp += other.fp
        self.fn += other.fn
        self.tn += other.tn
        self.anchors += other.anchors

    def metrics(self) -> dict[str, Any]:
        n = self.tp + self.fp + self.fn + self.tn
        precision = self.tp / (self.tp + self.fp) if self.tp + self.fp else None
        recall = self.tp / (self.tp + self.fn) if self.tp + self.fn else None
        f1 = (2 * precision * recall / (precision + recall)
              if precision is not None and recall is not None and precision + recall else None)
        return {
            "n": n, "tp": self.tp, "fp": self.fp, "fn": self.fn, "tn": self.tn,
            "prevalence": (self.tp + self.fn) / n if n else None,
            "precision": precision, "recall": recall, "f1": f1,
            "false_invalidation_rate": self.fp / (self.fp + self.tn) if self.fp + self.tn else None,
            "stale_served_rate": self.fn / (self.tp + self.fn) if self.tp + self.fn else None,
            "mean_anchors": self.anchors / n if n else None,
        }


@dataclass
class ReplayResult:
    repo: str
    pairs: list[dict[str, Any]] = field(default_factory=list)
    # cells[(k, fact_type, policy)] -> Confusion
    cells: dict[tuple[int, str, str], Confusion] = field(default_factory=lambda: defaultdict(Confusion))

    def summary(self) -> dict[str, Any]:
        by_k: dict[str, Any] = {}
        overall: dict[str, Confusion] = defaultdict(Confusion)
        by_fact: dict[str, dict[str, Confusion]] = defaultdict(lambda: defaultdict(Confusion))
        for (k, ft, pol), conf in sorted(self.cells.items()):
            by_k.setdefault(str(k), {}).setdefault(ft, {})[pol] = conf.metrics()
            overall[pol].merge(conf)
            by_fact[ft][pol].merge(conf)
        return {
            "repo": self.repo, "pairs": self.pairs,
            "by_k": by_k,
            "by_fact": {ft: {pol: c.metrics() for pol, c in sorted(rows.items())}
                        for ft, rows in sorted(by_fact.items())},
            "overall": {pol: c.metrics() for pol, c in sorted(overall.items())},
        }


def run_replay(
    repo: Path, *, ks: list[int], pairs_per_k: int, max_facts: int, ttls: list[int], seed: int = 0,
    fact_types: tuple[str, ...] = FACT_TYPES, log: Callable[[str], None] = print,
) -> ReplayResult:
    repo = Path(repo).resolve()
    ensure_repo_root(repo)
    commits = history(repo)
    rng = random.Random(seed)
    # per-snapshot lookup caches are keyed by id(); ids are reused once a run's snapshots are freed
    _SYMBOL_INDEX.clear()
    _QUERY_INDEX.clear()
    result = ReplayResult(repo=repo.name)
    policies = list(ANCHOR_POLICIES) + [f"TTL_{n}" for n in ttls]

    with tempfile.TemporaryDirectory(prefix="codexa-replay-") as tmp:
        tmp_root = Path(tmp)
        snaps: dict[str, Snapshot] = {}

        def snap_for(sha: str) -> Snapshot:
            if sha not in snaps:
                root = export(repo, sha, tmp_root / sha[:12])
                snaps[sha] = snapshot(root, analyze_repo(root))
            return snaps[sha]

        for k in ks:
            if len(commits) <= k:
                continue
            starts = list(range(0, len(commits) - k))
            if len(starts) > pairs_per_k:
                step = len(starts) / pairs_per_k
                starts = [starts[int(i * step)] for i in range(pairs_per_k)]
            for i in starts:
                t_sha, u_sha = commits[i], commits[i + k]
                t0 = time.perf_counter()
                snap_t, snap_u = snap_for(t_sha), snap_for(u_sha)
                diff = changed_files(repo, t_sha, u_sha)
                rev_imports: dict[str, set[str]] = defaultdict(set)
                for a, b in snap_t.analysis.imports:
                    rev_imports[b].add(a)
                lazy_u = _LazyAnalysis(snap_u.root, snap_u.analysis)
                file_cache: dict[str, str | None] = {}
                n_facts = 0
                for ft in fact_types:
                    subs = subjects(snap_t, ft)
                    if len(subs) > max_facts:
                        subs = rng.sample(subs, max_facts)
                    for subject in subs:
                        before = snap_t.value(ft, subject)
                        after = snap_u.value(ft, subject)
                        actual = after is None or after != before
                        n_facts += 1
                        for pol in policies:
                            if pol == "A0_never":
                                predicted, n_anchors = False, 0
                            elif pol == "A1_repo":
                                predicted, n_anchors = bool(diff), 1
                            elif pol.startswith("TTL_"):
                                predicted, n_anchors = k >= int(pol.split("_", 1)[1]), 0
                            else:
                                anchors = build_anchors(pol, ft, subject, snap_t, rev_imports)
                                # re-point file anchors at the later snapshot's tree: anchors are
                                # computed in snapshot t's directory, checked against t+k's.
                                check = check_anchors(snap_u.root, anchors, _lazy=lazy_u, _file_cache=file_cache)
                                predicted, n_anchors = check.status == "stale", len(anchors)
                            result.cells[(k, ft, pol)].add(predicted, actual, n_anchors)
                result.pairs.append({"k": k, "t": t_sha[:10], "t_plus_k": u_sha[:10],
                                     "files_changed": len(diff), "facts": n_facts,
                                     "seconds": round(time.perf_counter() - t0, 2)})
                log(f"  k={k} {t_sha[:8]}..{u_sha[:8]} files_changed={len(diff)} facts={n_facts}")
    return result


def _fmt(x: Any) -> str:
    return "  -  " if x is None else f"{x:.3f}"


def print_table(summary: dict[str, Any]) -> None:
    _print_rows(f"{summary['repo']} - overall (all k, all fact types)", summary["overall"])
    for ft, rows in summary.get("by_fact", {}).items():
        _print_rows(f"{summary['repo']} - {ft}", rows)


def _print_rows(title: str, rows: dict[str, Any]) -> None:
    print(f"\n== {title} ==")
    print(f"{'policy':18} {'n':>7} {'prev':>6} {'prec':>6} {'rec':>6} {'F1':>6} {'FIR':>6} {'SSR':>6} {'anch':>6}")
    for pol, m in rows.items():
        print(f"{pol:18} {m['n']:>7} {_fmt(m['prevalence'])} {_fmt(m['precision'])} {_fmt(m['recall'])} "
              f"{_fmt(m['f1'])} {_fmt(m['false_invalidation_rate'])} {_fmt(m['stale_served_rate'])} "
              f"{_fmt(m['mean_anchors'])}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, action="append", help="git repository path (repeatable)")
    ap.add_argument("--ks", default="1,5,20", help="commit distances k")
    ap.add_argument("--pairs", type=int, default=12, help="sampled (t, t+k) pairs per k")
    ap.add_argument("--max-facts", type=int, default=300, help="max sampled subjects per fact type per pair")
    ap.add_argument("--ttls", default="5,20", help="TTL baselines, in commits")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", help="output JSON path (one repo) or directory (several)")
    args = ap.parse_args(argv)

    ks = [int(x) for x in args.ks.split(",") if x.strip()]
    ttls = [int(x) for x in args.ttls.split(",") if x.strip()]
    single_file = bool(args.out) and len(args.repo) == 1 and args.out.endswith(".json")
    failures = 0
    for repo in args.repo:
        print(f"replaying {repo}")
        try:
            res = run_replay(Path(repo), ks=ks, pairs_per_k=args.pairs, max_facts=args.max_facts,
                             ttls=ttls, seed=args.seed)
        except Exception as exc:  # noqa: BLE001 - one bad repository must not lose the others
            failures += 1
            print(f"  FAILED: {type(exc).__name__}: {exc}")
            continue
        summary = res.summary()
        summary["config"] = {"ks": ks, "pairs_per_k": args.pairs, "max_facts": args.max_facts,
                             "ttls": ttls, "seed": args.seed}
        print_table(summary)
        if args.out:  # written per repository as it finishes
            out = Path(args.out) if single_file else Path(args.out) / f"{summary['repo']}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
