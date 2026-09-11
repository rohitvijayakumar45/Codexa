"""Real file access — the layer agents and the IDE tab both use.

Operates on the actual repository on disk (a cloned repo under .codexa/repos/<name>, or the Codexa
project root for 'codexa-os'). Read, list, search, and write, all path-guarded so nothing escapes the
repository root. Writes are real and auditable (logged), not a staged copy.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.memory.store import DATA_DIR

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SKIP = {".git", ".codexa-repo.json", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", ".agents",
         ".codexa", "coverage", ".pytest_cache", ".turbo", ".egg-info"}
_MAX_READ = 600_000
_LANG = {
    ".py": "python", ".ts": "typescript", ".tsx": "tsx", ".js": "javascript", ".jsx": "jsx",
    ".json": "json", ".md": "markdown", ".css": "css", ".html": "html", ".yml": "yaml",
    ".yaml": "yaml", ".toml": "toml", ".sql": "sql", ".sh": "bash", ".go": "go", ".rs": "rust",
    ".java": "java", ".rb": "ruby", ".txt": "text", ".env": "bash", ".mjs": "javascript",
}


class TreeNode(BaseModel):
    name: str
    path: str
    type: str  # dir | file
    children: list["TreeNode"] | None = None


class FileContent(BaseModel):
    path: str
    language: str
    content: str
    truncated: bool


class SearchHit(BaseModel):
    path: str
    line: int
    text: str


class WriteRequest(BaseModel):
    repository: str = Field(default="codexa-os")
    path: str
    content: str


class MkdirRequest(BaseModel):
    repository: str = Field(default="codexa-os")
    path: str


class DeleteRequest(BaseModel):
    repository: str = Field(default="codexa-os")
    path: str


class MoveRequest(BaseModel):
    repository: str = Field(default="codexa-os")
    from_path: str
    to_path: str


class EditRequest(BaseModel):
    repository: str = Field(default="codexa-os")
    path: str
    old_text: str
    new_text: str


def is_platform_repo(repository: str | None) -> bool:
    """True when this name resolves to Codexa's own source tree.

    The single question every mutation guard needs to ask, answered by RESOLVING the path rather
    than by comparing the string to "codexa-os". String comparison was the whole vulnerability:
    `repository="../.."` resolves to the project root while being unequal to "codexa-os", so the
    guard passed and write_file, delete_file and apply_patch all operated on Codexa's own code.
    """
    try:
        return repo_root(repository) == PROJECT_ROOT
    except HTTPException:
        return False


def repo_root(repository: str | None) -> Path:
    """Resolve a repository name to its root, refusing anything that escapes the repository store.

    Two separate protections, both load-bearing.

    Containment: the resolved path must sit directly inside DATA_DIR/"repos". Previously this only
    checked `root.exists()`, so a caller-supplied name containing `..` produced any directory on the
    machine — `"../.."` reached the project root, `"../../.."` its parent. Repository names arrive
    from HTTP request bodies and from model-authored tool arguments, so this is reachable input, and
    every path check downstream inherits whatever root it returns: `_safe` faithfully confines
    traversal to a root that was already wrong.

    Shape: a repository is one path segment. Rejecting separators and `..` up front means the
    resolve below cannot be steered at all, rather than being steered and then caught.
    """
    if not repository or repository == "codexa-os":
        return PROJECT_ROOT

    name = repository.strip().replace("\\", "/")
    if not name or name in (".", "..") or "/" in name or name.startswith("~"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Repository names are a single path segment: no separators, no '..'.",
        )

    store = (DATA_DIR / "repos").resolve()
    root = (store / name).resolve()
    if root.parent != store:
        # Belt and braces. The shape check above should make this unreachable; it stays because this
        # function is the single choke point every file operation in the platform depends on, and a
        # wrong root here silently disarms every check that runs after it.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Repository path escapes the repository store.")
    if not root.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Repository '{repository}' is not loaded.")
    return root


def _safe(root: Path, rel: str) -> Path:
    target = (root / rel).resolve()
    if root not in target.parents and target != root:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Path escapes the repository.")
    return target


def _language(path: Path) -> str:
    return _LANG.get(path.suffix.lower(), "text")


def build_tree(root: Path, rel: str = "", depth: int = 0, budget: list[int] | None = None) -> list[TreeNode]:
    budget = budget if budget is not None else [4000]
    here = (root / rel) if rel else root
    out: list[TreeNode] = []
    try:
        entries = sorted(here.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except OSError:
        return out
    for p in entries:
        if p.name in _SKIP or p.name.startswith(".git"):
            continue
        if budget[0] <= 0:
            break
        budget[0] -= 1
        child_rel = f"{rel}/{p.name}" if rel else p.name
        if p.is_dir():
            children = build_tree(root, child_rel, depth + 1, budget) if depth < 8 else []
            out.append(TreeNode(name=p.name, path=child_rel, type="dir", children=children))
        else:
            out.append(TreeNode(name=p.name, path=child_rel, type="file"))
    return out


def read_file(root: Path, rel: str) -> FileContent:
    target = _safe(root, rel)
    if not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No such file: {rel}")
    raw = target.read_bytes()
    truncated = len(raw) > _MAX_READ
    text = raw[:_MAX_READ].decode("utf-8", errors="replace")
    return FileContent(path=rel, language=_language(target), content=text, truncated=truncated)


def search_files(root: Path, query: str, limit: int = 120) -> list[SearchHit]:
    needle = query.lower()
    hits: list[SearchHit] = []
    for p in root.rglob("*"):
        if any(part in _SKIP for part in p.relative_to(root).parts):
            continue
        if not p.is_file() or p.suffix.lower() not in _LANG:
            continue
        try:
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if needle in line.lower():
                    hits.append(SearchHit(path=str(p.relative_to(root)).replace("\\", "/"), line=i, text=line.strip()[:200]))
                    if len(hits) >= limit:
                        return hits
        except OSError:
            continue
    return hits


def write_file(root: Path, rel: str, content: str) -> None:
    target = _safe(root, rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def create_directory(root: Path, rel: str) -> None:
    target = _safe(root, rel)
    target.mkdir(parents=True, exist_ok=True)


def delete_path(root: Path, rel: str) -> None:
    target = _safe(root, rel)
    if target == root:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Refusing to delete the repository root.")
    if target.is_dir():
        if any(target.iterdir()):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Directory is not empty.")
        target.rmdir()
    elif target.is_file():
        target.unlink()
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No such path: {rel}")


def move_path(root: Path, from_rel: str, to_rel: str) -> None:
    src = _safe(root, from_rel)
    dst = _safe(root, to_rel)
    if not src.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No such path: {from_rel}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)


def edit_file(root: Path, rel: str, old_text: str, new_text: str) -> None:
    """Surgical find-replace — requires old_text to appear exactly once, same discipline as the
    editor's own Edit tool. Safer than a full-file write_file for a small, targeted change."""
    target = _safe(root, rel)
    if not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No such file: {rel}")
    text = target.read_text(encoding="utf-8", errors="replace")
    count = text.count(old_text)
    if count == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "old_text not found in file.")
    if count > 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"old_text is not unique ({count} matches) — include more context.")
    target.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")


