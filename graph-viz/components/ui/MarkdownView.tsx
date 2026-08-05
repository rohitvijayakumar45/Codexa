import { Fragment, type ReactNode } from "react";

// Minimal, dependency-free markdown rendering tuned to the design system: headings, fenced code,
// lists, and inline code/bold. Deliberately small — not a full CommonMark parser.
function inline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const regex = /(`[^`]+`|\*\*[^*]+\*\*)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = regex.exec(text))) {
    if (m.index > last) nodes.push(<Fragment key={key++}>{text.slice(last, m.index)}</Fragment>);
    const token = m[0];
    if (token.startsWith("`")) {
      nodes.push(
        <code key={key++} className="num rounded bg-paper-sunk px-1.5 py-0.5 text-[0.85em] text-ink">
          {token.slice(1, -1)}
        </code>,
      );
    } else {
      nodes.push(
        <strong key={key++} className="font-semibold text-ink">
          {token.slice(2, -2)}
        </strong>,
      );
    }
    last = m.index + token.length;
  }
  if (last < text.length) nodes.push(<Fragment key={key++}>{text.slice(last)}</Fragment>);
  return nodes;
}

export function MarkdownView({ markdown }: { markdown: string }) {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.trim().startsWith("```")) {
      const buf: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) buf.push(lines[i++]);
      i++;
      blocks.push(
        <pre key={key++} className="num my-4 overflow-x-auto rounded-lg border border-line bg-panel-2 p-4 text-[12.5px] leading-relaxed text-ink-soft">
          {buf.join("\n")}
        </pre>,
      );
      continue;
    }

    if (/^#{1,6}\s/.test(line)) {
      const level = line.match(/^#+/)![0].length;
      const text = line.replace(/^#+\s/, "");
      const cls =
        level <= 1
          ? "display text-2xl font-semibold text-ink mt-8 mb-3"
          : level === 2
            ? "display text-lg font-semibold text-ink mt-8 mb-2"
            : "text-sm font-semibold text-ink mt-5 mb-1.5";
      blocks.push(
        <p key={key++} className={cls}>
          {inline(text)}
        </p>,
      );
      i++;
      continue;
    }

    if (/^\s*[-*]\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s/.test(lines[i])) items.push(lines[i++].replace(/^\s*[-*]\s/, ""));
      blocks.push(
        <ul key={key++} className="my-3 space-y-1.5 pl-1">
          {items.map((it, j) => (
            <li key={j} className="flex gap-2.5 text-[15px] leading-relaxed text-ink-soft">
              <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-faint" />
              <span>{inline(it)}</span>
            </li>
          ))}
        </ul>,
      );
      continue;
    }

    if (/^\s*\d+\.\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+\.\s/.test(lines[i])) items.push(lines[i++].replace(/^\s*\d+\.\s/, ""));
      blocks.push(
        <ol key={key++} className="my-3 space-y-1.5">
          {items.map((it, j) => (
            <li key={j} className="flex gap-2.5 text-[15px] leading-relaxed text-ink-soft">
              <span className="num mt-0.5 shrink-0 text-xs text-faint">{j + 1}.</span>
              <span>{inline(it)}</span>
            </li>
          ))}
        </ol>,
      );
      continue;
    }

    if (line.trim() === "") {
      i++;
      continue;
    }

    const para: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^(#{1,6}\s|\s*[-*]\s|\s*\d+\.\s|```)/.test(lines[i])
    )
      para.push(lines[i++]);
    blocks.push(
      <p key={key++} className="my-3 text-[15px] leading-relaxed text-ink-soft">
        {inline(para.join(" "))}
      </p>,
    );
  }

  return <div className="max-w-2xl">{blocks}</div>;
}
