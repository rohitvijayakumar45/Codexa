/*
  Typed client for the Codexa OS FastAPI backend. Every screen reads through here; there is no
  mock layer. The base URL defaults to the local backend and can be overridden with
  NEXT_PUBLIC_API_BASE.
*/

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ?? "http://localhost:8000";

export type GraphNodeType =
  | "Repository"
  | "File"
  | "CodeSymbol"
  | "ApiRoute"
  | "SchemaField"
  | "ExternalArtifact"
  | "ArchitectureTrend"
  | "SimulationScenario"
  | "CausalEvent"
  | "Decision"
  | "Tradeoff"
  | "RejectedAlternative"
  | "OnboardingPath"
  | "HealthMetric"
  | "PreventionRule"
  | "ConventionProfile";

export type GraphEdgeType =
  | "calls"
  | "imports"
  | "depends_on"
  | "causes"
  | "mitigates"
  | "increases_risk_of"
  | "correlates_with"
  | "derived_from"
  | "supersedes"
  | "flows_into"
  | "traces_to_decision";

export type GraphEdgeSourceType = "static_analysis" | "llm_inferred" | "human_asserted";

export interface GraphNode {
  id: string;
  node_type: GraphNodeType;
  stable_id: string;
  properties: Record<string, unknown>;
  created_at: string;
}

export interface GraphEdge {
  id: string;
  from_node_id: string;
  to_node_id: string;
  edge_type: GraphEdgeType;
  confidence: number;
  source_type: GraphEdgeSourceType;
  valid_from: string;
  valid_to: string | null;
  source_artifact_id: string | null;
  properties: Record<string, unknown>;
  created_at: string;
}

export interface GraphSnapshot {
  at_time: string | null;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GraphTimeline {
  starts_at: string | null;
  ends_at: string | null;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null,
    readonly cause?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function get<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { headers: { accept: "application/json" } });
  } catch (cause) {
    throw new ApiError(
      `Can't reach the Codexa backend at ${API_BASE}. Is it running (uvicorn backend.main:app) with CODEXA_SEED=1?`,
      null,
      cause,
    );
  }
  if (!res.ok) {
    throw new ApiError(`Backend responded ${res.status} for ${path}.`, res.status);
  }
  return (await res.json()) as T;
}

// --- Chat -------------------------------------------------------------------
export interface ChatModel {
  id: string;
  label: string;
  provider: string;
  context_window: number;
  default: boolean;
}
export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}
export interface ChatUsage {
  prompt_tokens: number;
  completion_tokens: number;
  context_window: number;
  model: string;
}

// --- Impact / blast radius --------------------------------------------------
export interface NodeRef {
  id: string;
  label: string;
  node_type: string;
}
export interface ImpactResult {
  resolved: boolean;
  targets: NodeRef[];
  affected: NodeRef[];
  affected_count: number;
  max_depth: number;
  max_depth_reached: number;
  confidence: number;
  risk_level: "None" | "Low" | "Medium" | "High" | "Critical";
  risk_score: number;
  paths_preview: string[][];
  summary: string;
  breakdown: Record<string, number>;
  files_touched: number;
  call_edges: number;
  import_edges: number;
  coupling_edges: number;
}

