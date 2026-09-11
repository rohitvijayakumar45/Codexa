"""Routes, commits and intent extraction for ingested repositories (backend/repository/intent.py)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from backend.graph.events import InMemoryGraphEventWriter
from backend.graph.repository import InMemoryGraphRepository
from backend.graph.schemas import GraphNodeCreate, GraphNodeType
from backend.graph.service import GraphService
from backend.repository.analyze import analyze_repo
from backend.repository.intent import (
    add_intent_to_graph,
    extract_conventions,
    extract_decisions,
    extract_routes,
    mine_commits,
)


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture()
def express_repo(tmp_path: Path) -> Path:
    root = tmp_path / "proctor"
    _write(root, "backend/app.js", """
const express = require('express');
const exams = require('./routes/examroute');
const users = require('./routes/userroute');
const app = express();
app.use('/api/v1/', exams);
app.use('/api/v1/', users);
app.get("/", (req, res) => { res.send("ok"); });
module.exports = app;
""")
    _write(root, "backend/routes/examroute.js", """
const express = require('express');
const { createExam, getAllExams } = require('../controllers/examController');
const { protect, adminOnly } = require("../middleware/authMiddleware");
const router = express.Router();
router.route('/exam').post(protect, adminOnly, createExam);
router.route('/exam/get').get(protect, getAllExams).put(protect, getAllExams);
module.exports = router;
""")
    _write(root, "backend/routes/userroute.js", """
const express = require('express');
const { login } = require('../controllers/userController');
const router = express.Router();
router.post('/login', login);
module.exports = router;
""")
    _write(root, "backend/controllers/examController.js", """
const Exam = require('mongoose').model('Exam');
async function createExam(req, res) { return res.json({}); }
async function getAllExams(req, res) { return res.json([]); }
module.exports = { createExam, getAllExams };
""")
    _write(root, "backend/controllers/userController.js", """
const jwt = require('jsonwebtoken');
function login(req, res) { return jwt.sign({}, 'k'); }
module.exports = { login };
""")
    _write(root, "backend/middleware/authMiddleware.js", "function protect(){}\nfunction adminOnly(){}\nmodule.exports={protect,adminOnly};\n")
    _write(root, "frontend/src/api.ts", """
import axios from 'axios';
export const list = () => axios.get('/api/v1/exam/get');
export const api = { get: (u: string) => fetch(u) };
""")
    _write(root, "frontend/src/App.tsx", "import React from 'react';\nexport default function App() { return null; }\n")
    _write(root, "frontend/src/main.tsx", "import React from 'react';\nimport App from './App';\n")
    _write(root, "frontend/src/Page.tsx", "import React from 'react';\nexport function Page() { return null; }\n")
    _write(root, "backend/package.json", json.dumps({"dependencies": {"express": "^5.1.0", "mongoose": "^8.18.1", "jsonwebtoken": "^9.0.2", "dotenv": "^17"}}))
    _write(root, "frontend/package.json", json.dumps({"dependencies": {"react": "^18.3.1", "axios": "^1.7.0", "@radix-ui/react-tabs": "^1.1.3"}}))
    return root


def test_express_routes_resolve_mount_prefix_chain_and_handler(express_repo: Path):
    files = analyze_repo(express_repo).files
    routes = {(r.method, r.path): r for r in extract_routes(express_repo, files)}
    assert ("POST", "/api/v1/exam") in routes
    assert routes[("POST", "/api/v1/exam")].handler == "createExam"
    assert ("GET", "/api/v1/exam/get") in routes and ("PUT", "/api/v1/exam/get") in routes
    assert routes[("POST", "/api/v1/login")].handler == "login"
    # An inline arrow handler has no named handler.
    assert routes[("GET", "/")].handler is None
    # An HTTP client call in the frontend is not a route definition.
    assert all(r.file.startswith("backend/") for r in routes.values())


def test_plain_http_route_tables(tmp_path: Path):
    """BarbellHub's style: a `routes` object keyed by "METHOD /path", looked up per request, with a
    second table spread in from another module that never mentions a framework."""
    root = tmp_path / "barbell"
    _write(root, "api/server.js", """
