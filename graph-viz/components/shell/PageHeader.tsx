import type { ReactNode } from "react";

/** The one header pattern the whole instrument uses: mono eyebrow, confident title, optional slot. */
export function PageHeader({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children?: ReactNode;
}) {
  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-line bg-panel px-7">
      <div className="flex flex-col">
        <span className="status-line">{eyebrow}</span>
        <h1 className="display text-lg font-semibold leading-tight text-ink">{title}</h1>
      </div>
      {children && <div className="flex items-center gap-6">{children}</div>}
    </header>
  );
}
