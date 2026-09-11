"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Search } from "lucide-react";
import type { GraphNode } from "@/lib/api";
import { NODE_STYLE, nodeLabel, typeColorCss } from "@/lib/graph-visual";

// Search the graph by function / file / node name. Selecting a result focuses that node (the scene
// eases the camera to it). Press "/" anywhere to focus the box.
export function GraphSearch({
  nodes,
  onSelect,
}: {
  nodes: GraphNode[];
  onSelect: (id: string) => void;
}) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (document.activeElement?.tagName ?? "").toLowerCase();
      if (e.key === "/" && tag !== "input" && tag !== "textarea") {
        e.preventDefault();
        inputRef.current?.focus();
      } else if (e.key === "Escape") {
        inputRef.current?.blur();
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const results = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return [];
    return nodes
      .map((n) => ({ n, label: nodeLabel(n.properties, n.stable_id) }))
      .filter(
        (x) =>
          x.label.toLowerCase().includes(needle) ||
          String(x.n.properties.file ?? "").toLowerCase().includes(needle),
      )
      .slice(0, 8);
  }, [q, nodes]);

  return (
    <div className="absolute left-1/2 top-5 z-20 w-[340px] max-w-[calc(100%-2.5rem)] -translate-x-1/2">
      <label className="flex cursor-text items-center gap-2 rounded-xl border border-line bg-panel/95 px-3 py-2.5 shadow-sm backdrop-blur-md transition-colors focus-within:border-ink/30 hover:border-line-strong">
        <Search size={15} className="shrink-0 text-faint" />
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder="Search functions, files…"
          className="w-full bg-transparent text-sm text-ink outline-none placeholder:text-faint"
        />
        {!q && (
          <kbd className="shrink-0 rounded border border-line-strong bg-paper-sunk px-1.5 py-0.5 text-[11px] text-muted">
            /
          </kbd>
        )}
      </label>

      {open && q.trim() && (
        <div className="mt-1.5 overflow-hidden rounded-xl border border-line bg-panel p-1 shadow-lg">
          {results.length === 0 ? (
            <p className="px-2.5 py-2 text-xs text-faint">No matches.</p>
          ) : (
            results.map(({ n, label }) => (
              <button
                key={n.id}
                onMouseDown={(e) => {
                  e.preventDefault();
                  onSelect(n.id);
                  setOpen(false);
                }}
                className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left transition-colors hover:bg-paper-sunk"
              >
                <span
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ background: typeColorCss(n.node_type) }}
                />
                <span className="min-w-0 flex-1 truncate text-[13px] text-ink">{label}</span>
                <span className="status-line shrink-0">{NODE_STYLE[n.node_type].label}</span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
