"use client";

import { useMemo } from "react";
import { ProvSwatch } from "./Glyph";
import {
  DAY,
  FAMILY_LABEL,
  PRED_FAM,
  SRC_LABEL,
  TYPE_LABEL,
  edgeLive,
  nodeLive,
  type SEdge,
  type SNode,
  type StrataModel,
} from "@/lib/strata/model";

type Mode = "strata" | "focus" | "matrix";

const fmtVal = (v: unknown): string => {
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(3);
  if (typeof v === "string") return v;
  if (Array.isArray(v)) return v.every((x) => typeof x !== "object") ? v.join(", ") : `${v.length} items`;
  if (v && typeof v === "object") return `${Object.keys(v).length} fields`;
  return String(v);
};

/** What the data cannot answer yet — computed, never hard-coded, so it disappears once fixed. */
function useGaps(model: StrataModel) {
  return useMemo(() => {
    const out: { key: string; text: React.ReactNode }[] = [];
    const typeOf = (id: string) => model.byId.get(id)?.type;
    const famOf = (id: string) => model.byId.get(id)?.fam;
    const symbols = model.nodes.filter((n) => n.type === "CodeSymbol");
    const noFile = symbols.filter(
      (s) => !model.edges.some((e) => (e.from === s.id && typeOf(e.to) === "File") || (e.to === s.id && typeOf(e.from) === "File")),
    );
    if (noFile.length)
      out.push({
        key: "sym",
        text:
          noFile.length === symbols.length
            ? "No symbol has an edge to its file. Hover one to see the link Strata infers."
            : `${noFile.length} of ${symbols.length} symbols have no edge to their file.`,
      });
    const events = model.nodes.filter((n) => n.type === "CausalEvent");
    const loose = events.filter(
      (ev) => !model.edges.some((e) => (e.from === ev.id && famOf(e.to) === "structure") || (e.to === ev.id && famOf(e.from) === "structure")),
    );
    if (loose.length)
      out.push({
        key: "ev",
        text: loose.length === events.length ? "The causal chain touches no code." : `${loose.length} causal events touch no code.`,
      });
    const isolated = model.nodes.filter((n) => !model.edges.some((e) => e.from === n.id || e.to === n.id));
    for (const n of isolated.slice(0, 3)) out.push({ key: `iso-${n.id}`, text: `${n.label} has no edges.` });
    for (const h of model.nodes.filter((n) => n.hull && !model.edges.some((e) => e.to === n.id && typeOf(e.from) !== "ArchitectureTrend")))
      out.push({
        key: `hull-${h.id}`,
        text: (
          <>
            The <code>{h.path}</code> module node is contained by nothing.
          </>
        ),
      });
    return out;
  }, [model]);
}

