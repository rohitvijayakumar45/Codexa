"use client";

import { useEffect, useState } from "react";
import { Rail } from "./Rail";
import { ThemeToggle } from "./ThemeToggle";

type Theme = "paper" | "aurora";
const STORAGE_KEY = "codexa-theme";

/** Owns the workspace's hot-swappable theme. Two instruments, one component tree: flipping
    `data-theme` on this root re-skins every descendant through CSS variables alone (colors, fonts,
    shadows, the page ground) — no page re-renders, no duplicated logic, nothing to keep in sync. */
export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>("paper");

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "aurora" || stored === "paper") setTheme(stored);
  }, []);

  function toggle() {
    setTheme((prev) => {
      const next: Theme = prev === "paper" ? "aurora" : "paper";
      window.localStorage.setItem(STORAGE_KEY, next);
      return next;
    });
  }

  return (
    <div
      data-theme={theme === "aurora" ? "aurora" : undefined}
      // Re-asserted here, not just inherited from <body> — body's font-family already resolved
      // var(--font-sans) once at the root; a descendant redefining that variable needs its own
      // declaration to actually pick up the new value (inherited *computed* font-family won't).
      style={{ fontFamily: "var(--font-sans)" }}
      className="workspace-ambient relative flex h-[100dvh] overflow-hidden"
    >
      <Rail />
      {/* Fully opaque, unlike the Rail's glass-panel — this card carries real reading text (chat
          bubbles, the composer), so it can't let the ground bleed through and soften contrast. */}
      <main className="relative my-3 ml-3 mr-3 flex min-w-0 flex-1 flex-col overflow-hidden rounded-[26px] border border-line-strong/70 bg-panel shadow-[inset_0_1.5px_0_var(--panel-highlight),inset_0_-1px_0_var(--panel-shadow-tint),0_18px_40px_-16px_var(--panel-shadow-tint)]">
        {children}
      </main>
      <ThemeToggle theme={theme} onToggle={toggle} />
    </div>
  );
}
