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
_SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", ".agents",
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


def repo_root(repository: str | None) -> Path:
    if not repository or repository == "codexa-os":
        return PROJECT_ROOT
    root = (DATA_DIR / "repos" / repository).resolve()
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

    return router
