"use client";

import { useId, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, Ban, Check, ChevronDown } from "lucide-react";
import type { PlanSnapshot, PlanTask, PlanTaskStatus } from "@/lib/api";
import { EASE_OUT } from "@/components/ui/primitives";

/*
  The execution plan, as the user sees it.

  This is the only window onto Codexa's own state machine (backend/agents/plan.py): which task is
  active, what has actually been verified on disk, and what remains. It deliberately shows execution
  state ONLY — never reasoning. The payload carries no chain of thought and none should be grafted
  in from the thinking stream; the whole point of the controller is that progress is judged from
  artifacts and exit codes rather than from the model's account of itself, and the card has to read
  the same way.
*/

// Row text weight per status. Completed work recedes rather than being struck through — the plan is
// a record of what happened, not a crossed-off shopping list.
const ROW_TEXT: Record<PlanTaskStatus, string> = {
  COMPLETED: "text-faint",
  IN_PROGRESS: "text-ink font-medium",
  PENDING: "text-muted",
  BLOCKED: "text-faint",
  FAILED: "text-warn",
};

function Marker({ status }: { status: PlanTaskStatus }) {
  if (status === "COMPLETED") return <Check size={12} className="text-signal" />;
  if (status === "FAILED") return <AlertTriangle size={12} className="text-warn" />;
  if (status === "BLOCKED") return <Ban size={11} className="text-faint" />;
  if (status === "IN_PROGRESS") {
    // The single animated element on the card. `animate-pulse` (not the .dot-pulse keyframes, which
    // globals.css deliberately exempts from the reduced-motion kill switch for the chat loaders) so
    // that prefers-reduced-motion actually stops it.
    return <span className="h-2 w-2 animate-pulse rounded-full bg-signal" />;
  }
  return <span className="h-2 w-2 rounded-full border border-line-strong" />;
}

function TaskRow({ task, active }: { task: PlanTask; active: boolean }) {
  const status = task.status;
  // `attempts` counts REJECTED completion claims, so one rejection means the task is now on its
  // second attempt. Surfacing it is the honest signal that Codexa refused a "done" and is retrying —
  // without it a task that silently loops looks identical to one making progress.
  const attempt = task.attempts > 0 ? task.attempts + 1 : 0;
  // Why the retry is happening, or why the task died. Shown for a hard failure, and for the active
  // task whose last check was rejected — those are the two moments the detail is load-bearing.
  const detail =
    status === "FAILED" || (active && task.validation_state === "FAILED") ? task.validation_detail : "";

  return (
    <li aria-current={active ? "step" : undefined} className="flex items-start gap-2.5">
      <span className="mt-1 grid h-4 w-4 shrink-0 place-items-center" aria-hidden="true">
        <Marker status={status} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <span className={`min-w-0 text-xs leading-relaxed ${ROW_TEXT[status]}`}>{task.objective}</span>
          {active && attempt > 0 && (
            <span className="num shrink-0 rounded-md border border-line bg-paper-sunk px-1.5 py-0.5 text-[10px] text-warn">
              attempt {attempt}
            </span>
          )}
          {status === "BLOCKED" && (
            <span className="num shrink-0 rounded-md border border-line bg-paper-sunk px-1.5 py-0.5 text-[10px] text-faint">
              blocked
            </span>
          )}
        </span>
        {detail && <span className="mt-0.5 block text-[11px] leading-relaxed text-warn">{detail}</span>}
      </span>
    </li>
  );
}

/** Live view of a job's execution plan. Renders nothing for a conversational turn — most turns have
 *  no plan, and that is the normal case rather than an empty state worth drawing. */
export function TaskPlanCard({ plan }: { plan: PlanSnapshot }) {
  // A finished plan collapses itself so a long run doesn't dominate scrollback; clicking either way
  // pins the user's choice from then on.
  const [override, setOverride] = useState<boolean | null>(null);
  const listId = useId();

  const tasks = plan?.tasks ?? [];
  const total = plan?.total ?? 0;
  const completed = plan?.completed ?? 0;
  if (!plan || total === 0 || tasks.length === 0) return null;

  const finished = completed >= total;
  const expanded = override ?? !finished;
  const active =
    tasks.find((t) => t.id === plan.current_task_id) ?? tasks.find((t) => t.status === "IN_PROGRESS");
  const lastProgress = active?.last_progress ?? "";
  const headline = plan.objective || "Execution plan";

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: EASE_OUT }}
      className="mb-3 ml-9 max-w-2xl overflow-hidden rounded-xl border border-line bg-panel-2"
    >
      <button
        type="button"
        onClick={() => setOverride(!expanded)}
        aria-expanded={expanded}
        aria-controls={listId}
        title={headline}
        className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left transition-colors hover:bg-paper-sunk"
      >
        {finished && <Check size={12} className="shrink-0 text-signal" />}
        <span className="status-line min-w-0 flex-1 truncate">{headline}</span>
        <span className="num shrink-0 text-[11px] text-muted">
          {completed}/{total}
        </span>
        <span className="sr-only">{expanded ? "Hide task list" : "Show task list"}</span>
        <ChevronDown
          size={12}
          className={`shrink-0 text-faint transition-transform ${expanded ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
      </button>

      {/* role="list" below is not redundant: Tailwind's preflight sets list-style:none, which
          strips list semantics from ol/ul in Safari + VoiceOver. */}
      {expanded && (
        <ol id={listId} role="list" className="space-y-2 border-t border-line px-3 py-2.5">
          {tasks.map((task) => (
            <TaskRow key={task.id} task={task} active={task.id === active?.id} />
          ))}
        </ol>
      )}

      {expanded && lastProgress && (
        <div
          role="status"
          className="flex items-baseline gap-2 border-t border-line px-3 py-2 text-[11px]"
        >
          <span className="status-line shrink-0">Last progress</span>
          <span className="min-w-0 flex-1 truncate text-muted">{lastProgress}</span>
        </div>
      )}
    </motion.div>
  );
}
