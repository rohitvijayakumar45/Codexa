import { create } from "zustand";

/*
  What the running job is doing, hoisted out of the chat page so every route can see it.

  Before this, a job's liveness was local state inside /chat: navigate to the graph or the codebase
  while a 120-round build was running and the workspace looked completely idle. For a platform whose
  whole value is unattended execution, "is it still working, and on what" is the one fact that
  should never go out of view.
*/
export interface JobState {
  /** Null when nothing is running. */
  jobId: string | null;
  /** Latest human-readable status from the backend's status events ("Writing app.py"). */
  status: string;
  /** Task objective currently being executed, when a plan is active. */
  task: string;
  /** Wall-clock second the current status arrived, for the idle readout. */
  since: number;
  /** Repo-relative paths the running job has read or written, newest last. Strata haloes these —
      the one place the graph uses the signal colour. */
  touched: string[];
  start: (jobId: string) => void;
  setStatus: (status: string) => void;
  setTask: (task: string) => void;
  touch: (paths: string[]) => void;
  stop: () => void;
}

export const useJobStore = create<JobState>((set) => ({
  jobId: null,
  status: "",
  task: "",
  since: Date.now(),
  touched: [],
  start: (jobId) => set({ jobId, status: "Starting", task: "", since: Date.now(), touched: [] }),
  // `since` resets on every status change, so the rail's counter measures time on the CURRENT step
  // rather than total job age — the number that actually tells you whether something is wedged.
  setStatus: (status) => set({ status, since: Date.now() }),
  setTask: (task) => set({ task }),
  touch: (paths) =>
    set((s) => {
      const fresh = paths.filter((p) => p && !s.touched.includes(p));
      return fresh.length ? { touched: [...s.touched, ...fresh].slice(-200) } : s;
    }),
  stop: () => set({ jobId: null, status: "", task: "", touched: [] }),
}));

/** File paths a tool call names: `path`, `paths[]`, or `files[]` (strings or `{path}` objects). */
export function pathsFromToolArgs(args: Record<string, unknown>): string[] {
  const out: string[] = [];
  const add = (v: unknown) => {
    if (typeof v === "string" && v.trim() && /\.[a-z0-9]+$/i.test(v.trim())) out.push(v.trim().replace(/^\.?\//, ""));
    else if (v && typeof v === "object" && typeof (v as { path?: unknown }).path === "string") add((v as { path: string }).path);
  };
  add(args.path);
  add(args.file_path);
  for (const key of ["paths", "files"]) if (Array.isArray(args[key])) (args[key] as unknown[]).forEach(add);
  return out;
}
