"use client";

import { useEffect, useMemo, useState } from "react";
import { codeToHtml } from "shiki";
import { codexaDark, codexaLight } from "@/lib/code-theme";
import { LANG } from "./CodeView";

/*
  A highlighted code editor without a dependency: a transparent <textarea> laid exactly over the
  same Shiki highlighting the read-only view uses. Both layers share one font, one line height, one
  padding and `white-space: pre`, so every character sits on the glyph drawn beneath it.

  Highlighting re-runs a moment after typing pauses. Until it has caught up, the textarea draws its
  own plain text and the stale highlight is hidden — a lagging colour layer must never show text
  that is no longer there.
*/

const INDENT = "  ";
export const EDITOR_LINE_PX = 20;

export function CodeEditor({
  value,
  language,
  onChange,
  onSave,
}: {
  value: string;
  language: string;
  onChange: (next: string) => void;
  onSave: () => void;
}) {
  const [hl, setHl] = useState<{ source: string; html: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(
      () => {
        codeToHtml(value, {
          lang: LANG[language] ?? "text",
          themes: { light: codexaLight, dark: codexaDark },
          defaultColor: false,
        })
          .then((html) => {
            if (!cancelled) setHl({ source: value, html: html.match(/<code>([\s\S]*)<\/code>/)?.[1] ?? "" });
          })
          .catch(() => {
            if (!cancelled) setHl(null);
          });
      },
      value.length > 150_000 ? 500 : 140,
    );
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [value, language]);

  const fresh = hl !== null && hl.source === value;
  const lines = useMemo(() => value.split("\n"), [value]);
  const widest = useMemo(() => lines.reduce((m, l) => Math.max(m, l.replace(/\t/g, INDENT).length), 0), [lines]);

  /** Replace [start, end) with `text` through the browser's editing command, so Ctrl+Z still works;
      falls back to setRangeText where that command is unavailable. */
  function replace(ta: HTMLTextAreaElement, text: string, start: number, end: number, select?: [number, number]) {
    ta.focus();
    ta.setSelectionRange(start, end);
    const ok = text ? document.execCommand("insertText", false, text) : document.execCommand("delete");
    if (!ok) {
      ta.setRangeText(text, start, end, "end");
      onChange(ta.value);
    }
    if (select) ta.setSelectionRange(select[0], select[1]);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    const ta = e.currentTarget;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      onSave();
      return;
    }
    if (e.key === "Escape") {
      // Leaves the editor so Tab can move focus on through the page again.
      ta.blur();
      return;
    }
    const { selectionStart: s, selectionEnd: end, value: v } = ta;
    const lineStart = v.lastIndexOf("\n", s - 1) + 1;
    if (e.key === "Tab") {
      e.preventDefault();
      if (e.shiftKey) {
        const block = v.slice(lineStart, Math.max(end, lineStart));
        const out = block.replace(/^( {1,2}|\t)/gm, "");
        if (out !== block) replace(ta, out, lineStart, lineStart + block.length, [lineStart, lineStart + out.length]);
      } else if (s === end) {
        replace(ta, INDENT, s, end);
      } else {
        const block = v.slice(lineStart, end);
        const out = block.replace(/^/gm, INDENT);
        replace(ta, out, lineStart, end, [lineStart, lineStart + out.length]);
      }
      return;
    }
    if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const indent = v.slice(lineStart, s).match(/^[ \t]*/)?.[0] ?? "";
      if (indent) {
        e.preventDefault();
        replace(ta, `\n${indent}`, s, end);
      }
    }
  }

  return (
    <div className="code-editor">
      <div className="ce-gutter" aria-hidden="true">
        {lines.map((_, i) => (
          <div key={i}>{i + 1}</div>
        ))}
      </div>
      <div className="ce-body" style={{ width: `calc(${widest + 6}ch + 2rem)`, minHeight: lines.length * EDITOR_LINE_PX + 24 }}>
        <pre
          className={`ce-hl${fresh ? "" : " stale"}`}
          aria-hidden="true"
          dangerouslySetInnerHTML={{ __html: fresh ? (hl?.html ?? "") : "" }}
        />
        <textarea
          className={`ce-input${fresh ? " painted" : ""}`}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          spellCheck={false}
          autoCapitalize="off"
          autoComplete="off"
          autoCorrect="off"
          wrap="off"
          aria-label="File contents"
        />
      </div>
    </div>
  );
}