import http from 'node:http';
import { coachRoutes } from './coach/routes.js';
function listUsers(req, res) {}
const routes = {
  'GET /api/health': async (req, res) => json(res, 200, { ok: true }),
  'POST /api/login/verify': async (req, res) => {
    console.log('POST /api/login/verify called');
  },
  'GET /api/admin/users': listUsers,
  'DELETE /api/data': function (req, res) {},
  ...coachRoutes({ json }),
};
http.createServer(async (req, res) => {
  const handler = routes[req.method + ' ' + new URL(req.url, 'http://x').pathname];
}).listen(3000);
""")
    _write(root, "api/coach/routes.js", """
export function coachRoutes({ json }) {
  return {
    'GET /api/coach/status': async (req, res) => {},
    'POST /api/coach/plan': (req, res) => {},
  };
}
""")
    got = {(r.method, r.path): (r.file, r.handler) for r in extract_routes(root, analyze_repo(root).files)}
    assert got == {
        ("GET", "/api/health"): ("api/server.js", None),
        ("POST", "/api/login/verify"): ("api/server.js", None),
        ("GET", "/api/admin/users"): ("api/server.js", "listUsers"),
        ("DELETE", "/api/data"): ("api/server.js", None),
        ("GET", "/api/coach/status"): ("api/coach/routes.js", None),
        ("POST", "/api/coach/plan"): ("api/coach/routes.js", None),
    }


def test_inline_require_mount_prefix(tmp_path: Path):
    root = tmp_path / "inline"
    _write(root, "server.js", "const express = require('express');\nconst app = express();\napp.use('/api', require('./routes/items'));\n")
    _write(root, "routes/items.js", "const router = require('express').Router();\nfunction list(req, res) {}\nrouter.get('/items', list);\nmodule.exports = router;\n")
    routes = {(r.method, r.path): r.handler for r in extract_routes(root, analyze_repo(root).files)}
    assert routes == {("GET", "/api/items"): "list"}


def test_fastapi_flask_and_next_routes(tmp_path: Path):
    root = tmp_path / "py"
    _write(root, "api/users.py", """
from fastapi import APIRouter
router = APIRouter(prefix="/users")

@router.get("/{user_id}")
async def get_user(user_id: int):
    return {}

@router.post("")
def create_user():
    return {}
""")
    _write(root, "web/views.py", """
from flask import Flask
app = Flask(__name__)

@app.route("/health", methods=["GET", "HEAD"])
def health():
    return "ok"
