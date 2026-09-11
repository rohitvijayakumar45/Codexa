/*
  Visual encoding for the 3D knowledge graph — theme-aware.

  The ~16 node types collapse into 3 semantic families, each carrying ONE hue taken from the theme's
  graph tokens (the same ones Strata uses), so the scene re-skins with Blueprint and Noir instead of
  carrying its own fixed palette. Type within a family is separated by a lightness step toward the
  canvas, not by inventing another hue. The theme's signal colour marks STATE only — recently changed,
  selected, and the data that visibly flows along edges.

    - node hue        -> family (structure / reasoning / signals)
    - node lightness  -> type within family
    - node size       -> importance by type, scaled by live degree
    - edge opacity/width -> confidence
    - edge dash       -> source_type (llm_inferred = dashed)
    - signal colour   -> state only (recent change, selection, flow particles)
*/

import type { GraphEdgeSourceType, GraphEdgeType, GraphNodeType } from "./api";
import { readCssVar, type ThemeName } from "./theme";

export type NodeFamily = "structure" | "reasoning" | "signals";

export const FAMILY_META: Record<NodeFamily, { label: string; cssVar: string; blurb: string }> = {
  structure: { label: "Structure", cssVar: "--color-g-sub", blurb: "repository, files, symbols, routes" },
  reasoning: { label: "Reasoning", cssVar: "--color-g-reason", blurb: "decisions, trade-offs, conventions" },
  signals: { label: "Signals", cssVar: "--color-g-sig", blurb: "events, health, risk, architecture" },
};

export interface NodeStyle {
  base: number;
  label: string;
  family: NodeFamily;
  /** Lightness step within the family, 0 = the family hue itself. */
  step: number;
}

export const NODE_STYLE: Record<GraphNodeType, NodeStyle> = {
  Repository: { base: 1.7, label: "Repository", family: "structure", step: 0 },
  File: { base: 1.05, label: "File", family: "structure", step: 1 },
  CodeSymbol: { base: 0.92, label: "Code symbol", family: "structure", step: 2 },
  ApiRoute: { base: 0.95, label: "API route", family: "structure", step: 3 },
  SchemaField: { base: 0.75, label: "Schema field", family: "structure", step: 4 },
  ExternalArtifact: { base: 0.82, label: "External artifact", family: "structure", step: 5 },

  Decision: { base: 1.1, label: "Decision", family: "reasoning", step: 0 },
  Tradeoff: { base: 0.9, label: "Trade-off", family: "reasoning", step: 1 },
  RejectedAlternative: { base: 0.82, label: "Rejected alternative", family: "reasoning", step: 2 },
  OnboardingPath: { base: 0.85, label: "Onboarding path", family: "reasoning", step: 3 },
  ConventionProfile: { base: 0.85, label: "Convention profile", family: "reasoning", step: 4 },

  CausalEvent: { base: 0.98, label: "Causal event", family: "signals", step: 0 },
  HealthMetric: { base: 1.05, label: "Health metric", family: "signals", step: 1 },
  PreventionRule: { base: 0.9, label: "Prevention rule", family: "signals", step: 2 },
  ArchitectureTrend: { base: 1.1, label: "Architecture trend", family: "signals", step: 3 },
  SimulationScenario: { base: 1.0, label: "Simulation", family: "signals", step: 4 },
};

const STEP_MIX = 9; // percent toward the canvas per lightness step

/** CSS colour for DOM swatches — follows the theme automatically. */
export const familyColor = (f: NodeFamily) => `var(${FAMILY_META[f].cssVar})`;
export function typeColorCss(type: GraphNodeType): string {
  const s = NODE_STYLE[type];
  return s.step === 0
    ? familyColor(s.family)
    : `color-mix(in srgb, ${familyColor(s.family)}, var(--color-g-canvas) ${s.step * STEP_MIX}%)`;
}

/** Resolved colours for the WebGL scene, which can't read CSS variables itself. */
export interface GraphPalette {
  family: Record<NodeFamily, string>;
  canvas: string;
  edge: string;
  accent: string;
  accentSoft: string;
  fog: string;
}

function parse(c: string): [number, number, number] | null {
  const hex = c.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (hex) {
    const h = hex[1].length === 3 ? hex[1].replace(/./g, (x) => x + x) : hex[1];
    return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)) as [number, number, number];
  }
  const rgb = c.match(/^rgba?\(\s*([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)/i);
  return rgb ? [Number(rgb[1]), Number(rgb[2]), Number(rgb[3])] : null;
}

function mix(a: string, b: string, t: number): string {
  const x = parse(a);
  const y = parse(b);
  if (!x || !y) return a;
  const out = x.map((v, i) => Math.round(v + (y[i] - v) * t));
  return `#${out.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

const FALLBACK: Record<ThemeName, GraphPalette> = {
  blueprint: {
    family: { structure: "#4b5767", reasoning: "#a8551f", signals: "#9b3aa6" },
    canvas: "#fbfcfe",
    edge: "#8797a8",
    accent: "#0f6fd4",
    accentSoft: "#57a0e8",
    fog: "#eef1f5",
  },
  noir: {
    family: { structure: "#a9a6a0", reasoning: "#b08a1c", signals: "#b377d9" },
    canvas: "#0c0c0d",
    edge: "#6f6f76",
    accent: "#c2415a",
    accentSoft: "#d77a8c",
    fog: "#0a0a0b",
  },
};

export function readGraphPalette(theme: ThemeName): GraphPalette {
  const fb = FALLBACK[theme];
  const v = (name: string, fallback: string) => (parse(readCssVar(name, theme)) ? readCssVar(name, theme) : fallback);
  const accent = v("--color-signal", fb.accent);
  return {
    family: {
      structure: v("--color-g-sub", fb.family.structure),
      reasoning: v("--color-g-reason", fb.family.reasoning),
      signals: v("--color-g-sig", fb.family.signals),
    },
    canvas: v("--color-g-canvas", fb.canvas),
    edge: v("--color-g-edge", fb.edge),
    accent,
    accentSoft: mix(accent, "#ffffff", 0.3),
    fog: v("--color-paper", fb.fog),
  };
}

export function nodeColor(type: GraphNodeType, p: GraphPalette): string {
  const s = NODE_STYLE[type];
  return mix(p.family[s.family], p.canvas, (s.step * STEP_MIX) / 100);
}

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
