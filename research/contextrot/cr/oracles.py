"""Deterministic validity oracles for context-file claims, evaluated against one repository snapshot.

Each oracle answers `true` (the claim holds in this snapshot), `false` (it demonstrably does not),
or `unknown` (this oracle cannot decide — never counted as rot). Evidence is recorded so every
verdict can be audited.

    path        the file/dir exists (globs allowed; placeholders like <name> -> unknown)
    structure   same as path, for tree-block entries
    command     package-manager scripts exist in the right package.json, Makefile targets exist,
                `python -m X` resolves to a repo module or a declared dependency, every repo-path
                argument exists, `cd dir &&` is followed
    symbol      declared somewhere in the code (tree-sitter, via Codexa's analyzer) or, for things
                like env vars / config keys, present in non-documentation source text
    dependency  declared in a manifest (package.json, pyproject, requirements, go.mod, Cargo.toml,
                pom.xml/gradle) — or, for "negative" claims ("never use X"), *not* declared;
                versioned claims compare the major version
    prose       always unknown here (LLM-judge territory)
"""
from __future__ import annotations

import json
import re
import shlex
import sys
import tomllib
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for _p in (ROOT, Path(__file__).resolve().parents[1]):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from cr.extract import TECH, Claim  # noqa: E402

_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", "coverage", ".tox"}
_DOC_EXT = {".md", ".mdx", ".rst", ".txt", ".adoc"}
_CODE_EXT = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".kts", ".scala", ".swift", ".m", ".mm", ".lua", ".r",
             ".dart", ".ex", ".exs", ".erl", ".hs", ".ml", ".clj", ".gradle", ".xml", ".properties", ".proto", ".graphql",
             ".vue", ".svelte", ".ps1", ".bat", ".cmake", ".mk",
             ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rs", ".java", ".kt", ".rb", ".php", ".cs",
             ".sh", ".yml", ".yaml", ".toml", ".json", ".ini", ".cfg", ".env", ".sql"}
_STDLIB_MODULES = {"pip", "venv", "http.server", "unittest", "json.tool", "pdb", "cProfile", "timeit", "ensurepip",
                   "compileall", "zipfile", "doctest", "site", "trace", "py_compile", "webbrowser", "pydoc"}
_MAX_TEXT_BYTES = 400_000


@dataclass
class Verdict:
    status: str                 # true | false | unknown
    evidence: str = ""


def _major(v: str | None) -> int | None:
    m = re.search(r"(\d+)", v or "")
    return int(m.group(1)) if m else None


