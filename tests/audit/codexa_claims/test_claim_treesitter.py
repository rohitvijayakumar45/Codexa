import tempfile
from pathlib import Path
from backend.repository.analyze import analyze_repo, Analysis


def test_claim_treesitter_multilang_symbol_and_call_extraction():
    """Claim: Tree-sitter extracts functions, classes, imports, and calls across Python, JS, and TS."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        
        # 1. Python file
        py_file = root / "service.py"
        py_file.write_text(
            "import os\n"
            "from math import sqrt\n\n"
            "class Engine:\n"
            "    def start(self):\n"
            "        self.run()\n"
            "    def run(self):\n"
            "        print('running')\n\n"
            "def launch():\n"
            "    eng = Engine()\n"
            "    eng.start()\n",
            encoding="utf-8"
        )
        
        # 2. TypeScript file
        ts_file = root / "handler.ts"
        ts_file.write_text(
            "import { Request, Response } from 'express';\n\n"
            "export class AuthHandler {\n"
            "    validate(token: string): boolean {\n"
            "        return Boolean(token);\n"
            "    }\n"
            "}\n\n"
            "export const processAuth = (req: Request) => {\n"
            "    const h = new AuthHandler();\n"
            "    h.validate('xyz');\n"
            "};\n",
            encoding="utf-8"
        )
        
        # 3. JavaScript file
        js_file = root / "util.js"
        js_file.write_text(
            "function computeSum(a, b) {\n"
            "    return a + b;\n"
            "}\n"
            "module.exports = { computeSum };\n",
            encoding="utf-8"
        )

        analysis = analyze_repo(root)
        
        # Check files found
        assert "service.py" in analysis.files
        assert "handler.ts" in analysis.files
        assert "util.js" in analysis.files

        # Check Python symbols
        py_symbols = {s.name: s for s in analysis.symbols if s.file == "service.py"}
        assert "Engine" in py_symbols
        assert py_symbols["Engine"].kind == "class"
        assert "start" in py_symbols
        assert "run" in py_symbols
        assert "launch" in py_symbols

        # Check TypeScript symbols
        ts_symbols = {s.name: s for s in analysis.symbols if s.file == "handler.ts"}
        assert "AuthHandler" in ts_symbols
        assert ts_symbols["AuthHandler"].kind == "class"
        assert "validate" in ts_symbols
        assert "processAuth" in ts_symbols

        # Check JavaScript symbols
        js_symbols = {s.name: s for s in analysis.symbols if s.file == "util.js"}
        assert "computeSum" in js_symbols

        # Check Call relationships extracted (from_symbol_key, to_symbol_key)
        assert len(analysis.calls) > 0
        call_targets = {target for _, target in analysis.calls}
        assert any("start" in t or "run" in t or "validate" in t for t in call_targets)


def test_claim_treesitter_handles_syntax_errors_gracefully():
    """Claim: Tree-sitter error recovery allows AST extraction even with broken/malformed syntax."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        malformed = root / "broken.py"
        malformed.write_text(
            "def good_function():\n"
            "    return 42\n\n"
            "def broken_syntax(:\n"
            "    ??? not valid python !!!\n\n"
            "class SurvivingClass:\n"
            "    pass\n",
            encoding="utf-8"
        )

        analysis = analyze_repo(root)
        symbols = {s.name for s in analysis.symbols}
        # Tree-sitter's error recovery should successfully salvage good_function and SurvivingClass
        assert "good_function" in symbols
        assert "SurvivingClass" in symbols
