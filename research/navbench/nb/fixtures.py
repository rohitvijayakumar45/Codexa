"""Layer A: seeded fixtures with a generator-produced manifest (independent of every evaluated tool).

Each fixture is a small repository containing one instance of every pattern. Names are either
unique (low lexical ambiguity) or drawn from a pool of common identifiers that also appear as
unrelated declarations and calls elsewhere in the fixture (high lexical ambiguity).

Manifest categories per target:
  explicit  - a source call expression whose callee statically binds to the target (gold for T1)
  dynamic   - call resolvable only at runtime (getattr / string index); reported separately
  indirect  - target passed as a value and invoked through a parameter; reported separately
  reference - non-call mention (import, argument, base class); never a call site
  distractor- same-name call/declaration/comment/string that does NOT refer to the target
"""
from __future__ import annotations

import json
import random
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

AMBIG_POOL = ["get", "run", "load", "update", "process", "handle", "build", "parse", "send", "close",
              "start", "reset", "apply_", "fetch", "render", "check", "merge", "resolve", "emit", "init_"]
WORDS = ["amber", "basil", "cobalt", "delta", "ember", "fjord", "garnet", "harbor", "indigo", "juniper",
         "kelp", "lumen", "mosaic", "nectar", "onyx", "prism", "quartz", "russet", "saffron", "tundra"]


@dataclass
class Site:
    file: str
    line: int
    col: int
    category: str          # explicit | dynamic | indirect | reference | distractor
    caller: str            # enclosing declaration key ("module:<file>" at module level)


@dataclass
class Target:
    key: str               # stable key within the fixture
    name: str
    qualname: str
    kind: str              # function | method | class
    file: str
    line: int
    col: int
    sites: list[Site] = field(default_factory=list)


class Writer:
    """Builds files line by line and records token positions for the manifest."""

    def __init__(self):
        self.files: dict[str, list[str]] = {}
        self.cur: str | None = None

    def open(self, rel: str):
        self.cur = rel
        self.files.setdefault(rel, [])

    def line(self, text: str) -> int:
        self.files[self.cur].append(text)
        return len(self.files[self.cur])

    def pos(self, line_no: int, token: str, nth: int = 0) -> tuple[str, int, int]:
        text = self.files[self.cur][line_no - 1]
        start = -1
        for _ in range(nth + 1):
            start = text.find(token, start + 1)
            # whole-identifier match
            while start >= 0 and ((start > 0 and (text[start - 1].isalnum() or text[start - 1] == "_")) or
                                  (start + len(token) < len(text) and (text[start + len(token)].isalnum() or text[start + len(token)] == "_"))):
                start = text.find(token, start + 1)
        if start < 0:
            raise ValueError(f"token {token!r} not on line {line_no}: {text!r}")
        return (self.cur, line_no, start)

    def dump(self, root: Path):
        for rel, lines in self.files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _names(rng: random.Random, ambiguous: bool) -> dict[str, str]:
    if ambiguous:
        pool = rng.sample(AMBIG_POOL, 8)
        # T_direct and T_reexp share common names; M is the method name shared with the distractor class
        return {"direct": pool[0], "reexp": pool[1], "M": pool[2], "decorated": pool[3], "hof": pool[4],
                "dyn": pool[5], "svc": rng.choice(["Client", "Handler", "Service", "Manager"]),
                "other": rng.choice(["Worker", "Session", "Adapter", "Store"]), "noise": [pool[0], pool[2], pool[1]]}
    w = rng.sample(WORDS, 9)
    n = rng.randint(10, 99)
    return {"direct": f"{w[0]}_{n}", "reexp": f"{w[1]}_relay{n}", "M": f"{w[2]}_op{n}",
            "decorated": f"{w[3]}_wrapped{n}", "hof": f"{w[4]}_cb{n}", "dyn": f"{w[5]}_dyn{n}",
            "svc": f"{w[6].capitalize()}Svc{n}", "other": f"{w[7].capitalize()}Peer{n}", "noise": [f"{w[8]}_x{n}"]}


