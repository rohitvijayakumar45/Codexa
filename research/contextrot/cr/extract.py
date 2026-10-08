"""Atomic, checkable claims from agent context files (AGENTS.md, CLAUDE.md, copilot-instructions…).

A context file mixes claims a machine can check against the repository with prose it cannot. This
module pulls out the checkable ones, deterministically, and labels everything else `prose` (for an
optional LLM pass; never guessed here).

Claim classes
    path        `src/config.ts`, [guide](docs/setup.md), `/backend/perception`
    command     `npm run test:unit`, lines of a ```bash block, `make dev`
    symbol      `AuthService.login`, `parse_config()`, `MAX_RETRIES`
    dependency  "FastAPI", "React 18", "Python 3.11+", "Neo4j" — with polarity: a sentence saying
                "never introduce MongoDB" claims *absence*
    structure   entries of a directory tree drawn in a code block
    prose       every other non-empty line (conventions, behaviour, architecture)
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

CONTEXT_FILES = ("AGENTS.md", "CLAUDE.md", ".github/copilot-instructions.md", ".cursorrules",
                 "GEMINI.md", ".windsurfrules")

COMMAND_TOOLS = {
    "npm", "npx", "pnpm", "yarn", "bun", "node", "deno", "tsc", "python", "python3", "py", "pip", "pip3",
    "pytest", "uv", "poetry", "pipenv", "tox", "nox", "make", "cmake", "go", "cargo", "rustc", "mvn",
    "gradle", "./gradlew", "dotnet", "docker", "docker-compose", "uvicorn", "gunicorn", "flask", "django-admin",
    "ruff", "black", "mypy", "eslint", "prettier", "jest", "vitest", "playwright", "alembic", "bash", "sh",
    "./scripts", "just", "turbo", "nx", "lerna", "composer", "bundle", "rake", "rails", "mix", "swift",
    "cd",  # `cd web && npm run dev`: the directory is part of the claim
}
SHELL_LANGS = {"", "bash", "sh", "shell", "console", "zsh", "terminal", "cmd", "powershell", "ps1", "fish"}
_NEG_WINDOW = 5  # a technology is negated only if a negation word precedes it within this many words
NEGATION = re.compile(r"\b(never|not|no|don'?t|do not|avoid|rejected|instead of|without|removed|deprecated|stop using)\b", re.I)

# Technology names a context file may claim, mapped to the package / file evidence that makes the
# claim true. Matching is case-insensitive on whole words.
TECH: dict[str, dict] = {
    "fastapi": {"pkgs": ["fastapi"]}, "django": {"pkgs": ["django"]}, "flask": {"pkgs": ["flask"]},
    "pydantic": {"pkgs": ["pydantic"]}, "sqlalchemy": {"pkgs": ["sqlalchemy"]},
    "postgresql": {"pkgs": ["psycopg", "psycopg2", "psycopg2-binary", "asyncpg", "pg", "postgres", "@prisma/client"]},
    "postgres": {"pkgs": ["psycopg", "psycopg2", "psycopg2-binary", "asyncpg", "pg", "postgres"]},
    "mongodb": {"pkgs": ["pymongo", "motor", "mongodb", "mongoose"]},
    "neo4j": {"pkgs": ["neo4j", "neo4j-driver", "py2neo"]},
    "qdrant": {"pkgs": ["qdrant-client", "@qdrant/js-client-rest"]},
    "redis": {"pkgs": ["redis", "ioredis", "aioredis"]}, "rq": {"pkgs": ["rq"]},
    "celery": {"pkgs": ["celery"]}, "kafka": {"pkgs": ["kafka-python", "confluent-kafka", "kafkajs"]},
    "react": {"pkgs": ["react"]}, "next.js": {"pkgs": ["next"]}, "nextjs": {"pkgs": ["next"]},
    "vue": {"pkgs": ["vue"]}, "angular": {"pkgs": ["@angular/core"]}, "svelte": {"pkgs": ["svelte"]},
    "express": {"pkgs": ["express"]}, "express.js": {"pkgs": ["express"]}, "nestjs": {"pkgs": ["@nestjs/core"]},
    "tailwind": {"pkgs": ["tailwindcss"]}, "tailwindcss": {"pkgs": ["tailwindcss"]},
    "vite": {"pkgs": ["vite"]}, "webpack": {"pkgs": ["webpack"]}, "jest": {"pkgs": ["jest"]},
    "vitest": {"pkgs": ["vitest"]}, "pytest": {"pkgs": ["pytest"]}, "playwright": {"pkgs": ["playwright", "@playwright/test"]},
    "prisma": {"pkgs": ["prisma", "@prisma/client"]}, "zustand": {"pkgs": ["zustand"]}, "redux": {"pkgs": ["redux", "@reduxjs/toolkit"]},
    "three.js": {"pkgs": ["three"]}, "tree-sitter": {"pkgs": ["tree-sitter", "tree_sitter", "web-tree-sitter"], "prefix": True},
    "litellm": {"pkgs": ["litellm"]}, "langchain": {"pkgs": ["langchain"], "prefix": True},
    "mcp": {"pkgs": ["mcp", "fastmcp", "@modelcontextprotocol/sdk"]},
    "docker": {"files": ["Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"], "glob": True},
    "typescript": {"pkgs": ["typescript"]},
}
VERSIONED = {"python": "python", "node": "node", "node.js": "node", "nodejs": "node", "react": "react",
             "next.js": "next", "typescript": "typescript", "vue": "vue", "django": "django", "go": "go",
             "java": "java", "angular": "@angular/core", "fastapi": "fastapi", "pydantic": "pydantic"}

_INLINE = re.compile(r"`([^`\n]+)`")
_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
_FENCE = re.compile(r"^\s*(```|~~~)\s*([\w+-]*)")
_PATHISH = re.compile(r"^(?:\.{0,2}/)?[\w.@-]+(?:/[\w.@*-]*)+/?$|^[\w.-]+\.(?:py|ts|tsx|js|jsx|mjs|cjs|json|ya?ml|toml|md|go|rs|java|kt|sh|cfg|ini|lock|txt|env|sql|css|scss|html)$")
_SYMBOLISH = re.compile(r"^[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*(?:\(\))?$")
_VERSION = re.compile(r"\b(Python|Node(?:\.js)?|NodeJS|React|Next\.js|TypeScript|Vue|Django|Go|Java|Angular|FastAPI|Pydantic)"
                      r"\s*(?:v|version\s*)?(?:>=|≥|\^|~)?\s*(\d+(?:\.\d+)?)(\+)?", re.I)
_TREE_CHARS = re.compile(r"[│├└─]")
_COMMON_WORDS = {"true", "false", "null", "none", "self", "this", "main", "master", "yes", "no", "id", "api",
                 "url", "json", "yaml", "http", "https", "todo", "src", "test", "tests", "docs", "string", "number"}


_ENGLISH_COLLISIONS = {"express", "next.js", "vue", "jest", "redux", "docker"}
_HYPOTHETICAL = re.compile(r"\b(e\.g\.|eg\.|for example|for instance|example|such as|create|creating|add a new|new file|"
                           r"generate[sd]?|name it|named like|e\.x\.|placeholder|template|pattern)\b", re.I)


def _codey(span: str) -> bool:
    """Backticked text that looks like a code identifier, not a word or an acronym: has `_`, `.`,
    `()`, a digit, or internal capitals (camelCase / PascalCase with 2+ capitals)."""
    core = span.rstrip("()")
    if re.fullmatch(r"[A-Z]{2,6}", core):           # SSRF, RCE, GHSA, TOCTOU: acronyms
        return False
    if span.endswith("()") or "_" in core or "." in core or re.search(r"\d", core):
        return True
    return bool(re.search(r"[a-z][A-Z]", core)) or len(re.findall(r"[A-Z]", core)) >= 2


def hypothetical(line: str) -> bool:
    """The line talks about an example / a file to create / a pattern, not about what exists."""
    return bool(_HYPOTHETICAL.search(line))


def negated(line: str, start: int) -> bool:
    """True if the mention at `start` is in the scope of a preceding negation in the same sentence
    ("Never introduce MongoDB or Express.js") — not merely on a line containing one ("Neo4j is a
    projection; never write to it directly")."""
    sentence_start = max(line.rfind(". ", 0, start), line.rfind("; ", 0, start), line.rfind(": ", 0, start)) + 1
    before = line[sentence_start:start]
    last = None
    for last in NEGATION.finditer(before):
        pass
    if last is None:
        return False
    return len(before[last.end():].split()) <= _NEG_WINDOW


@dataclass
class Claim:
    cls: str
    text: str                     # normalized claim text (the checkable part)
    line: int
    raw: str = ""
    polarity: str = "positive"    # dependency claims: "negative" = claims absence
    extra: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.cls}:{self.polarity}:{self.text}"

    def as_dict(self) -> dict:
        d = asdict(self)
        d["key"] = self.key
        return d


