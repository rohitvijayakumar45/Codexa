"""Routes, history and intent for an ingested repository — extracted, never invented.

Static analysis (analyze.py) gives the graph files, symbols, imports and calls. That leaves three
bands of the Strata view empty for every real repository: the API surface, the change history, and
the "why". This module fills them from evidence on disk only:

  - API routes   Express (`router.route('/x').post(h)`, `app.get('/x', h)`, `app.use('/prefix', r)`),
                 FastAPI / Flask decorators (with APIRouter / Blueprint prefixes) and Next.js route
                 files. Each route links to the handler symbol it names, when that can be resolved.
  - Commits      `git log` of the repository's OWN git directory — never a parent repo's (a clone
                 without its own `.git` makes git walk up into Codexa's history; that is refused).
                 Each commit links to the files it changed, dated when it happened.
  - Intent       Decisions evidenced by declared dependencies ("MongoDB via Mongoose" because
                 `mongoose` is in backend/package.json), linked to the files that actually import
                 them; conventions observed in the code itself (language split, module system, the
                 shared API prefix).

Nothing here is inferred by a model and nothing is guessed: no evidence, no node.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath

from backend.graph.schemas import (
    GraphEdgeCreate,
    GraphEdgeSourceType,
    GraphEdgeType,
    GraphNodeCreate,
    GraphNodeProvenance,
    GraphNodeType,
)
from backend.graph.service import GraphService
from backend.repository.analyze import Analysis

log = logging.getLogger(__name__)

_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", ".agents", "coverage"}
_JS_EXT = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")
_MAX_ROUTES = 150
_MAX_COMMITS = 40
_MAX_FILES_PER_COMMIT = 40
_MAX_FILES_PER_DECISION = 60
_MAX_READ = 200_000


@dataclass
class Route:
    method: str
    path: str
    file: str
    line: int
    handler: str | None = None


@dataclass
class Commit:
    sha: str
    at: datetime
    subject: str
    author: str
    files: list[str] = field(default_factory=list)
    total_files: int = 0  # every known file the commit changed; `files` is capped for edges


@dataclass
class Decision:
    slug: str
    title: str
    category: str
    packages: list[str]
    manifests: list[str]
    files: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        where = ", ".join(self.manifests)
        return f"{self.title}: declared in {where} ({', '.join(self.packages)})."


@dataclass
class Convention:
    slug: str
    title: str
    summary: str


def _read(root: Path, rel: str) -> str:
    p = root / rel
    try:
        if p.stat().st_size > _MAX_READ:
            return ""
        return p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _join(prefix: str, path: str) -> str:
    joined = "/" + "/".join(s for s in (prefix.strip("/") + "/" + path.strip("/")).split("/") if s)
    return joined


def _last_identifier(args: str) -> str | None:
    """Express handlers come last: `protect, adminOnly, createExam` -> createExam. An inline arrow
    function or anything that isn't a bare identifier yields None."""
    if "(" in args or "=>" in args or "function" in args:
        return None  # an inline handler (arrow function / function expression), not a named one
    parts = [a.strip() for a in args.split(",") if a.strip()]
    if not parts:
        return None
    last = parts[-1]
    return last if re.fullmatch(r"[A-Za-z_$][\w$]*(\.[A-Za-z_$][\w$]*)?", last) else None


def _resolve_js(spec: str, from_file: str, files: set[str]) -> str | None:
    base = PurePosixPath(from_file).parent
    target = PurePosixPath(os.path.normpath(str(base / spec)).replace("\\", "/"))
    candidates = [str(target)]
    for ext in _JS_EXT:
        candidates += [f"{target}{ext}", f"{target}/index{ext}"]
    return next((c for c in candidates if c in files), None)


# ---- Routes -------------------------------------------------------------------------------------

