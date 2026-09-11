"use client";

import { Moon, Sun } from "lucide-react";

export type Theme = "blueprint" | "noir";

/** Flips the workspace between the two instruments. Pure CSS-variable swap under the hood
    (`data-theme` on the shell root) - nothing re-renders page content, so switching is instant and
    never loses in-flight state.

    Lives in the rail, not floating over the page. It used to be a fixed pill at top-6 right-6, which
    sat on top of whatever each page put in its top-right corner (header buttons, the graph's node
    count, the docs Regenerate button); PageHeader even reserved padding just to dodge it. The rail is
    the one surface guaranteed never to hold page content, so nothing can end up underneath it. */
export function ThemeToggle({ theme, onToggle }: { theme: Theme; onToggle: () => void }) {
  const dark = theme === "noir";
  const next = dark ? "Blueprint" : "Noir";
  return (
    <button
      onClick={onToggle}
      aria-label={`Switch to the ${next} theme`}
      className="group relative grid h-11 w-11 place-items-center rounded-xl short:h-9 short:w-9 text-muted transition-colors duration-200 ease-out hover:bg-paper-sunk hover:text-ink active:scale-90"
    >
      {dark ? <Sun size={18} strokeWidth={1.75} /> : <Moon size={18} strokeWidth={1.75} />}
      <span className="pointer-events-none absolute left-[52px] z-30 flex translate-x-[-4px] items-center gap-2 whitespace-nowrap rounded-lg border border-line bg-panel px-2.5 py-1.5 text-xs font-medium text-ink opacity-0 shadow-md transition-all duration-200 ease-out group-hover:translate-x-0 group-hover:opacity-100">
        {next} theme
        <span className="status-line !tracking-[0.1em]">Theme</span>
      </span>
    </button>
  );
}
