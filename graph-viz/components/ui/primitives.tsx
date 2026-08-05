import clsx from "clsx";
import type { ButtonHTMLAttributes, ReactNode } from "react";

// Shared motion language — every screen eases the same way.
export const EASE_OUT = [0.16, 1, 0.3, 1] as const;
export const EASE_INOUT = [0.65, 0, 0.35, 1] as const;
export const DUR = { fast: 0.16, base: 0.28, slow: 0.5 } as const;

type Variant = "primary" | "ghost" | "quiet";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-ink text-panel hover:bg-ink-soft",
  ghost: "border border-line-strong text-ink hover:border-ink/40 hover:bg-paper-sunk",
  quiet: "text-muted hover:bg-paper-sunk hover:text-ink",
};

export function Button({
  variant = "primary",
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; children: ReactNode }) {
  return (
    <button
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium",
        "transition-[transform,background-color,border-color,color] duration-150 ease-out",
        "active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50",
        VARIANTS[variant],
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

/** The recurring small mono status label. */
export function StatusLine({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={clsx("status-line", className)}>{children}</span>;
}
