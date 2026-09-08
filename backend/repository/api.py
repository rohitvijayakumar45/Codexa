"""Load a repository: clone it, read it for real, and write grounded memory + docs.

The earlier version stored almost nothing about a repo (just its language and file count), which let
models hallucinate. This builds a real digest — package name, dependencies, structure, README — and
writes that into permanent memory and into LLM-generated documentation, so every answer is grounded
in what the repository actually is.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.agents.llm import LLMClient
from backend.graph.schemas import (
    GraphEdgeCreate,
    GraphEdgeSourceType,
    GraphEdgeType,
    GraphNodeCreate,
    GraphNodeProvenance,
    GraphNodeType,
)
from backend.graph.service import GraphService
from backend.memory.store import DATA_DIR, MemoryStore
from backend.repository.analyze import Analysis, analyze_repo
from backend.repository.coupling import mine_change_coupling
from backend.repository.scoring import score_repository
from backend.repository.semantic import annotate_repository_symbols

_EXT_LANG = {
    ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
    ".jsx": "JavaScript", ".go": "Go", ".rs": "Rust", ".java": "Java", ".rb": "Ruby",
    ".c": "C", ".cpp": "C++", ".cs": "C#", ".php": "PHP", ".swift": "Swift", ".kt": "Kotlin",
    ".sql": "SQL", ".sh": "Shell", ".css": "CSS", ".md": "Markdown",
}
_URL_RE = re.compile(r"^(https?://|git@)[\w./:@~-]+?(\.git)?/?$")
_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", ".agents"}
_FRAMEWORK = {
    "react": "React", "react-dom": "React", "next": "Next.js", "vue": "Vue", "svelte": "Svelte",
    "react-router-dom": "React Router", "@tanstack/react-query": "React Query",
    "react-dropzone": "file uploads (react-dropzone)", "gsap": "GSAP animation",
    "framer-motion": "Framer Motion", "tailwindcss": "Tailwind CSS", "tailwind-merge": "Tailwind CSS",
    "axios": "Axios (HTTP)", "express": "Express", "fastify": "Fastify", "socket.io": "realtime (socket.io)",
    "sonner": "toasts", "three": "Three.js", "@aws-sdk/client-s3": "AWS S3", "aws-sdk": "AWS SDK",
    "prisma": "Prisma ORM", "mongoose": "MongoDB", "pg": "PostgreSQL", "redis": "Redis",
    "fastapi": "FastAPI", "flask": "Flask", "django": "Django",
}

_docs_cache: dict[str, "RepoDocs"] = {}


class LoadRepoRequest(BaseModel):
    url: str


class CreateRepoRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = ""


class RepositoryInfo(BaseModel):
    name: str
    url: str
    path: str
    file_count: int
    languages: list[str]
    already_loaded: bool
    memories_created: int


class RepoDocs(BaseModel):
    repository: str
    generated_at: datetime
    markdown: str


class RepoListing(BaseModel):
    name: str
    url: str
    loaded: bool  # already has graph data in memory right now (vs. only sitting on disk)


class DeleteRepoResponse(BaseModel):
    name: str
    nodes_removed: int
    memories_removed: int
    deleted_from_disk: bool


def _repo_name(url: str) -> str:
    tail = url.rstrip("/").split("/")[-1]
    return re.sub(r"[^\w.-]", "-", tail[:-4] if tail.endswith(".git") else tail) or "repository"


def _slugify(name: str) -> str:
    slug = re.sub(r"[^\w.-]", "-", name.strip()).strip("-")
    return slug or "project"


def _read_manifest(path: Path) -> dict:
    out: dict = {"name": None, "description": None, "deps": [], "scripts": []}
    pkg = path / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8", errors="ignore"))
            out["name"] = data.get("name")
            out["description"] = data.get("description")
            out["deps"] = list({**data.get("dependencies", {}), **data.get("devDependencies", {})}.keys())
            out["scripts"] = list(data.get("scripts", {}).keys())
        except json.JSONDecodeError:
            pass
    pyproject = path / "pyproject.toml"
    if pyproject.exists() and not out["name"]:
        text = pyproject.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'name\s*=\s*"([^"]+)"', text)
        if m:
            out["name"] = m.group(1)
    return out


def _read_readme(path: Path) -> str:
    for candidate in ("README.md", "Readme.md", "readme.md", "README.rst", "README.txt", "README"):
        rp = path / candidate
        if rp.exists():
            return rp.read_text(encoding="utf-8", errors="ignore")[:2500].strip()
    return ""


def _tree(path: Path, max_lines: int = 40) -> str:
    lines: list[str] = []
    expand = {"src", "app", "server", "lambda", "packages", "lib", "components", "pages", "api", "backend", "frontend"}
    try:
        top = sorted(p for p in path.iterdir() if p.name not in _SKIP_DIRS and not p.name.startswith("."))
    except OSError:
        return ""
    for p in top:
        lines.append(p.name + ("/" if p.is_dir() else ""))
        if p.is_dir() and p.name in expand:
            for c in sorted(p.iterdir())[:10]:
                if c.name in _SKIP_DIRS:
                    continue
                lines.append("  " + c.name + ("/" if c.is_dir() else ""))
        if len(lines) >= max_lines:
            break
    return "\n".join(lines[:max_lines])


def _analyze(path: Path) -> dict:
    lang_counts: dict[str, int] = {}
    file_count = 0
    for p in path.rglob("*"):
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        if p.is_file():
            file_count += 1
            lang = _EXT_LANG.get(p.suffix.lower())
            if lang:
                lang_counts[lang] = lang_counts.get(lang, 0) + 1
            if file_count > 8000:
                break
    manifest = _read_manifest(path)
    languages = sorted(lang_counts, key=lambda k: -lang_counts[k])
    frameworks = []
    seen = set()
    for dep in manifest["deps"]:
        label = _FRAMEWORK.get(dep)
        if label and label not in seen:
            frameworks.append(label)
            seen.add(label)
    return {
        "file_count": file_count,
        "languages": languages,
        "name": manifest["name"],
        "description": manifest["description"],
        "deps": manifest["deps"],
        "scripts": manifest["scripts"],
        "frameworks": frameworks,
        "readme": _read_readme(path),
        "tree": _tree(path),
    }


def _digest_text(name: str, url: str, d: dict) -> str:
    parts = [
        f"Repository: {name}",
        f"Package name: {d['name'] or 'n/a'}",
        f"Description: {d['description'] or 'none provided'}",
        f"Languages: {', '.join(d['languages'][:6]) or 'unknown'}",
        f"Frameworks/libraries: {', '.join(d['frameworks'][:12]) or 'n/a'}",
        f"Key dependencies: {', '.join(d['deps'][:20]) or 'n/a'}",
        f"Scripts: {', '.join(d['scripts'][:8]) or 'n/a'}",
        f"File count: {d['file_count']}",
        "Structure:\n" + (d["tree"] or "n/a"),
        "README excerpt:\n" + (d["readme"] or "No README found."),
    ]
    return "\n".join(parts)


def create_repository_router(*, store: MemoryStore, graph: GraphService, llm: LLMClient) -> APIRouter:
    router = APIRouter(prefix="/repository", tags=["repository"])

    @router.post("/load", response_model=RepositoryInfo)
    def load(request: LoadRepoRequest, background_tasks: BackgroundTasks) -> RepositoryInfo:
        url = request.url.strip()
        if not _URL_RE.match(url):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provide a valid git URL (https:// or git@).")

        name = _repo_name(url)
        dest = (DATA_DIR / "repos" / name).resolve()
        already = store.has_repository(name) and dest.exists()

        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            try:
                # Depth 250, not 1 — change-coupling mining (which files historically change
                # together, even with zero static reference) needs real commit history to work
                # from. Still far lighter than a full clone for most repos.
                subprocess.run(
                    ["git", "clone", "--depth", "250", url, str(dest)],
                    capture_output=True, text=True, timeout=180, check=True,
                )
            except FileNotFoundError as exc:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "git is not available on the server.") from exc
            except subprocess.TimeoutExpired as exc:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Clone timed out.") from exc
            except subprocess.CalledProcessError as exc:
                detail = (exc.stderr or "").strip().splitlines()[-1:] or ["clone failed"]
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Clone failed: {detail[0]}") from exc

        # Remember the source URL on disk — the in-memory graph is wiped on every backend restart,
        # so this is what lets us rebuild a repo's graph/score without the user re-pasting the URL.
        (dest / ".codexa-repo.json").write_text(json.dumps({"url": url, "name": name}), encoding="utf-8")

        info = _ingest(name, url, dest, already, store=store, graph=graph)
        # Semantic annotation is a bulk LLM pass — never block the load response on it.
        background_tasks.add_task(_run_annotation, name, dest, store, llm)
        return info

    @router.post("/create", response_model=RepositoryInfo)
    def create(request: CreateRepoRequest) -> RepositoryInfo:
        """Scaffold a brand-new, empty project — not cloned from anywhere. Lets the chat agent (or a
        user) start a repository from nothing and build it up with the write_file/create_directory
        tools, instead of every repository having to already exist somewhere as a git remote."""
        try:
            return create_local_repository(request.name, request.description, store=store, graph=graph)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    @router.get("/list", response_model=list[RepoListing])
    def list_repositories() -> list[RepoListing]:
        """Every repository sitting on disk (previously cloned or created), for switching between
        them without re-cloning — plus the platform's own always-available 'codexa-os'."""
        have = {n.properties.get("repository") for n in graph.list_nodes() if n.node_type == GraphNodeType.REPOSITORY}
        out = [RepoListing(name="codexa-os", url="", loaded=True)]
        repos_dir = DATA_DIR / "repos"
        if not repos_dir.exists():
            return out
        for dest in sorted(p for p in repos_dir.iterdir() if p.is_dir()):
            meta_path = dest / ".codexa-repo.json"
            if not meta_path.exists():
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            name = meta.get("name") or dest.name
            out.append(RepoListing(name=name, url=meta.get("url", ""), loaded=name in have))
        return out

    @router.post("/activate", response_model=RepositoryInfo)
    def activate(name: str = Query(...)) -> RepositoryInfo:
        """Switch to a repository already sitting on disk, without re-cloning or recreating it. If
        its graph data isn't in memory right now (e.g. ingestion never completed), (re)ingest it
        from the existing local copy — still zero network/clone cost."""
        if name == "codexa-os":
            return RepositoryInfo(
                name="codexa-os", url="", path="", file_count=0, languages=[],
                already_loaded=True, memories_created=0,
            )
        dest = (DATA_DIR / "repos" / name).resolve()
        if not dest.exists():
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Repository '{name}' isn't on disk.")
        url = ""
        meta_path = dest / ".codexa-repo.json"
        if meta_path.exists():
            try:
                url = json.loads(meta_path.read_text(encoding="utf-8")).get("url", "")
            except (json.JSONDecodeError, OSError):
                pass
        have = {n.properties.get("repository") for n in graph.list_nodes() if n.node_type == GraphNodeType.REPOSITORY}
        if name in have:
            d = _analyze(dest)
            return RepositoryInfo(
                name=name, url=url, path=str(dest), file_count=d["file_count"],
                languages=d["languages"], already_loaded=True, memories_created=0,
            )
        return _ingest(name, url, dest, False, store=store, graph=graph, invalidate_docs=False)

    @router.delete("/{name}", response_model=DeleteRepoResponse)
    def delete(name: str) -> DeleteRepoResponse:
        """Forget a repository entirely: its graph nodes/edges, every memory record, cached docs,
        and its on-disk copy. The platform's own 'codexa-os' can never be deleted this way."""
        if name == "codexa-os":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "codexa-os can't be deleted.")

        nodes_removed = graph.remove_repository(name)
        memories_removed = store.remove(name)
        _docs_cache.pop(name, None)

        # Resolve strictly inside DATA_DIR/repos before removing anything from disk — `name` is
        # arbitrary client input, and this guards against a crafted "../../something" traversal.
        repos_dir = (DATA_DIR / "repos").resolve()
        dest = (repos_dir / name).resolve()
        deleted_from_disk = False
        if dest.is_relative_to(repos_dir) and dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
            deleted_from_disk = not dest.exists()

        if nodes_removed == 0 and memories_removed == 0 and not deleted_from_disk:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Repository '{name}' wasn't found.")

        return DeleteRepoResponse(
            name=name, nodes_removed=nodes_removed, memories_removed=memories_removed,
            deleted_from_disk=deleted_from_disk,
        )

    @router.post("/annotate", response_model=dict)
    def annotate(repository: str = Query(...)) -> dict:
        dest = (DATA_DIR / "repos" / repository).resolve()
        if not dest.exists():
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Repository '{repository}' is not loaded.")
        return _run_annotation(repository, dest, store, llm)

    @router.get("/docs", response_model=RepoDocs)
    def repo_docs(repository: str = Query(...)) -> RepoDocs:
        if repository in _docs_cache:
            return _docs_cache[repository]
        persisted = _load_persisted_docs(store, repository)
        if persisted:
            _docs_cache[repository] = persisted
            return persisted
        return _generate_docs(repository, llm, store)

    @router.post("/docs/regenerate", response_model=RepoDocs)
    def regen_docs(repository: str = Query(...)) -> RepoDocs:
        _docs_cache.pop(repository, None)
        store.remove(repository, source="docs_cache")
        return _generate_docs(repository, llm, store)

    return router