_REQ_RE = re.compile(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*require\(\s*['\"](\.[^'\"]+)['\"]\s*\)")
_IMP_RE = re.compile(r"import\s+([A-Za-z_$][\w$]*)\s+from\s+['\"](\.[^'\"]+)['\"]")
_USE_RE = re.compile(r"\.use\(\s*['\"`]([^'\"`]+)['\"`]\s*,([^)]*)\)")
_CHAIN_RE = re.compile(
    r"\b[A-Za-z_$][\w$]*\.route\(\s*['\"`]([^'\"`]+)['\"`]\s*\)((?:\s*\.\s*(?:get|post|put|patch|delete|all)\s*\([^)]*\))+)"
)
_CHAIN_STEP_RE = re.compile(r"\.\s*(get|post|put|patch|delete|all)\s*\(([^)]*)\)")
_DIRECT_RE = re.compile(
    r"\b(app|router|server|api|[A-Za-z_$][\w$]*Router)\.(get|post|put|patch|delete)\(\s*['\"`](/[^'\"`]*)['\"`]\s*(?:,([^)]*))?\)"
)
_SERVER_HINT_RE = re.compile(r"\bexpress\b|Router\(|\bfastify\b|koa-router|@koa/router")
# A dispatch table keyed by "METHOD /path" — the plain `http.createServer` style, where the server
# looks up `routes[req.method + ' ' + pathname]`:  'GET /api/health': async (req, res) => {...}
# The key must be followed by `:` and a handler (an identifier, a function, or an arrow), so a
# "GET /x" that merely appears in a log line or a comment is never mistaken for a route.
_TABLE_RE = re.compile(
    r"['\"`](GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|ALL)\s+(/[^'\"`\s]*)['\"`]\s*:\s*"
    r"(async\s+)?(function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>|[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)"
)
_PY_DECO_RE = re.compile(
    r"@([A-Za-z_]\w*)\.(get|post|put|patch|delete|route|api_route)\(\s*['\"]([^'\"]*)['\"]([^)]*)\)\s*\n(?:\s*@[^\n]*\n)*\s*(?:async\s+)?def\s+([A-Za-z_]\w*)"
)
_PY_PREFIX_RE = re.compile(r"([A-Za-z_]\w*)\s*=\s*(?:APIRouter|Blueprint)\([^)]*?(?:url_)?prefix\s*=\s*['\"]([^'\"]+)['\"]")
_PY_METHODS_RE = re.compile(r"methods\s*=\s*\[([^\]]*)\]")
_NEXT_APP_RE = re.compile(r"(?:^|/)app/(.*?)/?route\.(?:ts|js|tsx|jsx)$")
_NEXT_PAGES_RE = re.compile(r"(?:^|/)pages/api/(.*)\.(?:ts|js|tsx|jsx)$")
_NEXT_EXPORT_RE = re.compile(r"export\s+(?:async\s+)?(?:function|const)\s+(GET|POST|PUT|PATCH|DELETE)\b")


def extract_routes(root: Path, files: list[str]) -> list[Route]:
    fileset = set(files)
    texts = {f: _read(root, f) for f in files if f.endswith(_JS_EXT) or f.endswith(".py")}

    # Express mount prefixes: `const exams = require('./routes/examroute')` + `app.use('/api/v1', exams)`.
    prefix: dict[str, str] = {}
    for f, text in texts.items():
        if not f.endswith(_JS_EXT):
            continue
        var_file: dict[str, str] = {}
        for m in list(_REQ_RE.finditer(text)) + list(_IMP_RE.finditer(text)):
            target = _resolve_js(m.group(2), f, fileset)
            if target:
                var_file[m.group(1)] = target
        for m in _USE_RE.finditer(text):
            ident = _last_identifier(m.group(2))
            inline = re.search(r"require\(\s*['\"](\.[^'\"]+)['\"]", m.group(2))
            target = var_file.get(ident or "") or (_resolve_js(inline.group(1), f, fileset) if inline else None)
            if target:
                prefix[target] = m.group(1)

    routes: list[Route] = []
    seen: set[tuple[str, str]] = set()

    def add(method: str, path: str, file: str, line: int, handler: str | None) -> None:
        key = (method.upper(), path)
        if key in seen or len(routes) >= _MAX_ROUTES:
            return
        seen.add(key)
        routes.append(Route(method=method.upper(), path=path, file=file, line=line, handler=handler))

    for f, text in texts.items():
        if f.endswith(_JS_EXT):
            nxt = _NEXT_APP_RE.search(f)
            pages = _NEXT_PAGES_RE.search(f)
            if nxt or pages:
                raw = nxt.group(1) if nxt else "api/" + pages.group(1)
                segs = [s for s in raw.split("/") if s and not (s.startswith("(") and s.endswith(")"))]
                if segs and segs[-1] == "index":
                    segs = segs[:-1]
                path = "/" + "/".join(re.sub(r"^\[\.{0,3}(.+?)\]$", r":\1", s) for s in segs)
                methods = _NEXT_EXPORT_RE.findall(text) or (["ANY"] if pages else [])
                for meth in methods:
                    add(meth, path, f, 1, meth if nxt else None)
                continue
            for m in _TABLE_RE.finditer(text):
                value = m.group(4)
                named = value if re.fullmatch(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?", value) and value != "function" else None
                add("ANY" if m.group(1) == "ALL" else m.group(1), m.group(2), f, _line_of(text, m.start()), named)
            if not _SERVER_HINT_RE.search(text):
                continue  # an HTTP *client* (axios.get('/api/...')) is not a route definition
            pre = prefix.get(f, "")
            for m in _CHAIN_RE.finditer(text):
                for step in _CHAIN_STEP_RE.finditer(m.group(2)):
                    meth = step.group(1)
                    add("ANY" if meth == "all" else meth, _join(pre, m.group(1)), f, _line_of(text, m.start()), _last_identifier(step.group(2)))
            for m in _DIRECT_RE.finditer(text):
                add(m.group(2), _join(pre, m.group(3)), f, _line_of(text, m.start()), _last_identifier(m.group(4) or ""))
        else:
            prefixes = {m.group(1): m.group(2) for m in _PY_PREFIX_RE.finditer(text)}
            for m in _PY_DECO_RE.finditer(text):
                obj, kind, path, rest, fn = m.groups()
                if kind in ("route", "api_route"):
                    ms = _PY_METHODS_RE.search(rest)
                    methods = re.findall(r"['\"](\w+)['\"]", ms.group(1)) if ms else ["GET"]
                else:
                    methods = [kind]
                for meth in methods:
                    add(meth, _join(prefixes.get(obj, ""), path), f, _line_of(text, m.start()), fn)
    return routes


# ---- Commits ------------------------------------------------------------------------------------


def owns_git(root: Path) -> bool:
    """True only when `root` is itself the top of a git work tree. A directory with no `.git` of its
    own would otherwise report the history of whatever repository contains it."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if out.returncode != 0 or not out.stdout.strip():
        return False
    top = os.path.normcase(os.path.realpath(out.stdout.strip()))
    return top == os.path.normcase(os.path.realpath(str(root)))


def mine_commits(root: Path, known_files: set[str], limit: int = _MAX_COMMITS) -> list[Commit]:
    if not owns_git(root):
        return []
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "log", f"-n{limit}", "--no-merges", "--name-only",
             "--format=%x1e%H%x1f%aI%x1f%an%x1f%s"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode != 0:
        return []
    commits: list[Commit] = []
    for record in out.stdout.split("\x1e"):
        record = record.strip("\n")
        if not record.strip():
            continue
        head, *rest = record.split("\n")
        parts = head.split("\x1f")
        if len(parts) < 4:
            continue
        sha, iso, author, subject = parts[0], parts[1], parts[2], parts[3]
        try:
            at = datetime.fromisoformat(iso)
        except ValueError:
            continue
        changed = [p.strip() for p in rest if p.strip() in known_files]
        commits.append(Commit(sha=sha, at=at, subject=subject.strip() or "(no message)", author=author,
                              files=changed[:_MAX_FILES_PER_COMMIT], total_files=len(changed)))
    return commits


# ---- Intent: dependency-evidenced decisions ----------------------------------------------------

# (category, title, packages). A package ending in "/" matches every package under that scope.
_CATALOGUE: list[tuple[str, str, tuple[str, ...]]] = [
    ("http-api", "Express for the HTTP API", ("express",)),
    ("http-api", "Fastify for the HTTP API", ("fastify",)),
    ("http-api", "Koa for the HTTP API", ("koa",)),
    ("http-api", "NestJS for the backend", ("@nestjs/core",)),
    ("http-api", "FastAPI for the HTTP API", ("fastapi",)),
    ("http-api", "Flask for the HTTP API", ("flask",)),
    ("http-api", "Django for the backend", ("django",)),
    ("persistence", "MongoDB via Mongoose", ("mongoose",)),
    ("persistence", "MongoDB driver", ("mongodb",)),
    ("persistence", "PostgreSQL", ("pg", "postgres", "psycopg2", "psycopg2-binary", "asyncpg")),
    ("persistence", "Prisma ORM", ("prisma", "@prisma/client")),
    ("persistence", "Sequelize ORM", ("sequelize",)),
    ("persistence", "SQLAlchemy ORM", ("sqlalchemy",)),
    ("persistence", "MySQL", ("mysql", "mysql2")),
    ("persistence", "Redis", ("redis", "ioredis")),
    ("persistence", "Firebase", ("firebase", "firebase-admin")),
    ("persistence", "Supabase", ("@supabase/supabase-js",)),
    ("auth", "JWT for authentication", ("jsonwebtoken", "jose", "pyjwt", "python-jose")),
    ("auth", "Password hashing with bcrypt", ("bcrypt", "bcryptjs", "argon2", "passlib")),
    ("auth", "Passport for authentication", ("passport",)),
    ("auth", "NextAuth for authentication", ("next-auth",)),
    ("ui", "Next.js for the web app", ("next",)),
    ("ui", "React for the UI", ("react",)),
    ("ui", "Vue for the UI", ("vue",)),
    ("ui", "Svelte for the UI", ("svelte",)),
    ("ui", "Angular for the UI", ("@angular/core",)),
    ("components", "Radix UI primitives for components", ("@radix-ui/",)),
    ("components", "Material UI components", ("@mui/material",)),
    ("styling", "Tailwind CSS for styling", ("tailwindcss",)),
    ("build", "Vite for builds", ("vite",)),
    ("build", "Webpack for builds", ("webpack",)),
    ("realtime", "WebSockets for realtime", ("socket.io", "socket.io-client", "ws")),
    ("vision", "On-device vision with MediaPipe", ("@mediapipe/",)),
    ("vision", "TensorFlow.js models in the browser", ("@tensorflow/", "@tensorflow-models/")),
    ("llm", "Hosted LLM APIs", ("openai", "@anthropic-ai/sdk", "anthropic", "@google/generative-ai", "google-generativeai")),
    ("validation", "Schema validation", ("zod", "joi", "yup", "pydantic")),
    ("state", "Client state management", ("redux", "@reduxjs/toolkit", "zustand", "mobx", "jotai")),
    ("data-fetching", "React Query for server state", ("@tanstack/react-query", "react-query")),
    ("http-client", "Axios for HTTP calls", ("axios",)),
    ("routing", "React Router for navigation", ("react-router-dom", "react-router")),
    ("config", "Environment config via dotenv", ("dotenv", "python-dotenv")),
    ("testing", "Automated tests", ("jest", "vitest", "mocha", "pytest", "@playwright/test", "cypress")),
    ("charts", "Charts", ("recharts", "chart.js", "d3")),
]


def _manifests(root: Path) -> dict[str, dict[str, str]]:
    """Every dependency manifest in the tree: rel path -> {package: version}."""
    found: dict[str, dict[str, str]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        rel_dir = os.path.relpath(dirpath, root).replace("\\", "/")
        if rel_dir.count("/") > 3:
            dirnames[:] = []
            continue
        for fn in filenames:
            rel = fn if rel_dir == "." else f"{rel_dir}/{fn}"
            path = Path(dirpath) / fn
            try:
                if fn == "package.json":
                    data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
                    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                    found[rel] = {k: str(v) for k, v in deps.items()}
                elif fn.startswith("requirements") and fn.endswith(".txt"):
                    deps = {}
                    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                        m = re.match(r"\s*([A-Za-z0-9_.\-]+)\s*(?:\[.*?\])?\s*([<>=!~].*)?$", line)
                        if m and not line.strip().startswith(("#", "-")):
                            deps[m.group(1).lower()] = (m.group(2) or "").strip()
                    found[rel] = deps
                elif fn == "pyproject.toml":
                    text = path.read_text(encoding="utf-8", errors="ignore")
                    block = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.S)
                    deps = {}
                    if block:
                        for m in re.finditer(r"['\"]([A-Za-z0-9_.\-]+)\s*([<>=!~][^'\"]*)?['\"]", block.group(1)):
                            deps[m.group(1).lower()] = (m.group(2) or "").strip()
                    found[rel] = deps
            except (OSError, json.JSONDecodeError):
                continue
    return found


def _matches(pkg: str, pattern: str) -> bool:
    return pkg.startswith(pattern) if pattern.endswith("/") else pkg == pattern


def _import_re(packages: list[str]) -> re.Pattern[str]:
    alts = "|".join(re.escape(p.rstrip("/")) + (r"/[^'\"]+" if p.endswith("/") else r"(?:/[^'\"]*)?") for p in packages)
    return re.compile(
        rf"(?:from\s+['\"](?:{alts})['\"]|require\(\s*['\"](?:{alts})['\"]\s*\)|import\s+['\"](?:{alts})['\"]"
        rf"|^\s*(?:from|import)\s+(?:{'|'.join(re.escape(p.rstrip('/').replace('-', '_')) for p in packages)})\b)",
        re.M,
    )


def extract_decisions(root: Path, files: list[str]) -> list[Decision]:
    manifests = _manifests(root)
    if not manifests:
        return []
    texts = {f: _read(root, f) for f in files}
    decisions: list[Decision] = []
    for category, title, patterns in _CATALOGUE:
        hits: dict[str, list[str]] = {}
        for rel, deps in manifests.items():
            for pkg, ver in deps.items():
                if any(_matches(pkg.lower(), p) for p in patterns):
                    hits.setdefault(rel, []).append(f"{pkg}{'@' + ver if ver else ''}")
        if not hits:
            continue
        pkgs = sorted({p.split("@")[0] if not p.startswith("@") else "@" + p[1:].split("@")[0] for v in hits.values() for p in v})
        rx = _import_re(pkgs)
        using = [f for f, t in texts.items() if t and rx.search(t)][:_MAX_FILES_PER_DECISION]
        evidence = sorted({p for v in hits.values() for p in v})
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        decisions.append(Decision(slug=slug, title=title, category=category, packages=evidence[:8], manifests=sorted(hits), files=using))
    # One decision per category is enough to read the stack; keep the one with the most evidence.
    best: dict[str, Decision] = {}
    for d in decisions:
        cur = best.get(d.category)
        if cur is None or (len(d.files), len(d.packages)) > (len(cur.files), len(cur.packages)):
            best[d.category] = d
    order = [c for c, _, _ in _CATALOGUE]
    return sorted(best.values(), key=lambda d: order.index(d.category))


def extract_conventions(files: list[str], root: Path, routes: list[Route]) -> list[Convention]:
    out: list[Convention] = []
    # Language per top-level area (frontend/, backend/, ...), only when the areas differ.
    lang_of = {".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".py": "Python"}
    by_area: dict[str, dict[str, int]] = {}
    for f in files:
        lang = lang_of.get(PurePosixPath(f).suffix.lower())
        if not lang:
            continue
        area = f.split("/")[0] if "/" in f else "."
        by_area.setdefault(area, {}).setdefault(lang, 0)
        by_area[area][lang] += 1
    dominant = {a: max(c, key=lambda k: c[k]) for a, c in by_area.items() if sum(c.values()) >= 3 and a != "."}
    if len(set(dominant.values())) > 1:
        parts = [f"{lang} in {area}/" for area, lang in sorted(dominant.items())]
        out.append(Convention("language-split", ", ".join(parts), "Dominant language per top-level directory, by file count."))
    # Module system per area for JavaScript/TypeScript code.
    systems: dict[str, str] = {}
    for area in sorted(by_area):
        js = [f for f in files if (f.split("/")[0] if "/" in f else ".") == area and f.endswith(_JS_EXT)]
        if len(js) < 3:
            continue
        esm = sum(1 for f in js if re.search(r"^\s*import\s", _read(root, f), re.M))
        cjs = sum(1 for f in js if "require(" in _read(root, f))
        if esm or cjs:
            systems[area] = "ES modules" if esm >= cjs else "CommonJS"
    if len(set(systems.values())) > 1:
        out.append(Convention("module-systems", ", ".join(f"{s} in {a}/" for a, s in systems.items()), "import vs require usage per top-level directory."))
    # A prefix most routes share is an API convention.
    if len(routes) >= 3:
        counts: dict[str, int] = {}
        for r in routes:
            segs = [s for s in r.path.split("/") if s][:2]
            if segs and not segs[0].startswith(":"):
                key = "/" + "/".join(s for s in segs if not s.startswith(":"))
                counts[key] = counts.get(key, 0) + 1
        if counts:
            top, n = max(counts.items(), key=lambda kv: kv[1])
            if n >= max(3, int(len(routes) * 0.6)) and top.count("/") >= 1:
                out.append(Convention("api-prefix", f"REST API under {top}", f"{n} of {len(routes)} routes share the {top} prefix."))
    return out


# ---- Graph writing ------------------------------------------------------------------------------


def add_intent_to_graph(
    graph: GraphService,
    *,
    name: str,
    root: Path,
    code: Analysis,
    repo_node_id,
    file_nodes: dict,
    sym_nodes: dict,
) -> dict[str, int]:
    """Writes routes, commits, decisions and conventions for one repository. Every node carries the
    `repository` property so scoping and `remove_repository` treat it like the rest of the repo."""
    counts = {"routes": 0, "commits": 0, "decisions": 0, "conventions": 0}
    static = GraphEdgeSourceType.STATIC_ANALYSIS

    def edge(a, b, kind: GraphEdgeType, *, valid_from: datetime | None = None, props: dict | None = None) -> None:
        payload = {"from_node_id": a, "to_node_id": b, "edge_type": kind, "confidence": 1.0, "source_type": static,
                   "properties": props or {}}
        if valid_from is not None:
            payload["valid_from"] = valid_from
        graph.add_edge(GraphEdgeCreate(**payload))

    routes = extract_routes(root, code.files)
    imported_by = {}
    for a, b in code.imports:
        imported_by.setdefault(a, set()).add(b)
    by_name: dict[str, list[str]] = {}
    for key in sym_nodes:
        # Keys are file#Class.method for methods; a route handler names the bare function.
        by_name.setdefault(key.split("#", 1)[1].rsplit(".", 1)[-1], []).append(key)
    for r in routes:
        node = graph.add_node(GraphNodeCreate(
            node_type=GraphNodeType.API_ROUTE, stable_id=f"route://{name}/{r.method}{r.path}",
            properties={"method": r.method, "path": r.path, "file": r.file, "line": r.line,
                        "handler": r.handler, "repository": name},
            provenance=GraphNodeProvenance.INTERNAL_CODE,
        ))
        counts["routes"] += 1
        target = None
        if r.handler:
            short = r.handler.split(".")[-1]
            keys = by_name.get(short, [])
            near = [k for k in keys if k.split("#")[0] in imported_by.get(r.file, set()) or k.split("#")[0] == r.file]
            pick = near if near else keys
            if len(pick) == 1:
                target = sym_nodes[pick[0]].id
        if target is None and r.file in file_nodes:
            target = file_nodes[r.file].id
        if target is not None:
            edge(node.id, target, GraphEdgeType.FLOWS_INTO, props={"handler": r.handler})

    for c in mine_commits(root, set(file_nodes)):
        node = graph.add_node(GraphNodeCreate(
            node_type=GraphNodeType.CAUSAL_EVENT, stable_id=f"causal-event://{name}/commit/{c.sha[:12]}",
            properties={"event_kind": "commit", "sha": c.sha, "summary": c.subject, "author": c.author,
                        "occurred_at": c.at.isoformat(), "files_changed": c.total_files, "repository": name},
        ))
        counts["commits"] += 1
        for f in c.files:
            edge(node.id, file_nodes[f].id, GraphEdgeType.CAUSES, valid_from=c.at, props={"relation": "modified"})

    for d in extract_decisions(root, code.files):
        node = graph.add_node(GraphNodeCreate(
            node_type=GraphNodeType.DECISION, stable_id=f"decision://{name}/{d.slug}",
            properties={"title": d.title, "summary": d.summary, "category": d.category,
                        "evidence": d.packages, "manifests": d.manifests, "files_using": len(d.files),
                        "repository": name},
        ))
        counts["decisions"] += 1
        for f in d.files:
            if f in file_nodes:
                edge(node.id, file_nodes[f].id, GraphEdgeType.TRACES_TO_DECISION)

    for cv in extract_conventions(code.files, root, routes):
        node = graph.add_node(GraphNodeCreate(
            node_type=GraphNodeType.CONVENTION_PROFILE, stable_id=f"convention://{name}/{cv.slug}",
            properties={"title": cv.title, "summary": cv.summary, "repository": name},
        ))
        counts["conventions"] += 1
        edge(node.id, repo_node_id, GraphEdgeType.DERIVED_FROM)
    return counts