// --- Observability ----------------------------------------------------------
export interface EventRecord {
  id: string;
  event_type: string;
  occurred_at: string;
  summary: string;
  aggregate_id: string;
}
export interface SnapshotMarker {
  at: string;
  repository: string;
  files: number;
  symbols: number;
  score: number;
}
export interface AgentNode {
  id: string;
  name: string;
  role: string;
  layer: string;
  status: "active" | "idle";
  activity_count: number;
  last_active: string | null;
  current_task: string | null;
  depends_on: string[];
}
export interface UsageBucket {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  calls: number;
}
export interface UsageSummary {
  totals: UsageBucket;
  by_agent: Record<string, UsageBucket>;
  by_model: Record<string, UsageBucket>;
}
export interface UsageRecord {
  at: string;
  agent: string;
  model: string;
  provider: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

// --- Docs -------------------------------------------------------------------
export interface FieldDoc {
  name: string;
  type: string;
  required: boolean;
  description: string | null;
}
export interface ModelDoc {
  name: string;
  fields: FieldDoc[];
}
export interface EndpointDoc {
  method: string;
  path: string;
  name: string;
  summary: string | null;
  request_model: string | null;
  response_model: string | null;
}
export interface GroupDoc {
  tag: string;
  endpoints: EndpointDoc[];
}
export interface GeneratedDocs {
  generated_at: string;
  overview: string;
  groups: GroupDoc[];
  models: ModelDoc[];
}

// --- Memory -----------------------------------------------------------------
export type MemoryType = "semantic" | "episodic" | "procedural" | "organizational";
export interface MemoryRecord {
  id: string;
  repository: string;
  memory_type: MemoryType;
  title: string;
  content: string;
  created_at: string;
  metadata: Record<string, unknown>;
}
export interface ContextItem {
  kind: string;
  title: string;
  content: string;
}
export interface RepositorySummary {
  repository: string;
  counts: Record<MemoryType, number>;
  total: number;
  last_updated: string | null;
}
export interface RepositoryInfo {
  name: string;
  url: string;
  path: string;
  file_count: number;
  languages: string[];
  already_loaded: boolean;
  memories_created: number;
}
export interface RepoDocs {
  repository: string;
  generated_at: string;
  markdown: string;
}
export interface FileTreeNode {
  name: string;
  path: string;
  type: "dir" | "file";
  children?: FileTreeNode[];
}
export interface FileContent {
  path: string;
  language: string;
  content: string;
  truncated: boolean;
}
export interface FileSearchHit {
  path: string;
  line: number;
  text: string;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify(body),
    });
  } catch (cause) {
    throw new ApiError(`Can't reach the Codexa backend at ${API_BASE}.`, null, cause);
  }
  if (!res.ok) throw new ApiError(`Backend responded ${res.status} for ${path}.`, res.status);
  return (await res.json()) as T;
}

export interface StreamHandlers {
  onDelta: (text: string) => void;
  onDone: (usage: ChatUsage | null) => void;
  onError: (message: string) => void;
  onToolCall?: (call: { name: string; args: Record<string, unknown> }) => void;
  onToolResult?: (result: { name: string; result: string }) => void;
  signal?: AbortSignal;
}

/** Tool-calling agent chat: the model may read/search/write files, search the web, run code. */
export async function streamAgentChat(
  messages: ChatMessage[],
  model: string | null,
  repository: string,
  handlers: StreamHandlers,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/chat/agent`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ messages, model, repository }),
      signal: handlers.signal,
    });
  } catch {
    handlers.onError(`Can't reach the Codexa backend at ${API_BASE}.`);
    return;
  }
  if (!res.ok || !res.body) {
    handlers.onError(`Backend responded ${res.status}.`);
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data:")) continue;
        try {
          const evt = JSON.parse(line.slice(5).trim());
          if (evt.error) handlers.onError(evt.error);
          else if (evt.done) handlers.onDone(evt.usage ?? null);
          else if (evt.delta) handlers.onDelta(evt.delta);
          else if (evt.tool_call) handlers.onToolCall?.(evt.tool_call);
          else if (evt.tool_result) handlers.onToolResult?.(evt.tool_result);
        } catch {
          /* ignore */
        }
      }
    }
  } catch (err) {
    // A cancelled stream rejects reader.read() with an AbortError — expected when the user
    // navigates away mid-response, not a real failure. Anything else is a genuine drop.
    if (!(err instanceof DOMException && err.name === "AbortError")) {
      handlers.onError(err instanceof Error ? err.message : String(err));
    }
  }
}

/** Streams a completion over SSE from the real backend chat endpoint. */
export async function streamChat(
  messages: ChatMessage[],
  model: string | null,
  handlers: StreamHandlers,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/chat/stream`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ messages, model }),
      signal: handlers.signal,
    });
  } catch (cause) {
    handlers.onError(`Can't reach the Codexa backend at ${API_BASE}.`);
    return;
  }
  if (!res.ok || !res.body) {
    handlers.onError(`Backend responded ${res.status}.`);
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data:")) continue;
        try {
          const evt = JSON.parse(line.slice(5).trim());
          if (evt.error) handlers.onError(evt.error);
          else if (evt.done) handlers.onDone(evt.usage ?? null);
          else if (evt.delta) handlers.onDelta(evt.delta);
        } catch {
          /* ignore malformed chunk */
        }
      }
    }
  } catch (err) {
    if (!(err instanceof DOMException && err.name === "AbortError")) {
      handlers.onError(err instanceof Error ? err.message : String(err));
    }
  }
}

