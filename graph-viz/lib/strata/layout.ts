/*
  Strata layout. Three horizontal bands, each asking a different question:

    INTENT   decisions, trade-offs, conventions — each above the code it governs
    CODE     request order left to right: route -> symbol -> file (in its module) -> repository
    SIGNALS  causal chains left to right, then health / trends / rules under what they concern

  Deterministic: the same graph always lays out the same way. Ties break on the API's insertion
  order so nothing jitters between loads. Bands grow with the graph instead of overflowing it: a
  crowded intent band wraps into more rows (pushing the code band down), a long commit history wraps
  across the signals band, and a large code band tightens its row pitch.
*/

import { wrap, type Box, type Pt, type RouteHints } from "./geometry";
import { edgeLive, type SEdge, type SNode, type StrataModel } from "./model";

export const WIDTH = 1200;
const INTENT_Y = 78;
const INTENT_ROW = 64;
export const CODE_TOP = 128;
const ROUTE_X = 158;
const SYM_X = 330;
const SYM_Y0 = 180;
const SYM_STEP = 60;
const SYM_STEP_DENSE = 36;
const REPO_X = 1112;
const HULL_TOP = 148;
const HULL_GAP = 12;
const TILE_STEP = 36;
const SIGNAL_ROW = 82;
const COLS = [
  { x: 572, w: 170 },
  { x: 800, w: 210 },
];

export type LabelPlace = "r" | "b" | "t";

export interface ModuleRect {
  dir: string;
  name: string;
  x: number;
  y: number;
  w: number;
  h: number;
  nodeId?: string;
}

export interface StrataLayout {
  width: number;
  height: number;
  /** Top of the code band (grows when the intent band wraps). */
  codeTop: number;
  codeBottom: number;
  pos: Record<string, Pt>;
  boxes: Record<string, Box>;
  modules: ModuleRect[];
  hints: Record<string, RouteHints>;
  place: Record<string, LabelPlace>;
}

export function baseBox(n: SNode): Box {
  switch (n.type) {
    case "File":
      return { hw: 70, hh: 13 };
    case "ApiRoute":
      return { hw: 118, hh: 13 };
    case "Repository":
      return { hw: 12, hh: 12, round: true };
    case "ArchitectureTrend":
      return { hw: 78, hh: 26 };
    case "HealthMetric":
      return { hw: 19, hh: 19, round: true };
    case "CodeSymbol":
      return { hw: 7, hh: 7, round: true };
    case "CausalEvent":
      return { hw: 8, hh: 8, round: true };
    default:
      return { hw: 11, hh: 11, round: true };
  }
}

/** Half the width a node's wrapped label needs (12px Geist ≈ 6.3px a character). */
export function labelHalf(n: SNode): number {
  if (n.type === "ArchitectureTrend" || n.type === "ApiRoute" || n.type === "File") return baseBox(n).hw;
  const lines = wrap(n.label, 20);
  return Math.max(baseBox(n).hw, Math.max(...lines.map((l) => l.length)) * 3.15);
}

const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;

function weight(e: SEdge): number {
  if (e.type === "calls" || e.type === "imports" || e.type === "flows_into") return 1;
  if (e.type === "depends_on") return 0.5;
  return 0.5 * e.conf;
}

const lexLess = (a: number[], b: number[]) => {
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] < b[i];
  return false;
};

