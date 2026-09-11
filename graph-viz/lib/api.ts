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

/** The backend's own explanation of a failed request (FastAPI puts it in `detail`), falling back to
    the status line. Showing only "Backend responded 400" hid every actionable error — a private
    repository, a bad URL — behind the same useless sentence. */
async function failureMessage(res: Response, path: string): Promise<string> {
  try {
    const body = (await res.clone().json()) as { detail?: unknown };
    const d = body?.detail;
    if (typeof d === "string" && d.trim()) return d;
    if (Array.isArray(d) && d.length && typeof (d[0] as { msg?: unknown })?.msg === "string") return (d[0] as { msg: string }).msg;
  } catch {
    // not JSON — fall through to the status line
  }
  return `Backend responded ${res.status} for ${path}.`;
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
    throw new ApiError(await failureMessage(res, path), res.status);
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

// --- Execution plan ---------------------------------------------------------
// Mirrors summarize_for_event() in backend/agents/plan.py exactly. Emitted when the plan is created
// and again on every task transition; each event is a full SNAPSHOT that replaces the last, not a
// patch. Carries no reasoning of any kind, by design — the plan UI shows execution state only.
export type PlanTaskStatus = "PENDING" | "IN_PROGRESS" | "BLOCKED" | "COMPLETED" | "FAILED";
export type PlanValidationState = "UNVALIDATED" | "PASSED" | "FAILED";
export interface PlanTask {
  id: string;
  objective: string;
  status: PlanTaskStatus;
  /** Rejected completion claims so far — 1 means Codexa refused a "done" once and is retrying. */
  attempts: number;
  validation_state: PlanValidationState;
  validation_detail: string;
  expected_artifacts: string[];
  last_progress: string;
}
export interface PlanSnapshot {
  objective: string;
  current_task_id: string | null;
  tasks: PlanTask[];
  completed: number;
  total: number;
  /**
   * Where these tasks came from. "proposed" means the model decomposed this specific request;
   * "template" means the deterministic fallback ran. Surfaced because the fallback is silent by
   * design — it never fails a job — and so a generic plan and a request-specific one looked
   * identical from here while most plans were quietly the template.
   */
  source?: "proposed" | "template" | "";
  /** Why the fallback ran, when it did. Shown as the badge's tooltip. */
  source_detail?: string;
}

// --- Impact / blast radius --------------------------------------------------
export interface NodeRef {
  id: string;
  label: string;
  node_type: string;
}
export interface CouplingRisk {
  file_label: string;
  root_cause_summary: string;
  incident_summary: string;
  prevention_rule: string | null;
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
  coupling_risks: CouplingRisk[];
  change_kind?: "cosmetic" | "code";
  /** One sentence saying why the risk level is what it is. */
  risk_reason?: string;
  /** Files the target itself imports — what a root component renders. */
  composes?: number;
  root_component?: boolean;
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
export interface PlanResult {
  plan_id: string;
  repository: string;
  goal: string;
  plan: string;
}
export interface ProposedFileChange {
  path: string;
  diff: string;
}
export interface ProposeChangeResult {
  proposal_id: string;
  status: string;
  objective: string;
  changed_paths: string[];
  changes: ProposedFileChange[];
  rationale: string;
}
export interface ResearchCitation {
  url: string;
  title: string;
  summary: string;
}
export interface BeliefCardClaim {
  type: string;
  target: string;
  assertion: string;
}
export interface BeliefCard {
  model: string;
  answer: string;
  confidence: number;
  claims: BeliefCardClaim[];
  verified_count: number;
  failed_count: number;
  failed_reasons: string[];
  round: number;
  calibration: number;
}
export interface QuorumRunResult {
  quorum_id: string;
  query: string;
  winning_answer: string | null;
  winning_confidence: number | null;
  resolved: boolean;
  cards: BeliefCard[];
  debated: boolean;
  decision_node_id: string;
}
export interface ResearchAskResult {
  recommendation_node_id: string;
  query: string;
  recommendation: string;
  confidence: number;
  citations: ResearchCitation[];
  used_web_search: boolean;
}
export interface UsageBucket {
  prompt_tokens: number;
  completion_tokens: number;
  reasoning_tokens: number;
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
  reasoning_tokens: number;
  total_tokens: number;
}
export interface UsageDailyBucket {
  date: string;
  prompt_tokens: number;
  completion_tokens: number;
  reasoning_tokens: number;
  total_tokens: number;
  calls: number;
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
export interface RepoListing {
  name: string;
  url: string;
  loaded: boolean;
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
  /** sha256 of the bytes on disk when read — sent back on save to detect conflicting edits. */
  sha: string;
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
  if (!res.ok) throw new ApiError(await failureMessage(res, path), res.status);
  return (await res.json()) as T;
}

async function del<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { method: "DELETE", headers: { accept: "application/json" } });
  } catch (cause) {
    throw new ApiError(`Can't reach the Codexa backend at ${API_BASE}.`, null, cause);
  }
  if (!res.ok) throw new ApiError(await failureMessage(res, path), res.status);
  return (await res.json()) as T;
}

