"""The blast-radius card for "add the comment ... in src/App.tsx" on Auralis said Medium risk,
3 downstream, targets `server/src/app.ts` + `src/App.tsx`. Three separate errors:

1. `app.ts` is a substring of `app.tsx`, and target matching accepted any substring, so the server
   entry and its /health route joined a frontend comment's blast radius.
2. A comment cannot change what the program does; the risk ignored the kind of change.
3. For a real change it undersold App.tsx: only main.tsx imports it, but it renders fourteen pages.
"""

from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.agents.impact import _change_kind, create_impact_router

REPO = "Auralis"


def _file(path):
    return SimpleNamespace(id=uuid4(), node_type="File", stable_id=f"file://{REPO}/{path}",
                           properties={"path": path, "repository": REPO})


def _sym(name, file):
    return SimpleNamespace(id=uuid4(), node_type="CodeSymbol", stable_id=f"symbol://{REPO}/{file}#{name}",
                           properties={"name": name, "file": file, "repository": REPO})


def _edge(a, b, edge_type="imports"):
    return SimpleNamespace(from_node_id=a.id, to_node_id=b.id, edge_type=edge_type, confidence=1.0, properties={})


class _Graph:
    def __init__(self, nodes, edges):
        self._nodes, self._edges = nodes, edges

    def list_nodes(self):
        return self._nodes

    def list_edges_at(self, at_time=None):
        return self._edges


def _auralis():
    app, main = _file("src/App.tsx"), _file("src/main.tsx")
    server_app, server_index = _file("server/src/app.ts"), _file("server/src/index.ts")
    pages = [_file(f"src/pages/Page{i}.tsx") for i in range(12)]
    app_sym = _sym("App", "src/App.tsx")
    nodes = [app, main, server_app, server_index, app_sym, *pages]
    edges = [_edge(main, app), _edge(server_index, server_app), *[_edge(app, p) for p in pages]]
    client = TestClient(FastAPI())
    client.app.include_router(create_impact_router(graph=_Graph(nodes, edges), planner=None))
    return client


def _impact(description):
    return _auralis().post("/agents/impact", json={"description": description, "repository": REPO}).json()


def test_a_named_path_targets_that_file_only():
    res = _impact('add the comment "this files has been read by glm 5.3" in src/App.tsx')
    assert [t["label"] for t in res["targets"]] == ["src/App.tsx"]
    assert {a["label"] for a in res["affected"]} == {"src/main.tsx"}


def test_a_comment_is_not_a_risk():
    res = _impact('add the comment "this files has been read by glm 5.3" in src/App.tsx')
    assert res["change_kind"] == "cosmetic"
    assert res["risk_level"] == "None"
    assert "no runtime effect" in res["risk_reason"]


def test_a_real_change_to_the_root_component_is_high_risk():
    res = _impact("change the routes in src/App.tsx so settings opens first")
    assert res["change_kind"] == "code"
    assert res["root_component"] is True
    assert res["composes"] == 12
    assert res["risk_level"] == "High"
    assert "renders 12 files" in res["risk_reason"]


def test_a_basename_still_resolves_without_catching_its_lookalike():
    res = _impact("update the layout in App.tsx")
    assert [t["label"] for t in res["targets"]] == ["src/App.tsx"]


def test_quoted_words_do_not_decide_the_kind_of_change():
    # The quoted text is the comment's content; "routes" inside it is not the change.
    assert _change_kind('add the comment "handles routes" to src/App.tsx') == "cosmetic"
    assert _change_kind("rename the handler and fix its comment") == "code"