/** Order nodes on a line so related ones sit close: exact for small sets, barycentric beyond. */
function orderLinear(nodes: SNode[], edges: SEdge[]): SNode[] {
  const n = nodes.length;
  if (n <= 2) return [...nodes].sort((a, b) => a.order - b.order);
  const idx = new Map(nodes.map((x, i) => [x.id, i]));
  const pairs: [number, number, number][] = [];
  for (const e of edges) {
    const a = idx.get(e.from);
    const b = idx.get(e.to);
    if (a == null || b == null || a === b) continue;
    pairs.push([a, b, weight(e)]);
  }
  if (n > 8) {
    let order = [...nodes.keys()].sort((a, b) => nodes[a].order - nodes[b].order);
    for (let sweep = 0; sweep < 8; sweep++) {
      const at = new Map(order.map((v, i) => [v, i]));
      const bary = order.map((v) => {
        const ns = pairs.flatMap(([a, b]) => (a === v ? [at.get(b)!] : b === v ? [at.get(a)!] : []));
        return ns.length ? mean(ns) : at.get(v)!;
      });
      order = order.map((v, i) => [v, bary[i]] as const).sort((a, b) => a[1] - b[1]).map((x) => x[0]);
    }
    return order.map((i) => nodes[i]);
  }
  const perm = [...Array(n).keys()];
  let best = [...perm];
  let bestCost = Infinity;
  const posOf = new Array<number>(n);
  const visit = () => {
    perm.forEach((v, i) => (posOf[v] = i));
    let c = 0;
    for (const [a, b, w] of pairs) c += w * Math.abs(posOf[a] - posOf[b]);
    if (
      c < bestCost - 1e-9 ||
      (Math.abs(c - bestCost) < 1e-9 && lexLess(perm.map((i) => nodes[i].order), best.map((i) => nodes[i].order)))
    ) {
      bestCost = c;
      best = [...perm];
    }
  };
  // Heap's algorithm.
  const cnt = new Array<number>(n).fill(0);
  visit();
  let i = 0;
  while (i < n) {
    if (cnt[i] < i) {
      const j = i % 2 === 0 ? 0 : cnt[i];
      [perm[j], perm[i]] = [perm[i], perm[j]];
      visit();
      cnt[i]++;
      i = 0;
    } else {
      cnt[i] = 0;
      i++;
    }
  }
  return best.map((k) => nodes[k]);
}

type RowItem = { id: string; want: number; half: number; order: number };
const GAP = 26;
const rowWidth = (items: RowItem[]) => items.reduce((s, it) => s + it.half * 2, 0) + Math.max(0, items.length - 1) * GAP;

/** Place items on one row: each at its desired x where possible, never closer than their labels
    allow, then shifted so the row keeps the mean of what it wanted and clamped into the canvas. */
function spreadRow(items: RowItem[], minX: number, maxX: number): Map<string, number> {
  const sorted = [...items].sort((a, b) => a.want - b.want || a.order - b.order);
  const xs: number[] = [];
  sorted.forEach((it, i) => {
    const prev = i ? xs[i - 1] + sorted[i - 1].half + it.half + GAP : -Infinity;
    const want = Number.isFinite(it.want) ? it.want : prev === -Infinity ? minX + it.half : prev;
    xs.push(Math.max(want, prev));
  });
  const finite = sorted.map((it, i) => [it.want, xs[i]] as const).filter(([w]) => Number.isFinite(w));
  if (finite.length) {
    const shift = mean(finite.map(([w]) => w)) - mean(finite.map(([, x]) => x));
    for (let i = 0; i < xs.length; i++) xs[i] += shift;
  }
  if (xs.length) {
    const lo = minX + sorted[0].half - xs[0];
    if (lo > 0) for (let i = 0; i < xs.length; i++) xs[i] += lo;
    const hi = xs[xs.length - 1] + sorted[sorted.length - 1].half - maxX;
    if (hi > 0) for (let i = 0; i < xs.length; i++) xs[i] -= hi;
  }
  return new Map(sorted.map((it, i) => [it.id, xs[i]]));
}

/** Split items (in desired order) into as few rows as fit the given width. */
function packRows(items: RowItem[], width: number): RowItem[][] {
  const sorted = [...items].sort((a, b) => a.want - b.want || a.order - b.order);
  const rows: RowItem[][] = [];
  for (const it of sorted) {
    const row = rows[rows.length - 1];
    if (row && rowWidth([...row, it]) <= width) row.push(it);
    else rows.push([it]);
  }
  return rows;
}

