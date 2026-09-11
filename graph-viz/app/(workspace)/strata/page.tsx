"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type GraphEdge, type GraphNode } from "@/lib/api";
import { useRepoStore } from "@/lib/repo-store";
import { useJobStore } from "@/lib/job-store";
import { PageHeader } from "@/components/shell/PageHeader";
import { CenteredEmpty, CenteredError, CenteredLoading } from "@/components/shell/States";
import { StrataView } from "@/components/strata/StrataView";
import { DAY, buildModel, edgeLive } from "@/lib/strata/model";
import { layoutStrata } from "@/lib/strata/layout";

/*
  Strata — the knowledge graph as a layered map you read, not a cloud you orbit. Intent above, code
  in request order through the middle, signals below. This page owns the data; StrataView owns the
  interaction. The older 3D graph stays at /graph.
*/
export default function StrataPage() {
  const activeRepo = useRepoStore((s) => s.activeRepo);
  const timelineQ = useQuery({ queryKey: ["timeline"], queryFn: api.timeline });
  const nodesQ = useQuery({ queryKey: ["nodes", activeRepo], queryFn: () => api.nodes(activeRepo) });
  const edgesQ = useQuery({ queryKey: ["edges", "all", activeRepo], queryFn: () => api.allEdges(activeRepo) });

  const isLoading = timelineQ.isLoading || nodesQ.isLoading || edgesQ.isLoading;
  const error = timelineQ.error ?? nodesQ.error ?? edgesQ.error;
  const nodes = nodesQ.data ?? [];

  let body: React.ReactNode;
  if (isLoading) body = <CenteredLoading label="Laying out the strata" />;
  else if (error)
    body = (
      <CenteredError
        message={(error as Error).message}
        onRetry={() => {
          nodesQ.refetch();
          edgesQ.refetch();
          timelineQ.refetch();
        }}
      />
    );
  else if (nodes.length === 0)
    body = (
      <CenteredEmpty title="The graph is empty">
        Index a repository, or start the API with <span className="num">CODEXA_SEED=1</span> to load the seeded graph.
      </CenteredEmpty>
    );
  else
    body = (
      <StrataScreen
        nodes={nodes}
        edges={edgesQ.data ?? []}
        startsAt={timelineQ.data?.starts_at ?? null}
        endsAt={timelineQ.data?.ends_at ?? null}
      />
    );

  return (
    <div className="flex h-full flex-col">
      <PageHeader eyebrow="Engineering brain" title="Strata">
        {nodes.length ? (
          <span className="num text-sm text-muted">
            {activeRepo} · {nodes.length} nodes · {(edgesQ.data ?? []).length} edges
          </span>
        ) : null}
      </PageHeader>
      {body}
    </div>
  );
}

function StrataScreen({
  nodes,
  edges,
  startsAt,
  endsAt,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  startsAt: string | null;
  endsAt: string | null;
}) {
  const jobId = useJobStore((s) => s.jobId);
  const touched = useJobStore((s) => s.touched);
  const status = useJobStore((s) => s.status);

  // The scrubber spans THIS repository's own history (its earliest edge, e.g. its first commit) up
  // to now — not the global timeline, which another repository's history would stretch.
  const { startMs, endMs } = useMemo(() => {
    const from = edges.map((e) => Date.parse(e.valid_from)).filter(Number.isFinite);
    let end = endsAt ? Date.parse(endsAt) : NaN;
    if (!Number.isFinite(end)) end = Math.max(...from, ...nodes.map((n) => Date.parse(n.created_at)));
    let start = from.length ? Math.min(...from) : startsAt ? Date.parse(startsAt) : NaN;
    if (!Number.isFinite(start) || end - start < DAY) start = end - 30 * DAY;
    return { startMs: start, endMs: end };
  }, [nodes, edges, startsAt, endsAt]);

  const model = useMemo(() => buildModel(nodes, edges, endMs), [nodes, edges, endMs]);
  const layout = useMemo(() => layoutStrata(model, endMs), [model, endMs]);

  // Files the running job touched, and the symbols defined in them.
  const agentIds = useMemo(() => {
    const ids = new Set<string>();
    if (!jobId || touched.length === 0) return ids;
    const norm = (p: string) => p.replace(/\\/g, "/").replace(/^\.?\//, "");
    const hits = (path: string) =>
      touched.some((raw) => {
        const p = norm(raw);
        return p === path || path.endsWith(`/${p}`) || p.endsWith(`/${path}`);
      });
    for (const n of model.nodes) if (n.type === "File" && !n.hull && n.path && hits(n.path)) ids.add(n.id);
    for (const n of model.nodes) if (n.def && ids.has(n.def.fileId)) ids.add(n.id);
    return ids;
  }, [jobId, touched, model]);

  // Remount the view when the graph itself changes, so positions and selection start clean.
  const key = useMemo(
    () => `${model.nodes.length}:${model.edges.length}:${model.edges.filter((e) => edgeLive(e, endMs)).length}`,
    [model, endMs],
  );

  return (
    <StrataView
      key={key}
      model={model}
      layout={layout}
      startMs={startMs}
      endMs={endMs}
      agentIds={agentIds}
      agentStatus={jobId ? status : ""}
    />
  );
}