@dataclass
class Snapshot:
    root: Path
    _cache: dict = field(default_factory=dict)

    # -- files ---------------------------------------------------------------------------------
    @cached_property
    def files(self) -> list[str]:
        """Tracked files when the root is a git checkout (untracked clones, build output and caches
        are not "the repository"); otherwise every non-skipped file."""
        if (self.root / ".git").exists():
            import subprocess
            r = subprocess.run(["git", "-C", str(self.root), "ls-files", "-z"], capture_output=True)
            if r.returncode == 0:
                return sorted(x for x in r.stdout.decode("utf-8", errors="ignore").split("\0")
                              if x and not any(part in _SKIP_DIRS for part in x.split("/")))
        out = []
        for p in self.root.rglob("*"):
            if any(part in _SKIP_DIRS for part in p.relative_to(self.root).parts):
                continue
            if p.is_file():
                out.append(p.relative_to(self.root).as_posix())
        return sorted(out)

    @cached_property
    def dirs(self) -> set[str]:
        ds = set()
        for f in self.files:
            parts = f.split("/")[:-1]
            for i in range(1, len(parts) + 1):
                ds.add("/".join(parts[:i]))
        return ds

    @cached_property
    def _file_set(self) -> set[str]:
        return set(self.files)

    def exists(self, rel: str) -> bool:
        rel = rel.strip().strip("/").removeprefix("./")
        if not rel:
            return True
        return rel in self.dirs or rel in self._file_set

    def exists_anywhere(self, rel: str) -> str | None:
        """A partial path or bare file name ("netem.go", "commands/build/") written relative to some
        sub-directory: the first tracked path that ends with it, or None."""
        rel = rel.strip().strip("/").removeprefix("./")
        if not rel:
            return None
        suffix = "/" + rel
        for f in self.files:
            if f.endswith(suffix):
                return f
        for d in self.dirs:
            if d.endswith(suffix):
                return d
        return None

    # -- manifests -----------------------------------------------------------------------------
    @cached_property
    def package_jsons(self) -> dict[str, dict]:
        out = {}
        for f in self.files:
            if f.endswith("package.json") and f.split("/")[-1] == "package.json":
                try:
                    out[f.rsplit("/", 1)[0] if "/" in f else ""] = json.loads((self.root / f).read_text(encoding="utf-8", errors="ignore"))
                except (json.JSONDecodeError, ValueError, OSError):
                    pass
        return out

    @cached_property
    def deps(self) -> dict[str, str]:
        """dependency name (lowercase) -> declared version spec (may be '')."""
        d: dict[str, str] = {}
        for pj in self.package_jsons.values():
            for sec in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                for k, v in (pj.get(sec) or {}).items():
                    d.setdefault(k.lower(), str(v))
            eng = (pj.get("engines") or {}).get("node")
            if eng:
                d.setdefault("node", str(eng))
        for f in self.files:
            name = f.split("/")[-1]
            text = None
            if name == "pyproject.toml":
                try:
                    data = tomllib.loads((self.root / f).read_text(encoding="utf-8", errors="ignore"))
                except (tomllib.TOMLDecodeError, ValueError, OSError):
                    continue
                proj = data.get("project") or {}
                specs = list(proj.get("dependencies") or [])
                for grp in (proj.get("optional-dependencies") or {}).values():
                    specs += list(grp or [])
                for grp in (data.get("dependency-groups") or {}).values():
                    specs += [x for x in (grp or []) if isinstance(x, str)]
                poetry = ((data.get("tool") or {}).get("poetry") or {})
                for sec in ("dependencies", "dev-dependencies"):
                    for k, v in (poetry.get(sec) or {}).items():
                        specs.append(f"{k}{v if isinstance(v, str) else ''}")
                for s in specs:
                    n = re.split(r"[\s\[<>=!~;]", s.strip(), maxsplit=1)[0].lower().replace("_", "-")
                    d.setdefault(n, s)
                if proj.get("requires-python"):
                    d.setdefault("python", str(proj["requires-python"]))
            elif name.endswith(".txt") and ("requirements" in name or "/requirements/" in f"/{f}"):
                text = (self.root / f).read_text(encoding="utf-8", errors="ignore")
                for ln in text.splitlines():
                    ln = ln.split("#", 1)[0].strip()
                    if ln and not ln.startswith("-"):
                        d.setdefault(re.split(r"[\s\[<>=!~;]", ln, maxsplit=1)[0].lower().replace("_", "-"), ln)
            elif name == "go.mod":
                text = (self.root / f).read_text(encoding="utf-8", errors="ignore")
                m = re.search(r"^go\s+(\S+)", text, re.M)
                if m:
                    d.setdefault("go", m.group(1))
                for mm in re.finditer(r"^\s*([\w./-]+)\s+v[\d.]+", text, re.M):
                    d.setdefault(mm.group(1).lower(), "")
            elif name == "Cargo.toml":
                try:
                    data = tomllib.loads((self.root / f).read_text(encoding="utf-8", errors="ignore"))
                except (tomllib.TOMLDecodeError, ValueError, OSError):
                    continue
                for sec in ("dependencies", "dev-dependencies"):
                    for k in (data.get(sec) or {}):
                        d.setdefault(k.lower(), "")
            elif name in ("pom.xml", "build.gradle", "build.gradle.kts"):
                text = (self.root / f).read_text(encoding="utf-8", errors="ignore")
                for mm in re.finditer(r"<artifactId>([^<]+)</artifactId>|['\"][\w.-]+:([\w.-]+)", text):
                    d.setdefault((mm.group(1) or mm.group(2)).lower(), "")
        return d

    # -- code ----------------------------------------------------------------------------------
    @cached_property
    def symbols(self) -> set[str]:
        """Declared names and qualified names (Codexa's tree-sitter analyzer: py/js/ts)."""
        from backend.repository.analyze import analyze_repo

        names: set[str] = set()
        try:
            for s in analyze_repo(self.root).symbols:
                if s.kind == "module":
                    continue
                names.add(s.name)
                if s.qualname:
                    names.add(s.qualname)
        except Exception:  # noqa: BLE001 - an unparseable snapshot leaves symbols unknown, not false
            pass
        return names

    @cached_property
    def code_text(self) -> str:
        chunks = []
        for f in self.files:
            p = Path(f)
            if p.suffix.lower() in _DOC_EXT or p.suffix.lower() not in _CODE_EXT:
                continue
            try:
                b = (self.root / f).read_bytes()
            except OSError:
                continue
            if len(b) <= _MAX_TEXT_BYTES:
                chunks.append(b.decode("utf-8", errors="ignore"))
        return "\n".join(chunks)

    @cached_property
    def has_parseable_code(self) -> bool:
        return any(Path(f).suffix in (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs") for f in self.files)


# ------------------------------------------------------------------------------------ oracles ----
def check_path(s: Snapshot, rel: str) -> Verdict:
    if re.search(r"[<>{}$]|\.\.\.", rel) or rel.startswith(("http", "#", "~")):
        return Verdict("unknown", "placeholder or non-repo path")
    rel = rel.strip().strip("/").removeprefix("./")
    if "*" in rel:
        hits = list(s.root.glob(rel)) or list(s.root.glob("**/" + rel))
        return Verdict("true" if hits else "false", f"glob matched {len(hits)}")
    if s.exists(rel):
        return Verdict("true", "exists")
    hit = s.exists_anywhere(rel)
    if hit:
        return Verdict("true", f"exists as {hit}")
    first, _, rest = rel.partition("/")  # tree diagrams often start with the repository's own folder
    if rest and (s.exists(rest) or s.exists_anywhere(rest)):
        return Verdict("true", f"exists below the drawn root '{first}/'")
    return Verdict("false", "no such file or directory")


def _scripts(s: Snapshot, cwd: str) -> dict | None:
    pj = s.package_jsons.get(cwd.strip("/"))
    return (pj or {}).get("scripts") if pj is not None else None


def _check_one(s: Snapshot, argv: list[str], cwd: str) -> Verdict:
    tool = argv[0]
    rest = argv[1:]
    # repo-path arguments must exist (in the current directory)
    for a in rest:
        if a.startswith("-") or "=" in a or re.search(r"[<>{}$*]", a):
            continue
        a = a.split("::", 1)[0]                       # pytest node id
        a = re.sub(r"/\.\.\.$", "", a)                 # go package pattern ./x/...
        if re.match(r"^[\w-]+(\.[\w-]+)+/", a) and not s.exists(a.split("/", 1)[0]):
            continue                                  # ghcr.io/org/img, github.com/x/y: not a repo path
        if ":" in a and not re.match(r"^[A-Za-z]:[\\/]", a):
            continue                                  # image:tag, host:port
        if ("/" in a or re.search(r"\.(py|ts|js|json|ya?ml|toml|sh|txt|cfg|ini)$", a)) and not a.startswith(("http", "git@")):
            rel = f"{cwd}/{a}".strip("/") if cwd else a
            if a.startswith(("./", "../")) or not a.startswith("/"):
                if not s.exists(rel.removeprefix("./")) and not s.exists(a.removeprefix("./")):
                    return Verdict("false", f"argument path missing: {a}")
    if tool in ("npm", "pnpm", "yarn", "bun"):
        sub = rest[0] if rest else ""
        scripts = _scripts(s, cwd)
        if scripts is None:
            return Verdict("false", f"no package.json in '{cwd or '.'}'")
        if sub in ("install", "i", "ci", "add", "remove", "exec", "dlx", "create", "init", "x"):
            return Verdict("true", "package manager builtin with package.json present")
        name = rest[1] if sub == "run" and len(rest) > 1 else sub
        if sub == "run" or name in scripts or (tool != "npm" and name):
            if name in scripts:
                return Verdict("true", f"script '{name}' defined")
            if tool == "npm" and name in ("test", "start") and sub != "run":
                return Verdict("false", f"npm {name}: no '{name}' script")
            return Verdict("false", f"script '{name}' not in package.json scripts")
        if tool == "npm" and sub in ("test", "start", "t"):
            return Verdict("true" if ("test" if sub in ("test", "t") else "start") in scripts else "false", "npm builtin script")
        return Verdict("unknown", "unrecognised package-manager subcommand")
    if tool == "make":
        mk = next((f for f in (f"{cwd}/Makefile".strip("/"), f"{cwd}/makefile".strip("/")) if f in set(s.files)), None)
        if mk is None:
            if any(f.split("/")[-1] in ("CMakeLists.txt", "configure", "configure.ac", "meson.build") for f in s.files):
                return Verdict("unknown", "Makefile is generated by the build system")
            return Verdict("false", "no Makefile")
        targets = set(re.findall(r"^([\w.-]+)\s*:", (s.root / mk).read_text(encoding="utf-8", errors="ignore"), re.M))
        tgt = next((a for a in rest if not a.startswith("-") and "=" not in a), None)
        if tgt is None:
            return Verdict("true", "default target")
        return Verdict("true", f"target {tgt}") if tgt in targets else Verdict("false", f"no Makefile target '{tgt}'")
    if tool in ("python", "python3", "py") and len(rest) >= 2 and rest[0] == "-m":
        mod = rest[1]
        if mod in _STDLIB_MODULES or mod.split(".")[0] in _STDLIB_MODULES:
            return Verdict("true", "stdlib module")
        base = mod.replace(".", "/")
        for cand in (f"{base}.py", f"{base}/__init__.py", f"{base}/__main__.py", f"src/{base}.py", f"src/{base}/__main__.py",
                     f"src/{base}/__init__.py"):
            if s.exists(f"{cwd}/{cand}".strip("/")):
                return Verdict("true", f"repo module {cand}")
        if mod.split(".")[0].lower().replace("_", "-") in s.deps:
            return Verdict("true", "declared dependency")
        return Verdict("unknown", f"module {mod} not in repo or manifests (may be a transitive/global tool)")
    if tool in ("pytest", "uvicorn", "gunicorn", "alembic", "ruff", "black", "mypy", "jest", "vitest", "eslint", "prettier",
                "tsc", "playwright", "tox", "nox"):
        dep = {"tsc": "typescript"}.get(tool, tool)
        if tool in ("uvicorn", "gunicorn") and rest:
            app = next((a for a in rest if ":" in a and not a.startswith("-")), None)
            if app:
                base = app.split(":")[0].replace(".", "/")
                if not any(s.exists(c) for c in (f"{base}.py", f"{base}/__init__.py", f"src/{base}.py")):
                    return Verdict("false", f"app module {app.split(':')[0]} missing")
        if dep in s.deps or f"@{dep}/test" in s.deps:
            return Verdict("true", f"{dep} declared")
        return Verdict("unknown", f"{dep} not declared (may be installed globally)")
    if tool in ("docker", "docker-compose"):
        if "compose" in rest[:1] or tool == "docker-compose":
            files = [rest[i + 1] for i, a in enumerate(rest) if a in ("-f", "--file") and i + 1 < len(rest)]
            if not files:
                found = any(s.exists(f"{cwd}/{n}".strip("/")) for n in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"))
                return Verdict("true" if found else "false", "compose file present" if found else "no compose file")
            return Verdict("true", "compose file(s) exist")  # existence already checked above
        if rest[:1] == ["build"]:
            return Verdict("true" if any(f.endswith("Dockerfile") for f in s.files) else "false", "Dockerfile")
        return Verdict("unknown", "docker subcommand")
    if tool in ("go",):
        return Verdict("true" if s.exists("go.mod") or any(f.endswith("go.mod") for f in s.files) else "false", "go.mod")
    if tool == "cargo":
        return Verdict("true" if any(f.endswith("Cargo.toml") for f in s.files) else "false", "Cargo.toml")
    if tool in ("pip", "pip3", "uv", "poetry", "pipenv"):
        if any(a in ("-e", "--editable") for a in rest) or "install" in rest or "sync" in rest:
            ok = any(s.exists(f"{cwd}/{n}".strip("/")) for n in ("pyproject.toml", "setup.py", "setup.cfg")) or \
                any(re.search(r"requirements.*\.txt", a) for a in rest)
            return Verdict("true" if ok else "false", "python project metadata")
        return Verdict("unknown", "python tool subcommand")
    if tool.startswith("./") or tool in ("bash", "sh"):
        script = tool if tool.startswith("./") else (rest[0] if rest else "")
        if script:
            rel = f"{cwd}/{script}".strip("/").removeprefix("./")
            return Verdict("true" if s.exists(rel) or s.exists(script.removeprefix("./")) else "false", f"script {script}")
    return Verdict("unknown", f"no oracle for '{tool}'")


def check_command(s: Snapshot, cmd: str) -> Verdict:
    cwd = ""
    verdicts = []
    for part in re.split(r"\s*(?:&&|\|\||;)\s*", cmd):
        if not part.strip():
            continue
        try:
            argv = shlex.split(part, posix=True)
        except ValueError:
            return Verdict("unknown", "unparseable command")
        argv = [a for a in argv if not re.match(r"^\w+=", a)] or argv  # drop leading VAR=x
        if not argv:
            continue
        if argv[0] == "cd":
            target = argv[1] if len(argv) > 1 else ""
            nxt = f"{cwd}/{target}".strip("/") if cwd else target.strip("/").removeprefix("./")
            if target and not re.search(r"[<>{}$~]", target) and not s.exists(nxt):
                return Verdict("false", f"cd target missing: {target}")
            cwd = nxt
            continue
        verdicts.append(_check_one(s, argv, cwd))
    if any(v.status == "false" for v in verdicts):
        return next(v for v in verdicts if v.status == "false")
    if verdicts and all(v.status == "true" for v in verdicts):
        return Verdict("true", "; ".join(v.evidence for v in verdicts))
    return Verdict("unknown", "; ".join(v.evidence for v in verdicts) or "no executable part")


def check_symbol(s: Snapshot, name: str) -> Verdict:
    if name in s.symbols:
        return Verdict("true", "declared")
    if re.search(rf"(?<![\w$]){re.escape(name.split('.')[-1])}(?![\w$])", s.code_text):
        return Verdict("true", "present in source text")
    if not s.has_parseable_code and not s.code_text:
        return Verdict("unknown", "no source to check")
    return Verdict("false", "not declared or mentioned in any source file")


def check_dependency(s: Snapshot, c: Claim) -> Verdict:
    name = c.text
    spec = TECH.get(name, {})
    pkgs = [p.lower() for p in spec.get("pkgs", [name])]
    if spec.get("files"):
        present = any(f.split("/")[-1] in spec["files"] for f in s.files)
        ev = "evidence file present" if present else "no evidence file"
    else:
        if spec.get("prefix"):
            hits = [d for d in s.deps if any(d.startswith(p) for p in pkgs)]
        else:
            hits = [p for p in pkgs if p in s.deps]
        present = bool(hits)
        ev = f"declared: {hits[0]}" if hits else "not declared in any manifest"
        # versioned claim ("React 18"): the declared major must match unless the claim says "18+"
        if present and c.extra.get("version") and c.polarity == "positive" and not c.extra.get("at_least"):
            declared = s.deps.get(hits[0], "")
            dm, cm = _major(declared), _major(c.extra.get("version"))
            if dm is not None and cm is not None and dm != cm:
                return Verdict("false", f"declared {declared!r}, claim says {c.extra['version']}")
    if name in ("python", "node", "go", "java") and not present:
        return Verdict("unknown", f"{name} version not declared")
    if c.polarity == "negative":
        return Verdict("false" if present else "true", ("present despite 'never/avoid' claim: " if present else "absent as claimed: ") + ev)
    return Verdict("true" if present else "false", ev)


def check(s: Snapshot, c: Claim) -> Verdict:
    v = _check(s, c)
    if v.status == "false" and c.extra.get("hypothetical"):
        return Verdict("unknown", "example / to-be-created context: " + v.evidence)
    return v


def _check(s: Snapshot, c: Claim) -> Verdict:
    if c.cls in ("path", "structure"):
        return check_path(s, c.text)
    if c.cls == "command":
        return check_command(s, c.text)
    if c.cls == "symbol":
        return check_symbol(s, c.text)
    if c.cls == "dependency":
        return check_dependency(s, c)
    return Verdict("unknown", "prose: needs a judge")
