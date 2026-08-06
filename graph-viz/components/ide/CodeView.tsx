"use client";

import { useEffect, useState } from "react";
import { codeToHtml } from "shiki";

const LANG: Record<string, string> = {
  tsx: "tsx", typescript: "typescript", javascript: "javascript", jsx: "jsx", python: "python",
  json: "json", markdown: "markdown", css: "css", html: "html", yaml: "yaml", toml: "toml",
  bash: "bash", sql: "sql", go: "go", rust: "rust", java: "java", ruby: "ruby", text: "text",
};

export function CodeView({ code, language }: { code: string; language: string }) {
  const [html, setHtml] = useState("");

  useEffect(() => {
    let cancelled = false;
    codeToHtml(code, { lang: LANG[language] ?? "text", theme: "github-light" })
      .then((h) => !cancelled && setHtml(h))
      .catch(() => !cancelled && setHtml(""));
    return () => {
      cancelled = true;
    };
  }, [code, language]);

  if (!html) {
    return <pre className="num whitespace-pre p-4 text-[12.5px] leading-relaxed text-ink-soft">{code}</pre>;
  }
  return (
    <div
      className="shiki-wrap num text-[12.5px] leading-relaxed"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
