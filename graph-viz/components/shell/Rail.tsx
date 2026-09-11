"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { MessagesSquare, Code2, Share2, Activity, Gauge, LayoutGrid, BrainCircuit, History, FileText, BarChart3, Layers } from "lucide-react";
import clsx from "clsx";
import { useEffect, useState } from "react";
import { Mark } from "./Mark";
import { RepoSwitcher } from "./RepoSwitcher";
import { ThemeToggle, type Theme } from "./ThemeToggle";
import { springPanel, springState } from "@/lib/motion";
import { useJobStore } from "@/lib/job-store";

type Item = { href: string; label: string; icon: typeof Share2 };

/*
  Ten destinations used to sit in one undifferentiated column of unlabelled icons, which meant
  finding anything was a memory exercise. They group cleanly into three jobs, and the grouping is
  real rather than decorative — it maps to what you are doing, not to what the pages are built from:

    Work        the two surfaces you act through
    Understand  the four that explain the codebase back to you
    Watch       the three that report on the machine itself
*/
const GROUPS: { name: string; items: Item[] }[] = [
  {
    name: "Work",
    items: [
      { href: "/chat", label: "Chat", icon: MessagesSquare },
      { href: "/ide", label: "Codebase", icon: Code2 },
    ],
  },
  {
    name: "Understand",
    items: [
      { href: "/strata", label: "Strata", icon: Layers },
      { href: "/graph", label: "Knowledge graph", icon: Share2 },
      { href: "/architecture", label: "Architecture", icon: LayoutGrid },
      { href: "/memory", label: "Memory", icon: BrainCircuit },
      { href: "/time-machine", label: "Time machine", icon: History },
    ],
  },
  {
    name: "Watch",
    items: [
      { href: "/agents", label: "Agent network", icon: Activity },
      { href: "/usage", label: "Usage", icon: BarChart3 },
      { href: "/repository", label: "Repository score", icon: Gauge },
      { href: "/docs", label: "Documentation", icon: FileText },
    ],
  },
];

export function Rail({ theme, onToggleTheme }: { theme: Theme; onToggleTheme: () => void }) {
  const pathname = usePathname();

  return (
    <motion.nav
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={springPanel}
      className="glass-panel relative z-10 my-3 ml-3 flex max-h-[calc(100%-1.5rem)] w-[68px] shrink-0 flex-col items-center self-start rounded-[26px] py-5 short:py-3"
    >
      <Link
        href="/graph"
        aria-label="Codexa OS"
        className="mb-5 grid h-10 w-10 place-items-center short:mb-3 short:h-9 short:w-9 rounded-xl text-ink transition-transform duration-200 ease-out hover:scale-105 active:scale-95"
      >
        <Mark size={26} />
      </Link>

      <div className="flex flex-col items-center gap-1 short:gap-0.5">
        {GROUPS.map((group, gi) => (
          <div key={group.name} className="flex flex-col items-center gap-1 short:gap-0.5">
            {gi > 0 ? <span className="my-1.5 h-px w-6 bg-line short:my-1" aria-hidden /> : null}
            <ul className="flex flex-col items-center gap-1 short:gap-0.5">
              {group.items.map((item) => (
                <RailLink key={item.href} item={item} group={group.name} pathname={pathname} />
              ))}
            </ul>
          </div>
        ))}
      </div>

      <span className="my-1.5 h-px w-6 bg-line short:my-1" aria-hidden />
      <JobPulse />
      <RepoSwitcher />
      <ThemeToggle theme={theme} onToggle={onToggleTheme} />

      <div className="mt-3 grid h-9 w-9 place-items-center rounded-full short:mt-2 short:h-8 short:w-8 border border-line-strong bg-paper-sunk text-[13px] font-medium text-ink-soft">
        R
      </div>
    </motion.nav>
  );
}

function RailLink({ item, group, pathname }: { item: Item; group: string; pathname: string }) {
  const { href, label, icon: Icon } = item;
  const active = pathname === href || pathname.startsWith(`${href}/`);

  return (
    <li>
      <Link href={href} aria-current={active ? "page" : undefined}>
        <span
          className={clsx(
            "group relative grid h-11 w-11 place-items-center rounded-xl short:h-9 short:w-9 transition-colors duration-200 ease-out active:scale-90",
            active ? "text-signal" : "text-muted hover:bg-paper-sunk hover:text-ink",
          )}
        >
          {active && (
            <motion.span
              layoutId="rail-active-pill"
              transition={springState}
              className="absolute inset-0 rounded-xl bg-signal-wash"
              aria-hidden
            />
          )}
          {active && (
            <motion.span
              layoutId="rail-active-mark"
              transition={springState}
              className="absolute -left-[13px] h-6 w-[3px] rounded-full bg-signal"
              aria-hidden
            />
          )}
          <Icon size={19} strokeWidth={1.75} className="relative" />
          {/* The label carries its group, so hovering also teaches the structure. */}
          <span className="pointer-events-none absolute left-[52px] z-30 flex translate-x-[-4px] items-center gap-2 whitespace-nowrap rounded-lg border border-line bg-panel px-2.5 py-1.5 text-xs font-medium text-ink opacity-0 shadow-md transition-all duration-200 ease-out group-hover:translate-x-0 group-hover:opacity-100">
            {label}
            <span className="status-line !tracking-[0.1em]">{group}</span>
          </span>
        </span>
      </Link>
    </li>
  );
}

/*
  The live job, visible from every route. Breathing dot plus seconds-on-current-step; hovering gives
  the status text. Deliberately small — this is peripheral awareness, not a notification.
*/
function JobPulse() {
  const jobId = useJobStore((s) => s.jobId);
  const status = useJobStore((s) => s.status);
  const task = useJobStore((s) => s.task);
  const since = useJobStore((s) => s.since);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!jobId) return;
    const tick = () => setElapsed(Math.floor((Date.now() - since) / 1000));
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [jobId, since]);

  if (!jobId) return null;

  return (
    <Link href="/chat" className="group relative mb-3 grid h-9 w-9 place-items-center short:mb-2 short:h-8 short:w-8" aria-label="Job running">
      <span className="absolute inset-0 rounded-full bg-signal-wash" aria-hidden />
      <span
        className="relative h-2 w-2 rounded-full bg-signal-live"
        style={{ animation: "breathe 2s ease-in-out infinite" }}
        aria-hidden
      />
      <span className="pointer-events-none absolute left-[52px] z-30 w-[190px] translate-x-[-4px] rounded-lg border border-line bg-panel px-2.5 py-2 text-left opacity-0 shadow-md transition-all duration-200 ease-out group-hover:translate-x-0 group-hover:opacity-100">
        <span className="block truncate text-xs font-medium text-ink">{status || "Working"}</span>
        {task ? <span className="mt-0.5 block truncate text-[11px] text-muted">{task}</span> : null}
        <span className="num mt-1 block text-[10px] tabular-nums text-faint">{elapsed}s on this step</span>
      </span>
    </Link>
  );
}