def create_local_repository(
    name: str, description: str, *, store: MemoryStore, graph: GraphService,
) -> RepositoryInfo:
    """Scaffold a brand-new, empty project on disk and ingest it — shared by the /repository/create
    route and the create_project agent tool, so "the LLM starts a project on its own" and "a user
    starts one from the UI" go through identical, equally-real ingestion."""
    slug = _slugify(name)
    dest = (DATA_DIR / "repos" / slug).resolve()
    if dest.exists():
        raise ValueError(f"A repository named '{slug}' already exists.")

    dest.mkdir(parents=True)
    try:
        subprocess.run(["git", "init", str(dest)], capture_output=True, text=True, timeout=15, check=True)
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
        pass  # git is a nice-to-have here (history mining), not a requirement to scaffold

    if description:
        (dest / "README.md").write_text(f"# {slug}\n\n{description}\n", encoding="utf-8")

    (dest / ".codexa-repo.json").write_text(
        json.dumps({"url": "", "name": slug, "created_locally": True}), encoding="utf-8",
    )
    return _ingest(slug, "", dest, False, store=store, graph=graph)


def _run_annotation(repository: str, dest: Path, store: MemoryStore, llm: LLMClient) -> dict:
    """Re-parses (cheap) and annotates symbols whose content hash changed since the last pass."""
    from backend.repository.analyze import analyze_repo as _analyze_repo

    code = _analyze_repo(dest)
    return annotate_repository_symbols(repository, dest, code.symbols, store=store, llm=llm)


