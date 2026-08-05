"use client";

import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Search, RefreshCw } from "lucide-react";
import { api, type EndpointDoc, type ModelDoc } from "@/lib/api";
import { useRepoStore } from "@/lib/repo-store";
import { PageHeader } from "@/components/shell/PageHeader";
import { CenteredError, CenteredLoading } from "@/components/shell/States";
import { EASE_OUT } from "@/components/ui/primitives";
import { MarkdownView } from "@/components/ui/MarkdownView";

// The Documentation tab reflects the active repository: the platform itself is documented from its
// live API surface; a loaded repo is documented from its real files (LLM-grounded).
export default function DocsPage() {
  const activeRepo = useRepoStore((s) => s.activeRepo);
  return activeRepo === "codexa-os" ? <ApiDocsView /> : <RepoDocsView repository={activeRepo} />;
}

function RepoDocsView({ repository }: { repository: string }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["repo-docs", repository], queryFn: () => api.repoDocs(repository) });
  const regen = useMutation({
    mutationFn: () => api.regenerateRepoDocs(repository),
    onSuccess: (data) => qc.setQueryData(["repo-docs", repository], data),
  });

  return (
    <div className="flex h-full flex-col">
      <PageHeader eyebrow={`Repository · ${repository}`} title="Documentation">
        {q.data && (
          <span className="status-line hidden sm:inline">
            generated {new Date(q.data.generated_at).toLocaleTimeString()}
          </span>
        )}
        <button
          onClick={() => regen.mutate()}
          disabled={regen.isPending}
          className="flex items-center gap-2 rounded-lg border border-line-strong px-3 py-1.5 text-xs font-medium text-ink-soft transition-colors hover:bg-paper-sunk disabled:opacity-50"
        >
          <RefreshCw size={13} className={regen.isPending ? "animate-spin" : ""} />
          Regenerate
        </button>
      </PageHeader>
      {q.isLoading || regen.isPending ? (
        <CenteredLoading label="Generating documentation from the codebase" />
      ) : q.error ? (
        <CenteredError message={(q.error as Error).message} onRetry={() => q.refetch()} />
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto px-10 py-8">
          <motion.div
            key={q.data?.generated_at}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, ease: EASE_OUT }}
            className="mx-auto max-w-2xl"
          >
            <MarkdownView markdown={q.data?.markdown ?? ""} />
          </motion.div>
        </div>
      )}
    </div>
  );
}

const METHOD_COLOR: Record<string, string> = {
  GET: "text-signal",
  POST: "text-gold",
  PUT: "text-gold",
  DELETE: "text-danger",
};

