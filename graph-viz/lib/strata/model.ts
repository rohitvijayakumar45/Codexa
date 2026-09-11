/*
  Strata data model: the API's GraphNode/GraphEdge turned into what the view reads.

  Everything here is derived from real properties. Where the data has a gap (a symbol with no edge
  to the file that defines it), the model may infer the link, but it records HOW it inferred it so
  the inspector can say so — nothing is presented as more certain than it is.
*/

import type { GraphEdge, GraphEdgeSourceType, GraphEdgeType, GraphNode, GraphNodeType } from "@/lib/api";

export const DAY = 86_400_000;

export type Family = "structure" | "reasoning" | "signals";
export type PredFamily = "struct" | "intent" | "signal";

export const TYPE_FAM: Record<GraphNodeType, Family> = {
  Repository: "structure",
  File: "structure",
  CodeSymbol: "structure",
  ApiRoute: "structure",
  SchemaField: "structure",
  ExternalArtifact: "structure",
  Decision: "reasoning",
  Tradeoff: "reasoning",
  RejectedAlternative: "reasoning",
  OnboardingPath: "reasoning",
  ConventionProfile: "reasoning",
  CausalEvent: "signals",
  HealthMetric: "signals",
  PreventionRule: "signals",
  ArchitectureTrend: "signals",
  SimulationScenario: "signals",
};

export const TYPE_LABEL: Record<GraphNodeType, string> = {
  Repository: "Repository",
  File: "File",
  CodeSymbol: "Code symbol",
  ApiRoute: "API route",
  SchemaField: "Schema field",
  ExternalArtifact: "External artifact",
  Decision: "Decision",
  Tradeoff: "Trade-off",
  RejectedAlternative: "Rejected alternative",
  OnboardingPath: "Onboarding path",
  ConventionProfile: "Convention",
  CausalEvent: "Causal event",
  HealthMetric: "Health metric",
  PreventionRule: "Prevention rule",
  ArchitectureTrend: "Architecture trend",
  SimulationScenario: "Simulation",
};

export const FAMILY_LABEL: Record<Family, string> = {
  structure: "Structure",
  reasoning: "Intent",
  signals: "Signals",
};

export const PRED_FAM: Record<GraphEdgeType, PredFamily> = {
  calls: "struct",
  imports: "struct",
  depends_on: "struct",
  flows_into: "struct",
  derived_from: "struct",
  traces_to_decision: "intent",
  supersedes: "intent",
  causes: "signal",
  mitigates: "signal",
  increases_risk_of: "signal",
  correlates_with: "signal",
};

export const SRC_LABEL: Record<GraphEdgeSourceType, string> = {
  static_analysis: "Static analysis",
  human_asserted: "Human asserted",
  llm_inferred: "LLM inferred",
};

export interface SNode {
  id: string;
  type: GraphNodeType;
  fam: Family;
  label: string;
  sub?: string;
  method?: string;
  path?: string;
  stableId: string;
  props: Record<string, unknown>;
  /** First moment the node exists in history (ms). */
  t0: number;
  /** Position in the API's insertion order — the stable tie-breaker for layout. */
  order: number;
  /** A File node that is really a directory: drawn as its module's region, not a tile. */
  hull: boolean;
  /** Directory of a file tile. */
  dir?: string;
  /** The file that defines a symbol, and how that was established. */
  def?: { fileId: string; how: "property" | "name" };
  score?: number;
  trend?: { metric: string; first: number; latest: number };
}

export interface SEdge {
  id: string;
  from: string;
  to: string;
  type: GraphEdgeType;
  conf: number;
  src: GraphEdgeSourceType;
  vf: number;
  vt: number | null;
  /** Repository-contains-file: drawn as the region the file sits in, never as a line. */
  contain: boolean;
  props: Record<string, unknown>;
}

export interface StrataModel {
  nodes: SNode[];
  edges: SEdge[];
  byId: Map<string, SNode>;
}

export const edgeLive = (e: SEdge, t: number) => e.vf <= t && (e.vt === null || e.vt > t);
/** Expired within the last 20 days of the viewed moment: drawn as a dashed ghost. */
export const edgeGhost = (e: SEdge, t: number) => e.vt !== null && e.vt <= t && t - e.vt <= 20 * DAY && e.vf <= t;
export const nodeLive = (n: SNode, t: number) => n.t0 <= t;

export function daysAgoLabel(ms: number, nowMs: number): string {
  const d = Math.max(0, Math.round((nowMs - ms) / DAY));
  return d === 0 ? "today" : d === 1 ? "1 day ago" : `${d} days ago`;
}

const str = (v: unknown) => (typeof v === "string" && v.trim() ? v.trim() : undefined);
const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Turn a stable-id slug into words, borrowing each word's casing from the node's own text when that
    text capitalises it mid-sentence ("neo4j" -> "Neo4j", "pydantic" -> "Pydantic"). */