def _is_command(s: str) -> bool:
    first = s.strip().lstrip("$> ").split()
    if not first:
        return False
    w = first[0]
    return w in COMMAND_TOOLS or w.startswith("./") and not _PATHISH.match(s.strip())


def _clean_cmd(line: str) -> str:
    s = line.strip()
    s = re.sub(r"^(\$|>|PS>|C:\\.*?>)\s*", "", s)
    return s.split(" #", 1)[0].strip()


def _tree_paths(block: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Directory-tree code block -> (line, path) entries, nesting reconstructed from indentation."""
    out, stack = [], []
    for ln, raw in block:
        if not raw.strip():
            continue
        m = re.match(r"^([\s│├└─|`+\\-]*)([^\s#│├└─][^#]*?)\s*(?:#.*)?$", raw)
        if not m:
            continue
        prefix, name = m.group(1), m.group(2).strip()
        if not re.match(r"^[\w.@/*-]+/?$", name):
            continue
        depth = len(prefix.replace("\t", "    ")) // 2 if _TREE_CHARS.search(prefix) or prefix.startswith(" ") else 0
        while stack and stack[-1][0] >= depth:
            stack.pop()
        parent = stack[-1][1] if stack else ""
        path = (parent.rstrip("/") + "/" + name.lstrip("/")) if parent else name
        if name.endswith("/"):
            stack.append((depth, path))
        out.append((ln, path))
    return out


def _looks_like_tree(block: list[tuple[int, str]]) -> bool:
    lines = [r for _, r in block if r.strip()]
    if not lines:
        return False
    treeish = sum(1 for r in lines if _TREE_CHARS.search(r) or re.match(r"^\s*[\w.@-]+/\s*(#.*)?$", r))
    return treeish >= max(2, len(lines) // 2)


def extract(text: str) -> list[Claim]:
    claims: list[Claim] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        fm = _FENCE.match(line)
        if fm:
            fence, lang = fm.group(1), fm.group(2).lower()
            block = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(fence):
                block.append((i + 1, lines[i]))
                i += 1
            i += 1
            if _looks_like_tree(block):
                for ln, p in _tree_paths(block):
                    claims.append(Claim("structure", p.removeprefix("./").strip("/"), ln, raw=p))
            elif lang in SHELL_LANGS:
                for ln, raw in block:
                    cmd = _clean_cmd(raw)
                    if cmd and not cmd.startswith("#") and _is_command(cmd):
                        claims.append(Claim("command", cmd, ln, raw=raw.strip()))
            continue
        ln = i + 1
        stripped = line.strip()
        found = False
        for m in _LINK.finditer(line):
            target = m.group(1).split("#", 1)[0]
            if target and not re.match(r"^[a-z]+:", target):
                claims.append(Claim("path", target.removeprefix("./"), ln, raw=m.group(0)))
                found = True
        for m in _INLINE.finditer(line):
            span = m.group(1).strip()
            if not span or len(span) > 200:
                continue
            if _is_command(span):
                claims.append(Claim("command", _clean_cmd(span), ln, raw=span))
            elif _PATHISH.match(span) and not re.search(r"[<>{}]", span):
                claims.append(Claim("path", span.removeprefix("./") if not span.startswith("/") else span[1:], ln, raw=span))
            elif _SYMBOLISH.match(span) and span.lower() not in _COMMON_WORDS and len(span.rstrip("()")) >= 3 \
                    and _codey(span):
                claims.append(Claim("symbol", span.rstrip("()"), ln, raw=span))
            else:
                continue
            found = True
        for m in _VERSION.finditer(line):
            name = m.group(1).lower()
            claims.append(Claim("dependency", VERSIONED.get(name, name), ln, raw=m.group(0),
                                polarity="negative" if negated(line, m.start()) else "positive",
                                extra={"version": m.group(2), "at_least": bool(m.group(3)) or bool(re.search(r">=|≥", m.group(0)))}))
            found = True
        lowered = re.sub(r"`[^`]*`", lambda mm: " " * len(mm.group(0)), line.lower())  # keep offsets
        for tech in TECH:
            mt = re.search(rf"(?<![\w.-]){re.escape(tech)}(?![\w-])", lowered)
            if mt and tech in _ENGLISH_COLLISIONS and not line[mt.start():mt.end()][:1].isupper():
                continue  # "express the intent" is a verb, "Express" is the framework
            if mt:
                if any(c.cls == "dependency" and c.line == ln and (
                        c.text in (tech, VERSIONED.get(tech))
                        or (c.text in TECH and TECH[c.text] == TECH[tech])) for c in claims):
                    continue  # same technology already claimed on this line (aliases: express / express.js)
                claims.append(Claim("dependency", tech, ln, raw=tech,
                                    polarity="negative" if negated(line, mt.start()) else "positive"))
                found = True
        if not found and stripped and not stripped.startswith(("#", "|---", "---")) and len(stripped) > 3:
            claims.append(Claim("prose", stripped, ln, raw=stripped))
        i += 1
    for c in claims:  # existence claims made in an example / "create a file …" context are not assertions
        if c.cls in ("path", "symbol", "command", "structure") and 0 < c.line <= len(lines) and hypothetical(lines[c.line - 1]):
            c.extra["hypothetical"] = True
    # de-duplicate (same claim stated twice in a file counts once; keep first line)
    seen, out = set(), []
    for c in claims:
        if c.key not in seen:
            seen.add(c.key)
            out.append(c)
    return out