export interface StreamHandlers {
  onDelta: (text: string) => void;
  onDone: (usage: ChatUsage | null) => void;
  // continuable is true only for an agent job that errored out solely from running out of
  // tool-calling rounds (backend/agents/jobs.py's round_budget) — that specific case can be
  // resumed with the SAME message/tool-call history via continueAgentJob, instead of losing
  // everything to a fresh retry. Undefined/false for every other error.
  onError: (message: string, continuable?: boolean) => void;
  onThinking?: (text: string) => void;
  // Human-readable status ("Writing app.py", "Running tests") filling the gap between rounds/tool
  // calls that "thinking" alone leaves silent on models that never emit reasoning_content.
  onStatus?: (text: string) => void;
  // Full snapshot of the job's execution plan — later ones replace earlier ones wholesale.
  onPlan?: (plan: PlanSnapshot) => void;
  onToolCall?: (call: { name: string; args: Record<string, unknown> }) => void;
  onToolResult?: (result: { name: string; result: string }) => void;
  onRepoSwitched?: (repository: string) => void;
  onModelSwitched?: (modelId: string) => void;
  // What tasks of this classified kind have cost before (backend/agents/token_budget.py).
  onPredictedBudget?: (budget: PredictedBudget) => void;
  signal?: AbortSignal;
}

export interface PredictedBudget {
  intent: string;
  predicted_tokens: number;
  based_on_samples: number;
  confidence: "low" | "medium" | "high";
}

/** How a job subscription ended: the job's stream closed normally, the connection broke, or the
 *  caller aborted it. "network" is what a caller retries on — the job itself keeps running. */
export type SubscriptionEnd = "ended" | "network" | "aborted";

export interface PhasedBuildPhase {
  title: string;
  job_id: string | null;
  status: string;
  detail: string;
}

export interface PhasedBuildStatus {
  phased_build_id: string;
  status: string;
  current_phase: number;
  phases: PhasedBuildPhase[];
}

/** Splits a large spec into up to 8 phases, each run as its own fresh job (backend/agents/phased_build.py). */
export async function startPhasedBuild(spec: string, repository: string, model: string | null) {
  const res = await fetch(`${API_BASE}/chat/agent/phased`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ spec, repository, model }),
  });
  if (!res.ok) throw new ApiError(await failureMessage(res, "/chat/agent/phased"), res.status);
  return (await res.json()) as { phased_build_id: string; phases: { title: string; prompt: string }[] };
}

export async function phasedBuildStatus(buildId: string): Promise<PhasedBuildStatus> {
  const res = await fetch(`${API_BASE}/chat/agent/phased/${buildId}`);
  if (!res.ok) throw new ApiError(await failureMessage(res, `/chat/agent/phased/${buildId}`), res.status);
  return (await res.json()) as PhasedBuildStatus;
}

