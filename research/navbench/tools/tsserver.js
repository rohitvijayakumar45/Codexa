// TS/JS source index + language-service reference provider (same engine as tsserver).
// Line-delimited JSON on stdin: {"cmd": "index"} | {"cmd": "refs", file, line, col} | {"cmd": "def", file, line, col}
// Lines are 1-based, columns 0-based UTF-16 (character) offsets.
const ts = require("typescript");
const fs = require("fs");
const path = require("path");

const root = path.resolve(process.argv[2]);
const SKIP = new Set([".git", "node_modules", "dist", "build", "coverage", ".next", "out", "vendor", "__pycache__", ".turbo", ".cache"]);
const EXT = /\.(ts|tsx|js|jsx|mjs|cjs|mts|cts)$/;

function walk(dir, acc) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (e.isDirectory()) { if (!SKIP.has(e.name)) walk(path.join(dir, e.name), acc); }
    else if (EXT.test(e.name) && !e.name.endsWith(".d.ts") && !/\.min\.js$/.test(e.name)) acc.push(path.join(dir, e.name));
  }
  return acc;
}
const files = walk(root, []);
let options = { allowJs: true, checkJs: false, noEmit: true, jsx: ts.JsxEmit.Preserve, target: ts.ScriptTarget.ESNext,
  module: ts.ModuleKind.ESNext, moduleResolution: ts.ModuleResolutionKind.Bundler, skipLibCheck: true, resolveJsonModule: true };
const tsconfig = path.join(root, "tsconfig.json");
if (fs.existsSync(tsconfig)) {
  try {
    const cfg = ts.readConfigFile(tsconfig, ts.sys.readFile);
    const parsed = ts.parseJsonConfigFileContent(cfg.config || {}, ts.sys, root);
    options = { ...parsed.options, ...{ allowJs: true, noEmit: true, skipLibCheck: true } };
    if (!options.moduleResolution) options.moduleResolution = ts.ModuleResolutionKind.Bundler;
  } catch (e) { /* fall back to defaults */ }
}
const versions = new Map(files.map((f) => [f, "1"]));
const host = {
  getScriptFileNames: () => files,
  getScriptVersion: (f) => versions.get(f) || "1",
  getScriptSnapshot: (f) => (fs.existsSync(f) ? ts.ScriptSnapshot.fromString(fs.readFileSync(f, "utf8")) : undefined),
  getCurrentDirectory: () => root,
  getCompilationSettings: () => options,
  getDefaultLibFileName: (o) => ts.getDefaultLibFilePath(o),
  fileExists: ts.sys.fileExists, readFile: ts.sys.readFile, readDirectory: ts.sys.readDirectory,
  directoryExists: ts.sys.directoryExists, getDirectories: ts.sys.getDirectories,
};
const ls = ts.createLanguageService(host, ts.createDocumentRegistry());
const rel = (f) => path.relative(root, f).split(path.sep).join("/");
const isTest = (r) => /(^|\/)(__tests__|tests?|spec|__mocks__)\//.test(r) || /\.(test|spec)\.[cm]?[jt]sx?$/.test(r);

function sf(file) { return ls.getProgram().getSourceFile(path.join(root, file)); }
function lc(s, pos) { const p = s.getLineAndCharacterOfPosition(pos); return [p.line + 1, p.character]; }

