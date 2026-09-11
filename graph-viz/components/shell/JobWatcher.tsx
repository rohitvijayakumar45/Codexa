"use client";

import { useEffect } from "react";
import { subscribeAgentJob } from "@/lib/api";
import { pathsFromToolArgs, useJobStore } from "@/lib/job-store";

/*
  Keeps the shared job state live on every route, not just /chat.

  The chat page fed the job store only while it was mounted, and cleared it when its subscription
  was aborted — so the moment you opened Strata to watch the agent work, the files it was touching
  (the agent halo) and the rail's status were wiped. This follows the running job from the shell
  instead: an independent replay-and-tail subscription (safe to run alongside the chat page's own),
  and it clears the store only when the job's stream actually ends.
*/
export function JobWatcher() {
  const jobId = useJobStore((s) => s.jobId);

  useEffect(() => {
    if (!jobId) return;
    const controller = new AbortController();
    const store = useJobStore.getState;
    const live = () => !controller.signal.aborted && store().jobId === jobId;
    (async () => {
      // Reconnect after a dropped connection (the job keeps running on the backend); give up after
      // a handful of tries rather than hammering a backend that is actually down.
      for (let attempt = 0; attempt < 6 && live(); attempt++) {
        if (attempt > 0) await new Promise((r) => setTimeout(r, 1500 * attempt));
        const end = await subscribeAgentJob(jobId, {
          signal: controller.signal,
          onDelta: () => {},
          onDone: () => {},
          onError: () => {},
          onStatus: (text) => {
            if (live()) store().setStatus(text);
          },
          onToolCall: ({ args }) => {
            if (live()) store().touch(pathsFromToolArgs(args));
          },
        });
        if (end === "ended") {
          // The backend closes the stream only when the job is finished (done, or stopped with an error).
          if (live()) store().stop();
          return;
        }
        if (end === "aborted") return;
      }
    })();
    return () => controller.abort();
  }, [jobId]);

  return null;
}