/** Starts the tool-calling agent loop as a background job on the backend and returns its id.
 *  The job runs detached from this request — it survives the browser tab losing focus, the page
 *  navigating away, or even a backend restart (it checkpoints to disk and auto-resumes). Pair with
 *  `subscribeAgentJob` to watch it, from this page load or a later one. */
export async function startAgentJob(
  messages: ChatMessage[],
  model: string | null,
  repository: string,
): Promise<string> {
  const res = await fetch(`${API_BASE}/chat/agent`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ messages, model, repository }),
  });
  if (!res.ok) throw new ApiError(`Backend responded ${res.status} starting the agent job.`, res.status);
  const data = (await res.json()) as { job_id: string };
  return data.job_id;
}

/** Tells the backend to stop a running agent job after its current round finishes. Best-effort —
 *  swallow failures, the caller is already tearing down its own local stream reader regardless. */
export async function cancelAgentJob(jobId: string): Promise<void> {
  try {
    await fetch(`${API_BASE}/chat/agent/job/${jobId}/cancel`, { method: "POST" });
  } catch {
    /* best-effort */
  }
}

/** Resumes a job that errored out ONLY from running out of tool-calling rounds — grants it a
 *  bigger round budget and re-runs it with its full existing message/tool-call history intact.
 *  Pair with subscribeAgentJob(jobId, ...) afterward to watch it continue. Throws if the job isn't
 *  in that specific continuable state (see the "continuable" flag on StreamHandlers.onError). */
export async function continueAgentJob(jobId: string): Promise<string> {
  const res = await fetch(`${API_BASE}/chat/agent/job/${jobId}/continue`, { method: "POST" });
  if (!res.ok) throw new ApiError(`Backend responded ${res.status} continuing the job.`, res.status);
  const data = (await res.json()) as { job_id: string };
  return data.job_id;
}

/** Subscribes to an agent job's event log over SSE: replays everything emitted so far (so
 *  reattaching after a dropped connection catches up on what was missed) then tails new events
 *  live until the job finishes. Safe to call more than once for the same job_id — each call is an
 *  independent replay-from-start subscription. */