function index() {
  const decls = [], calls = [], failures = [];
  const program = ls.getProgram();
  for (const f of files) {
    const s = program.getSourceFile(f);
    const r = rel(f);
    if (!s) { failures.push(r); continue; }
    if (s.parseDiagnostics && s.parseDiagnostics.length) failures.push(r + " (partial)");
    const stack = [];   // enclosing decl ids for caller attribution
    const qual = [];
    function declName(n) {
      if (ts.isConstructorDeclaration(n)) {
        const kw = n.getChildren(s).find((c) => c.kind === ts.SyntaxKind.ConstructorKeyword);
        return kw ? { text: "constructor", getStart: (sf) => kw.getStart(sf) } : null;
      }
      if ((ts.isGetAccessorDeclaration(n) || ts.isSetAccessorDeclaration(n)) && n.name && ts.isIdentifier(n.name)) return n.name;
      if ((ts.isFunctionDeclaration(n) || ts.isClassDeclaration(n) || ts.isMethodDeclaration(n)) && n.name && ts.isIdentifier(n.name)) return n.name;
      if ((ts.isPropertyDeclaration(n) || ts.isVariableDeclaration(n) || ts.isPropertyAssignment(n)) && n.name && ts.isIdentifier(n.name) && n.initializer &&
          (ts.isArrowFunction(n.initializer) || ts.isFunctionExpression(n.initializer) || ts.isClassExpression(n.initializer))) return n.name;
      return null;
    }
    function kindOf(n) {
      if (ts.isConstructorDeclaration(n)) return "constructor";
      if (ts.isGetAccessorDeclaration(n) || ts.isSetAccessorDeclaration(n)) return "accessor";
      if (ts.isClassDeclaration(n) || (n.initializer && ts.isClassExpression(n.initializer))) return "class";
      if (ts.isMethodDeclaration(n) || ts.isPropertyDeclaration(n)) return "method";
      return "function";
    }
    function visit(n) {
      const nm = declName(n);
      let pushed = false;
      if (nm) {
        const [line, col] = lc(s, nm.getStart(s));
        const [endLine] = lc(s, n.getEnd());
        const id = `${r}:${line}:${col}`;
        const q = [...qual, nm.text].join(".");
        decls.push({ id, file: r, kind: kindOf(n), name: nm.text, qualname: q, line, col, first_line: lc(s, n.getStart(s))[0], end_line: endLine, is_test: isTest(r),
          caller: stack.length ? stack[stack.length - 1] : `module:${r}` });
        // enclosing scope covers the declaration body
        stack.push(id); qual.push(nm.text); pushed = true;
      }
      if (ts.isCallExpression(n) || ts.isNewExpression(n)) {
        let e = n.expression, nameNode = null;
        while (e && (ts.isParenthesizedExpression(e) || ts.isNonNullExpression(e) || ts.isAsExpression(e))) e = e.expression;
        if (e && ts.isIdentifier(e)) nameNode = e;
        else if (e && ts.isPropertyAccessExpression(e)) nameNode = e.name;
        else if (e && ts.isElementAccessExpression(e) && ts.isStringLiteralLike(e.argumentExpression)) nameNode = e.argumentExpression;
        else if (e && e.kind === ts.SyntaxKind.SuperKeyword) nameNode = null;
        const anchor = nameNode || n.expression;
        const [line, col] = lc(s, nameNode && ts.isStringLiteralLike(nameNode) ? nameNode.getStart(s) + 1 : anchor.getStart(s));
        calls.push({ id: `${r}:${line}:${col}`, file: r, line, col, name: nameNode ? (ts.isStringLiteralLike(nameNode) ? nameNode.text : nameNode.text) : null,
          isNew: ts.isNewExpression(n), caller: stack.length ? stack[stack.length - 1] : `module:${r}` });
      }
      ts.forEachChild(n, visit);
      if (pushed) { stack.pop(); qual.pop(); }
    }
    visit(s);
  }
  return { files: files.map(rel), decls, calls, failures };
}

function locs(entries) {
  const out = [];
  for (const e of entries || []) {
    const s = ls.getProgram().getSourceFile(e.fileName);
    const r = path.relative(root, e.fileName).split(path.sep).join("/");
    if (!s) { out.push([r, 0, 0]); continue; }
    const [line, col] = lc(s, e.textSpan.start);
    out.push([r.startsWith("..") ? "<external>" + e.fileName : r, line, col]);
  }
  return out;
}

const rl = require("readline").createInterface({ input: process.stdin });
rl.on("line", (line) => {
  let msg, res;
  try {
    msg = JSON.parse(line);
    if (msg.cmd === "index") res = index();
    else {
      const s = sf(msg.file);
      if (!s) throw new Error("no source file " + msg.file);
      const pos = s.getPositionOfLineAndCharacter(msg.line - 1, msg.col);
      const abs = path.join(root, msg.file);
      if (msg.cmd === "refs") {
        const refs = ls.getReferencesAtPosition(abs, pos) || [];
        // path.resolve normalises separators (TS reports "C:/x" on Windows; path.join gives "C:\x")
        res = locs(refs.filter((r) => !r.isDefinition && !(path.resolve(r.fileName) === path.resolve(abs) && r.textSpan.start === pos)));
      } else if (msg.cmd === "def") res = locs(ls.getDefinitionAtPosition(abs, pos));
    }
    process.stdout.write(JSON.stringify({ ok: true, res }) + "\n");
  } catch (e) {
    process.stdout.write(JSON.stringify({ ok: false, err: String(e && e.message || e) }) + "\n");
  }
});