def _ingest(
    name: str, url: str, dest: Path, already: bool, *, store: MemoryStore, graph: GraphService,
    invalidate_docs: bool = True,
) -> RepositoryInfo:
    d = _analyze(dest)
    display = d["name"] or name
    primary = d["languages"][0] if d["languages"] else "unknown"

    # Rewrite this repo's memory from the fresh digest so re-loading refreshes grounding. Docs are
    # only invalidated on an explicit reload, not the automatic startup rehydration — the source
    # on disk hasn't changed then, so the persisted docs are still accurate.
    store.remove(name, source="repo_load")
    if invalidate_docs:
        _docs_cache.pop(name, None)
        store.remove(name, source="docs_cache")

    semantic = f"{display}"
    if d["description"]:
        semantic += f" — {d['description']}"
    semantic += f". A {primary} project. Key libraries: {', '.join(d['frameworks'][:8]) or ', '.join(d['deps'][:8]) or 'n/a'}."
    if d["readme"]:
        semantic += f" README: {d['readme'][:400]}"

    created = 0
    created += _mem(store, name, "semantic", f"What {display} is", semantic)
    created += _mem(store, name, "semantic", "Project structure", d["tree"] or "n/a")
    created += _mem(store, name, "organizational", "Stack & conventions",
                    f"Languages: {', '.join(d['languages'][:5]) or 'n/a'}. "
                    f"Frameworks: {', '.join(d['frameworks'][:10]) or 'n/a'}.")
    created += _mem(store, name, "procedural", "How to build & run",
                    (" · ".join(f"npm run {s}" for s in d["scripts"][:5]) if d["scripts"] else "See README."))
    origin = f"Cloned from {url}" if url else "Created locally (scaffolded from nothing, not cloned)"
    created += _mem(store, name, "episodic", "Loaded into Codexa",
                    f"{origin} on {datetime.now(UTC):%Y-%m-%d %H:%M} UTC — {d['file_count']} files.")

    # Static-analyze the source and build the knowledge graph from it: files, the functions and
    # classes they define, file imports, and the call graph between symbols. All tagged with the
    # repository so graph/architecture can scope to it.
    code = analyze_repo(dest)
    created += _mem(store, name, "semantic", "Key functions & components", _functions_summary(code))

    repo_node = graph.add_node(GraphNodeCreate(
        node_type=GraphNodeType.REPOSITORY, stable_id=f"repo://{name}",
        properties={"name": display, "url": url, "primary_language": primary,
                    "file_count": d["file_count"], "repository": name},
        provenance=GraphNodeProvenance.INTERNAL_CODE,
    ))
    file_nodes = {}
    for rel in code.files[:180]:
        file_nodes[rel] = graph.add_node(GraphNodeCreate(
            node_type=GraphNodeType.FILE, stable_id=f"file://{name}/{rel}",
            properties={"path": rel, "repository": name},
            provenance=GraphNodeProvenance.INTERNAL_CODE,
        ))
    for a, b in code.imports:
        if a in file_nodes and b in file_nodes:
            graph.add_edge(GraphEdgeCreate(
                from_node_id=file_nodes[a].id, to_node_id=file_nodes[b].id,
                edge_type=GraphEdgeType.IMPORTS, confidence=1.0,
                source_type=GraphEdgeSourceType.STATIC_ANALYSIS,
            ))
    sym_nodes = {}
    for s in code.symbols[:450]:
        key = f"{s.file}#{s.name}"
        sym_nodes[key] = graph.add_node(GraphNodeCreate(
            node_type=GraphNodeType.CODE_SYMBOL, stable_id=f"symbol://{name}/{key}",
            properties={"name": s.name, "kind": s.kind, "file": s.file, "line": s.line, "repository": name},
            provenance=GraphNodeProvenance.INTERNAL_CODE,
        ))
    for a, b in code.calls:
        if a in sym_nodes and b in sym_nodes:
            graph.add_edge(GraphEdgeCreate(
                from_node_id=sym_nodes[a].id, to_node_id=sym_nodes[b].id,
                edge_type=GraphEdgeType.CALLS, confidence=1.0,
                source_type=GraphEdgeSourceType.STATIC_ANALYSIS,
            ))

    # Git-mined change coupling: files with no import/call link at all, but that historically break
    # together (CodeScene's "hidden coupling" insight). Blast radius should catch this too. Unlike
    # imports/calls this relationship is symmetric, so it's added in both directions — changing
    # either file should surface the other, not just one way.
    for coupling in mine_change_coupling(dest, set(file_nodes.keys())):
        if coupling.file_a in file_nodes and coupling.file_b in file_nodes:
            a_id, b_id = file_nodes[coupling.file_a].id, file_nodes[coupling.file_b].id
            for from_id, to_id in ((a_id, b_id), (b_id, a_id)):
                graph.add_edge(GraphEdgeCreate(
                    from_node_id=from_id, to_node_id=to_id,
                    edge_type=GraphEdgeType.CORRELATES_WITH, confidence=coupling.strength,
                    source_type=GraphEdgeSourceType.STATIC_ANALYSIS,
                    properties={"shared_commits": coupling.shared_commits},
                ))

    # Score the repository automatically on ingestion — real metrics, reasoning, suggestions.
    scored = score_repository(dest, code)
    graph.add_node(GraphNodeCreate(
        node_type=GraphNodeType.HEALTH_METRIC, stable_id=f"health://{name}",
        properties={
            "repository": name, "metric_kind": "repository_health",
            "score": scored["score"], "components": scored["components"],
            "reasoning": scored["reasoning"], "suggestions": scored["suggestions"],
            "measured": scored["measured"],
        },
    ))
    created += _mem(store, name, "organizational", "Repository health",
                    f"Score {int(scored['score'] * 100)}/100 — "
                    + "; ".join(f"{k.replace('_', ' ')} {int(v * 100)}" for k, v in scored["components"].items()))

    # Record an ingestion snapshot so the Time Machine has a real historical marker to scrub to.
    graph.event_writer.append(
        event_type="repository.ingested",
        aggregate_id=repo_node.id,
        payload={"repository": name, "files": d["file_count"], "symbols": len(code.symbols),
                 "score": scored["score"]},
    )

    return RepositoryInfo(
        name=name, url=url, path=str(dest), file_count=d["file_count"],
        languages=d["languages"], already_loaded=already, memories_created=created,
    )


