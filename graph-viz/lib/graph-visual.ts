/*
  Visual encoding — a family system, pushed to jewel-tone saturation for a light canvas.

  The ~16 node types collapse into 3 semantic families, each carrying ONE vivid hue. Type within a
  family is separated by lightness step + size, not by inventing another unrelated hue. The single
  saturated accent (electric teal) is reserved for STATE — recently-changed, selected, and the data
  that visibly flows along edges — so state never competes with the type palette.

    - node hue        -> family (structure / reasoning / signals)
    - node lightness  -> type within family
    - node size       -> importance by type, scaled by live degree
    - edge opacity/width -> confidence
    - edge dash       -> source_type (llm_inferred = dashed)
    - teal            -> state only (recent change, selection, flow particles)
*/

import type { GraphEdgeSourceType, GraphEdgeType, GraphNodeType } from "./api";

export type NodeFamily = "structure" | "reasoning" | "signals";

export const STATE_ACCENT = "#00c2b8"; // electric teal — recent change / selection / flow, nothing else
export const STATE_ACCENT_SOFT = "#5fe8de";
export const EDGE_NEUTRAL = "#7c86c4";

export const FAMILY_META: Record<NodeFamily, { label: string; swatch: string; blurb: string }> = {
  structure: { label: "Structure", swatch: "#4f46e5", blurb: "repository, files, symbols, routes" },
  reasoning: { label: "Reasoning", swatch: "#d97706", blurb: "decisions, trade-offs, conventions" },
  signals: { label: "Signals", swatch: "#e11d48", blurb: "events, health, risk, architecture" },
};

export interface NodeStyle {
  color: string;
  base: number;
  label: string;
  family: NodeFamily;
}

// Lightness steps run dark→light within a family, roughly foundational→peripheral.
export const NODE_STYLE: Record<GraphNodeType, NodeStyle> = {
  // Structure — indigo/violet
  Repository: { color: "#312e81", base: 1.7, label: "Repository", family: "structure" },
  File: { color: "#4338ca", base: 1.05, label: "File", family: "structure" },
  CodeSymbol: { color: "#4f46e5", base: 0.92, label: "Code symbol", family: "structure" },
  ApiRoute: { color: "#6366f1", base: 0.95, label: "API route", family: "structure" },
  SchemaField: { color: "#818cf8", base: 0.75, label: "Schema field", family: "structure" },
  ExternalArtifact: { color: "#a5b4fc", base: 0.82, label: "External artifact", family: "structure" },

  // Reasoning — amber/gold
  Decision: { color: "#92400e", base: 1.1, label: "Decision", family: "reasoning" },
  Tradeoff: { color: "#b45309", base: 0.9, label: "Trade-off", family: "reasoning" },
  RejectedAlternative: { color: "#d97706", base: 0.82, label: "Rejected alternative", family: "reasoning" },
  OnboardingPath: { color: "#f59e0b", base: 0.85, label: "Onboarding path", family: "reasoning" },
  ConventionProfile: { color: "#fbbf24", base: 0.85, label: "Convention profile", family: "reasoning" },

  // Signals — rose/crimson
  CausalEvent: { color: "#9f1239", base: 0.98, label: "Causal event", family: "signals" },
  HealthMetric: { color: "#be123c", base: 1.05, label: "Health metric", family: "signals" },
  PreventionRule: { color: "#e11d48", base: 0.9, label: "Prevention rule", family: "signals" },
  ArchitectureTrend: { color: "#f43f5e", base: 1.1, label: "Architecture trend", family: "signals" },
  SimulationScenario: { color: "#fb7185", base: 1.0, label: "Simulation", family: "signals" },
};

export const EDGE_LABEL: Record<GraphEdgeType, string> = {
  calls: "calls",
  imports: "imports",
  depends_on: "depends on",
  causes: "causes",
  mitigates: "mitigates",
  increases_risk_of: "increases risk of",
  correlates_with: "correlates with",
  derived_from: "derived from",
  supersedes: "supersedes",
  flows_into: "flows into",
  traces_to_decision: "traces to decision",
};

export const SOURCE_LABEL: Record<GraphEdgeSourceType, string> = {
  static_analysis: "Static analysis",
  llm_inferred: "LLM inferred",
  human_asserted: "Human asserted",
};

/** Confidence drives how present an edge feels — widened range so it reads at a glance. */
export function edgeOpacity(confidence: number, dimmed: boolean): number {
  const base = 0.22 + confidence * 0.72;
  return dimmed ? base * 0.14 : base;
}

export function edgeWidth(confidence: number): number {
  return 0.9 + confidence * 3.2;
}

export function edgeIsDashed(source: GraphEdgeSourceType): boolean {
  return source === "llm_inferred";
}

export function nodeRadius(type: GraphNodeType, degree: number): number {
  return NODE_STYLE[type].base * (0.85 + Math.min(degree, 8) * 0.06);
}

export function nodeLabel(props: Record<string, unknown>, stableId: string): string {
  const candidate =
    (props.name as string) ??
    (props.path as string) ??
    (props.title as string) ??
    (props.summary as string) ??
    (props.repository as string) ??
    (props.module_path as string);
  if (candidate) return candidate;
  const tail = stableId.split("://").pop() ?? stableId;
  return tail.length > 40 ? `${tail.slice(0, 39)}…` : tail;
}