# --------------------------------------------------------------------------------------- Python
def gen_python(root: Path, seed: int, ambiguous: bool) -> dict:
    rng = random.Random(seed)
    N = _names(rng, ambiguous)
    pkg = rng.choice(["app", "core_lib", "svc", "toolkit"]) + f"{seed}"
    W = Writer()
    T: dict[str, Target] = {}

    def tgt(key, name, qual, kind, line, token, nth=0):
        f, l, c = W.pos(line, token, nth)
        T[key] = Target(key, name, qual, kind, f, l, c)

    def site(key, line, token, cat, caller, nth=0):
        f, l, c = W.pos(line, token, nth)
        T[key].sites.append(Site(f, l, c, cat, caller))

    d, rx, M, dec, hof, dyn, Svc, Oth = (N["direct"], N["reexp"], N["M"], N["decorated"], N["hof"], N["dyn"],
                                         N["svc"], N["other"])
    core = f"{pkg}/core.py"
    W.open(core)
    W.line("import functools")
    W.line("")
    W.line("")
    l = W.line(f"def {d}(x):"); tgt("direct", d, d, "function", l, d)
    W.line("    return x + 1")
    W.line("")
    W.line("")
    l = W.line(f"def {rx}(x):"); tgt("reexp", rx, rx, "function", l, rx)
    W.line("    return x * 2")
    W.line("")
    W.line("")
    l = W.line(f"class {Svc}:"); tgt("svc", Svc, Svc, "class", l, Svc)
    W.line("    def __init__(self):")
    W.line("        self.v = 0")
    W.line("")
    l = W.line(f"    def {M}(self, x):"); tgt("M", M, f"{Svc}.{M}", "method", l, M)
    W.line("        return x - 1")
    W.line("")
    W.line("    def caller_self(self):")
    l = W.line(f"        return self.{M}(1)"); site("M", l, M, "explicit", f"{Svc}.caller_self")
    W.line("")
    W.line("")
    W.line(f"class {Oth}:")
    l = W.line(f"    def {M}(self, x):")
    W.line("        return -x")
    W.line("")
    W.line("")
    W.line("def deco(fn):")
    W.line("    @functools.wraps(fn)")
    W.line("    def wrapper(*a):")
    wrap_line = W.line("        return fn(*a)")
    W.line("    return wrapper")
    W.line("")
    W.line("")
    W.line("@deco")
    l = W.line(f"def {dec}(x):"); tgt("decorated", dec, dec, "function", l, dec)
    # implicit: the decorator's wrapper invokes the decorated function at runtime
    T["decorated"].sites.append(Site(core, wrap_line, W.files[core][wrap_line - 1].find("fn(*a)"), "indirect", "deco.wrapper"))
    W.line("    return x + 3")
    W.line("")
    W.line("")
    l = W.line(f"def {hof}(x):"); tgt("hof", hof, hof, "function", l, hof)
    W.line("    return x + 4")
    W.line("")
    W.line("")
    W.line("def apply_fn(fn, v):")
    l = W.line("    return fn(v)")
    T["hof"].sites.append(Site(core, l, W.files[core][l - 1].find("fn(v)"), "indirect", "apply_fn"))
    W.line("")
    W.line("")
    l = W.line(f"def {dyn}(x):"); tgt("dyn", dyn, dyn, "function", l, dyn)
    W.line("    return x + 5")

    init = f"{pkg}/__init__.py"
    W.open(init)
    l = W.line(f"from .core import {rx}"); site("reexp", l, rx, "reference", f"module:{init}")
    W.line(f"__all__ = [\"{rx}\"]")

    # noise module: unrelated same-name declarations and calls (ambiguity for name-based lookup)
    noise = f"{pkg}/noise.py"
    W.open(noise)
    for nm in N["noise"]:
        l = W.line(f"def {nm}(*a):")
        W.line("    return len(a)")
        W.line("")
        W.line("")
    W.line("def noise_driver():")
    for nm in N["noise"]:
        l = W.line(f"    {nm}(0)")
        for k in ("direct", "M", "reexp"):
            if T[k].name == nm:
                T[k].sites.append(Site(noise, l, W.files[noise][l - 1].find(nm), "distractor", "noise_driver"))
    W.line("    return 0")

    use = f"{pkg}/use_{rng.choice(['a', 'main', 'flow'])}.py"
    W.open(use)
    l = W.line(f"from .core import {d}, {Svc}, {Oth}, {dec}, {hof}, apply_fn")
    for k, tok in (("direct", d), ("svc", Svc), ("decorated", dec), ("hof", hof)):
        site(k, l, tok, "reference", f"module:{use}")
    l = W.line(f"from .core import {d} as alias_call"); site("direct", l, d, "reference", f"module:{use}")
    W.line("from . import core")
    l = W.line(f"from {pkg} import {rx}"); site("reexp", l, rx, "reference", f"module:{use}")
    W.line("")
    W.line(f"# {d} is mentioned in this comment and must not count")
    l = W.line(f"LABEL = \"{d}\"")
    T["direct"].sites.append(Site(use, l, W.files[use][l - 1].find(d), "distractor", f"module:{use}"))
    l = W.line(f"VALUE = {d}(0)"); site("direct", l, d, "explicit", f"module:{use}")
    W.line("")
    W.line("")
    body = []

    def fn(name, lines_spec):
        body.append((name, lines_spec))

    fn("use_direct", [(f"    return {d}(1)", [("direct", d, "explicit")])])
    fn("use_alias", [("    return alias_call(2)", [("direct", "alias_call", "explicit")])])
    fn("use_module_attr", [(f"    return core.{d}(3)", [("direct", d, "explicit")])])
    fn("use_typed", [(f"    s: {Svc} = {Svc}()", [("svc", Svc, "reference", 0), ("svc", Svc, "explicit", 1)]),
                     (f"    return s.{M}(4)", [("M", M, "explicit")])])
    fn("use_other", [(f"    o = {Oth}()", []), (f"    return o.{M}(5)", [("M", M, "distractor")])])
    fn("use_decorated", [(f"    return {dec}(6)", [("decorated", dec, "explicit")])])
    fn("use_hof", [(f"    return apply_fn({hof}, 7)", [("hof", hof, "reference")])])
    fn("use_dynamic", [(f"    return getattr(core, \"{dyn}\")(8)", [("dyn", dyn, "dynamic")])])
    fn("use_reexport", [(f"    return {rx}(9)", [("reexp", rx, "explicit")])])
    fn("use_shadow", [(f"    def {d}(x):", [("direct", d, "distractor")]), ("        return -x", []),
                      (f"    return {d}(10)", [("direct", d, "distractor")])])
    rng.shuffle(body)
    for name, spec in body:
        W.line(f"def {name}():")
        for text, marks in spec:
            l = W.line(text)
            for mk in marks:
                key, tok, cat = mk[0], mk[1], mk[2]
                nth = mk[3] if len(mk) > 3 else 0
                f_, l_, c_ = W.pos(l, tok, nth)
                T[key].sites.append(Site(f_, l_, c_, cat, name))
        W.line("")
        W.line("")
    l = W.line(f"class Sub({Svc}):"); site("svc", l, Svc, "reference", f"module:{use}")
    l = W.line(f"    def {M}(self, x):")
    l = W.line(f"        return super().{M}(x)"); site("M", l, M, "explicit", f"Sub.{M}")
    W.line("")
    W.line("")
    W.line("def run_all():")
    W.line("    total = VALUE")
    for name, _ in sorted(body):
        W.line(f"    total += {name}()")
    l = W.line(f"    total += {Svc}().caller_self() + Sub().{M}(11)"); site("svc", l, Svc, "explicit", "run_all")
    W.line("    return total")
    # run_all's own calls to use_* are not targets; Sub().M(11) calls Sub.M (not Svc.M directly).
    main = "main.py"
    W.open(main)
    W.line(f"from {pkg}.{Path(use).stem} import run_all")
    W.line(f"from {pkg}.noise import noise_driver")
    W.line("")
    W.line("if __name__ == \"__main__\":")
    W.line("    print(run_all() + noise_driver())")

    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    W.dump(root)
    man = {"language": "python", "seed": seed, "ambiguous": ambiguous, "package": pkg,
           "targets": [asdict(t) for t in T.values()]}
    (root / ".navbench-manifest.json").write_text(json.dumps(man, indent=1))
    return man