def rehydrate_repositories(*, store: MemoryStore, graph: GraphService) -> int:
    """Rebuild the graph/score for every previously-cloned repo.

    The graph is in-memory and empties on every backend restart, while `.codexa/repos/<name>`
    clones survive on disk — without this, a restart silently leaves Graph/Architecture/Repository
    score blank for any repo that isn't the seed until the user re-pastes its URL to reload it.
    """
    repos_dir = DATA_DIR / "repos"
    if not repos_dir.exists():
        return 0
    have = {n.properties.get("repository") for n in graph.list_nodes() if n.node_type == GraphNodeType.REPOSITORY}
    rebuilt = 0
    for dest in sorted(p for p in repos_dir.iterdir() if p.is_dir()):
        meta_path = dest / ".codexa-repo.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        name = meta.get("name") or dest.name
        if name in have:
            continue
        try:
            _ingest(name, meta.get("url", ""), dest, True, store=store, graph=graph, invalidate_docs=False)
            rebuilt += 1
        except Exception:  # noqa: BLE001 - one bad repo shouldn't block startup
            continue
    return rebuilt


def reindex_repository(name: str, *, store: MemoryStore, graph: GraphService) -> RepositoryInfo | None:
    """Re-parses a repository from disk and rebuilds its graph/memory footprint.

    Before this, the graph was only ever built once, at initial load (`_ingest`, above) or an
    explicit `/reload` — a chat-agent edit via write_file/edit_file/delete_file never touched it, so
    lookup_symbol/get_dependencies/find_references kept returning pre-edit results indefinitely
    after any agent-driven change. Called from the agent job loop (backend/agents/jobs.py) once a
    turn that mutated files finishes.

    Clears the repository's existing graph nodes/edges first (`remove_repository`) rather than
    relying on `_ingest`'s per-node upsert-by-stable_id alone — that leaves deleted files' and
    symbols' nodes as zombies forever, since nothing ever removes a stable_id that stopped
    reappearing. A full clear-then-rebuild is more expensive than a true incremental single-file
    reindex would be, but reuses the exact tested ingestion path instead of a second, divergent
    graph-building implementation, and repos edited through chat are typically small.
    """
    if name == "codexa-os":
        return None  # the platform's own graph is seeded once (backend/seed.py), not a repo clone
    dest = (DATA_DIR / "repos" / name).resolve()
    meta_path = dest / ".codexa-repo.json"
    if not dest.exists() or not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        meta = {}
    graph.remove_repository(name)
    return _ingest(name, meta.get("url", ""), dest, True, store=store, graph=graph, invalidate_docs=True)


