"""Re-check of tests/benchmarks/memory_graph/retrieval_payload.py with two extra arms.

Same sampling as the original (symbols with >=1 incoming imports/calls/depends_on/flows_into edge,
seed 7, n=40). Adds:
  grep arm   : `grep -rnw <name>` over source files, lines clipped to 200 chars -> tokens
  correctness: file-level recall/precision of the graph's referencing-file set against
               a textual ground truth (files with a word-boundary occurrence of the name outside
               the definition line) and, for Python, against jedi.get_references.
Usage: CODEXA_DATA_DIR=<dir> python payload_recheck.py <repo>
"""
import json, os, random, re, subprocess, sys, statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import re as _re
from backend.graph.service import GraphService
from backend.graph.repository import InMemoryGraphRepository
from backend.graph.events import InMemoryGraphEventWriter
from backend.repository.api import reindex_repository
from backend.memory.store import MemoryStore
from backend.files.api import repo_root
import backend.agents.tools as T

REPO = sys.argv[1]
TOKMODE = os.environ.get("TOKMODE", "regex")
toks = (lambda s: len(_re.findall(r"\w+|[^\w\s]", s or ""))) if TOKMODE == "regex" else (lambda s: len(s or "") // 4)
random.seed(7)
graph = GraphService(repository=InMemoryGraphRepository(), event_writer=InMemoryGraphEventWriter())
store = MemoryStore()
reindex_repository(REPO, store=store, graph=graph, llm=None)
nodes = graph.list_nodes(); edges = graph.list_edges_at(); by_id = {n.id: n for n in nodes}
dep = {"imports", "calls", "depends_on", "flows_into"}
inc = {}
for e in edges:
    if e.edge_type in dep:
        inc.setdefault(e.to_node_id, set()).add(e.from_node_id)
cands = []
for n in nodes:
    if n.properties.get("repository") != REPO: continue
    kind = str(n.node_type).lower(); name = n.properties.get("name"); f = n.properties.get("file") or n.properties.get("path")
    if name and f and any(k in kind for k in ("function", "method", "symbol", "class")) and n.id in inc:
        cands.append(n)
random.shuffle(cands); sample = cands[:40]
root = repo_root(REPO)
SRC = (".py", ".js", ".ts", ".tsx", ".jsx", ".mjs")
fcache = {}
def ftok(rel):
    if rel not in fcache:
        try: fcache[rel] = toks((root / rel).read_text(encoding="utf-8", errors="ignore"))
        except Exception: fcache[rel] = 0
    return fcache[rel]

def grep(name):
    inc_args = sum((["--include", f"*{x}"] for x in SRC), [])
    out = subprocess.run(["grep", "-rnw", *inc_args, "--exclude-dir=node_modules", "--exclude-dir=.git", name, "."],
                         cwd=root, capture_output=True, text=True).stdout
    lines = [l[:200] for l in out.splitlines()]
    return lines

try:
    import jedi
except ImportError:
    jedi = None

rows = []
for n in sample:
    name = n.properties["name"]; dfile = n.properties.get("file") or n.properties.get("path"); line = n.properties.get("line")
    g_files = set()
    for s in inc.get(n.id, ()):
        src = by_id.get(s)
        if src:
            f = src.properties.get("file") or src.properties.get("path")
            if f: g_files.add(f)
    raw = sum(ftok(f) for f in g_files | {dfile})
    gout = T._lookup_symbol(name, REPO, graph=graph, store=store) + "\n" + T._get_dependencies(name, REPO, graph=graph)
    glines = grep(name)
    grep_tok = toks("\n".join(glines))
    # textual ground truth: files with an occurrence other than the def line
    txt_files = set()
    for l in glines:
        p, ln, _ = (l.split(":", 2) + ["", ""])[:3]
        p = p[2:] if p.startswith("./") else p
        if p == dfile and str(ln) == str(line): continue
        txt_files.add(p)
    # graph files excluding def file only if def file has no other textual ref
    jedi_files = None
    if jedi and dfile.endswith(".py") and line:
        try:
            src = (root / dfile).read_text(encoding="utf-8", errors="ignore")
            ln = int(line); col = src.splitlines()[ln - 1].find(name)
            if col >= 0:
                refs = jedi.Script(src, path=str(root / dfile), project=jedi.Project(str(root))).get_references(ln, col, scope="project")
                jedi_files = set()
                for r in refs:
                    if r.module_path and not (str(r.module_path) == str(root / dfile) and r.line == ln):
                        try: jedi_files.add(str(Path(r.module_path).relative_to(root)))
                        except ValueError: pass
        except Exception:
            jedi_files = None
    def pr(pred, truth):
        if not truth: return None, None
        tp = len(pred & truth)
        return (tp / len(pred) if pred else None), tp / len(truth)
    p_txt, r_txt = pr(g_files, txt_files)
    p_j, r_j = pr(g_files, jedi_files) if jedi_files is not None else (None, None)
    rows.append(dict(symbol=name, def_file=dfile, raw=raw, graph=toks(gout), grep=grep_tok,
                     n_graph_files=len(g_files), n_txt_files=len(txt_files),
                     prec_txt=p_txt, rec_txt=r_txt, prec_jedi=p_j, rec_jedi=r_j,
                     n_jedi_files=None if jedi_files is None else len(jedi_files)))

def agg(k): return sum(r[k] for r in rows)
def mean(k):
    v = [r[k] for r in rows if r[k] is not None]
    return (round(st.mean(v), 3), len(v)) if v else (None, 0)
summary = dict(repo=REPO, n=len(rows), n_candidates=len(cands), raw=agg("raw"), graph=agg("graph"), grep=agg("grep"),
               raw_over_graph=round(agg("raw") / agg("graph"), 1), grep_over_graph=round(agg("grep") / agg("graph"), 2),
               median_grep_over_graph=round(st.median(r["grep"] / r["graph"] for r in rows), 2),
               prec_txt=mean("prec_txt"), rec_txt=mean("rec_txt"), prec_jedi=mean("prec_jedi"), rec_jedi=mean("rec_jedi"))
print(json.dumps(summary))
Path(os.environ.get("OUT", "."), f"recheck_{REPO}.json").write_text(json.dumps(dict(summary=summary, rows=rows), indent=1))