export function layoutStrata(m: StrataModel, nowMs: number): StrataLayout {
  const live = m.edges.filter((e) => edgeLive(e, nowMs) || e.vf > nowMs);
  const pos: Record<string, Pt> = {};
  const boxes: Record<string, Box> = {};
  const place: Record<string, LabelPlace> = {};
  for (const n of m.nodes) boxes[n.id] = baseBox(n);
  const of = (t: SNode["type"]) => m.nodes.filter((n) => n.type === t);
  const neighbours = (id: string) =>
    live.flatMap((e) => (e.from === id ? [e.to] : e.to === id ? [e.from] : []));

  // ---- Code band: symbols ordered so related ones sit together.
  const symbols = orderLinear(of("CodeSymbol"), live);
  const column = [...symbols, ...of("SchemaField").sort((a, b) => a.order - b.order)];
  // Pitch shrinks as the column grows, but never below what a 12px label needs to breathe.
  const dense = m.nodes.length > 80;
  const symStep = column.length > 100 ? 32 : column.length > 12 ? SYM_STEP_DENSE + 4 : SYM_STEP;
  column.forEach((s, i) => {
    pos[s.id] = { x: SYM_X, y: SYM_Y0 + i * symStep };
    place[s.id] = "r";
  });

  // Routes line up with the symbol they flow into.
  const routeList = of("ApiRoute");
  const routeGap = routeList.length > 8 || column.length > 12 ? 46 : 56;
  const routes = routeList.map((r) => {
    const ys = live.filter((e) => e.from === r.id && pos[e.to]).map((e) => pos[e.to].y);
    return { r, want: ys.length ? mean(ys) : Infinity };
  });
  routes.sort((a, b) => a.want - b.want || a.r.order - b.r.order);
  let prevY = -Infinity;
  for (const { r, want } of routes) {
    const y = Number.isFinite(want) ? Math.max(want, prevY + routeGap) : prevY === -Infinity ? SYM_Y0 : prevY + routeGap;
    pos[r.id] = { x: ROUTE_X, y };
    prevY = y;
  }

  // Files, grouped into module regions by directory.
  const tiles = m.nodes.filter((n) => n.type === "File" && !n.hull);
  const hullNodes = m.nodes.filter((n) => n.hull);
  const dirs: string[] = [];
  for (const f of tiles) if (!dirs.includes(f.dir!)) dirs.push(f.dir!);
  for (const h of hullNodes) if (!dirs.includes(h.path!)) dirs.push(h.path!);
  const dirOf = new Map(tiles.map((f) => [f.id, f.dir!]));
  const symbolYs = (fileId: string) => symbols.filter((s) => s.def?.fileId === fileId).map((s) => pos[s.id].y);
  const degree = (ids: Set<string>) => live.filter((e) => !e.contain && (ids.has(e.from) || ids.has(e.to))).length;

  const mods = dirs.map((dir) => {
    const files = tiles.filter((f) => f.dir === dir);
    const withBary = files.map((f) => {
      const ys = symbolYs(f.id);
      return { f, bary: ys.length ? mean(ys) : Infinity, deg: degree(new Set([f.id])) };
    });
    withBary.sort((a, b) => a.bary - b.bary || b.deg - a.deg || a.f.path!.localeCompare(b.f.path!));
    const barys = withBary.filter((x) => Number.isFinite(x.bary)).map((x) => x.bary);
    const importsIn = live.filter(
      (e) =>
        (e.type === "imports" || e.type === "depends_on") &&
        dirOf.get(e.to) === dir &&
        dirOf.has(e.from) &&
        dirOf.get(e.from) !== dir,
    ).length;
    return {
      dir,
      files: withBary.map((x) => x.f),
      bary: barys.length ? mean(barys) : Infinity,
      deg: degree(new Set(files.map((f) => f.id))),
      importsIn,
      hull: hullNodes.find((h) => h.path === dir),
    };
  });
  // The module everything imports from gets the right-hand column, nearest the repository.
  const sink = mods.length > 1 ? [...mods].sort((a, b) => b.importsIn - a.importsIn)[0] : undefined;
  const right = sink && sink.importsIn > 0 ? [sink] : [];
  const left = mods
    .filter((x) => !right.includes(x))
    .sort((a, b) => a.bary - b.bary || b.deg - a.deg || a.dir.localeCompare(b.dir));

  const modules: ModuleRect[] = [];
  const tileStep = dense ? TILE_STEP + 6 : TILE_STEP;
  const hullGap = dense ? HULL_GAP + 10 : HULL_GAP;
  [left, right].forEach((list, ci) => {
    const col = COLS[ci];
    let y = HULL_TOP;
    for (const mod of list) {
      const n = Math.max(1, mod.files.length);
      const h = 36 + tileStep * (n - 1) + 24;
      const rect: ModuleRect = { dir: mod.dir, name: `${mod.dir}/`, x: col.x, y, w: col.w, h, nodeId: mod.hull?.id };
      modules.push(rect);
      mod.files.forEach((f, k) => (pos[f.id] = { x: col.x + col.w / 2, y: y + 36 + tileStep * k }));
      if (mod.hull) {
        pos[mod.hull.id] = { x: col.x + col.w / 2, y: y + h / 2 };
        boxes[mod.hull.id] = { hw: col.w / 2, hh: h / 2 };
      }
      y += h + hullGap;
    }
  });

  // Repository (and anything outside it) in the last column.
  const repoCol = [...of("Repository"), ...of("ExternalArtifact")].sort(
    (a, b) => (a.type === "Repository" ? 0 : 1) - (b.type === "Repository" ? 0 : 1) || a.order - b.order,
  );
  const symMid = symbols.length ? Math.min(mean(symbols.map((s) => pos[s.id].y)), SYM_Y0 + 240) : 300;
  repoCol.forEach((r, i) => {
    pos[r.id] = { x: REPO_X, y: symMid + i * 70 };
    place[r.id] = "b";
  });

  let codeMax = CODE_TOP + 180;
  for (const n of m.nodes) {
    if (n.fam !== "structure" || !pos[n.id]) continue;
    const extra = place[n.id] === "b" ? 30 : 0;
    codeMax = Math.max(codeMax, pos[n.id].y + boxes[n.id].hh + extra);
  }
  for (const r of modules) codeMax = Math.max(codeMax, r.y + r.h);
  let codeBottom = codeMax + 26;

  // ---- Intent band: each node above the code it concerns, wrapping into rows when crowded.
  const intent = m.nodes.filter((n) => n.fam === "reasoning");
  const want = new Map<string, number>();
  for (const n of intent) {
    const xs = neighbours(n.id)
      .map((id) => m.byId.get(id)!)
      .filter((o) => o.fam === "structure" && pos[o.id])
      .map((o) => pos[o.id].x);
    if (xs.length) want.set(n.id, mean(xs));
  }
  for (let pass = 0; pass < 3; pass++) {
    for (const n of intent) {
      if (want.has(n.id)) continue;
      for (const e of live) {
        const other = e.from === n.id ? e.to : e.to === n.id ? e.from : null;
        if (!other || !want.has(other) || m.byId.get(other)!.fam !== "reasoning") continue;
        want.set(n.id, want.get(other)! + (e.from === n.id ? -1 : 1));
        break;
      }
    }
  }
  const intentItems = intent.map((n) => ({ id: n.id, want: want.get(n.id) ?? Infinity, half: labelHalf(n), order: n.order }));
  const intentMin = 440;
  const intentMax = WIDTH - 10;
  const intentRows = intentItems.length ? packRows(intentItems, intentMax - intentMin) : [];
  intentRows.forEach((row, r) => {
    const xs = spreadRow(row, intentMin, intentMax);
    for (const it of row) {
      pos[it.id] = { x: xs.get(it.id)!, y: INTENT_Y + r * INTENT_ROW };
      place[it.id] = "t";
    }
  });
  const dy = Math.max(0, intentRows.length - 1) * INTENT_ROW;
  if (dy) {
    for (const n of m.nodes) if (n.fam === "structure" && pos[n.id]) pos[n.id] = { x: pos[n.id].x, y: pos[n.id].y + dy };
    for (const r of modules) r.y += dy;
    codeBottom += dy;
  }
  const codeTop = CODE_TOP + dy;

  // ---- Signals band: causal chains in time order, then everything else under its subject.
  const events = of("CausalEvent").sort((a, b) => a.t0 - b.t0 || a.order - b.order);
  const others = m.nodes.filter((n) => n.fam === "signals" && n.type !== "CausalEvent");
  const otherItems = others.map((n) => {
    const xs = neighbours(n.id)
      .map((id) => m.byId.get(id)!)
      .filter((o) => o.fam !== "signals" && pos[o.id])
      .map((o) => pos[o.id].x);
    return { id: n.id, want: xs.length ? mean(xs) : 700, half: labelHalf(n), order: n.order };
  });
  const eventWidth = events.reduce((s, ev, i) => s + labelHalf(ev) * 2 + (i ? GAP : 0), 0);
  const rowY = (i: number) => codeBottom + 78 + i * SIGNAL_ROW;
  let signalRows = 1;
  if (eventWidth + rowWidth(otherItems) + 150 <= WIDTH - 40) {
    // Everything fits on one row: the chain on the left, the rest under what it concerns.
    let x = 150;
    events.forEach((ev, i) => {
      if (i) x += labelHalf(events[i - 1]) + labelHalf(ev) + GAP;
      pos[ev.id] = { x, y: codeBottom + 80 };
    });
    const leftBound = events.length ? x + labelHalf(events[events.length - 1]) + GAP : 40;
    const sx = spreadRow(otherItems, leftBound, WIDTH - 10);
    for (const it of otherItems) pos[it.id] = { x: sx.get(it.id)!, y: codeBottom + 76 };
  } else {
    // A long history: the rest keep row one, the chain wraps across the full width below it.
    let row = 0;
    if (otherItems.length) {
      const sx = spreadRow(otherItems, 40, WIDTH - 10);
      for (const it of otherItems) pos[it.id] = { x: sx.get(it.id)!, y: rowY(0) - 2 };
      row = 1;
    }
    let x = -Infinity;
    for (let i = 0; i < events.length; i++) {
      const half = labelHalf(events[i]);
      const next = x === -Infinity ? 60 + half : x + labelHalf(events[i - 1]) + half + GAP;
      if (next + half > WIDTH - 20) {
        row++;
        x = 60 + half;
      } else x = next;
      pos[events[i].id] = { x, y: rowY(row) + 2 };
    }
    signalRows = row + 1;
  }
  for (const n of [...events, ...others]) place[n.id] = "b";
  const height = Math.max(codeBottom + 162, rowY(signalRows - 1) + 84);

  // ---- Routing hints.
  const hints: Record<string, RouteHints> = {};
  const sameCol = (a: Pt, b: Pt) => Math.abs(a.x - b.x) < 10;
  const tileModule = new Map<string, SNode[]>();
  const byDir = new Map<string, SNode[]>();
  for (const f of tiles) byDir.set(f.dir!, [...(byDir.get(f.dir!) ?? []), f]);
  for (const list of byDir.values()) {
    list.sort((a, b) => pos[a.id].y - pos[b.id].y);
    for (const f of list) tileModule.set(f.id, list);
  }
  const colNodes = new Map<number, number[]>();
  for (const n of m.nodes) {
    if (!pos[n.id] || n.hull) continue;
    const key = Math.round(pos[n.id].x);
    colNodes.set(key, [...(colNodes.get(key) ?? []), pos[n.id].y]);
  }
  for (const e of m.edges) {
    const a = pos[e.from];
    const b = pos[e.to];
    if (!a || !b || e.contain) continue;
    const h: RouteHints = {};
    if (sameCol(a, b)) {
      const lo = Math.min(a.y, b.y);
      const hi = Math.max(a.y, b.y);
      const skipped = (colNodes.get(Math.round(a.x)) ?? []).some((y) => y > lo + 1 && y < hi - 1);
      h.side = -1;
      if (skipped) h.bend = 1.6;
    }
    const target = m.byId.get(e.to)!;
    const source = m.byId.get(e.from)!;
    const vertical = Math.abs(b.x - a.x) < Math.abs(b.y - a.y) * 0.9;
    if (target.type === "File" && !target.hull && source.fam !== "structure" && vertical && !sameCol(a, b)) {
      const sibs = tileModule.get(target.id) ?? [];
      const blocked = a.y > b.y ? sibs[sibs.length - 1]?.id !== target.id : sibs[0]?.id !== target.id;
      if (blocked) h.enter = "right";
    }
    hints[e.id] = h;
  }
  // Spread arrivals on a tile's left edge in the order their sources sit, top to bottom.
  const incomingByTile = new Map<string, SEdge[]>();
  for (const e of m.edges) {
    const t = pos[e.to];
    const s = pos[e.from];
    if (!t || !s || e.contain || hints[e.id]?.enter || !dirOf.has(e.to)) continue;
    if (sameCol(s, t) || (s.x < t.x - 10 && Math.abs(t.x - s.x) >= Math.abs(t.y - s.y) * 0.9))
      incomingByTile.set(e.to, [...(incomingByTile.get(e.to) ?? []), e]);
  }
  for (const incoming of incomingByTile.values()) {
    const distinct = [...new Map(incoming.map((e) => [e.from, e])).values()].sort((p, q) => pos[p.from].y - pos[q.from].y);
    if (distinct.length < 2) continue;
    const pinOf = new Map(distinct.map((e, i) => [e.from, -7 + (17 * i) / (distinct.length - 1)]));
    for (const e of incoming) hints[e.id] = { ...hints[e.id], pin: pinOf.get(e.from) };
  }

  return { width: WIDTH, height, codeTop, codeBottom, pos, boxes, modules, hints, place };
}

