"use client";

import { useMemo } from "react";
import { PRED_FAM, edgeLive, type SEdge, type StrataModel } from "@/lib/strata/model";
import { matrixOrder, type StrataLayout } from "@/lib/strata/layout";

const X = 430;
const Y = 176;

/** Cell size stays readable at any scale: the matrix grows and the canvas scrolls, instead of the
    cells shrinking until a large repository falls off the page. */
export function matrixGeometry(count: number) {
  const S = count <= 60 ? 15 : 12;
  return { S, width: Math.max(1200, X + count * S + 40), height: Math.max(560, Y + count * S + 40) };
}

/** Adjacency matrix: rows are sources, columns targets, ordered by the Strata columns so the
    diagonal blocks are the bands. Squares are static/human edges, circles LLM-inferred. */
export function StrataMatrix({
  model,
  layout,
  t,
  onCell,
  onMove,
  onLeave,
}: {
  model: StrataModel;
  layout: StrataLayout;
  t: number;
  onCell: (e: SEdge, ev: React.MouseEvent) => void;
  onMove: (ev: React.MouseEvent) => void;
  onLeave: () => void;
}) {
  const { ids, breaks } = useMemo(() => matrixOrder(model, layout), [model, layout]);
  const N = ids.length;
  const { S } = matrixGeometry(N);
  const idx = useMemo(() => new Map(ids.map((id, i) => [id, i])), [ids]);
  const cut = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

  return (
    <g>
      {[
        ["Rows are sources, columns are targets.", "lbl"],
        ["Blocks along the diagonal are the bands:", "band-cap"],
        ["intent, routes, symbols, files, signals.", "band-cap"],
        ["Squares are static or human edges;", "band-cap"],
        ["circles are LLM-inferred.", "band-cap"],
        ["Fill strength is confidence.", "band-cap"],
      ].map(([text, cls], i) => (
        <text key={i} x={24} y={36 + i * 19} className={cls}>
          {text}
        </text>
      ))}
      {ids.map((id, i) => {
        const n = model.byId.get(id)!;
        const name = n.hull ? `${n.path}` : n.label;
        const cx = X + i * S + S / 2 + 3;
        return (
          <g key={id}>
            <rect x={X + i * S + 1} y={Y + i * S + 1} width={S - 2} height={S - 2} rx={2} className="mx-diag" />
            <text x={X - 10} y={Y + i * S + S / 2 + 3.5} textAnchor="end" className="mx-lbl">
              {cut(name, 26)}
            </text>
            <text x={cx} y={Y - 8} className="mx-lbl" transform={`rotate(-55 ${cx} ${Y - 8})`}>
              {cut(name, 22)}
            </text>
          </g>
        );
      })}
      {breaks.map((k) => (
        <g key={`b${k}`}>
          <line x1={X} x2={X + N * S} y1={Y + k * S} y2={Y + k * S} className="mx-grid" />
          <line y1={Y} y2={Y + N * S} x1={X + k * S} x2={X + k * S} className="mx-grid" />
        </g>
      ))}
      <rect x={X} y={Y} width={N * S} height={N * S} fill="none" className="mx-grid" />
      {model.edges.map((e) => {
        const r = idx.get(e.from);
        const c = idx.get(e.to);
        if (r == null || c == null) return null;
        const fam = PRED_FAM[e.type];
        const x = X + c * S;
        const y = Y + r * S;
        const op = edgeLive(e, t) ? 0.35 + 0.6 * e.conf : 0.08;
        const common = {
          className: `e-${fam}`,
          opacity: op,
          onMouseEnter: (ev: React.MouseEvent) => onCell(e, ev),
          onMouseMove: onMove,
          onMouseLeave: onLeave,
        };
        return e.src === "llm_inferred" ? (
          <circle key={e.id} cx={x + S / 2} cy={y + S / 2} r={S * 0.31} {...common} />
        ) : (
          <rect key={e.id} x={x + 1.5} y={y + 1.5} width={S - 3} height={S - 3} rx={2.5} {...common} />
        );
      })}
    </g>
  );
}
