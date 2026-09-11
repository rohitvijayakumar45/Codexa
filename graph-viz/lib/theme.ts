"use client";

import { useSyncExternalStore } from "react";

/*
  The workspace theme, readable from anywhere.

  WorkspaceShell flips `data-theme="noir"` on its root; CSS re-skins everything through variables.
  Things CSS can't reach — a WebGL scene, an SVG filter colour — need the resolved values instead,
  so this subscribes to that attribute and lets them re-read the variables when it changes.
*/

export type ThemeName = "blueprint" | "noir";

function current(): ThemeName {
  return document.querySelector('[data-theme="noir"]') ? "noir" : "blueprint";
}

function subscribe(onChange: () => void) {
  const mo = new MutationObserver(onChange);
  mo.observe(document.body, { attributes: true, attributeFilter: ["data-theme"], subtree: true });
  return () => mo.disconnect();
}

export function useWorkspaceTheme(): ThemeName {
  return useSyncExternalStore(subscribe, current, () => "blueprint");
}

/** Resolved value of a theme variable for the given theme (e.g. "--color-signal" -> "#c2415a"). */
export function readCssVar(name: string, theme: ThemeName): string {
  if (typeof document === "undefined") return "";
  const el = (theme === "noir" && document.querySelector('[data-theme="noir"]')) || document.documentElement;
  return getComputedStyle(el).getPropertyValue(name).trim();
}
