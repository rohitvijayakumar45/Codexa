"use client";

import { Moon, Sun } from "lucide-react";

type Theme = "paper" | "aurora";

/** Floating pill that flips the workspace between the two hot-swappable instruments. Pure CSS
    variable swap under the hood (`data-theme` on the shell root) — nothing here re-renders any
    page content, so switching is instant and never loses in-flight state. */
export function ThemeToggle({ theme, onToggle }: { theme: Theme; onToggle: () => void }) {
  const aurora = theme === "aurora";
  return (
    <button
      onClick={onToggle}
      aria-label={aurora ? "Switch to the Paper theme" : "Switch to the Aurora theme"}
      className="glass-panel fixed right-6 top-6 z-40 flex h-10 items-center gap-2 rounded-full px-4 text-xs font-medium text-ink-soft transition-transform duration-200 ease-out hover:scale-105 active:scale-95"
    >
      {aurora ? <Sun size={14} className="text-signal" /> : <Moon size={14} className="text-signal" />}
      {aurora ? "Paper" : "Aurora"}
    </button>
  );
}
