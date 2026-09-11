"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Maximize2, Minimize2 } from "lucide-react";
import { Glyph, ProvSwatch, type GlyphData } from "./Glyph";
import { StrataInspector } from "./Inspector";
import { StrataMatrix, matrixGeometry } from "./Matrix";
import { StrataTimeBar } from "./TimeBar";
import { cubic, curveLen, pathD, route, taper, wrap, type Box, type Pt } from "@/lib/strata/geometry";
import {
  PRED_FAM,
  SRC_LABEL,
  TYPE_LABEL,
  edgeGhost,
  edgeLive,
  nodeLive,
  type SEdge,
  type SNode,
  type StrataModel,
} from "@/lib/strata/model";
import { focusLayout, type FocusLayout, type LabelPlace, type StrataLayout } from "@/lib/strata/layout";

type Mode = "strata" | "focus" | "matrix";
type Tip = { t: string; n: string; d?: string };

const MODES: { id: Mode; label: string }[] = [
  { id: "strata", label: "Strata" },
  { id: "focus", label: "Focus" },
  { id: "matrix", label: "Matrix" },
];

const INSIDE = new Set(["File", "ApiRoute", "ArchitectureTrend"]);
// A signal or intent node linked to more files than this draws its links only on demand (hover or
// select it, or a file it links to) — a first commit that touched 79 files is one fact, not 79 lines,
// and a dozen decisions each fanning into their files would bury the code band under intent lines.
const BUNDLE_OVER = 2;

function summaryOf(n: SNode): string {
  const p = n.props;
  const s = (k: string) => (typeof p[k] === "string" ? (p[k] as string) : "");
  return s("summary") || s("rule") || s("role") || (n.type !== "File" && s("path")) || s("kind") || "";
}

function NodeLabels({ n, mode, place, box, extra }: { n: SNode; mode: Mode; place?: LabelPlace; box: Box; extra?: string }) {
  if (INSIDE.has(n.type)) return null;
  const lp = mode === "strata" ? (place ?? "b") : "b";
  if (lp === "r")
    return (
      <text x={box.hw + 7} y={4} className="lbl">
        {n.label}
      </text>
    );
  const lines = wrap(n.label, mode === "strata" ? 20 : 22);
  if (lp === "t")
    return (
      <>
        {lines.map((l, i) => (
          <text key={i} y={-box.hh - 9 - (lines.length - 1 - i) * 14} textAnchor="middle" className="lbl">
            {l}
          </text>
        ))}
        {extra ? (
          <text y={box.hh + 14} textAnchor="middle" className="lbl sub">
            {extra}
          </text>
        ) : null}
      </>
    );
  const subs = [n.sub, extra].filter(Boolean) as string[];
  return (
    <>
      {lines.map((l, i) => (
        <text key={i} y={box.hh + 16 + i * 14} textAnchor="middle" className="lbl">
          {l}
        </text>
      ))}
      {subs.map((s, i) => (
        <text key={`s${i}`} y={box.hh + 16 + (lines.length + i) * 14} textAnchor="middle" className="lbl sub">
          {s}
        </text>
      ))}
    </>
  );
}

/** Selection ring (cls "sel-ring") or related-node ring (cls "rel-ring"), shaped to the glyph. */
function Ring({ n, box, cls }: { n: SNode; box: Box; cls: string }) {
  if (n.hull) return <rect x={-box.hw - 3} y={-box.hh - 3} width={2 * box.hw + 6} height={2 * box.hh + 6} rx={14} className={cls} />;
  if (n.type === "File" || n.type === "ApiRoute" || n.type === "ArchitectureTrend")
    return (
      <rect
        x={-box.hw - 4}
        y={-box.hh - 4}
        width={2 * box.hw + 8}
        height={2 * box.hh + 8}
        rx={n.type === "ApiRoute" ? 17 : n.type === "File" ? 9 : 13}
        className={cls}
      />
    );
  return <circle r={box.hw + 4} className={cls} />;
}

function AgentRing({ n, box }: { n: SNode; box: Box }) {
  if (n.type === "File" && !n.hull) {
    const r = { x: -box.hw - 5, y: -box.hh - 5, width: 2 * box.hw + 10, height: 2 * box.hh + 10, rx: 10 };
    return (
      <>
        <rect {...r} className="agent-ring" />
        <rect {...r} className="agent-pulse" />
      </>
    );
  }
  return (
    <>
      <circle r={box.hw + 5} className="agent-ring" />
      <circle r={box.hw + 5} className="agent-pulse" />
    </>
  );
}