const FOCUS_ROWS = 9;
const FOCUS_ROW = 62;
const FOCUS_COL = 260;
const FOCUS_RING_GAP = 110;
const FOCUS_TOP = 70;
const TYPE_RANK: Partial<Record<SNode["type"], number>> = { ApiRoute: 0, CodeSymbol: 1, File: 2, Repository: 3 };

export interface FocusLayout {
  pos: Record<string, Pt>;
  set: Set<string>;
  width: number;
  height: number;
  centerX: number;
}

/** Focus view (Sourcetrail): the node in the middle, what points at it on the left, what it points
    at on the right, and a second ring beyond each. Every neighbour is listed — a big ring becomes a
    grid of columns (never a "+N more"), and the canvas widens to hold it rather than growing a void
    above and below. */
export function focusLayout(m: StrataModel, id: string, t: number): FocusLayout {
  const liveNow = m.edges.filter(
    (e) => edgeLive(e, t) && m.byId.get(e.from)!.t0 <= t && m.byId.get(e.to)!.t0 <= t,
  );
  const used = new Set([id]);
  const take = (ids: string[]) => {
    const fresh = [...new Set(ids)].filter((i) => !used.has(i));
    fresh.forEach((i) => used.add(i));
    return fresh.sort((a, b) => {
      const na = m.byId.get(a)!;
      const nb = m.byId.get(b)!;
      return (TYPE_RANK[na.type] ?? 9) - (TYPE_RANK[nb.type] ?? 9) || na.label.localeCompare(nb.label);
    });
  };
  const in1 = take(liveNow.filter((e) => e.to === id).map((e) => e.from));
  const out1 = take(liveNow.filter((e) => e.from === id).map((e) => e.to));
  const in2 = take(liveNow.filter((e) => in1.includes(e.to)).map((e) => e.from));
  const out2 = take(liveNow.filter((e) => out1.includes(e.from)).map((e) => e.to));
  const rings = [in2, in1, [id], out1, out2];

  const maxRows = Math.max(1, ...rings.map((r) => Math.min(FOCUS_ROWS, r.length)));
  const cy = FOCUS_TOP + ((maxRows - 1) * FOCUS_ROW) / 2;
  const pos: Record<string, Pt> = {};
  let cursor = 40;
  for (const ring of rings) {
    if (!ring.length) continue;
    const cols = Math.ceil(ring.length / FOCUS_ROWS);
    // Balance the columns so a ring of 10 is 5 + 5, not 9 + 1.
    const perCol = Math.ceil(ring.length / cols);
    for (let c = 0; c < cols; c++) {
      const items = ring.slice(c * perCol, (c + 1) * perCol);
      const x = cursor + c * FOCUS_COL + FOCUS_COL / 2;
      items.forEach((nid, r) => (pos[nid] = { x, y: cy - ((items.length - 1) * FOCUS_ROW) / 2 + r * FOCUS_ROW }));
    }
    cursor += cols * FOCUS_COL + FOCUS_RING_GAP;
  }
  let width = cursor - FOCUS_RING_GAP + 40;
  if (width < WIDTH) {
    const shift = (WIDTH - width) / 2;
    for (const k in pos) pos[k] = { x: pos[k].x + shift, y: pos[k].y };
    width = WIDTH;
  }
  const height = Math.max(FOCUS_TOP * 2 + (maxRows - 1) * FOCUS_ROW + 50, 420);
  return { pos, set: used, width, height, centerX: pos[id].x };
}

