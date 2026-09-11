/*
  Strata geometry: boundary anchoring, edge routing and the tapered ribbon.

  Edges are cubic Béziers chosen by how the two ends sit relative to each other:
    - same column  -> an arc bulging to one side (arc-diagram style), so it never cuts the column
    - mostly level -> horizontal tangents at both ends (reads as left-to-right flow)
    - mostly stacked -> vertical tangents (reads as "this explains that" between bands)
  The ribbon is wide at the source and a point at the target — Holten & van Wijk found a taper
  reads direction better than an arrowhead.
*/

export type Pt = { x: number; y: number };
export type Curve = [Pt, Pt, Pt, Pt];

/** Half extents used for anchoring an edge on a node's boundary. */
export interface Box {
  hw: number;
  hh: number;
  round?: boolean;
}

/** Per-edge routing hints the layout computes (Strata view only). */
export interface RouteHints {
  /** Which side a same-column arc bulges to: -1 left, 1 right. */
  side?: number;
  /** Arc bulge multiplier, raised for arcs that skip over other nodes. */
  bend?: number;
  /** Arrival offset on the target's edge, so several edges into one tile don't converge on a point. */
  pin?: number;
  /** Arrive on the target's right edge instead of crossing sibling tiles. */
  enter?: "right";
}

export function cubic(c: Curve, t: number): Pt {
  const u = 1 - t;
  return {
    x: u * u * u * c[0].x + 3 * u * u * t * c[1].x + 3 * u * t * t * c[2].x + t * t * t * c[3].x,
    y: u * u * u * c[0].y + 3 * u * u * t * c[1].y + 3 * u * t * t * c[2].y + t * t * t * c[3].y,
  };
}

export function anchor(b: Box, p: Pt, toward: Pt): Pt {
  const dx = toward.x - p.x;
  const dy = toward.y - p.y;
  const len = Math.hypot(dx, dy) || 1;
  if (b.round) return { x: p.x + (dx / len) * (b.hw + 2), y: p.y + (dy / len) * (b.hh + 2) };
  const s = Math.max(Math.abs(dx) / b.hw, Math.abs(dy) / b.hh) || 1;
  return { x: p.x + dx / s, y: p.y + dy / s };
}

export function route(h: RouteHints, ba: Box, pa: Pt, bb: Box, pb: Pt): Curve {
  const dx = pb.x - pa.x;
  const dy = pb.y - pa.y;
  if (Math.abs(dx) < 10) {
    const side = h.side ?? -1;
    const s = { x: pa.x + side * ba.hw, y: pa.y };
    const t = { x: pb.x + side * bb.hw, y: pb.y + (h.pin ?? 0) };
    const bulge = (16 + Math.abs(dy) * 0.2) * (h.bend ?? 1) * side;
    return [s, { x: s.x + bulge, y: s.y }, { x: t.x + bulge, y: t.y }, t];
  }
  if (h.enter === "right") {
    const s = anchor(ba, pa, { x: pa.x, y: pb.y });
    const t = { x: pb.x + bb.hw, y: pb.y };
    return [s, { x: s.x, y: s.y - (s.y - t.y) * 0.75 }, { x: t.x + 70, y: t.y }, t];
  }
  if (Math.abs(dx) >= Math.abs(dy) * 0.9) {
    const s = anchor(ba, pa, { x: pb.x, y: pa.y });
    const t = anchor(bb, pb, { x: pa.x, y: pb.y });
    t.y += h.pin ?? 0;
    const k = (t.x - s.x) * 0.5;
    return [s, { x: s.x + k, y: s.y }, { x: t.x - k, y: t.y }, t];
  }
  const s = anchor(ba, pa, { x: pa.x, y: pb.y });
  const t = anchor(bb, pb, { x: pb.x, y: pa.y });
  const k = (t.y - s.y) * 0.5;
  return [s, { x: s.x, y: s.y + k }, { x: t.x, y: t.y - k }, t];
}

/** Filled ribbon along the curve, width w0 at the source narrowing to w1 at the target. Sampled by
    length (one step per ~5px): a fixed 28 steps drew long edges as visibly faceted polylines. */
export function taper(c: Curve, w0: number, w1: number): string {
  const N = Math.max(24, Math.min(180, Math.round(curveLen(c) / 5)));
  const L: string[] = [];
  const R: string[] = [];
  for (let i = 0; i <= N; i++) {
    const t = i / N;
    const p = cubic(c, t);
    const q = cubic(c, Math.min(1, t + 0.01));
    const r = cubic(c, Math.max(0, t - 0.01));
    let nx = -(q.y - r.y);
    let ny = q.x - r.x;
    const l = Math.hypot(nx, ny) || 1;
    nx /= l;
    ny /= l;
    const w = (w0 * (1 - t) + w1 * t) / 2;
    L.push(`${(p.x + nx * w).toFixed(2)} ${(p.y + ny * w).toFixed(2)}`);
    R.push(`${(p.x - nx * w).toFixed(2)} ${(p.y - ny * w).toFixed(2)}`);
  }
  return `M${L.join("L")}L${R.reverse().join("L")}Z`;
}

export function curveLen(c: Curve): number {
  let l = 0;
  let p = c[0];
  for (let i = 1; i <= 20; i++) {
    const q = cubic(c, i / 20);
    l += Math.hypot(q.x - p.x, q.y - p.y);
    p = q;
  }
  return l;
}

export const pathD = (c: Curve) =>
  `M${c[0].x} ${c[0].y}C${c[1].x} ${c[1].y} ${c[2].x} ${c[2].y} ${c[3].x} ${c[3].y}`;

/** Greedy word wrap to a character budget. */
export function wrap(s: string, max: number): string[] {
  const out: string[] = [];
  let line = "";
  for (const w of s.split(" ")) {
    if ((line + " " + w).trim().length > max && line) {
      out.push(line);
      line = w;
    } else line = (line + " " + w).trim();
  }
  if (line) out.push(line);
  return out;
}