""")
    _write(root, "site/app/api/items/[id]/route.ts", "export async function GET() {}\nexport async function DELETE() {}\n")
    _write(root, "site/app/(marketing)/api/ping/route.ts", "export const POST = async () => {};\n")
    files = analyze_repo(root).files
    got = {(r.method, r.path, r.handler) for r in extract_routes(root, files)}
    assert ("GET", "/users/{user_id}", "get_user") in got
    assert ("POST", "/users", "create_user") in got
    assert ("GET", "/health", "health") in got and ("HEAD", "/health", "health") in got
    assert ("GET", "/api/items/:id", "GET") in got and ("DELETE", "/api/items/:id", "DELETE") in got
    assert ("POST", "/api/ping", "POST") in got


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_commits_come_from_the_repository_own_git_only(tmp_path: Path):
    root = tmp_path / "outer"
    _write(root, "a.py", "x = 1\n")
    _git(root, "init", "-q")
    _git(root, "-c", "user.email=t@example.com", "-c", "user.name=T", "add", "a.py")
    _git(root, "-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-q", "-m", "first")
    _write(root, "a.py", "x = 2\n")
    _write(root, "b.py", "y = 1\n")
    _git(root, "add", "a.py", "b.py")
    _git(root, "-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-q", "-m", "second change")

    commits = mine_commits(root, {"a.py", "b.py"})
    assert [c.subject for c in commits] == ["second change", "first"]
    assert sorted(commits[0].files) == ["a.py", "b.py"] and commits[1].files == ["a.py"]

    # A directory inside that repository, with no .git of its own, must NOT inherit its history —
    # neither for commit events nor for change-coupling mining.
    inner = root / "nested"
    _write(inner, "c.py", "z = 1\n")
    assert mine_commits(inner, {"c.py"}) == []
    from backend.repository.coupling import mine_change_coupling

    assert mine_change_coupling(inner, {"a.py", "b.py", "c.py"}) == []


def test_decisions_need_manifest_evidence_and_link_importing_files(express_repo: Path):
    files = analyze_repo(express_repo).files
    by_title = {d.title: d for d in extract_decisions(express_repo, files)}
    assert "MongoDB via Mongoose" in by_title
    assert by_title["MongoDB via Mongoose"].files == ["backend/controllers/examController.js"]
    assert "backend/package.json" in by_title["MongoDB via Mongoose"].manifests
    assert by_title["JWT for authentication"].files == ["backend/controllers/userController.js"]
    assert "React for the UI" in by_title and len(by_title["React for the UI"].files) == 3
    assert "Radix UI primitives for components" in by_title
    # Nothing declared, nothing claimed.
    assert "Tailwind CSS for styling" not in by_title and "Redis" not in by_title


def test_conventions_are_observed_not_assumed(express_repo: Path):
    files = analyze_repo(express_repo).files
    routes = extract_routes(express_repo, files)
    titles = {c.title for c in extract_conventions(files, express_repo, routes)}
    assert "JavaScript in backend/, TypeScript in frontend/" in titles
    assert "CommonJS in backend/, ES modules in frontend/" in titles
    assert "REST API under /api/v1" in titles


def test_add_intent_to_graph_writes_scoped_nodes_and_valid_edges(express_repo: Path):
    graph = GraphService(repository=InMemoryGraphRepository(), event_writer=InMemoryGraphEventWriter())
    code = analyze_repo(express_repo)
    repo = graph.add_node(GraphNodeCreate(node_type=GraphNodeType.REPOSITORY, stable_id="repo://proctor",
                                          properties={"name": "proctor", "repository": "proctor"}))
    file_nodes = {f: graph.add_node(GraphNodeCreate(node_type=GraphNodeType.FILE, stable_id=f"file://proctor/{f}",
                                                    properties={"path": f, "repository": "proctor"})) for f in code.files}
    sym_nodes = {f"{s.file}#{s.name}": graph.add_node(GraphNodeCreate(
        node_type=GraphNodeType.CODE_SYMBOL, stable_id=f"symbol://proctor/{s.file}#{s.name}",
        properties={"name": s.name, "file": s.file, "repository": "proctor"})) for s in code.symbols}

    counts = add_intent_to_graph(graph, name="proctor", root=express_repo, code=code, repo_node_id=repo.id,
                                 file_nodes=file_nodes, sym_nodes=sym_nodes)
    assert counts["routes"] >= 5 and counts["decisions"] >= 4 and counts["conventions"] >= 2
    assert counts["commits"] == 0  # not a git repository

    nodes = {n.id: n for n in graph.list_nodes()}
    assert all(n.properties.get("repository") == "proctor" for n in nodes.values())
    route = next(n for n in nodes.values() if n.node_type == GraphNodeType.API_ROUTE and n.properties["path"] == "/api/v1/exam")
    out = [e for e in graph.list_edges_at() if e.from_node_id == route.id]
    assert len(out) == 1 and nodes[out[0].to_node_id].properties["name"] == "createExam"

    # Removing the repository removes everything this module added.
    graph.remove_repository("proctor")
    assert graph.list_nodes() == []
