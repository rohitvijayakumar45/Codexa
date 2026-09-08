"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { MessagesSquare, Code2, Share2, Activity, Gauge, LayoutGrid, BrainCircuit, History, FileText, BarChart3 } from "lucide-react";
import clsx from "clsx";
import { Mark } from "./Mark";
import { RepoSwitcher } from "./RepoSwitcher";
import { EASE_OUT } from "@/components/ui/primitives";

type Item = { href: string; label: string; icon: typeof Share2; ready: boolean };

// Order reflects the intended flow: converse, explore the graph, watch the agents, read the
// architecture, judge the repo, replay history, document.
const ITEMS: Item[] = [
  { href: "/chat", label: "Chat", icon: MessagesSquare, ready: true },
  { href: "/ide", label: "Codebase", icon: Code2, ready: true },
  { href: "/graph", label: "Knowledge graph", icon: Share2, ready: true },
  { href: "/agents", label: "Agent network", icon: Activity, ready: true },
  { href: "/usage", label: "Usage", icon: BarChart3, ready: true },
  { href: "/architecture", label: "Architecture", icon: LayoutGrid, ready: true },
  { href: "/repository", label: "Repository score", icon: Gauge, ready: true },
  { href: "/memory", label: "Memory", icon: BrainCircuit, ready: true },
  { href: "/time-machine", label: "Time machine", icon: History, ready: true },
  { href: "/docs", label: "Documentation", icon: FileText, ready: true },
];

export function Rail() {
  const pathname = usePathname();

  return (
    <motion.nav
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.5, ease: EASE_OUT }}
      className="glass-panel relative z-10 my-3 ml-3 flex h-[calc(100%-1.5rem)] w-[68px] shrink-0 flex-col items-center rounded-[26px] py-5"
    >
      <Link
        href="/graph"
        aria-label="Codexa OS"
        className="mb-6 grid h-10 w-10 place-items-center rounded-xl text-ink transition-transform duration-200 ease-out hover:scale-105 active:scale-95"
      >
        <Mark size={26} />
      </Link>

      <ul className="flex flex-1 flex-col items-center gap-1.5">
        {ITEMS.map(({ href, label, icon: Icon, ready }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
          const inner = (
            <span
              className={clsx(
                "group relative grid h-11 w-11 place-items-center rounded-xl transition-colors duration-200 ease-out active:scale-90",
                active
                  ? "text-signal"
                  : ready
                    ? "text-muted hover:bg-paper-sunk hover:text-ink"
                    : "text-faint/55",
              )}
            >
              {active && (
                <motion.span
                  layoutId="rail-active-pill"
                  transition={{ type: "spring", stiffness: 480, damping: 34 }}
                  className="absolute inset-0 rounded-xl bg-signal-wash"
                  aria-hidden
                />
              )}
              {active && (
                <motion.span
                  layoutId="rail-active-mark"
                  transition={{ type: "spring", stiffness: 480, damping: 34 }}
                  className="absolute -left-[13px] h-6 w-[3px] rounded-full bg-signal"
                  aria-hidden
                />
              )}
              <Icon size={19} strokeWidth={1.75} className="relative" />
              <span className="pointer-events-none absolute left-[52px] z-30 flex translate-x-[-4px] items-center gap-2 whitespace-nowrap rounded-lg border border-line bg-panel px-2.5 py-1.5 text-xs font-medium text-ink opacity-0 shadow-md transition-all duration-200 ease-out group-hover:translate-x-0 group-hover:opacity-100">
                {label}
                {!ready && <span className="status-line !tracking-[0.1em]">soon</span>}
              </span>
            </span>
          );
          return (
            <li key={href}>
              {ready ? (
                <Link href={href} aria-current={active ? "page" : undefined}>
                  {inner}
                </Link>
              ) : (
                <span aria-disabled>{inner}</span>
              )}
            </li>
          );
        })}
      </ul>

      <RepoSwitcher />

      <div className="mt-4 grid h-9 w-9 place-items-center rounded-full border border-line-strong bg-paper-sunk text-[13px] font-medium text-ink-soft">
        R
      </div>
    </motion.nav>
  );
}
