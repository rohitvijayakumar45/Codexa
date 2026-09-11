import type { GraphNodeType } from "@/lib/api";

/*
  One silhouette per node type. Hue carries the family (via the s-/r-/g- classes), shape carries the
  type — sixteen types are never told apart by shade alone. Two glyphs draw their own data: the
  health gauge its score, the trend card its metric's movement.
*/

const DIAMOND = "M0 -11L11 0L0 11L-11 0Z";

function poly(n: number, r: number, rot = 0) {
  let d = "";
  for (let i = 0; i < n; i++) {
    const a = rot + (i * 2 * Math.PI) / n;
    d += `${i ? "L" : "M"}${(Math.cos(a) * r).toFixed(2)} ${(Math.sin(a) * r).toFixed(2)}`;
  }
  return `${d}Z`;
}

export interface GlyphData {
  type: GraphNodeType;
  label?: string;
  method?: string;
  loc?: number;
  hullName?: string;
  hullW?: number;
  hullH?: number;
  score?: number;
  trend?: { metric: string; first: number; latest: number };
}

const CH = 6.6; // Geist Mono at 11px, per character

function fitTail(s: string, max: number) {
  return s.length <= max ? s : `…${s.slice(s.length - max + 1)}`;
}

export function Glyph({ d, mini = false }: { d: GlyphData; mini?: boolean }) {
  switch (d.type) {
    case "Repository":
      return (
        <>
          <rect x={-11} y={-11} width={22} height={22} rx={5} className="s-fill" />
          <rect x={-4} y={-4} width={8} height={8} rx={1.5} className="hole" />
        </>
      );
    case "File": {
      if (mini)
        return (
          <>
            <rect x={-16} y={-7} width={32} height={14} rx={3.5} className="tile" strokeWidth={1.2} />
            <path d="M-11 -1H6M-11 3H1" className="s-stroke" strokeWidth={1.3} strokeLinecap="round" fill="none" />
          </>
        );
      if (d.hullW && d.hullH)
        return (
          <>
            <rect x={-d.hullW / 2} y={-d.hullH / 2} width={d.hullW} height={d.hullH} rx={12} className="hull" />
            <text x={-d.hullW / 2 + 10} y={-d.hullH / 2 + 15} className="hull-name">
              {d.hullName}
            </text>
          </>
        );
      const name = d.label ?? "";
      const loc = typeof d.loc === "number" ? `${d.loc} loc` : "";
      // Drop the line count rather than let it collide with a long name.
      const showLoc = loc && name.length * CH + loc.length * 6 + 22 <= 142;
      return (
        <>
          <rect x={-70} y={-13} width={140} height={26} rx={6} className="tile" />
          <text x={-60} y={4} className="lbl in">
            {fitTail(name, showLoc ? 18 : 18)}
          </text>
          {showLoc ? (
            <text x={62} y={4} textAnchor="end" className="lbl sub" style={{ stroke: "none" }}>
              {loc}
            </text>
          ) : null}
        </>
      );
    }
    case "CodeSymbol":
      return <circle r={6.5} className="s-fill" />;
    case "ApiRoute": {
      if (mini)
        return (
          <>
            <rect x={-18} y={-7} width={36} height={14} rx={7} className="tile" strokeWidth={1.2} />
            <rect x={-16} y={-5} width={11} height={10} rx={5} className="s-fill" />
          </>
        );
      const method = d.method ?? "GET";
      const cw = method.length <= 3 ? 30 : 37;
      const room = Math.floor((236 - cw - 14) / CH);
      return (
        <>
          <rect x={-118} y={-13} width={236} height={26} rx={13} className="tile" />
          <rect x={-114} y={-9} width={cw} height={18} rx={9} className="s-fill" />
          <text x={-114 + cw / 2} y={3.5} textAnchor="middle" className="lbl method">
            {method}
          </text>
          <text x={-114 + cw + 7} y={4} className="lbl in">
            {fitTail(d.label ?? "", room)}
          </text>
        </>
      );
    }
    case "SchemaField":
      return <rect x={-5} y={-5} width={10} height={10} rx={1.5} className="s-fill" />;
    case "ExternalArtifact":
      return <circle r={7} fill="none" className="s-stroke" strokeWidth={1.6} strokeDasharray="2.5 2" />;
    case "Decision":
      return <path d={DIAMOND} className="r-fill" />;
    case "Tradeoff":
      return (
        <>
          <path d={DIAMOND} className="r-stroke r-wash" strokeWidth={1.6} />
          <path d="M0 -11L-11 0L0 11Z" className="r-fill" />
        </>
      );
    case "RejectedAlternative":
      return (
        <>
          <path d={DIAMOND} className="r-stroke hole" strokeWidth={1.6} />
          <path d="M-6 6L6 -6" className="r-stroke" strokeWidth={1.6} strokeLinecap="round" />
        </>
      );
    case "OnboardingPath":
      return (
        <path
          d="M-9 -8L0 0L-9 8M0 -8L9 0L0 8"
          fill="none"
          className="r-stroke"
          strokeWidth={2.2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      );
    case "ConventionProfile":
      return (
        <>
          <path d={poly(6, 10.5, Math.PI / 6)} className="r-stroke r-wash" strokeWidth={1.6} />
          <circle r={2.6} className="r-fill" />
        </>
      );
    case "CausalEvent":
      return <circle r={7.5} className="g-fill" />;
    case "PreventionRule":
      return (
        <>
          <path d={poly(8, 10.5, Math.PI / 8)} className="g-stroke g-wash" strokeWidth={1.6} />
          <path
            d="M-4 0.5L-1 3.5L4.5 -3"
            fill="none"
            className="g-stroke"
            strokeWidth={1.6}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </>
      );
    case "SimulationScenario":
      return <path d="M0 -10L10 8H-10Z" className="g-fill" />;
    case "HealthMetric": {
      const r = mini ? 12 : 17;
      const sw = mini ? 3.5 : 4;
      const sc = Math.max(0, Math.min(1, d.score ?? 0));
      const c = 2 * Math.PI * r;
      return (
        <>
          <circle r={r} className="track-ring" strokeWidth={sw} />
          <circle
            r={r}
            fill="none"
            className="g-stroke"
            strokeWidth={sw}
            strokeLinecap="round"
            strokeDasharray={`${c * sc} ${c}`}
            transform="rotate(-90)"
          />
          {!mini ? (
            <text y={4} textAnchor="middle" className="lbl in" style={{ fontSize: 10.5 }}>
              {sc.toFixed(2)}
            </text>
          ) : null}
        </>
      );
    }
    case "ArchitectureTrend": {
      const tr = d.trend ?? { metric: "coupling", first: 0.42, latest: 0.71 };
      const w = mini ? 30 : 70;
      const h = mini ? 16 : 26;
      const ox = mini ? -15 : -4;
      const oy = mini ? 8 : 12;
      const lo = Math.min(tr.first, tr.latest);
      const hi = Math.max(tr.first, tr.latest);
      const span = hi - lo || 1;
      const py = (v: number) => oy - ((v - lo) / span) * h * 0.85 - h * 0.08;
      const pts: [number, number][] = [
        [ox, py(tr.first)],
        [ox + w, py(tr.latest)],
      ];
      const delta = tr.latest - tr.first;
      const fmt = (v: number) => (Math.abs(v) < 10 ? v.toFixed(2) : v.toFixed(0));
      return (
        <>
          {mini ? (
            <rect x={-18} y={-12} width={36} height={24} rx={5} className="tile" strokeWidth={1.2} />
          ) : (
            <>
              <rect x={-78} y={-26} width={156} height={52} rx={10} className="tile" />
              <text x={-68} y={-8} className="lbl sub" style={{ stroke: "none" }}>
                {tr.metric.replace(/_/g, " ")}
              </text>
              <text x={-68} y={14} className="lbl big">
                {fmt(tr.latest)}
              </text>
              <text x={-27} y={14} className="lbl sub" style={{ stroke: "none" }}>
                {`${delta >= 0 ? "↑" : "↓"} ${Math.abs(delta) < 10 ? Math.abs(delta).toFixed(2).replace(/^0/, "") : Math.abs(delta).toFixed(0)}`}
              </text>
            </>
          )}
          <path
            d={`M${pts[0][0]} ${pts[0][1]}L${pts[1][0]} ${pts[1][1]}L${pts[1][0]} ${oy + 2}L${pts[0][0]} ${oy + 2}Z`}
            className="g-wash"
          />
          <path d={`M${pts[0][0]} ${pts[0][1]}L${pts[1][0]} ${pts[1][1]}`} fill="none" className="g-stroke" strokeWidth={1.8} />
          <circle cx={pts[1][0]} cy={pts[1][1]} r={mini ? 2 : 2.8} className="g-fill" />
        </>
      );
    }
    default:
      return <circle r={6} className="s-fill" />;
  }
}

/** The provenance swatch used in the legend and inspector rows. */
export function ProvSwatch({
  src,
  fam,
  conf,
}: {
  src: "static_analysis" | "human_asserted" | "llm_inferred";
  fam: "struct" | "intent" | "signal";
  conf: number;
}) {
  const o = (0.35 + 0.6 * conf).toFixed(2);
  if (src === "llm_inferred")
    return (
      <svg width="26" height="10" viewBox="0 0 26 10" aria-hidden>
        <g className={`e-${fam}`} opacity={o}>
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <circle key={i} cx={2 + i * 4} cy={5} r={(2 - (1.2 * i) / 5).toFixed(2)} />
          ))}
        </g>
      </svg>
    );
  return (
    <svg width="26" height="10" viewBox="0 0 26 10" aria-hidden>
      <path d="M1 2.6L24 4.7L24 5.3L1 7.4Z" className={`e-${fam}`} opacity={o} />
      {src === "human_asserted" ? (
        <circle cx={12.5} cy={5} r={2.6} className={`hole ring-${fam}`} strokeWidth={1.3} />
      ) : null}
    </svg>
  );
}
