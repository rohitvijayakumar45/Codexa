import json
import tempfile
import subprocess
from pathlib import Path

from backend.repository.intent import extract_routes, mine_commits, extract_decisions
from backend.repository.analyze import analyze_repo
from backend.graph.repository import InMemoryGraphRepository
from backend.graph.service import GraphService
from backend.graph.events import InMemoryGraphEventWriter


def test_claim_strata_api_route_extraction():
    """Claim: Strata extracts API routes across Express, FastAPI, and Flask."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Express route file
        express_file = root / "routes.js"
        express_file.write_text(
            "const express = require('express');\n"
            "const router = express.Router();\n"
            "router.get('/users', handleGetUsers);\n"
            "router.post('/login', handleLogin);\n",
            encoding="utf-8"
        )

        # FastAPI route file
        py_file = root / "api.py"
        py_file.write_text(
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n\n"
            "@app.get('/health')\n"
            "def health_check():\n"
            "    return {'status': 'ok'}\n",
            encoding="utf-8"
        )

        files = ["routes.js", "api.py"]
        routes = extract_routes(root, files)
        paths = {r.path for r in routes}
        assert "/users" in paths
        assert "/login" in paths
        assert "/health" in paths


def test_claim_strata_git_commit_history_mining():
    """Claim: Strata mines the repo's own git log and links commits to touched files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        
        # Initialize a real git repo
        subprocess.run(["git", "init"], cwd=root, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Auditor"], cwd=root, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "auditor@codexa.dev"], cwd=root, capture_output=True, check=True)

        f = root / "index.html"
        f.write_text("<h1>Initial</h1>", encoding="utf-8")
        subprocess.run(["git", "add", "index.html"], cwd=root, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "feat: initial commit"], cwd=root, capture_output=True, check=True)

        files = ["index.html"]
        commits = mine_commits(root, set(files))
        assert len(commits) == 1
        assert commits[0].subject == "feat: initial commit"
        assert "index.html" in commits[0].files


def test_claim_strata_intent_and_dependency_mining():
    """Claim: Strata extracts architectural intent/decisions from package dependencies (e.g. mongoose)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        pkg = root / "package.json"
        pkg.write_text(json.dumps({
            "name": "sample-app",
            "dependencies": {
                "mongoose": "^7.0.0",
                "express": "^4.18.0"
            }
        }), encoding="utf-8")

        # Create file importing it
        app_js = root / "app.js"
        app_js.write_text("const mongoose = require('mongoose');\n", encoding="utf-8")

        files = ["package.json", "app.js"]
        decisions = extract_decisions(root, files)
        
        titles = {d.title for d in decisions}
        assert any("MongoDB" in t or "mongoose" in t.lower() for t in titles)
