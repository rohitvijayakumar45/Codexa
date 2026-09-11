"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { DAY, type SEdge } from "@/lib/strata/model";

/** Scrubber with an edge-activity histogram: bars are edges that became valid in each bin, the ticks
    under the baseline are edges that expired. */
export function StrataTimeBar({
  startMs,
  endMs,
  t,
  edges,
  liveNodes,
  liveEdges,
  onChange,
}: {
  startMs: number;
  endMs: number;
  t: number;
  edges: SEdge[];
  liveNodes: number;
  liveEdges: number;
  onChange: (t: number) => void;
}) {
  const total = Math.max(1, Math.round((endMs - startMs) / DAY));
  const daysAgo = Math.max(0, Math.round((endMs - t) / DAY));
  const span = Math.max(1, endMs - startMs);
  const [playing, setPlaying] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const { bins, max, ends } = useMemo(() => {
    const b = new Array(30).fill(0) as number[];
    for (const e of edges) b[Math.max(0, Math.min(29, Math.floor(((e.vf - startMs) / span) * 30)))]++;
    return {
      bins: b,
      max: Math.max(1, ...b),
      ends: edges.filter((e) => e.vt !== null && e.vt >= startMs && e.vt <= endMs).map((e) => ((e.vt! - startMs) / span) * 900),
    };
  }, [edges, startMs, endMs, span]);

  useEffect(() => {
    const ref = timer;
    return () => {
      if (ref.current) clearInterval(ref.current);
    };
  }, []);

  function stop() {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    setPlaying(false);
  }

  function play() {
    if (timer.current) return stop();
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let d = total;
    onChange(endMs - d * DAY);
    setPlaying(true);
    timer.current = setInterval(
      () => {
        d -= reduce ? 10 : 1;
        if (d <= 0) {
          onChange(endMs);
          stop();
          return;
        }
        onChange(endMs - d * DAY);
      },
      reduce ? 450 : 70,
    );
  }

  const cursor = ((t - startMs) / span) * 900;

  return (
    <div className="time">
      <button className="play" onClick={play} aria-label={playing ? "Stop replay" : `Replay the last ${total} days`}>
        {playing ? (
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden>
            <rect x="2" y="2" width="8" height="8" rx="1.5" fill="currentColor" />
          </svg>
        ) : (
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden>
            <path d="M2.5 1.5l8 4.5-8 4.5z" fill="currentColor" />
          </svg>
        )}
      </button>
      <div className="track">
        <svg viewBox="0 0 900 34" preserveAspectRatio="none" aria-hidden>
          {bins.map((v, i) =>
            v ? (
              <rect
                key={i}
                x={i * 30 + 4}
                y={30 - (v / max) * 26}
                width={22}
                height={(v / max) * 26}
                rx={2}
                style={{ fill: i * 30 <= cursor ? "var(--ink-soft)" : "var(--line-strong)" }}
              />
            ) : null,
          )}
          {ends.map((x, i) => (
            <rect key={`e${i}`} x={x - 1} y={30} width={2} height={4} style={{ fill: "var(--faint)" }} />
          ))}
          <line x1={0} x2={900} y1={30.5} y2={30.5} style={{ stroke: "var(--line)" }} />
          <line x1={cursor} x2={cursor} y1={0} y2={34} style={{ stroke: "var(--ink)", strokeWidth: 2 }} />
        </svg>
        <input
          type="range"
          min={0}
          max={total}
          step={1}
          value={total - daysAgo}
          onChange={(e) => {
            stop();
            const d = total - Number(e.target.value);
            onChange(d === 0 ? endMs : endMs - d * DAY);
          }}
          aria-label="Viewed date, days before today"
        />
        <div className="ends">
          <span>{total} days ago</span>
          <span>{Math.round(total / 2)}</span>
          <span>today</span>
        </div>
      </div>
      <div className="readout">
        <b>{daysAgo === 0 ? "Today" : daysAgo === 1 ? "1 day ago" : `${daysAgo} days ago`}</b>
        {liveNodes} nodes · {liveEdges} live edges
      </div>
    </div>
  );
}
