import sys, random, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import jedi
from backend.graph.service import GraphService
from backend.graph.repository import InMemoryGraphRepository
from backend.graph.events import InMemoryGraphEventWriter
from backend.repository.api import reindex_repository
from backend.memory.store import MemoryStore
from backend.files.api import repo_root
REPO = sys.argv[1]; random.seed(11)
g = GraphService(repository=InMemoryGraphRepository(), event_writer=InMemoryGraphEventWriter())
reindex_repository(REPO, store=MemoryStore(), graph=g, llm=None)
nodes = g.list_nodes(); by = {n.id: n for n in nodes}
inc = {}
for e in g.list_edges_at():
    if e.edge_type in {"imports","calls","depends_on","flows_into"}: inc.setdefault(e.to_node_id, set()).add(e.from_node_id)
syms = [n for n in nodes if n.node_type == "CodeSymbol" and n.properties.get("repository") == REPO and str(n.properties.get("file","")).endswith(".py") and n.properties.get("line")]
random.shuffle(syms); root = repo_root(REPO); proj = jedi.Project(str(root))
stats = dict(n=0, jedi_has_refs=0, graph_has_edge=0, jedi_refs_but_no_graph_edge=0, file_recall=[])
for n in syms[:120]:
    f = n.properties["file"]; ln = int(n.properties["line"]); name = n.properties["name"]
    src = (root / f).read_text(encoding="utf-8", errors="ignore"); col = src.splitlines()[ln-1].find(name)
    if col < 0: continue
    try: refs = jedi.Script(src, path=str(root/f), project=proj).get_references(ln, col, scope="project")
    except Exception: continue
    jf = set()
    for r in refs:
        if r.module_path and not (str(r.module_path) == str(root/f) and r.line == ln):
            try: jf.add(str(Path(r.module_path).relative_to(root)))
            except ValueError: pass
    gf = {by[s].properties.get("file") or by[s].properties.get("path") for s in inc.get(n.id, ()) if s in by}
    stats["n"] += 1; stats["jedi_has_refs"] += bool(jf); stats["graph_has_edge"] += bool(gf)
    stats["jedi_refs_but_no_graph_edge"] += bool(jf) and not gf
    if jf: stats["file_recall"].append(len(gf & jf)/len(jf))
fr = stats.pop("file_recall"); stats["mean_file_recall_unconditioned"] = round(sum(fr)/len(fr),3); print(REPO, json.dumps(stats))