export function StrataView({
  model,
  layout,
  startMs,
  endMs,
  agentIds,
  agentStatus,
}: {
  model: StrataModel;
  layout: StrataLayout;
  startMs: number;
  endMs: number;
  agentIds: Set<string>;
  agentStatus: string;
}) {
  const [mode, setMode] = useState<Mode>("strata");
  const [t, setT] = useState(endMs);
  const [sel, setSel] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [pos, setPos] = useState<Record<string, Pt>>(layout.pos);
  const [focus, setFocus] = useState<FocusLayout | null>(null);
  const [tip, setTip] = useState<Tip | null>(null);
  const posRef = useRef(layout.pos);
  const raf = useRef(0);
  const tipRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const drag = useRef<{ x: number; y: number; l: number; t: number; moved: boolean } | null>(null);
  const dragMoved = useRef(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const [isFull, setIsFull] = useState(false);
  // The document-level key handler is registered once; these refs let it reach the current state.
  const fullOnRef = useRef(false);
  const fullToggleRef = useRef<() => void>(() => {});
  const fullExitRef = useRef<() => void>(() => {});
  const pendingScroll = useRef<{ x: number | null } | null>(null);
  const [scrollTick, setScrollTick] = useState(0);

  // The symbol most of the code band depends on — Focus opens on it, the overview offers it.
  const hubId = useMemo(() => {
    const indeg = new Map<string, number>();
    for (const e of model.edges) if (!e.contain && e.vt === null) indeg.set(e.to, (indeg.get(e.to) ?? 0) + 1);
    const symbols = model.nodes.filter((n) => n.type === "CodeSymbol");
    const pool = symbols.length ? symbols : model.nodes;
    let best: string | null = null;
    let bestIn = -1;
    for (const n of pool) {
      const d = indeg.get(n.id) ?? 0;
      if (d > bestIn) {
        bestIn = d;
        best = n.id;
      }
    }
    return best;
  }, [model]);

  // A big graph shows its overview as fine, quiet lines and brings forward only what touches the
  // hovered or selected node; every intent / commit link is drawn on demand. Small graphs keep the
  // full-weight drawing.
  const dense = model.edges.length > 120;

  // Signal / intent nodes whose file links are drawn only on demand, and how many they carry.
  const bundled = useMemo(() => {
    const fan = new Map<string, number>();
    for (const e of model.edges) {
      if (e.contain) continue;
      const a = model.byId.get(e.from)!;
      const b = model.byId.get(e.to)!;
      if (a.fam !== "structure" && b.fam === "structure") fan.set(e.from, (fan.get(e.from) ?? 0) + 1);
    }
    return new Map([...fan].filter(([, n]) => n > (dense ? 0 : BUNDLE_OVER)));
  }, [model, dense]);

  const mxGeom = useMemo(() => matrixGeometry(model.nodes.length), [model]);

  const animateTo = useCallback((target: Record<string, Pt>) => {
    cancelAnimationFrame(raf.current);
    const from = posRef.current;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const D = reduce ? 0 : 560;
    const t0 = performance.now();
    const step = (now: number) => {
      const k = D ? Math.min(1, (now - t0) / D) : 1;
      const e = 1 - Math.pow(1 - k, 3);
      const next: Record<string, Pt> = {};
      for (const id in target) {
        const a = from[id] ?? target[id];
        const b = target[id];
        next[id] = { x: a.x + (b.x - a.x) * e, y: a.y + (b.y - a.y) * e };
      }
      posRef.current = next;
      setPos(next);
      if (k < 1) raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
  }, []);

  useEffect(() => {
    const r = raf;
    return () => cancelAnimationFrame(r.current);
  }, []);

  useEffect(() => {
    const want = pendingScroll.current;
    const c = canvasRef.current;
    if (!want || !c) return;
    pendingScroll.current = null;
    c.scrollTo({ left: want.x == null ? 0 : Math.max(0, want.x - c.clientWidth / 2), top: 0 });
  }, [scrollTick, focus, mode]);

  // Full screen is an in-page overlay that always works, upgraded to the browser's native full
  // screen where it is allowed (embedded browsers often refuse it). Leaving native full screen with
  // the browser's own Esc also leaves the overlay.
  useEffect(() => {
    const onChange = () => {
      if (!document.fullscreenElement) setIsFull(false);
    };
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  function setFull(on: boolean) {
    setIsFull(on);
    if (on) {
      const el = rootRef.current;
      el?.requestFullscreen?.().catch(() => {
        // Not allowed here — the overlay alone still fills the window.
      });
    } else if (document.fullscreenElement) {
      void document.exitFullscreen().catch(() => {});
    }
  }

  function toggleFull() {
    setFull(!isFull);
  }

  useEffect(() => {
    fullOnRef.current = isFull;
    fullToggleRef.current = () => setFull(!fullOnRef.current);
    fullExitRef.current = () => setFull(false);
  });

  // "/" jumps to search, "f" toggles full screen, from anywhere on the page.
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      const el = document.activeElement;
      const typing = el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement;
      if (ev.key === "/" && !typing) {
        ev.preventDefault();
        searchRef.current?.focus();
      }
      if ((ev.key === "f" || ev.key === "F") && !typing && !ev.metaKey && !ev.ctrlKey && !ev.altKey) {
        ev.preventDefault();
        fullToggleRef.current();
      }
      if (ev.key === "Escape" && !typing && fullOnRef.current) {
        fullExitRef.current();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  /** Ask for the canvas to be scrolled so x (view units, 1:1 with pixels outside Strata) is centred,
      at the top. Applied by the effect below, after the resized canvas has been committed — scrolling
      from the handler raced the re-render and could land on the old, narrower canvas. */
  function scrollCanvas(x: number | null) {
    pendingScroll.current = { x };
    setScrollTick((n) => n + 1);
  }

  function relayout(m: Mode, s: string | null, at: number, scroll = true): string | null {
    if (m === "focus") {
      const id = s ?? hubId;
      if (!id) return s;
      const f = focusLayout(model, id, at);
      setFocus(f);
      animateTo({ ...layout.pos, ...f.pos });
      if (scroll) scrollCanvas(f.centerX);
      return id;
    }
    setFocus(null);
    animateTo(layout.pos);
    if (scroll) scrollCanvas(null);
    return s;
  }

  function changeMode(m: Mode) {
    setMode(m);
    const s = relayout(m, sel, t);
    if (s !== sel) setSel(s);
  }

  function select(id: string) {
    if (mode === "focus") {
      setSel(id);
      relayout("focus", id, t);
      return;
    }
    setSel((cur) => (cur === id && mode === "strata" ? null : id));
  }

  function changeTime(nt: number) {
    setT(nt);
    if (mode === "focus" && sel) relayout("focus", sel, nt, false);
  }

  function act(a: "focus" | "strata" | "clear") {
    if (a === "clear") {
      setSel(null);
      if (mode === "focus") {
        setMode("strata");
        relayout("strata", null, t);
      }
      return;
    }
    changeMode(a);
  }

  function moveTip(ev: React.MouseEvent) {
    const c = canvasRef.current;
    const el = tipRef.current;
    if (!c || !el) return;
    const r = c.getBoundingClientRect();
    let x = ev.clientX - r.left + c.scrollLeft + 14;
    const y = ev.clientY - r.top + c.scrollTop + 14;
    if (x + 290 > r.width + c.scrollLeft) x -= 310;
    el.style.transform = `translate(${x}px, ${y}px)`;
  }

  // ---- Drag the background to pan, in any view (a wide Focus ring or a big Matrix scrolls sideways).
  function onPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    if (e.button !== 0 || (e.target as Element).closest?.(".node, input, button")) return;
    const c = canvasRef.current;
    if (!c) return;
    drag.current = { x: e.clientX, y: e.clientY, l: c.scrollLeft, t: c.scrollTop, moved: false };
    dragMoved.current = false;
  }
  function onPointerMove(e: React.PointerEvent<HTMLDivElement>) {
    const d = drag.current;
    const c = canvasRef.current;
    if (!d || !c) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (!d.moved && Math.hypot(dx, dy) < 4) return;
    d.moved = true;
    dragMoved.current = true;
    c.classList.add("panning");
    c.scrollLeft = d.l - dx;
    c.scrollTop = d.t - dy;
  }
  function endDrag() {
    drag.current = null;
    canvasRef.current?.classList.remove("panning");
  }

  // ---- Derived state for this frame.
  const active = hover ?? sel;
  const near = useMemo(() => {
    if (!active) return null;
    const s = new Set([active]);
    for (const e of model.edges) {
      if (!edgeLive(e, t) || (mode === "strata" && e.contain)) continue;
      if (e.from === active) s.add(e.to);
      if (e.to === active) s.add(e.from);
    }
    return s;
  }, [active, model, t, mode]);

  // What the selection lights up: a file's own symbols and what they call; a module's files; a
  // symbol's file. These wear a lighter ring in the signal colour and never dim.
  const lit = useMemo(() => {
    if (!sel) return null;
    const n = model.byId.get(sel);
    if (!n) return null;
    const s = new Set<string>();
    if (n.type === "File" && !n.hull) {
      const own = model.nodes.filter((x) => x.def?.fileId === sel).map((x) => x.id);
      own.forEach((id) => s.add(id));
      const ownSet = new Set(own);
      for (const e of model.edges) if (e.type === "calls" && ownSet.has(e.from) && edgeLive(e, t)) s.add(e.to);
    } else if (n.hull) {
      for (const x of model.nodes) if (x.type === "File" && !x.hull && x.dir === n.path) s.add(x.id);
    } else if (n.def) {
      s.add(n.def.fileId);
    }
    s.delete(sel);
    return s;
  }, [sel, model, t]);

  const match = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return null;
    return new Set(
      model.nodes
        .filter((n) => `${n.label} ${n.type} ${n.path ?? ""}`.toLowerCase().includes(needle))
        .map((n) => n.id),
    );
  }, [q, model]);

  const nodeVisible = (n: SNode) => mode !== "matrix" && nodeLive(n, t) && (mode !== "focus" || !focus || focus.set.has(n.id));
  const inFocus = (e: SEdge) => mode !== "focus" || !focus || (focus.set.has(e.from) && focus.set.has(e.to));
  const endsLive = (e: SEdge) => nodeLive(model.byId.get(e.from)!, t) && nodeLive(model.byId.get(e.to)!, t);
  const isLit = (id: string) => id === sel || (lit?.has(id) ?? false);

  function edgeState(e: SEdge): "gone" | "dim" | "on" {
    if (mode === "matrix" || !edgeLive(e, t) || !endsLive(e) || !inFocus(e) || (mode === "strata" && e.contain)) return "gone";
    if (mode === "strata" && bundled.has(e.from) && !(active === e.from || active === e.to || sel === e.from)) return "gone";
    if (match) return match.has(e.from) && match.has(e.to) ? "on" : "dim";
    if (active && e.from !== active && e.to !== active && !(isLit(e.from) && isLit(e.to))) return "dim";
    return "on";
  }

  const leaderFor = mode === "strata" ? active : null;
  const leaders = useMemo(() => {
    if (!leaderFor) return [];
    const n = model.byId.get(leaderFor);
    if (!n) return [];
    const pairs = n.def ? [[n.id, n.def.fileId]] : model.nodes.filter((s) => s.def?.fileId === n.id).map((s) => [s.id, n.id]);
    return pairs
      .filter(([s, f]) => nodeLive(model.byId.get(s)!, t) && !!pos[s] && !!pos[f])
      .map(([s, f]) => {
        const a = pos[s];
        const b = pos[f];
        const sx = a.x + 8;
        const tx = b.x - 70;
        return `M${sx} ${a.y}C${sx + 110} ${a.y} ${tx - 110} ${b.y} ${tx} ${b.y}`;
      });
  }, [leaderFor, model, pos, t]);

  const liveEdges = model.edges.filter((e) => edgeLive(e, t));
  const liveNodes = model.nodes.filter((n) => nodeLive(n, t));
  const selNode = sel ? (model.byId.get(sel) ?? null) : null;
  const order = useMemo(() => [...model.nodes].sort((a, b) => Number(b.hull) - Number(a.hull)), [model]);
  const view =
    mode === "focus" && focus
      ? { w: focus.width, h: focus.height }
      : mode === "matrix"
        ? { w: mxGeom.width, h: mxGeom.height }
        : { w: layout.width, h: layout.height };
  const ct = layout.codeTop;
  const cb = layout.codeBottom;
  const hints = mode === "strata" ? layout.hints : null;

  const glyphData = (n: SNode): GlyphData => ({
    type: n.type,
    label: n.label,
    method: n.method,
    loc: typeof n.props.loc === "number" ? (n.props.loc as number) : undefined,
    hullName: n.hull ? `${n.path}/` : undefined,
    hullW: n.hull ? layout.boxes[n.id].hw * 2 : undefined,
    hullH: n.hull ? layout.boxes[n.id].hh * 2 : undefined,
    score: n.score,
    trend: n.trend,
  });

  const curveOf = (e: SEdge) => {
    const a = pos[e.from];
    const b = pos[e.to];
    if (!a || !b) return null;
    return route(hints?.[e.id] ?? {}, layout.boxes[e.from], a, layout.boxes[e.to], b);
  };

  return (
    <div ref={rootRef} className={`strata flex min-h-0 flex-1 flex-col${isFull ? " is-full" : ""}`}>
      <div className="bar">
        <div className="seg" role="tablist" aria-label="View">
          {MODES.map((m) => (
            <button key={m.id} role="tab" aria-selected={mode === m.id} onClick={() => changeMode(m.id)}>
              {m.label}
            </button>
          ))}
        </div>
        <label className="search">
          <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden style={{ color: "var(--faint)" }}>
            <circle cx="7" cy="7" r="5" fill="none" stroke="currentColor" strokeWidth="1.6" />
            <path d="M11 11l3.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
          <input
            ref={searchRef}
            type="search"
            placeholder="Find a node"
            aria-label="Find a node"
            autoComplete="off"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                const needle = q.trim().toLowerCase();
                const hit = model.nodes.find(
                  (n) => nodeLive(n, t) && `${n.label} ${n.path ?? ""}`.toLowerCase().includes(needle),
                );
                if (hit && needle) {
                  setQ("");
                  if (mode === "focus") select(hit.id);
                  else setSel(hit.id);
                  e.currentTarget.blur();
                }
              }
              if (e.key === "Escape") {
                setQ("");
                e.currentTarget.blur();
              }
            }}
          />
          <kbd>/</kbd>
        </label>
        <button
          className="fs-btn"
          onClick={toggleFull}
          aria-pressed={isFull}
          aria-label={isFull ? "Exit full screen" : "Full screen"}
          title={isFull ? "Exit full screen (F or Esc)" : "Full screen (F)"}
        >
          {isFull ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          <span>{isFull ? "Exit full screen" : "Full screen"}</span>
        </button>
        <div className="legend" aria-label="Legend">
          <span>
            <svg width="16" height="16" viewBox="-8 -8 16 16" aria-hidden>
              <circle r="5" className="s-fill" />
            </svg>
            Structure
          </span>
          <span>
            <svg width="16" height="16" viewBox="-8 -8 16 16" aria-hidden>
              <path d="M0 -6L6 0L0 6L-6 0Z" className="r-fill" />
            </svg>
            Intent
          </span>
          <span>
            <svg width="16" height="16" viewBox="-8 -8 16 16" aria-hidden>
              <circle r="5" className="g-fill" />
            </svg>
            Signals
          </span>
          <span>
            <svg width="16" height="16" viewBox="-8 -8 16 16" aria-hidden>
              <circle r="5" className="agent-ring" strokeWidth="2" />
            </svg>
            Agent
          </span>
          <span className="sep" />
          <span>
            <ProvSwatch src="static_analysis" fam="struct" conf={1} />
            Static
          </span>
          <span>
            <ProvSwatch src="human_asserted" fam="struct" conf={1} />
            Human
          </span>
          <span>
            <ProvSwatch src="llm_inferred" fam="struct" conf={1} />
            LLM
          </span>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 grid-rows-[minmax(0,1fr)_minmax(0,40%)] lg:grid-cols-[minmax(0,1fr)_312px] lg:grid-rows-1">
        <div
          className="canvas"
          ref={canvasRef}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerLeave={endDrag}
        >
          <svg
            viewBox={`0 0 ${view.w} ${view.h}`}
            shapeRendering="geometricPrecision"
            style={mode === "strata" ? undefined : { width: view.w, height: view.h, margin: "0 auto" }}
            role="img"
            aria-label={`Knowledge graph, ${mode} view`}
            onClick={() => {
              if (dragMoved.current) {
                dragMoved.current = false;
                return;
              }
              if (sel && mode === "strata") setSel(null);
            }}
          >
            {/* Bands, column heads and the module regions that aren't nodes themselves. */}
            <g className={mode === "strata" ? "" : "gone"}>
              <line x1={14} x2={1186} y1={ct} y2={ct} className="band-rule" />
              <line x1={14} x2={1186} y1={cb} y2={cb} className="band-rule" />
              {(
                [
                  ["INTENT", (28 + ct) / 2],
                  ["CODE", (ct + cb) / 2],
                  ["SIGNALS", (cb + layout.height) / 2],
                ] as const
              ).map(([name, y]) => (
                <text key={name} x={24} y={y} className="band-name" transform={`rotate(-90 24 ${y})`} textAnchor="middle">
                  {name}
                </text>
              ))}
              <text x={44} y={66} className="band-cap">
                Why it is built this way.
              </text>
              <text x={44} y={84} className="band-cap">
                Each decision sits above the code it governs.
              </text>
              {(
                [
                  ["ROUTE", 44],
                  ["SYMBOL", 323],
                  ["FILE IN MODULE", 572],
                  ["REPOSITORY", 1076],
                ] as const
              ).map(([name, x]) => (
                <text key={name} x={x} y={ct + 14} className="band-name" style={{ fill: "var(--faint)" }}>
                  {name}
                </text>
              ))}
              <text x={44} y={cb + 26} className="band-cap">
                What happened, and how healthy it is. Causal chains read left to right.
              </text>
              {layout.modules
                .filter((r) => !r.nodeId)
                .map((r) => (
                  <g key={r.dir}>
                    <rect x={r.x} y={r.y} width={r.w} height={r.h} rx={12} className="hull" />
                    <text x={r.x + 10} y={r.y + 15} className="hull-name">
                      {r.name}
                    </text>
                  </g>
                ))}
            </g>

            {/* Recently expired relations, dashed, while scrubbing history. */}
            <g>
              {mode === "matrix"
                ? null
                : model.edges.map((e) => {
                    if (!(edgeGhost(e, t) && endsLive(e) && inFocus(e) && !(mode === "strata" && e.contain))) return null;
                    const c = curveOf(e);
                    return c ? <path key={e.id} d={pathD(c)} className="ghost" /> : null;
                  })}
            </g>

            <g>
              {model.edges.map((e) => {
                const state = edgeState(e);
                if (state === "gone") return null;
                const c = curveOf(e);
                if (!c) return null;
                const fam = PRED_FAM[e.type];
                const touches = !!active && (e.from === active || e.to === active || (isLit(e.from) && isLit(e.to)));
                const quiet = dense && mode === "strata" && !touches;
                const op = (quiet ? 0.18 + 0.24 * e.conf : 0.35 + 0.6 * e.conf).toFixed(2);
                const w0 = quiet ? 0.8 + 0.7 * e.conf : dense ? 1.3 + 1.7 * e.conf : 1.6 + 2.6 * e.conf;
                let beads: { x: number; y: number; r: number }[] | null = null;
                if (e.src === "llm_inferred") {
                  const n = Math.max(4, Math.round(curveLen(c) / 7));
                  beads = Array.from({ length: n + 1 }, (_, i) => {
                    const p = cubic(c, i / n);
                    return { x: p.x, y: p.y, r: 2.1 - (1.3 * i) / n };
                  });
                }
                const ring = e.src === "human_asserted" ? cubic(c, 0.5) : null;
                return (
                  <g key={e.id} className={state === "dim" ? "edge dim" : "edge"}>
                    {beads ? (
                      <g className={`e-${fam}`} opacity={op}>
                        {beads.map((b, i) => (
                          <circle key={i} cx={b.x.toFixed(1)} cy={b.y.toFixed(1)} r={b.r.toFixed(2)} />
                        ))}
                      </g>
                    ) : (
                      <path d={taper(c, w0, quiet ? 0.3 : 0.5)} className={`e-${fam}`} opacity={op} />
                    )}
                    {ring ? (
                      <circle
                        cx={ring.x.toFixed(1)}
                        cy={ring.y.toFixed(1)}
                        r={2.7}
                        className={`hole ring-${fam}`}
                        strokeWidth={1.3}
                        opacity={(0.45 + 0.5 * e.conf).toFixed(2)}
                      />
                    ) : null}
                  </g>
                );
              })}
            </g>

            <g>
              {leaders.map((d, i) => (
                <path key={i} d={d} className="leader" />
              ))}
            </g>

            <g>
              {order.map((n) => {
                const p = pos[n.id];
                if (!p) return null;
                const box = layout.boxes[n.id];
                const visible = nodeVisible(n);
                let cls = "node";
                if (!visible) cls += " gone";
                else if (match && !match.has(n.id)) cls += " dim";
                else if (near && !near.has(n.id) && !isLit(n.id)) cls += " dim";
                const hitBox = n.hull
                  ? { x: -box.hw, y: -box.hh, width: 2 * box.hw, height: 22 }
                  : { x: -box.hw - 6, y: -box.hh - 6, width: 2 * box.hw + 12, height: 2 * box.hh + 12 };
                const fan = mode === "strata" ? bundled.get(n.id) : undefined;
                return (
                  <g
                    key={n.id}
                    className={cls}
                    transform={`translate(${p.x.toFixed(1)} ${p.y.toFixed(1)})`}
                    tabIndex={visible ? 0 : -1}
                    role="button"
                    aria-label={`${TYPE_LABEL[n.type]}: ${n.hull ? n.path : n.label}`}
                    onMouseEnter={(ev) => {
                      setHover(n.id);
                      setTip({ t: TYPE_LABEL[n.type], n: n.path ?? n.label, d: summaryOf(n) || undefined });
                      moveTip(ev);
                    }}
                    onMouseMove={moveTip}
                    onMouseLeave={() => {
                      setHover(null);
                      setTip(null);
                    }}
                    onClick={(ev) => {
                      ev.stopPropagation();
                      select(n.id);
                    }}
                    onKeyDown={(ev) => {
                      if (ev.key === "Enter" || ev.key === " ") {
                        ev.preventDefault();
                        select(n.id);
                      }
                    }}
                  >
                    <rect {...hitBox} rx={8} className="hit" />
                    {agentIds.has(n.id) && !n.hull ? <AgentRing n={n} box={box} /> : null}
                    <g>
                      <Glyph d={glyphData(n)} />
                    </g>
                    {mode !== "matrix" && sel === n.id ? <Ring n={n} box={box} cls="sel-ring" /> : null}
                    {mode !== "matrix" && sel !== n.id && lit?.has(n.id) ? <Ring n={n} box={box} cls="rel-ring" /> : null}
                    <NodeLabels
                      n={n}
                      mode={mode}
                      place={layout.place[n.id]}
                      box={box}
                      extra={fan ? `${fan} file${fan === 1 ? "" : "s"}` : undefined}
                    />
                  </g>
                );
              })}
            </g>

            {mode === "matrix" ? (
              <StrataMatrix
                model={model}
                layout={layout}
                t={t}
                onCell={(e, ev) => {
                  const a = model.byId.get(e.from)!;
                  const b = model.byId.get(e.to)!;
                  const ago = (ms: number) => Math.max(0, Math.round((endMs - ms) / 86_400_000));
                  setTip({
                    t: `${e.type.replace(/_/g, " ")} · ${SRC_LABEL[e.src]}`,
                    n: `${a.label} → ${b.label}`,
                    d: `confidence ${e.conf.toFixed(2)} · valid from ${ago(e.vf)} days ago${e.vt !== null ? ` · ended ${ago(e.vt)} days ago` : ""}`,
                  });
                  moveTip(ev);
                }}
                onMove={moveTip}
                onLeave={() => setTip(null)}
              />
            ) : null}
          </svg>
          <div className={`tip${tip ? " on" : ""}`} ref={tipRef} role="status">
            {tip ? (
              <>
                <div className="t">{tip.t}</div>
                <div className="n">{tip.n}</div>
                {tip.d ? <div className="d">{tip.d}</div> : null}
              </>
            ) : null}
          </div>
        </div>
        <aside className="insp" aria-live="polite">
          <StrataInspector
            model={model}
            sel={selNode}
            t={t}
            nowMs={endMs}
            mode={mode}
            agentIds={agentIds}
            agentStatus={agentStatus}
            hubId={hubId}
            onGo={(id) => {
              if (mode === "focus") select(id);
              else setSel(id);
            }}
            onAct={act}
          />
        </aside>
      </div>

      <StrataTimeBar
        startMs={startMs}
        endMs={endMs}
        t={t}
        edges={model.edges}
        liveNodes={liveNodes.length}
        liveEdges={liveEdges.length}
        onChange={changeTime}
      />
    </div>
  );
}