def _load_persisted_docs(store: MemoryStore, repository: str) -> RepoDocs | None:
    """Recover previously-generated docs from durable memory (survives a backend restart)."""
    for record in store.list(repository=repository, memory_type="organizational"):
        if record.metadata.get("source") == "docs_cache":
            return RepoDocs(repository=repository, generated_at=record.created_at, markdown=record.content)
    return None


def _persist_docs(store: MemoryStore, docs: RepoDocs) -> None:
    store.remove(docs.repository, source="docs_cache")
    store.add(
        repository=docs.repository, memory_type="organizational", title="Generated documentation",
        content=docs.markdown, metadata={"source": "docs_cache"},
    )


def _generate_docs(repository: str, llm: LLMClient, store: MemoryStore) -> RepoDocs:
    dest = (DATA_DIR / "repos" / repository).resolve()
    if not dest.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Repository '{repository}' is not loaded.")
    d = _analyze(dest)
    digest = _digest_text(repository, "", d)
    prompt = (
        "You are writing developer documentation for a code repository. Use ONLY the facts below. "
        "Do NOT invent features, modules, or use-cases that are not supported by the facts — if "
        "something is unknown, say so. Write clean Markdown with these sections: '## Overview' (what "
        "this project actually is, inferred strictly from its package name, description, dependencies "
        "and structure), '## Tech stack', '## Project structure', '## Getting started' (from the "
        "scripts), and '## Key areas' (from the directories). Keep it concise and accurate.\n\n"
        f"FACTS:\n{digest}"
    )
    try:
        markdown = llm.generate("docs", prompt).strip()
    except Exception:  # noqa: BLE001
        markdown = _fallback_docs(repository, d)
    if not markdown:
        markdown = _fallback_docs(repository, d)
    docs = RepoDocs(repository=repository, generated_at=datetime.now(UTC), markdown=markdown)
    _docs_cache[repository] = docs
    _persist_docs(store, docs)
    return docs


