"use client";

import { useSyncExternalStore } from "react";
import { Rail } from "./Rail";
import { JobWatcher } from "./JobWatcher";

type Theme = "blueprint" | "noir";
const STORAGE_KEY = "codexa-theme";
const CHANGE_EVENT = "codexa-theme-change";

// The stored theme is external state, so it is read through a subscription rather than copied into
// component state from an effect. The server (and the first client render) sees Blueprint; React then
// re-renders with the stored value without a hydration mismatch. The `storage` event also keeps
// every open tab on the same theme.
function readTheme(): Theme {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "noir" ? "noir" : "blueprint";
  } catch {
    return "blueprint";
  }
}

function subscribe(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(CHANGE_EVENT, onChange);
  };
}

/** Owns the workspace's hot-swappable theme. Two instruments, one component tree: flipping
    `data-theme` on this root re-skins every descendant through CSS variables alone (colors, fonts,
    shadows, the page ground) — no page re-renders, no duplicated logic, nothing to keep in sync. */
export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const theme = useSyncExternalStore<Theme>(subscribe, readTheme, () => "blueprint");

  function toggle() {
    const next: Theme = theme === "blueprint" ? "noir" : "blueprint";
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Storage unavailable (private mode, blocked site data): the event below still flips this tab.
    }
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }

  return (
    <div
      data-theme={theme === "noir" ? "noir" : undefined}
      // Re-asserted here, not just inherited from <body> — body's font-family already resolved
      // var(--font-sans) once at the root; a descendant redefining that variable needs its own
      // declaration to actually pick up the new value (inherited *computed* font-family won't).
      style={{ fontFamily: "var(--font-sans)" }}
      className="workspace-ambient relative flex h-[100dvh] overflow-hidden"
    >
      <JobWatcher />
      <Rail theme={theme} onToggleTheme={toggle} />
      {/* Fully opaque, unlike the Rail's glass-panel — this card carries real reading text (chat
          bubbles, the composer), so it can't let the ground bleed through and soften contrast. */}
      <main className="relative my-3 ml-3 mr-3 flex min-w-0 flex-1 flex-col overflow-hidden rounded-[26px] border border-line-strong/70 bg-panel shadow-[inset_0_1.5px_0_var(--panel-highlight),inset_0_-1px_0_var(--panel-shadow-tint),0_18px_40px_-16px_var(--panel-shadow-tint)]">
        {children}
      </main>
    </div>
  );
}
