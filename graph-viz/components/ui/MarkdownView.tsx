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

const TABLE_ROW = /^\s*\|.*\|\s*$/;
const TABLE_SEP = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$/;

// Some models emit an entire table as one run-on line (rows joined by "| |" instead of real
// newlines). Split those back into rows before the normal per-line table parse below.
function splitRunOnTableRows(line: string): string[] {
  return line.split(/\|\s*\|/).map((seg, i, arr) => {
    if (arr.length === 1) return seg;
    if (i === 0) return `${seg}|`;
    if (i === arr.length - 1) return `|${seg}`;
    return `|${seg}|`;
  });
}

function splitCells(row: string): string[] {
  const trimmed = row.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((c) => c.trim());
}

function Table({ header, rows }: { header: string[]; rows: string[][] }) {
  return (
    <div className="my-4 overflow-x-auto rounded-lg border border-line">
      <table className="w-full border-collapse text-[13.5px]">
        <thead>
          <tr className="bg-panel-2">
            {header.map((h, i) => (
              <th key={i} className="border-b border-line px-3 py-2 text-left font-semibold text-ink">
                {inline(h)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-line last:border-0">
              {r.map((c, j) => (
                <td key={j} className="px-3 py-2 align-top text-ink-soft">
                  {inline(c)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
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

    if (TABLE_ROW.test(line)) {
      const expanded: string[] = [];
      while (i < lines.length && TABLE_ROW.test(lines[i])) {
        expanded.push(...splitRunOnTableRows(lines[i]));
        i++;
      }
      if (expanded.length >= 2 && TABLE_SEP.test(expanded[1])) {
        const header = splitCells(expanded[0]);
        const rows = expanded.slice(2).filter((r) => TABLE_ROW.test(r)).map(splitCells);
        blocks.push(<Table key={key++} header={header} rows={rows} />);
      } else {
        blocks.push(
          <p key={key++} className="my-3 text-[15px] leading-relaxed text-ink-soft">
            {inline(expanded.join(" "))}
          </p>,
        );
      }
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
      !/^(#{1,6}\s|\s*[-*]\s|\s*\d+\.\s|```)/.test(lines[i]) &&
      !TABLE_ROW.test(lines[i])
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