export async function subscribeAgentJob(jobId: string, handlers: StreamHandlers): Promise<SubscriptionEnd> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/chat/agent/stream/${jobId}`, { signal: handlers.signal });
  } catch (err) {
    // No onError here: a broken connection is the caller's to retry (the job keeps running), and
    // an error bubble flashed before a successful reconnect is noise.
    return err instanceof DOMException && err.name === "AbortError" ? "aborted" : "network";
  }
  if (!res.ok || !res.body) {
    handlers.onError(`Backend responded ${res.status}.`);
    return "ended";
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
          if (evt.error) handlers.onError(evt.error, evt.continuable === true);
          else if (evt.done) handlers.onDone(evt.usage ?? null);
          else if (evt.thinking) handlers.onThinking?.(evt.thinking);
          else if (evt.status) handlers.onStatus?.(evt.status);
          else if (evt.delta) handlers.onDelta(evt.delta);
          else if (evt.plan) handlers.onPlan?.(evt.plan as PlanSnapshot);
          else if (evt.tool_call) handlers.onToolCall?.(evt.tool_call);
          else if (evt.tool_result) handlers.onToolResult?.(evt.tool_result);
          else if (evt.repo_switched) handlers.onRepoSwitched?.(evt.repo_switched);
          else if (evt.model_switched) handlers.onModelSwitched?.(evt.model_switched);
          else if (evt.predicted_budget) handlers.onPredictedBudget?.(evt.predicted_budget as PredictedBudget);
        } catch {
          /* ignore */
        }
      }
    }
  } catch (err) {
    // Only this SUBSCRIPTION dies on abort/disconnect — the job itself keeps running on the
    // backend regardless. Report which, so the caller can reconnect after a network drop.
    return err instanceof DOMException && err.name === "AbortError" ? "aborted" : "network";
  }
  return handlers.signal?.aborted ? "aborted" : "ended";
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
          if (evt.error) handlers.onError(evt.error, false);
          else if (evt.done) handlers.onDone(evt.usage ?? null);
          else if (evt.thinking) handlers.onThinking?.(evt.thinking);
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
  // `repository` scopes the blast radius to the project actually being changed. Without it the
  // backend matched the description against every loaded repository at once, including Codexa's
  // own source — a new empty repo returned a blast radius naming `backend/graph` and `Board`.
  impact: (description: string, repository?: string, maxDepth = 3) =>
    post<ImpactResult>("/agents/impact", { description, repository, max_depth: maxDepth }),
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
  createRepository: (name: string, description = "") =>
    post<RepositoryInfo>("/repository/create", { name, description }),
  listRepositories: () => get<RepoListing[]>("/repository/list"),
  activateRepository: (name: string) =>
    post<RepositoryInfo>(`/repository/activate?name=${encodeURIComponent(name)}`, {}),
  deleteRepository: (name: string) =>
    del<{ name: string; nodes_removed: number; memories_removed: number; deleted_from_disk: boolean }>(
      `/repository/${encodeURIComponent(name)}`,
    ),
  fileTree: (repository: string) =>
    get<FileTreeNode[]>(`/files/tree?repository=${encodeURIComponent(repository)}`),
  fileRead: (repository: string, path: string) =>
    get<FileContent>(`/files/read?repository=${encodeURIComponent(repository)}&path=${encodeURIComponent(path)}`),
  fileSearch: (repository: string, q: string) =>
    get<FileSearchHit[]>(`/files/search?repository=${encodeURIComponent(repository)}&q=${encodeURIComponent(q)}`),
  /** The Codebase editor's save: 409 if the file changed on disk since `baseSha` was read. */
  saveFile: (repository: string, path: string, content: string, baseSha: string | null, force = false) =>
    post<{ ok: boolean; path: string; sha: string }>("/files/save", { repository, path, content, base_sha: baseSha, force }),
  repoDocs: (repository: string) =>
    get<RepoDocs>(`/repository/docs?repository=${encodeURIComponent(repository)}`),
  regenerateRepoDocs: (repository: string) =>
    post<RepoDocs>(`/repository/docs/regenerate?repository=${encodeURIComponent(repository)}`, {}),
  events: (limit = 120) => get<EventRecord[]>(`/observability/events?limit=${limit}`),
  snapshots: () => get<SnapshotMarker[]>("/observability/snapshots"),
  agents: () => get<{ agents: AgentNode[] }>("/observability/agents"),
  planGoal: (repository: string, goal: string, model?: string | null) =>
    post<PlanResult>("/agents/planner/plan", { repository, goal, model: model ?? null }),
  proposeChange: (repository: string, objective: string, filePaths: string[], model?: string | null) =>
    post<ProposeChangeResult>("/agents/coder/propose", {
      repository, objective, file_paths: filePaths, model: model ?? null,
    }),
  askResearch: (repository: string, query: string, model?: string | null) =>
    post<ResearchAskResult>("/agents/research/ask", { repository, query, model: model ?? null }),
  runQuorum: (repository: string, query: string) =>
    post<QuorumRunResult>("/agents/quorum/run", { repository, query }),
  usageSummary: (days?: number) =>
    get<UsageSummary>(`/observability/usage${days ? `?days=${days}` : ""}`),
  usageRecords: (limit = 100, days?: number) =>
    get<UsageRecord[]>(`/observability/usage/records?limit=${limit}${days ? `&days=${days}` : ""}`),
  usageDaily: (days = 30) => get<UsageDailyBucket[]>(`/observability/usage/daily?days=${days}`),
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