function ApiDocsView() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["docs"], queryFn: api.docs });
  const regen = useMutation({
    mutationFn: () => api.regenerateDocs(true),
    onSuccess: (data) => qc.setQueryData(["docs"], data),
  });

  const [section, setSection] = useState("overview");
  const [query, setQuery] = useState("");

  const docs = q.data;
  const filtered = useMemo(() => {
    if (!docs || !query.trim()) return docs;
    const needle = query.toLowerCase();
    return {
      ...docs,
      groups: docs.groups
        .map((g) => ({
          ...g,
          endpoints: g.endpoints.filter(
            (e) => e.path.toLowerCase().includes(needle) || (e.summary ?? "").toLowerCase().includes(needle),
          ),
        }))
        .filter((g) => g.endpoints.length > 0),
      models: docs.models.filter((m) => m.name.toLowerCase().includes(needle)),
    };
  }, [docs, query]);

  if (q.isLoading)
    return (
      <div className="flex h-full flex-col">
        <PageHeader eyebrow="Reference" title="Documentation" />
        <CenteredLoading label="Generating documentation" />
      </div>
    );
  if (q.error || !docs || !filtered)
    return (
      <div className="flex h-full flex-col">
        <PageHeader eyebrow="Reference" title="Documentation" />
        <CenteredError message={(q.error as Error)?.message ?? "No docs"} onRetry={() => q.refetch()} />
      </div>
    );

  return (
    <div className="flex h-full flex-col">
      <PageHeader eyebrow="Reference" title="Documentation">
        <span className="status-line hidden sm:inline">
          generated {new Date(docs.generated_at).toLocaleTimeString()}
        </span>
        <button
          onClick={() => regen.mutate()}
          disabled={regen.isPending}
          className="flex items-center gap-2 rounded-lg border border-line-strong px-3 py-1.5 text-xs font-medium text-ink-soft transition-colors hover:bg-paper-sunk disabled:opacity-50"
        >
          <RefreshCw size={13} className={regen.isPending ? "animate-spin" : ""} />
          Regenerate
        </button>
      </PageHeader>

      <div className="grid min-h-0 flex-1 grid-cols-[220px_1fr] overflow-hidden">
        <nav className="overflow-y-auto border-r border-line bg-panel-2 px-3 py-5">
          <div className="relative mb-4">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search"
              className="w-full rounded-lg border border-line bg-panel py-1.5 pl-8 pr-2 text-xs text-ink outline-none placeholder:text-faint focus:border-ink/30"
            />
          </div>
          <NavItem id="overview" label="Overview" active={section === "overview"} onClick={setSection} />
          <p className="status-line mt-4 px-2">Endpoints</p>
          {filtered.groups.map((g) => (
            <NavItem key={g.tag} id={`g-${g.tag}`} label={g.tag} active={section === `g-${g.tag}`} onClick={setSection} count={g.endpoints.length} />
          ))}
          <p className="status-line mt-4 px-2">Data models</p>
          <NavItem id="models" label={`${filtered.models.length} models`} active={section === "models"} onClick={setSection} />
        </nav>

        <div className="min-h-0 overflow-y-auto px-10 py-8">
          <motion.div
            key={section + query}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, ease: EASE_OUT }}
            className="mx-auto max-w-3xl"
          >
            {section === "overview" && (
              <article>
                <h2 className="display text-2xl font-semibold text-ink">Codexa OS</h2>
                <p className="mt-4 text-[15px] leading-relaxed text-ink-soft">{docs.overview}</p>
              </article>
            )}

            {section.startsWith("g-") && (
              <EndpointGroup
                tag={section.slice(2)}
                endpoints={filtered.groups.find((g) => g.tag === section.slice(2))?.endpoints ?? []}
              />
            )}

            {section === "models" && (
              <div className="space-y-8">
                {filtered.models.map((m) => (
                  <ModelBlock key={m.name} model={m} />
                ))}
              </div>
            )}
          </motion.div>
        </div>
      </div>
    </div>
  );
}

function NavItem({
  id,
  label,
  active,
  onClick,
  count,
}: {
  id: string;
  label: string;
  active: boolean;
  onClick: (id: string) => void;
  count?: number;
}) {
  return (
    <button
      onClick={() => onClick(id)}
      className={`flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left text-sm capitalize transition-colors ${
        active ? "bg-signal-wash font-medium text-signal" : "text-ink-soft hover:bg-paper-sunk"
      }`}
    >
      {label}
      {count != null && <span className="num text-[10px] text-faint">{count}</span>}
    </button>
  );
}

function EndpointGroup({ tag, endpoints }: { tag: string; endpoints: EndpointDoc[] }) {
  return (
    <div>
      <h2 className="display text-2xl font-semibold capitalize text-ink">{tag}</h2>
      <div className="mt-6 divide-y divide-line">
        {endpoints.map((e) => (
          <div key={`${e.method}-${e.path}`} className="py-4">
            <div className="flex items-center gap-3">
              <span className={`num text-xs font-medium ${METHOD_COLOR[e.method] ?? "text-muted"}`}>{e.method}</span>
              <code className="num text-sm text-ink">{e.path}</code>
            </div>
            {e.summary && <p className="mt-1.5 text-sm text-muted">{e.summary}</p>}
            {(e.request_model || e.response_model) && (
              <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1">
                {e.request_model && (
                  <span className="status-line">
                    body <span className="!normal-case text-ink-soft">{e.request_model}</span>
                  </span>
                )}
                {e.response_model && (
                  <span className="status-line">
                    returns <span className="!normal-case text-ink-soft">{e.response_model}</span>
                  </span>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function ModelBlock({ model }: { model: ModelDoc }) {
  return (
    <div>
      <h3 className="display text-lg font-semibold text-ink">{model.name}</h3>
      <div className="mt-3 overflow-hidden rounded-lg border border-line">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-line bg-panel-2">
              <th className="status-line px-3 py-2 font-normal">Field</th>
              <th className="status-line px-3 py-2 font-normal">Type</th>
              <th className="status-line px-3 py-2 font-normal">Required</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {model.fields.map((f) => (
              <tr key={f.name}>
                <td className="num px-3 py-2 text-ink">{f.name}</td>
                <td className="num px-3 py-2 text-muted">{f.type}</td>
                <td className="px-3 py-2 text-xs text-faint">{f.required ? "yes" : "optional"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