export const api = {
  snapshot: (atTime?: string | null, repository?: string) => {
    const p = new URLSearchParams();
    if (atTime) p.set("at_time", atTime);
    if (repository) p.set("repository", repository);
    const qs = p.toString();
    return get<GraphSnapshot>(`/graph/snapshots${qs ? `?${qs}` : ""}`);
  },
  nodes: (repository?: string) =>
    get<GraphNode[]>(`/graph/nodes${repository ? `?repository=${encodeURIComponent(repository)}` : ""}`),
  /** Full temporal edge set incl. superseded — powers smooth time-machine replay. */
  allEdges: (repository?: string) =>
    get<GraphEdge[]>(`/graph/edges/all${repository ? `?repository=${encodeURIComponent(repository)}` : ""}`),
  timeline: () => get<GraphTimeline>("/graph/timeline"),
  causalOverview: () =>
    get<{ event_node_ids: string[]; causal_edge_ids: string[] }>("/graph/causal/overview"),
  chatModels: () => get<ChatModel[]>("/chat/models"),
  impact: (description: string, maxDepth = 3) =>
    post<ImpactResult>("/agents/impact", { description, max_depth: maxDepth }),
  memoryRecords: (repository?: string, memoryType?: MemoryType) => {
    const p = new URLSearchParams();
    if (repository) p.set("repository", repository);
    if (memoryType) p.set("memory_type", memoryType);
    const qs = p.toString();
    return get<MemoryRecord[]>(`/memory/records${qs ? `?${qs}` : ""}`);
  },
  memoryRepositories: () => get<RepositorySummary[]>("/memory/repositories"),
  contextFor: (repository: string, query: string) =>
    get<ContextItem[]>(
      `/memory/context?repository=${encodeURIComponent(repository)}&query=${encodeURIComponent(query)}`,
    ),
  loadRepository: (url: string) => post<RepositoryInfo>("/repository/load", { url }),
  fileTree: (repository: string) =>
    get<FileTreeNode[]>(`/files/tree?repository=${encodeURIComponent(repository)}`),
  fileRead: (repository: string, path: string) =>
    get<FileContent>(`/files/read?repository=${encodeURIComponent(repository)}&path=${encodeURIComponent(path)}`),
  fileSearch: (repository: string, q: string) =>
    get<FileSearchHit[]>(`/files/search?repository=${encodeURIComponent(repository)}&q=${encodeURIComponent(q)}`),
  repoDocs: (repository: string) =>
    get<RepoDocs>(`/repository/docs?repository=${encodeURIComponent(repository)}`),
  regenerateRepoDocs: (repository: string) =>
    post<RepoDocs>(`/repository/docs/regenerate?repository=${encodeURIComponent(repository)}`, {}),
  events: (limit = 120) => get<EventRecord[]>(`/observability/events?limit=${limit}`),
  snapshots: () => get<SnapshotMarker[]>("/observability/snapshots"),
  agents: () => get<{ agents: AgentNode[] }>("/observability/agents"),
  usageSummary: () => get<UsageSummary>("/observability/usage"),
  usageRecords: (limit = 100) => get<UsageRecord[]>(`/observability/usage/records?limit=${limit}`),
  archTrends: () =>
    get<
      {
        trend_node_id: string;
        module_path: string;
        trends: { metric: string; first_value: number; latest_value: number; slope_per_day: number }[];
        alerts: string[];
        bottleneck_eta_days: number | null;
      }[]
    >("/understanding/architecture/trends"),
  docs: () => get<GeneratedDocs>("/docs-gen/generated"),
  regenerateDocs: (llmProse = false) =>
    post<GeneratedDocs>(`/docs-gen/regenerate?llm_prose=${llmProse}`, {}),
};