# --------------------------------------------------------------------------------------- TypeScript
def gen_ts(root: Path, seed: int, ambiguous: bool) -> dict:
    rng = random.Random(seed + 7919)
    N = _names(rng, ambiguous)
    W = Writer()
    T: dict[str, Target] = {}
    d, rx, M, arrow, hof, dyn, Svc, Oth = (N["direct"], N["reexp"], N["M"], N["decorated"], N["hof"], N["dyn"],
                                           N["svc"], N["other"])

    def tgt(key, name, qual, kind, line, token, nth=0):
        f, l, c = W.pos(line, token, nth)
        T[key] = Target(key, name, qual, kind, f, l, c)

    def site(key, line, token, cat, caller, nth=0):
        f, l, c = W.pos(line, token, nth)
        T[key].sites.append(Site(f, l, c, cat, caller))

    core = "src/core.ts"
    W.open(core)
    l = W.line(f"export function {d}(x: number): number {{"); tgt("direct", d, d, "function", l, d)
    W.line("  return x + 1;")
    W.line("}")
    W.line("")
    l = W.line(f"export function {rx}(x: number): number {{"); tgt("reexp", rx, rx, "function", l, rx)
    W.line("  return x * 2;")
    W.line("}")
    W.line("")
    l = W.line(f"export class {Svc} {{"); tgt("svc", Svc, Svc, "class", l, Svc)
    W.line("  v = 0;")
    l = W.line(f"  {M}(x: number): number {{"); tgt("M", M, f"{Svc}.{M}", "method", l, M)
    W.line("    return x - 1;")
    W.line("  }")
    W.line("  callerSelf(): number {")
    l = W.line(f"    return this.{M}(1);"); site("M", l, M, "explicit", f"{Svc}.callerSelf")
    W.line("  }")
    W.line("}")
    W.line("")
    W.line(f"export class {Oth} {{")
    W.line(f"  {M}(x: number): number {{")
    W.line("    return -x;")
    W.line("  }")
    W.line("}")
    W.line("")
    l = W.line(f"export const {arrow} = (x: number): number => x + 3;"); tgt("decorated", arrow, arrow, "function", l, arrow)
    W.line("")
    l = W.line(f"export function {hof}(x: number): number {{"); tgt("hof", hof, hof, "function", l, hof)
    W.line("  return x + 4;")
    W.line("}")
    W.line("")
    W.line("export function applyFn(fn: (v: number) => number, v: number): number {")
    l = W.line("  return fn(v);")
    T["hof"].sites.append(Site(core, l, W.files[core][l - 1].find("fn(v)"), "indirect", "applyFn"))
    W.line("}")
    W.line("")
    l = W.line(f"export function {dyn}(x: number): number {{"); tgt("dyn", dyn, dyn, "function", l, dyn)
    W.line("  return x + 5;")
    W.line("}")

    idx = "src/index.ts"
    W.open(idx)
    l = W.line(f"export {{ {rx} }} from \"./core\";"); site("reexp", l, rx, "reference", f"module:{idx}")

    noise = "src/noise.ts"
    W.open(noise)
    for nm in N["noise"]:
        W.line(f"export function {nm}(...a: number[]): number {{")
        W.line("  return a.length;")
        W.line("}")
        W.line("")
    W.line("export function noiseDriver(): number {")
    for nm in N["noise"]:
        l = W.line(f"  {nm}(0);")
        for k in ("direct", "M", "reexp"):
            if T[k].name == nm:
                T[k].sites.append(Site(noise, l, W.files[noise][l - 1].find(nm), "distractor", "noiseDriver"))
    W.line("  return 0;")
    W.line("}")

    use = f"src/use{rng.choice(['A', 'Main', 'Flow'])}.ts"
    W.open(use)
    l = W.line(f"import {{ {d}, {Svc}, {Oth}, {arrow}, {hof}, applyFn }} from \"./core\";")
    for k, tok in (("direct", d), ("svc", Svc), ("decorated", arrow), ("hof", hof)):
        site(k, l, tok, "reference", f"module:{use}")
    l = W.line(f"import {{ {d} as aliasCall }} from \"./core\";"); site("direct", l, d, "reference", f"module:{use}")
    W.line("import * as core from \"./core\";")
    l = W.line(f"import {{ {rx} }} from \"./index\";"); site("reexp", l, rx, "reference", f"module:{use}")
    W.line("")
    W.line(f"// {d} is mentioned in this comment and must not count")
    l = W.line(f"export const LABEL = \"{d}\";")
    T["direct"].sites.append(Site(use, l, W.files[use][l - 1].find(d), "distractor", f"module:{use}"))
    l = W.line(f"export const VALUE = {d}(0);"); site("direct", l, d, "explicit", f"module:{use}")
    W.line("")
    body = []

    def fn(name, spec):
        body.append((name, spec))

    fn("useDirect", [(f"  return {d}(1);", [("direct", d, "explicit")])])
    fn("useAlias", [("  return aliasCall(2);", [("direct", "aliasCall", "explicit")])])
    fn("useNamespace", [(f"  return core.{d}(3);", [("direct", d, "explicit")])])
    fn("useTyped", [(f"  const s: {Svc} = new {Svc}();", [("svc", Svc, "reference", 0), ("svc", Svc, "explicit", 1)]),
                    (f"  return s.{M}(4);", [("M", M, "explicit")])])
    fn("useOther", [(f"  const o = new {Oth}();", []), (f"  return o.{M}(5);", [("M", M, "distractor")])])
    fn("useArrow", [(f"  return {arrow}(6);", [("decorated", arrow, "explicit")])])
    fn("useHof", [(f"  return applyFn({hof}, 7);", [("hof", hof, "reference")])])
    fn("useDynamic", [(f"  return (core as any)[\"{dyn}\"](8);", [("dyn", dyn, "dynamic")])])
    fn("useReexport", [(f"  return {rx}(9);", [("reexp", rx, "explicit")])])
    fn("useShadow", [(f"  function {d}(x: number): number {{", [("direct", d, "distractor")]), ("    return -x;", []),
                     ("  }", []), (f"  return {d}(10);", [("direct", d, "distractor")])])
    rng.shuffle(body)
    for name, spec in body:
        W.line(f"export function {name}(): number {{")
        for text, marks in spec:
            l = W.line(text)
            for mk in marks:
                key, tok, cat = mk[0], mk[1], mk[2]
                nth = mk[3] if len(mk) > 3 else 0
                f_, l_, c_ = W.pos(l, tok, nth)
                T[key].sites.append(Site(f_, l_, c_, cat, name))
        W.line("}")
        W.line("")
    l = W.line(f"export class Sub extends {Svc} {{"); site("svc", l, Svc, "reference", f"module:{use}")
    W.line(f"  {M}(x: number): number {{")
    l = W.line(f"    return super.{M}(x);"); site("M", l, M, "explicit", f"Sub.{M}")
    W.line("  }")
    W.line("}")
    W.line("")
    W.line("export function runAll(): number {")
    W.line("  let total = VALUE;")
    for name, _ in sorted(body):
        W.line(f"  total += {name}();")
    l = W.line(f"  total += new {Svc}().callerSelf() + new Sub().{M}(11);"); site("svc", l, Svc, "explicit", "runAll")
    W.line("  return total;")
    W.line("}")
    main = "src/main.ts"
    W.open(main)
    W.line(f"import {{ runAll }} from \"./{Path(use).stem}\";")
    W.line("import { noiseDriver } from \"./noise\";")
    W.line("console.log(runAll() + noiseDriver());")
    W.open("tsconfig.json")
    W.line(json.dumps({"compilerOptions": {"target": "ES2020", "module": "commonjs", "strict": True,
                                           "outDir": "out", "rootDir": "src"}, "include": ["src"]}))

    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    W.dump(root)
    man = {"language": "typescript", "seed": seed, "ambiguous": ambiguous,
           "targets": [asdict(t) for t in T.values()]}
    (root / ".navbench-manifest.json").write_text(json.dumps(man, indent=1))
    return man


SPLITS = {"calib": range(0, 4), "heldout": range(100, 116)}


def generate_all(base: Path) -> list[dict]:
    out = []
    for split, seeds in SPLITS.items():
        for seed in seeds:
            amb = seed % 2 == 1
            for lang, gen in (("py", gen_python), ("ts", gen_ts)):
                name = f"fx-{lang}-{split}-{seed:03d}"
                man = gen(base / name, seed, amb)
                man.update({"repo": name, "split": split})
                (base / name / ".navbench-manifest.json").write_text(json.dumps(man, indent=1))
                (base / name / ".codexa-repo.json").write_text(json.dumps({"url": f"fixture://{name}"}))
                out.append(man)
    return out


if __name__ == "__main__":
    import sys
    ms = generate_all(Path(sys.argv[1]))
    print(len(ms), "fixtures,", sum(len(m["targets"]) for m in ms), "targets")