def create_files_router() -> APIRouter:
    router = APIRouter(prefix="/files", tags=["files"])

    @router.get("/tree", response_model=list[TreeNode])
    def tree(repository: str = Query(default="codexa-os")) -> list[TreeNode]:
        return build_tree(repo_root(repository))

    @router.get("/read", response_model=FileContent)
    def read(repository: str = Query(default="codexa-os"), path: str = Query(...)) -> FileContent:
        return read_file(repo_root(repository), path)

    @router.get("/search", response_model=list[SearchHit])
    def search(repository: str = Query(default="codexa-os"), q: str = Query(..., min_length=2)) -> list[SearchHit]:
        return search_files(repo_root(repository), q)

    @router.post("/write")
    def write(request: WriteRequest) -> dict:
        write_file(repo_root(request.repository), request.path, request.content)
        return {"ok": True, "path": request.path}

    @router.post("/mkdir")
    def mkdir(request: MkdirRequest) -> dict:
        create_directory(repo_root(request.repository), request.path)
        return {"ok": True, "path": request.path}

    @router.post("/delete")
    def delete(request: DeleteRequest) -> dict:
        delete_path(repo_root(request.repository), request.path)
        return {"ok": True, "path": request.path}

    @router.post("/move")
    def move(request: MoveRequest) -> dict:
        move_path(repo_root(request.repository), request.from_path, request.to_path)
        return {"ok": True, "from_path": request.from_path, "to_path": request.to_path}

    @router.post("/edit")
    def edit(request: EditRequest) -> dict:
        edit_file(repo_root(request.repository), request.path, request.old_text, request.new_text)
        return {"ok": True, "path": request.path}

    return router