export function StrataInspector({
  model,
  sel,
  t,
  nowMs,
  mode,
  agentIds,
  agentStatus,
  hubId,
  onGo,
  onAct,
}: {
  model: StrataModel;
  sel: SNode | null;
  t: number;
  nowMs: number;
  mode: Mode;
  agentIds: Set<string>;
  agentStatus: string;
  hubId: string | null;
  onGo: (id: string) => void;
  onAct: (a: "focus" | "strata" | "clear") => void;
}) {
  const gaps = useGaps(model);
  const ago = (ms: number) => `${Math.max(0, Math.round((nowMs - ms) / DAY))}d ago`;

  if (!sel) {
    const live = model.edges.filter((e) => edgeLive(e, t));
    const nodes = model.nodes.filter((n) => nodeLive(n, t));
    const cnt = (k: SEdge["src"]) => live.filter((e) => e.src === k).length;
    const fam = (f: SNode["fam"]) => nodes.filter((n) => n.fam === f).length;
    const mx = Math.max(1, live.length);
    const hub = hubId ? model.byId.get(hubId) : null;
    const repo = model.nodes.find((n) => n.type === "Repository");
    return (
      <>
        <div className="eyebrow">Graph at a glance</div>
        <h3>{repo?.label ?? "Repository"}</h3>
        <div className="stat">
          <div>
            <b>{nodes.length}</b>
            <span>nodes</span>
          </div>
          <div>
            <b>{live.length}</b>
            <span>live edges</span>
          </div>
          <div>
            <b>{live.filter((e) => !e.contain).length}</b>
            <span>drawn</span>
          </div>
        </div>
        <h4>
          <span>Families</span>
        </h4>
        <div className="bars">
          {(["structure", "reasoning", "signals"] as const).map((f) => (
            <div className="row" key={f}>
              <span>{FAMILY_LABEL[f]}</span>
              <i>
                <u style={{ width: `${(fam(f) / Math.max(1, nodes.length)) * 100}%` }} />
              </i>
              <em>{fam(f)}</em>
            </div>
          ))}
        </div>
        <h4>
          <span>Provenance</span>
        </h4>
        <div className="bars">
          {(["static_analysis", "human_asserted", "llm_inferred"] as const).map((k) => (
            <div className="row" key={k}>
              <span>{SRC_LABEL[k]}</span>
              <i>
                <u style={{ width: `${(cnt(k) / mx) * 100}%` }} />
              </i>
              <em>{cnt(k)}</em>
            </div>
          ))}
        </div>
        {agentIds.size > 0 ? (
          <>
            <h4>
              <span>Agent</span>
              <span>{agentIds.size}</span>
            </h4>
            <div className="agent-note">
              <i />
              <span>{agentStatus || "A job is running"} — ringed nodes are files it has touched.</span>
            </div>
          </>
        ) : null}
        {gaps.length ? (
          <>
            <h4>
              <span>Gaps in the data</span>
            </h4>
            {gaps.map((g) => (
              <div className="s-gap" key={g.key}>
                {g.text}
              </div>
            ))}
          </>
        ) : null}
        {hub ? (
          <div className="actions">
            <button className="btn" onClick={() => onGo(hub.id)}>
              Inspect {hub.label}
            </button>
          </div>
        ) : null}
      </>
    );
  }

  const ins = model.edges.filter((e) => e.to === sel.id);
  const outs = model.edges.filter((e) => e.from === sel.id);
  const defFile = sel.def ? model.byId.get(sel.def.fileId) : undefined;
  const defines = model.nodes.filter((n) => n.def?.fileId === sel.id);

  const row = (e: SEdge, other: SNode, dir: string) => {
    const live = edgeLive(e, t);
    const when = e.vt !== null ? (live ? `until ${ago(e.vt)}` : `ended ${ago(e.vt)}`) : `since ${ago(e.vf)}`;
    return (
      <div className={`erow${live ? "" : " off"}`} key={`${dir}${e.id}`}>
        <ProvSwatch src={e.src} fam={PRED_FAM[e.type]} conf={e.conf} />
        <div>
          <button onClick={() => onGo(other.id)}>{other.label}</button>
          <div className="p">
            {dir} {e.type.replace(/_/g, " ")}
            {e.contain ? " · drawn as the frame" : ""} · {SRC_LABEL[e.src].toLowerCase()} · {when}
          </div>
        </div>
        <div className="c">{e.conf.toFixed(2)}</div>
      </div>
    );
  };

  return (
    <>
      <div className="eyebrow">
        {TYPE_LABEL[sel.type]} · {FAMILY_LABEL[sel.fam]}
      </div>
      <h3>{sel.type === "ApiRoute" ? `${sel.method ?? ""} ${sel.label}`.trim() : sel.hull ? `${sel.path}/` : sel.label}</h3>
      {agentIds.has(sel.id) ? (
        <div className="agent-note">
          <i />
          <span>The running job has touched this{agentStatus ? ` · ${agentStatus}` : ""}.</span>
        </div>
      ) : null}
      <dl className="kv">
        {Object.entries(sel.props).map(([k, v]) => (
          <div key={k} style={{ display: "contents" }}>
            <dt>{k.replace(/_/g, " ")}</dt>
            <dd>{fmtVal(v)}</dd>
          </div>
        ))}
      </dl>
      {defFile ? (
        <>
          <h4>
            <span>Defined in</span>
            <span>inferred</span>
          </h4>
          <div className="erow">
            <span />
            <div>
              <button onClick={() => onGo(defFile.id)}>{defFile.path}</button>
              <div className="p">
                {sel.def?.how === "property" ? "from the symbol's path; no edge in the data" : "from the symbol's name; no edge in the data"}
              </div>
            </div>
            <span />
          </div>
        </>
      ) : null}
      {defines.length ? (
        <>
          <h4>
            <span>Defines</span>
            <span>inferred</span>
          </h4>
          {defines.map((s) => (
            <div className="erow" key={s.id}>
              <span />
              <div>
                <button onClick={() => onGo(s.id)}>{s.label}</button>
              </div>
              <span />
            </div>
          ))}
        </>
      ) : null}
      <h4>
        <span>Incoming</span>
        <span>{ins.length}</span>
      </h4>
      {ins.length ? ins.map((e) => row(e, model.byId.get(e.from)!, "←")) : <div className="s-gap">None</div>}
      <h4>
        <span>Outgoing</span>
        <span>{outs.length}</span>
      </h4>
      {outs.length ? outs.map((e) => row(e, model.byId.get(e.to)!, "→")) : <div className="s-gap">None</div>}
      <div className="actions">
        {mode !== "focus" ? (
          <button className="btn primary" onClick={() => onAct("focus")}>
            Focus on this
          </button>
        ) : (
          <button className="btn primary" onClick={() => onAct("strata")}>
            Back to Strata
          </button>
        )}
        <button className="btn" onClick={() => onAct("clear")}>
          Clear
        </button>
      </div>
    </>
  );
}
