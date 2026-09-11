"use client";

import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import type { GraphEdge, GraphNode } from "@/lib/api";
import { EDGE_LABEL, NODE_STYLE, SOURCE_LABEL, nodeLabel, typeColorCss } from "@/lib/graph-visual";

interface Props {
  node: GraphNode | null;
  edges: GraphEdge[];
  nodesById: Map<string, GraphNode>;
  onClose: () => void;
}

export function Inspector({ node, edges, nodesById, onClose }: Props) {
  return (
    <AnimatePresence>
      {node && (
        <motion.aside
          key={node.id}
          initial={{ x: 24, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 24, opacity: 0 }}
          transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
          className="absolute right-4 top-4 z-20 flex max-h-[calc(100%-2rem)] w-80 flex-col overflow-hidden rounded-xl border border-line bg-panel/95 shadow-lg backdrop-blur-sm"
        >
          <header className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ background: typeColorCss(node.node_type) }}
                  aria-hidden
                />
                <span className="text-[11px] font-medium uppercase tracking-wide text-muted">
                  {NODE_STYLE[node.node_type].label}
                </span>
              </div>
              <h2 className="display mt-1 truncate text-[15px] font-semibold text-ink" title={nodeLabel(node.properties, node.stable_id)}>
                {nodeLabel(node.properties, node.stable_id)}
              </h2>
            </div>
            <button
              onClick={onClose}
              className="grid h-7 w-7 shrink-0 place-items-center rounded-md text-muted transition-colors hover:bg-paper-sunk hover:text-ink"
              aria-label="Close inspector"
            >
              <X size={15} />
            </button>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
            <dl className="space-y-2 text-xs">
              <Row label="Stable id" value={node.stable_id} mono />
              <Row label="Created" value={new Date(node.created_at).toLocaleString()} mono />
              {Object.entries(node.properties)
                .filter(([, v]) => typeof v !== "object")
                .slice(0, 6)
                .map(([k, v]) => (
                  <Row key={k} label={k.replace(/_/g, " ")} value={String(v)} />
                ))}
            </dl>

            <h3 className="mb-2 mt-5 text-[11px] font-medium uppercase tracking-wide text-muted">
              Relationships
            </h3>
            {edges.length === 0 ? (
              <p className="text-xs text-muted">No edges at the current point in time.</p>
            ) : (
              <ul className="space-y-1.5">
                {edges.map((e) => {
                  const outgoing = e.from_node_id === node.id;
                  const otherId = outgoing ? e.to_node_id : e.from_node_id;
                  const other = nodesById.get(otherId);
                  return (
                    <li
                      key={e.id}
                      className="rounded-lg border border-line bg-paper px-2.5 py-2 text-xs"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium text-signal">
                          {outgoing ? EDGE_LABEL[e.edge_type] : `is ${EDGE_LABEL[e.edge_type]} by`}
                        </span>
                        <span className="num text-[11px] text-muted" title="confidence">
                          {e.confidence.toFixed(2)}
                        </span>
                      </div>
                      <div className="mt-0.5 truncate text-ink-soft">
                        {other ? nodeLabel(other.properties, other.stable_id) : "unknown node"}
                      </div>
                      <div className="mt-0.5 text-[10.5px] text-faint">
                        {SOURCE_LABEL[e.source_type]}
                        {e.valid_to ? " · superseded" : ""}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex gap-2">
      <dt className="w-24 shrink-0 text-faint">{label}</dt>
      <dd className={`min-w-0 flex-1 break-words text-ink-soft ${mono ? "num text-[11px]" : ""}`}>
        {value}
      </dd>
    </div>
  );
}