function humanize(slug: string, context: string): string {
  const words = slug.split(/[-_/]+/).filter(Boolean);
  const out = words.map((w) => {
    const re = new RegExp(`\\b${escapeRe(w)}\\b`, "gi");
    let m: RegExpExecArray | null;
    while ((m = re.exec(context))) {
      const atSentenceStart = m.index === 0 || /[.!?]\s*$/.test(context.slice(0, m.index));
      if (!atSentenceStart && /[A-Z]/.test(m[0])) return m[0];
    }
    return w;
  });
  const s = out.join(" ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const tail = (stableId: string) => stableId.split("://").pop() ?? stableId;

function describe(n: GraphNode, nowMs: number): Pick<SNode, "label" | "sub" | "method"> {
  const p = n.properties;
  const context = Object.values(p).filter((v) => typeof v === "string").join(" ");
  const slug = tail(n.stable_id);
  switch (n.node_type) {
    case "Repository":
      return { label: str(p.name) ?? slug };
    case "File": {
      const path = str(p.path) ?? slug;
      return { label: path.split("/").pop() || path };
    }
    case "CodeSymbol":
    case "SchemaField":
      return { label: str(p.name) ?? slug };
    case "ApiRoute":
      return { label: str(p.path) ?? slug, method: str(p.method)?.toUpperCase() };
    case "Decision":
      return { label: str(p.title) ?? humanize(slug, context) };
    case "CausalEvent": {
      const kind = str(p.event_kind) ?? "event";
      const sha = str(p.sha);
      const id = sha ? sha.slice(0, 7) : (slug.split("/").pop() ?? slug);
      const summary = str(p.summary);
      const label = /^[0-9a-f]{6,40}$/i.test(id)
        ? `${kind} ${id}`
        : summary && summary.length <= 40
          ? summary
          : `${kind}: ${humanize(id, context).toLowerCase()}`;
      const at = str(p.occurred_at);
      return { label, sub: at ? daysAgoLabel(Date.parse(at), nowMs) : undefined };
    }
    case "HealthMetric": {
      const comps = p.components && typeof p.components === "object" ? Object.keys(p.components).length : 0;
      return { label: "Repository health", sub: comps ? `${comps} components` : undefined };
    }
    case "ArchitectureTrend":
      return { label: `${str(p.module_path) ?? slug} coupling` };
    default:
      return { label: str(p.title) ?? str(p.name) ?? humanize(slug, context) };
  }
}

const tokens = (s: string) =>
  s
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((t) => t.length > 2);

export function buildModel(raw: GraphNode[], rawEdges: GraphEdge[], nowMs: number): StrataModel {
  const ids = new Set(raw.map((n) => n.id));
  const typeOf = new Map(raw.map((n) => [n.id, n.node_type] as const));

  const edges: SEdge[] = [];
  for (const e of rawEdges) {
    if (!ids.has(e.from_node_id) || !ids.has(e.to_node_id)) continue;
    edges.push({
      id: e.id,
      from: e.from_node_id,
      to: e.to_node_id,
      type: e.edge_type,
      // A git co-change edge is a certain fact (confidence 1.0) whose coupling strength is a property.
      conf: typeof e.properties?.strength === "number" ? (e.properties.strength as number) : e.confidence,
      src: e.source_type,
      vf: Date.parse(e.valid_from),
      vt: e.valid_to ? Date.parse(e.valid_to) : null,
      contain: typeOf.get(e.from_node_id) === "Repository" && typeOf.get(e.to_node_id) === "File",
      props: e.properties ?? {},
    });
  }

  const firstSeen = new Map<string, number>();
  for (const e of edges) {
    for (const id of [e.from, e.to]) firstSeen.set(id, Math.min(firstSeen.get(id) ?? Infinity, e.vf));
  }

  const filePaths = raw.filter((n) => n.node_type === "File").map((n) => str(n.properties.path) ?? "");

  const nodes: SNode[] = raw.map((n, i) => {
    const p = n.properties;
    const path = str(p.path);
    const base = path?.split("/").pop() ?? "";
    const hull =
      n.node_type === "File" &&
      !!path &&
      (p.kind === "module" || (!base.includes(".") && filePaths.some((fp) => fp.startsWith(path + "/"))));
    const at = n.node_type === "CausalEvent" ? str(p.occurred_at) : undefined;
    const t0 = at ? Date.parse(at) : (firstSeen.get(n.id) ?? Date.parse(n.created_at));
    let trend: SNode["trend"];
    if (n.node_type === "ArchitectureTrend" && Array.isArray(p.trends)) {
      const list = p.trends as { metric: string; first_value: number; latest_value: number }[];
      const m = list.find((x) => x.metric === "coupling") ?? list[0];
      if (m) trend = { metric: m.metric, first: m.first_value, latest: m.latest_value };
    }
    return {
      id: n.id,
      type: n.node_type,
      fam: TYPE_FAM[n.node_type],
      ...describe(n, nowMs),
      path,
      stableId: n.stable_id,
      props: p,
      t0,
      order: i,
      hull,
      dir: n.node_type === "File" && !hull && path ? path.split("/").slice(0, -1).join("/") || "." : undefined,
      score: n.node_type === "HealthMetric" && typeof p.score === "number" ? p.score : undefined,
      trend,
    };
  });

  // Symbol -> defining file. The data has no such edge, so: an explicit `file` property first; else
  // a file whose name is made only of words distinctive to this one symbol (engine.py for
  // EngineeringSimulationEngine), and only when exactly one file qualifies.
  const files = nodes.filter((n) => n.type === "File" && !n.hull && n.path);
  const symbols = nodes.filter((n) => n.type === "CodeSymbol");
  const freq = new Map<string, number>();
  for (const s of symbols) for (const t of new Set(tokens(s.label))) freq.set(t, (freq.get(t) ?? 0) + 1);
  for (const s of symbols) {
    const fp = str(s.props.file);
    if (fp) {
      const f = files.find((x) => x.path === fp || x.path!.endsWith("/" + fp));
      if (f) {
        s.def = { fileId: f.id, how: "property" };
        continue;
      }
    }
    const st = new Set(tokens(s.label));
    const hits = files.filter((f) => {
      const stem = tokens((f.path!.split("/").pop() ?? "").replace(/\.[^.]+$/, ""));
      return stem.length > 0 && stem.every((t) => st.has(t) && freq.get(t) === 1);
    });
    if (hits.length === 1) s.def = { fileId: hits[0].id, how: "name" };
  }

  return { nodes, edges, byId: new Map(nodes.map((n) => [n.id, n])) };
}
