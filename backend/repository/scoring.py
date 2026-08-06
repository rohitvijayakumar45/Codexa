"""Repository scoring from real static analysis.

Runs as part of ingestion (not a separate manual step). Each metric is measured from the actual
repository — file counts, test files, import density, file sizes, typing, directory layout — and
carries a reasoning string explaining the number, plus a concrete suggestion when it's weak.
"""

from __future__ import annotations

from pathlib import Path

from backend.repository.analyze import Analysis

_SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", ".agents"}
_CONVENTIONAL = {"src", "components", "hooks", "services", "lib", "utils", "tests", "test", "api",
                 "routes", "pages", "models", "server", "backend", "frontend"}


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def score_repository(dest: Path, code: Analysis) -> dict:
    files = code.files
    source = len(files)
    test_files = sum(1 for f in files if "test" in f.lower() or "spec" in f.lower() or "__tests__" in f.lower())
    ts_files = sum(1 for f in files if f.endswith((".ts", ".tsx")))
    readme = any((dest / n).exists() for n in ("README.md", "readme.md", "README.rst", "Readme.md"))
    md_files = sum(1 for f in files if f.endswith(".md"))
    docs_dir = (dest / "docs").exists()

    # Average lines per source file (maintainability signal).
    total_lines = 0
    counted = 0
    for f in files[:200]:
        try:
            total_lines += sum(1 for _ in (dest / f).open(encoding="utf-8", errors="ignore"))
            counted += 1
        except OSError:
            continue
    avg_loc = (total_lines / counted) if counted else 0

    avg_imports = len(code.imports) / max(source, 1)
    top_dirs = {p.name for p in dest.iterdir() if p.is_dir() and p.name not in _SKIP} if dest.exists() else set()
    src_dirs = top_dirs | ({d.name for d in (dest / "src").iterdir() if d.is_dir()} if (dest / "src").exists() else set())
    conventional_hits = _CONVENTIONAL & {d.lower() for d in src_dirs}

    components: dict[str, float] = {}
    reasoning: dict[str, str] = {}
    suggestions: list[str] = []

    # Documentation.
    doc = _clamp(0.45 * (1 if readme else 0) + 0.25 * (1 if docs_dir else 0) + 0.30 * min(md_files / 4, 1))
    components["documentation"] = round(doc, 3)
    reasoning["documentation"] = (
        f"{'README present. ' if readme else 'No README found. '}"
        f"{md_files} markdown file(s){', a docs/ directory' if docs_dir else ''} across {source} files."
    )
    if doc < 0.7:
        suggestions.append(
            "Documentation: add a README with setup/usage and per-module docs — "
            f"currently {md_files} markdown files{' and no README' if not readme else ''}."
        )

    # Test coverage (proxy: test-file ratio).
    ratio = test_files / max(source, 1)
    tc = _clamp(ratio / 0.25)  # ~25% test files reads as strong
    components["test_coverage"] = round(tc, 3)
    reasoning["test_coverage"] = f"{test_files} test/spec file(s) across {source} source files (~{ratio * 100:.0f}%)."
    if tc < 0.7:
        suggestions.append(
            f"Test coverage: only {test_files} test files for {source} sources — add unit tests around core modules."
        )

    # Modularity (import density — high coupling scores lower).
    mod = _clamp(1 - (avg_imports - 2) / 8)
    components["modularity"] = round(mod, 3)
    reasoning["modularity"] = f"~{avg_imports:.1f} internal imports per file ({len(code.imports)} total); lower coupling scores higher."
    if mod < 0.7:
        suggestions.append("Modularity: high import coupling — introduce interfaces/barrels to reduce direct cross-file dependencies.")

    # Maintainability (average file size).
    maint = _clamp(1 - (avg_loc - 120) / 400)
    components["maintainability"] = round(maint, 3)
    reasoning["maintainability"] = f"~{avg_loc:.0f} lines per source file on average; smaller files are easier to maintain."
    if maint < 0.7:
        suggestions.append(f"Maintainability: average file is ~{avg_loc:.0f} lines — split the largest files into focused modules.")

    # Type safety (TS share; for non-TS repos this reflects language consistency toward typed code).
    typing = _clamp(ts_files / max(source, 1)) if ts_files else 0.55
    components["type_safety"] = round(typing, 3)
    reasoning["type_safety"] = f"{ts_files}/{source} files are TypeScript." if ts_files else "No TypeScript detected; typing not measured."
    if typing < 0.6 and ts_files:
        suggestions.append("Type safety: convert remaining JavaScript files to TypeScript for stronger guarantees.")

    # Structure (conventional directory layout).
    structure = _clamp(len(conventional_hits) / 5)
    components["structure"] = round(structure, 3)
    reasoning["structure"] = f"Recognised directories: {', '.join(sorted(conventional_hits)) or 'none'}."
    if structure < 0.6:
        suggestions.append("Structure: organise code into conventional directories (src, components, services, tests).")

    score = round(sum(components.values()) / len(components), 3)
    if not suggestions:
        suggestions.append("Solid across the board — keep tests and docs current as the codebase grows.")

    return {"score": score, "components": components, "reasoning": reasoning, "suggestions": suggestions,
            "measured": {"source_files": source, "test_files": test_files, "avg_loc": round(avg_loc, 1),
                         "avg_imports": round(avg_imports, 2), "ts_files": ts_files}}