def _fallback_docs(repository: str, d: dict) -> str:
    return "\n".join([
        f"# {d['name'] or repository}",
        "",
        "## Overview",
        (d["description"] or f"A {d['languages'][0] if d['languages'] else 'software'} project.")
        + f" Built with {', '.join(d['frameworks'][:6]) or 'n/a'}.",
        "",
        "## Tech stack",
        "- Languages: " + (", ".join(d["languages"][:6]) or "n/a"),
        "- Libraries: " + (", ".join(d["frameworks"][:10]) or ", ".join(d["deps"][:10]) or "n/a"),
        "",
        "## Project structure",
        "```",
        d["tree"] or "n/a",
        "```",
        "",
        "## Getting started",
        "\n".join(f"- `npm run {s}`" for s in d["scripts"][:6]) or "See the repository README.",
    ])


def _mem(store: MemoryStore, repo: str, mtype: str, title: str, content: str) -> int:
    store.add(repository=repo, memory_type=mtype, title=title, content=content, metadata={"source": "repo_load"})
    return 1


def _functions_summary(code: Analysis) -> str:
    areas: dict[str, list[str]] = {}
    for s in code.symbols:
        parts = s.file.split("/")
        area = parts[-2] if len(parts) > 1 else (parts[0] or "root")
        bucket = areas.setdefault(area, [])
        if s.name not in bucket:
            bucket.append(s.name)
    head = (
        f"{len(code.symbols)} functions/classes across {len(code.files)} source files, "
        f"{len(code.imports)} file imports, {len(code.calls)} call edges. By area:"
    )
    lines = [f"{area}/: {', '.join(names[:10])}" for area, names in sorted(areas.items())]
    return head + "\n" + "\n".join(lines[:16])
