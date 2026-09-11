"""Load a repository: clone it, read it for real, and write grounded memory + docs.

The earlier version stored almost nothing about a repo (just its language and file count), which let
models hallucinate. This builds a real digest — package name, dependencies, structure, README — and
writes that into permanent memory and into LLM-generated documentation, so every answer is grounded
in what the repository actually is.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import stat
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

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
from backend.repository.intent import add_intent_to_graph
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
    tail = url.rstrip("/").replace(":", "/").split("/")[-1]
    return re.sub(r"[^\w.-]", "-", tail[:-4] if tail.endswith(".git") else tail) or "repository"


# Hosts whose web UI puts the repository at exactly /owner/repo, with everything after it (/tree/main,
# /blob/..., /pulls) being pages ABOUT the repository rather than part of its clone URL. GitLab nests
# groups arbitrarily deep, so there the repository path ends where its UI's "/-/" separator begins.
_OWNER_REPO_HOSTS = ("github.com", "bitbucket.org")
_CLONE_TIMEOUT = 600
_GRAPH_MAX_FILES = 800
_GRAPH_MAX_SYMBOLS = 3000
_CLONE_ATTEMPTS = 3
# Failures that are about the DOWNLOAD, not the repository: the connection dropped, or the pack git
# was indexing came out truncated/disturbed ("fetch-pack: invalid index-pack output", seen live on a
# repository that cloned fine seconds later). Worth another attempt; "not found" never is.
_TRANSIENT_MARKERS = (
    "index-pack", "fetch-pack", "early eof", "rpc failed", "unexpected disconnect",
    "remote end hung up", "connection reset", "connection was reset", "curl 18", "curl 56",
    "curl 92", "operation timed out", "transfer closed", "unpack-objects failed",
)


class CloneError(Exception):
    """A load that failed for a reason the user can act on; the message is shown to them verbatim."""


def _normalize_url(raw: str) -> str | None:
    """The clone URL for whatever the user pasted, or None if it isn't one.

    People paste what their browser shows: `https://github.com/owner/repo/tree/main`, or
    `github.com/owner/repo` with no scheme. Handing those to git verbatim failed ("repository
    '.../tree/main/' not found") or was rejected outright, so normalise them to the repository root.
    """
    url = raw.strip().strip("<>\"'").strip()
    if not url:
        return None
    if url.startswith("git@"):
        return url if _URL_RE.match(url) else None
    if not re.match(r"^https?://", url, re.I):
        if not re.match(r"^(www\.)?[\w.-]+\.[a-z]{2,}(:\d+)?/[\w.~-]+/[\w.~-]+", url, re.I):
            return None
        url = "https://" + url
    parts = urlsplit(url)
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    segs = [seg for seg in parts.path.split("/") if seg]
    if host in _OWNER_REPO_HOSTS:
        segs = segs[:2]
    elif host == "gitlab.com" and "-" in segs:
        segs = segs[: segs.index("-")]
    if len(segs) < 2:
        return None
    candidate = f"{parts.scheme.lower()}://{host}/{'/'.join(segs)}"
    return candidate if _URL_RE.match(candidate) else None


def _canonical(url: str) -> str:
    """Comparable identity for a repository URL: host/owner/repo, lower-cased, no .git, no scheme."""
    u = url.strip().lower()
    u = re.sub(r"^(https?://|git@)", "", u).replace(":", "/")
    u = u[4:] if u.startswith("www.") else u
    u = u.rstrip("/")
    return u[:-4] if u.endswith(".git") else u


def _owner(url: str) -> str:
    segs = [seg for seg in re.split(r"[/:]", _canonical(url)) if seg]
    return re.sub(r"[^\w.-]", "-", segs[-2]) if len(segs) >= 3 else ""


def _clone_error_message(stderr: str) -> str:
    """git's stderr, turned into one sentence that says what to do. Its LAST line is usually the
    useless "Cloning into '...'" preamble, which is what the old message showed."""
    low = stderr.lower()
    if any(k in low for k in ("repository not found", "could not read username", "authentication failed",
                              "terminal prompts disabled", "access denied", "403")):
        return "Repository not found, or it's private. Check the URL — only public repositories can be cloned without credentials."
    if "could not resolve host" in low or "failed to connect" in low or "timed out" in low:
        return "Couldn't reach the git host. Check your network connection and try again."
    if any(k in low for k in _TRANSIENT_MARKERS):
        return (
            "The download from the git host kept getting interrupted before git could finish "
            "(a flaky connection, or antivirus scanning the files as they arrive). Try again in a moment."
        )
    if "filename too long" in low:
        return "The repository contains paths too long for this system to check out."
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    useful = next((line for line in lines if line.lower().startswith(("fatal:", "error:"))), None)
    if useful is None:
        useful = next((line for line in reversed(lines) if not line.lower().startswith("cloning into")), None)
    return f"Clone failed: {useful}" if useful else "Clone failed: git exited with an error and gave no reason."


def _git_clone(url: str, dest: Path) -> None:
    """Clone `url` into `dest`, raising CloneError with an actionable message on any failure.

    Credential prompts are disabled: a private or mistyped URL used to make git wait on a terminal
    prompt (or pop a Git Credential Manager window) until the timeout. Now it fails in a second.
    `core.longpaths` lets deep JavaScript trees check out on Windows.
    """
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    # Depth 250, not 1 — change-coupling mining and commit history need real history to work from.
    base = ["git", "-c", "core.longpaths=true", "-c", "credential.interactive=never"]
    tail = ["clone", "--depth", "250", url, str(dest)]
    for attempt in range(1, _CLONE_ATTEMPTS + 1):
        if dest.exists():
            _discard(dest)  # a failed attempt leaves a partial checkout behind
        # The last try drops to HTTP/1.1: "unexpected disconnect while reading sideband packet" on
        # HTTP/2 was one of the failures seen live on encode/httpx, twice in a row.
        cmd = base + (["-c", "http.version=HTTP/1.1"] if attempt == _CLONE_ATTEMPTS else []) + tail
        try:
            subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=_CLONE_TIMEOUT, check=True, env=env)
            return
        except FileNotFoundError as exc:
            raise CloneError("git isn't installed on the server, so repositories can't be cloned.") from exc
        except subprocess.TimeoutExpired as exc:
            raise CloneError(f"The clone took longer than {_CLONE_TIMEOUT // 60} minutes and was stopped — the repository may be very large.") from exc
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr or ""
            # No reason at all is treated as transient too: seen live as the second of three failed
            # attempts on a repository that then cloned fine ("git exited with an error and gave no
            # reason"). A real refusal (not found, private) always says so.
            silent = not any(line.strip() and not line.lower().startswith("cloning into")
                             for line in stderr.splitlines())
            transient = silent or any(k in stderr.lower() for k in _TRANSIENT_MARKERS)
            if transient and attempt < _CLONE_ATTEMPTS:
                logging.getLogger(__name__).warning("clone attempt %d of %s failed transiently: %s",
                                                    attempt, url, stderr.strip().splitlines()[-1:] or "")
                # Longer than the 2s/4s it was: GitHub's flaky spells last several seconds, and all
                # three attempts on httpx landed inside one.
                time.sleep(5 * attempt)
                continue
            raise CloneError(_clone_error_message(stderr)) from exc


def _clone_tmp_root() -> Path:
    """Where clones are written before being moved into `.codexa/repos/`. Deliberately the system temp
    folder, NOT the repository folder: Codexa lives inside OneDrive, and OneDrive's filter driver
    scanning a pack file while git is still indexing it is a known way to get "fetch-pack: invalid
    index-pack output". Git gets an unsynced folder to write in; only the finished checkout moves."""
    root = Path(tempfile.gettempdir()) / "codexa-clones"
    root.mkdir(parents=True, exist_ok=True)
    return root


_LOAD_LOCKS: dict[str, threading.Lock] = {}
_LOAD_LOCKS_GUARD = threading.Lock()


def _lock_for(name: str) -> threading.Lock:
    """One load per repository at a time — a double-clicked "Clone" must not race itself."""
    with _LOAD_LOCKS_GUARD:
        return _LOAD_LOCKS.setdefault(name, threading.Lock())


def _read_meta(dest: Path) -> dict | None:
    try:
        return json.loads((dest / ".codexa-repo.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _is_healthy_clone(dest: Path) -> bool:
    """Whether `dest` is a genuine, complete git checkout — not merely a directory that exists.

    The specific failure this guards against: `git clone` interrupted mid-operation (observed live
    — a backend restart landing while a clone subprocess was running) leaves a `.git` directory
    behind with no working tree and a HEAD that cannot resolve. `dest.exists()` is true for that
    directory exactly as it is for a healthy one, so a check that stops there cannot tell them
    apart — which is how a broken clone gets ingested as an empty repository and then silently
    re-ingested as the same empty repository on every later load of the same URL.

    `rev-parse HEAD` alone is NOT enough, and shipping it alone was itself a bug, caught the first
    time this ran against a real broken clone rather than a synthetic one: every cloned repository
    lives under `.codexa/repos/`, which is itself INSIDE Codexa's own git-tracked working tree. When
    a nested clone's own `.git` is broken, git does not fail — it walks UP the directory tree
    looking for a valid repository, exactly as it is designed to when you run a git command from a
    subdirectory of a real repo, and finds Codexa's own `.git` several levels above. `rev-parse
    HEAD` then happily returns Codexa's own commit hash, and this function would report a
    genuinely empty, broken clone as healthy — the opposite of what it exists to catch, and worse
    than never having the check at all, because it looks confirmed rather than merely unverified.
    `--show-toplevel` names which repository git actually resolved; requiring it to equal `dest`
    itself (not an ancestor of it) is what makes this immune to that walk-up.
    """
    if not (dest / ".git").exists():
        return False
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(dest),
            capture_output=True, text=True, timeout=10,
        )
        if head.returncode != 0:
            return False
        toplevel = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=str(dest),
            capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    if toplevel.returncode != 0:
        return False
    try:
        resolved_top = Path(toplevel.stdout.strip()).resolve()
    except OSError:
        return False
    return resolved_top == dest.resolve()


# Same retry shape as jobs.py's checkpoint write (_CHECKPOINT_ATTEMPTS/_CHECKPOINT_RETRY_DELAY) —
# used again below for the final rename, not just the delete. Cloning straight into `dest` (even
# after successfully deleting a prior broken clone there) was tried first and reproduced the same
# failure it was meant to fix: `git clone` died almost immediately, its only stderr line being its
# own opening "Cloning into '...'" — the signature of a process that failed to acquire the
# directory it had just been told was empty. This repository lives inside an actively-synced
# OneDrive folder, and the most likely explanation is OneDrive's own filter driver touching a path
# in the instant after it is deleted and before git's mkdir on that same path completes. Cloning
# into a brand-new, never-before-existing temp path sidesteps that race entirely — nothing has ever
# touched it, so there is nothing to contend with — and only the final swap (delete the old
# directory, rename the temp one into place) ever operates on `dest` itself, with its own retry.
def _replace_directory(tmp: Path, dest: Path) -> None:
    if dest.exists():
        _remove_directory(dest)
    last_exc: OSError | None = None
    for attempt in range(_RMTREE_ATTEMPTS):
        try:
            tmp.rename(dest)
            return
        except OSError as exc:
            last_exc = exc
            if getattr(exc, "winerror", None) == 17 or getattr(exc, "errno", None) == 18:
                break  # different volume: rename can never work, copy instead
            time.sleep(_RMTREE_RETRY_DELAY)
    try:
        shutil.move(str(tmp), str(dest))
        return
    except OSError as exc:
        last_exc = exc
    raise last_exc or OSError(f"could not move {tmp} into place at {dest}")
# the same class of problem, a different file. `shutil.rmtree(..., ignore_errors=True)` was the
# first version of this and it is what let the actual bug through: on Windows a `.git` file can be
# held open by a scanner, an indexer, or the just-finished git process itself for a handful of
# milliseconds after it exits, `ignore_errors=True` swallows that instead of surfacing it, and the
# code proceeded straight to `git clone` into a directory that LOOKED removed but was not — which
# `git clone` then correctly refuses ("destination path already exists and is not an empty
# directory"), one line of which became a confusing, contextless "Clone failed: Cloning into
# '...'" instead of a clear explanation. Retrying the delete a few times resolves the same
# transient hold a checkpoint write already retries around; actually checking it worked, rather
# than trusting `ignore_errors`, is what turns a silent failure into either a clean success or a
# real error message.
_RMTREE_ATTEMPTS = 10
# 0.05s (250ms total) was the first value here and it was too short — live, against a real broken
# clone's pack directory, deleting it failed with WinError 5 ("Access is denied") on a freshly
# git-written `tmp_pack_*` file with no git process holding it: nothing pathological, just
# OneDrive's own sync engine scanning a directory tree of many small object files immediately after
# git finished writing them, for longer than 250ms. 0.2s x 10 = 2s total gives that scan room to
# finish without making a genuinely stuck case (a real permission problem, a file held open by
# something else entirely) hang for an unreasonable share of the HTTP request's own timeout.
_RMTREE_RETRY_DELAY = 0.2


def _make_writable(func, path, _exc) -> None:
    """rmtree error hook: git writes its pack files and indexes READ-ONLY, and on Windows a read-only
    file cannot be deleted. That alone made every re-clone fail with "[WinError 5] Access is denied"
    on `.git/objects/pack/*.idx` — after deleting everything else in the old checkout, so each
    failed attempt also destroyed the working copy it was replacing. Clear the flag and retry."""
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        func(path)
    except FileNotFoundError:
        pass


def _discard(path: Path) -> None:
    """Best-effort removal of a temp or leftover directory; logs instead of raising."""
    try:
        _remove_directory(path)
    except OSError:
        logging.getLogger(__name__).warning("could not remove %s", path, exc_info=True)


def _remove_directory(dest: Path) -> None:
    """Delete `dest` and confirm it is actually gone before returning. Raises OSError (the last
    real one seen) if it still exists after every retry — never silently leaves a partial directory
    behind for the caller to clone into."""
    last_exc: OSError | None = None
    for attempt in range(_RMTREE_ATTEMPTS):
        try:
            shutil.rmtree(dest, onexc=_make_writable)
        except FileNotFoundError:
            return
        except OSError as exc:
            last_exc = exc
        if not dest.exists():
            return
        time.sleep(_RMTREE_RETRY_DELAY)
    raise last_exc or OSError(f"could not remove {dest}")


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
        try:
            info, dest = load_repository(request.url, store=store, graph=graph)
        except (ValueError, CloneError) as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        # Semantic annotation is a bulk LLM pass — never block the load response on it.
        background_tasks.add_task(_run_annotation, info.name, dest, store, llm)
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
            try:
                _remove_directory(dest)
            except OSError:
                logging.getLogger(__name__).warning("could not delete %s", dest, exc_info=True)
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


def _destination(url: str, repos_dir: Path) -> str:
    """The folder name to clone `url` into. Reuses the plain repository name when that folder is
    free, is already this repository's clone, or is a broken clone (a `.git` that no longer resolves
    — safe to replace). Anything else living there (a different repository with the same name, or a
    project the agent created locally) is never overwritten: use `owner-repo` instead."""
    base = _repo_name(url)
    candidates = [base] + ([f"{_owner(url)}-{base}"] if _owner(url) else []) + [f"{base}-{i}" for i in range(2, 50)]
    for name in candidates:
        dest = repos_dir / name
        if not dest.exists():
            return name
        meta = _read_meta(dest)
        if meta and meta.get("url") and _canonical(meta["url"]) == _canonical(url):
            return name
        if meta is None and (dest / ".git").exists() and not _is_healthy_clone(dest):
            return name
    raise CloneError(f"Too many folders already named like '{base}'. Delete an old one and try again.")


def load_repository(raw_url: str, *, store: MemoryStore, graph: GraphService) -> tuple[RepositoryInfo, Path]:
    """Clone (or reuse) a repository and ingest it — the whole /repository/load pipeline.

    Order of operations, each step leaving the disk consistent if the next one fails:
      1. normalise the URL and pick a folder that is safe to use;
      2. under a per-repository lock, sweep temp clones a previous failed load left behind;
      3. if there is no healthy checkout, clone into a brand-new temp folder (OneDrive-safe) and only
         then swap it into place — a failed clone never touches the existing folder;
      4. record the URL, then ingest (graph, memory, routes, commits, intent, health).
    """
    url = _normalize_url(raw_url)
    if url is None:
        raise ValueError("That doesn't look like a git URL. Paste something like https://github.com/owner/repo — a GitHub page URL works too.")
    repos_dir = (DATA_DIR / "repos").resolve()
    repos_dir.mkdir(parents=True, exist_ok=True)
    name = _destination(url, repos_dir)
    dest = repos_dir / name
    with _lock_for(name):
        tmp_root = _clone_tmp_root()
        for stale in [*repos_dir.glob(f".{name}.load-*"), *tmp_root.glob(f"{name}.load-*")]:
            _discard(stale)
        healthy_on_disk = dest.exists() and _is_healthy_clone(dest)
        already = store.has_repository(name) and healthy_on_disk
        if not healthy_on_disk:
            tmp_dest = tmp_root / f"{name}.load-{uuid.uuid4().hex[:8]}"
            try:
                _git_clone(url, tmp_dest)
                if not _is_healthy_clone(tmp_dest):
                    raise CloneError("The clone finished but produced no usable checkout — the repository may be empty.")
                try:
                    _replace_directory(tmp_dest, dest)
                except OSError as exc:
                    raise CloneError(
                        f"Cloned {name}, but couldn't move it into place ({exc}). Close anything that has "
                        "files from that folder open, then try again."
                    ) from exc
            finally:
                if tmp_dest.exists():
                    _discard(tmp_dest)
        # Remember the source URL on disk — the in-memory graph is wiped on every backend restart,
        # so this is what lets us rebuild a repo's graph/score without the user re-pasting the URL.
        (dest / ".codexa-repo.json").write_text(json.dumps({"url": url, "name": name}), encoding="utf-8")
        if already or store.has_repository(name):
            # Re-loading replaces the repository's graph rather than piling a second copy on top.
            graph.remove_repository(name)
        try:
            info = _ingest(name, url, dest, already, store=store, graph=graph)
        except Exception as exc:  # noqa: BLE001 - report it; the clone itself is kept for a retry
            logging.getLogger(__name__).exception("ingestion failed for %s", name)
            raise CloneError(f"Cloned {name}, but analysing it failed: {exc}") from exc
    return info, dest


def _run_annotation(repository: str, dest: Path, store: MemoryStore, llm: LLMClient) -> dict:
    """Re-parses (cheap) and annotates symbols whose content hash changed since the last pass."""
    from backend.repository.analyze import analyze_repo as _analyze_repo

    code = _analyze_repo(dest)
    return annotate_repository_symbols(repository, dest, code.symbols, store=store, llm=llm, calls=code.calls)


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
    # Graph caps (were 180 files / 450 symbols, which left a third of httpx unmapped). Sized for
    # mid-sized repositories; the parser's own caps are in analyze.py.
    for rel in code.files[:_GRAPH_MAX_FILES]:
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
    for s in code.symbols[:_GRAPH_MAX_SYMBOLS]:
        key = f"{s.file}#{s.qualname or s.name}"
        sym_nodes[key] = graph.add_node(GraphNodeCreate(
            node_type=GraphNodeType.CODE_SYMBOL, stable_id=f"symbol://{name}/{key}",
            properties={"name": s.name, "qualname": s.qualname or s.name, "kind": s.kind, "file": s.file,
                        "line": s.line, "repository": name},
            provenance=GraphNodeProvenance.INTERNAL_CODE,
        ))
    for a, b in code.calls:
        if a in sym_nodes and b in sym_nodes:
            graph.add_edge(GraphEdgeCreate(
                from_node_id=sym_nodes[a].id, to_node_id=sym_nodes[b].id,
                edge_type=GraphEdgeType.CALLS, confidence=1.0,
                source_type=GraphEdgeSourceType.STATIC_ANALYSIS,
            ))

    # API routes, commit history and dependency-evidenced intent (intent.py). Extras, not the core
    # graph: a failure here is logged and ingestion carries on with what it already has.
    try:
        add_intent_to_graph(graph, name=name, root=dest, code=code, repo_node_id=repo_node.id,
                            file_nodes=file_nodes, sym_nodes=sym_nodes)
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).exception("intent extraction failed for %s", name)

    # Git-mined change coupling: files with no import/call link at all, but that historically break
    # together (CodeScene's "hidden coupling" insight). Blast radius should catch this too. Unlike
    # imports/calls this relationship is symmetric, so it's added in both directions — changing
    # either file should surface the other, not just one way.
    #
    # That two files changed together is a fact read straight from git, so the edge is static
    # analysis at confidence 1.0; HOW strongly they are coupled is a property. Writing the strength
    # into `confidence` (the first version) violated the static-analysis invariant, so every
    # repository with enough history to produce a coupling pair crashed mid-ingestion and was left
    # half-loaded — which is why cloning worked for tiny repos and failed for real ones.
    try:
        for coupling in mine_change_coupling(dest, set(file_nodes.keys())):
            if coupling.file_a in file_nodes and coupling.file_b in file_nodes:
                a_id, b_id = file_nodes[coupling.file_a].id, file_nodes[coupling.file_b].id
                for from_id, to_id in ((a_id, b_id), (b_id, a_id)):
                    graph.add_edge(GraphEdgeCreate(
                        from_node_id=from_id, to_node_id=to_id,
                        edge_type=GraphEdgeType.CORRELATES_WITH, confidence=1.0,
                        source_type=GraphEdgeSourceType.STATIC_ANALYSIS,
                        properties={"strength": coupling.strength, "shared_commits": coupling.shared_commits,
                                    "relation": "changes_with"},
                    ))
    except Exception:  # noqa: BLE001 - an extra, like intent: never sink the whole load
        logging.getLogger(__name__).exception("change-coupling mining failed for %s", name)

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
    # Temp clones from a load that crashed or failed before the fix that cleans them up. Nothing is
    # loading at startup, so every one of them is garbage.
    for stale in [*repos_dir.glob(".*.load-*"), *_clone_tmp_root().glob("*.load-*")]:
        _discard(stale)
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


_ANNOTATING: set[str] = set()
_ANNOTATING_GUARD = threading.Lock()


def _refresh_annotations_async(name: str, dest: Path, store: MemoryStore, llm: LLMClient) -> None:
    """Re-explain only the functions an edit changed, in the background (unchanged ones are reused by
    fingerprint). One pass per repository at a time; an edit arriving mid-pass is picked up by the
    next edit's pass."""
    with _ANNOTATING_GUARD:
        if name in _ANNOTATING:
            return
        _ANNOTATING.add(name)

    def run() -> None:
        try:
            _run_annotation(name, dest, store, llm)
        except Exception:  # noqa: BLE001 - a failed refresh leaves the graph correct, meanings sparser
            logging.getLogger(__name__).exception("annotation refresh failed for %s", name)
        finally:
            with _ANNOTATING_GUARD:
                _ANNOTATING.discard(name)

    threading.Thread(target=run, name=f"annotate-{name}", daemon=True).start()


def reindex_repository(
    name: str, *, store: MemoryStore, graph: GraphService, llm: LLMClient | None = None,
) -> RepositoryInfo | None:
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
    info = _ingest(name, meta.get("url", ""), dest, True, store=store, graph=graph, invalidate_docs=True)
    # Function meanings follow edits too: without this they were refreshed only on a full reload, and
    # context served the old sentence for a function whose code had changed.
    if llm is not None:
        _refresh_annotations_async(name, dest, store, llm)
    return info


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