/** Matrix row/column order follows the Strata columns, so blocks on the diagonal are the bands. */
export function matrixOrder(m: StrataModel, L: StrataLayout) {
  const by = (f: (n: SNode) => boolean, key: (n: SNode) => number) =>
    m.nodes.filter(f).sort((a, b) => key(a) - key(b) || a.order - b.order);
  const px = (n: SNode) => L.pos[n.id]?.x ?? 0;
  const py = (n: SNode) => L.pos[n.id]?.y ?? 0;
  const groups = [
    by((n) => n.fam === "reasoning", (n) => py(n) * 10000 + px(n)),
    by((n) => n.type === "ApiRoute", py),
    by((n) => n.type === "CodeSymbol" || n.type === "SchemaField", py),
    [...by((n) => n.hull, (n) => px(n) * 10000 + py(n)), ...by((n) => n.type === "File" && !n.hull, (n) => px(n) * 10000 + py(n))],
    by((n) => n.type === "Repository" || n.type === "ExternalArtifact", py),
    by((n) => n.fam === "signals", (n) => py(n) * 10000 + px(n)),
  ].filter((g) => g.length);
  const ids = groups.flat().map((n) => n.id);
  const breaks: number[] = [];
  let acc = 0;
  for (const g of groups.slice(0, -1)) {
    acc += g.length;
    breaks.push(acc);
  }
  return { ids, breaks };
}
