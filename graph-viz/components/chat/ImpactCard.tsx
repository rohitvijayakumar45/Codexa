"use client";

import { motion } from "framer-motion";
import { ArrowRight, ShieldCheck } from "lucide-react";
import type { ImpactResult } from "@/lib/api";
import { Button, EASE_OUT } from "@/components/ui/primitives";

const RISK: Record<string, { color: string; bg: string; fill: number }> = {
  None: { color: "var(--color-muted)", bg: "var(--color-paper-sunk)", fill: 0.08 },
  Low: { color: "var(--color-signal)", bg: "var(--color-signal-wash)", fill: 0.3 },
  Medium: { color: "var(--color-gold)", bg: "var(--color-gold-wash)", fill: 0.55 },
  High: { color: "var(--color-warn)", bg: "#f7ece2", fill: 0.8 },
  Critical: { color: "var(--color-danger)", bg: "#f7e6e6", fill: 1 },
};

export function ImpactCard({
  impact,
  pending,
  onProceed,
  onCancel,
}: {
  impact: ImpactResult;
  pending: boolean;
  onProceed: () => void;
  onCancel: () => void;
}) {
  const risk = RISK[impact.risk_level] ?? RISK.None;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: EASE_OUT }}
      className="mb-6 overflow-hidden rounded-2xl border border-line bg-panel shadow-md"
    >
      <div className="flex items-center justify-between border-b border-line px-5 py-3">
        <span className="status-line">Blast radius</span>
        <span
          className="rounded-full px-2.5 py-1 text-[11px] font-semibold"
          style={{ background: risk.bg, color: risk.color }}
        >
          {impact.risk_level} risk
        </span>
      </div>

      <div className="px-5 py-4">
        <div className="flex items-end gap-6">
          <div>
            <span className="num text-4xl font-medium leading-none text-ink">{impact.affected_count}</span>
            <p className="status-line mt-1.5">downstream affected</p>
          </div>
          <div className="pb-1">
            <span className="num text-lg font-medium text-ink">{Math.round(impact.confidence * 100)}%</span>
            <p className="status-line mt-0.5">confidence</p>
          </div>
          <div className="flex-1 pb-2">
            <div className="h-1.5 overflow-hidden rounded-full bg-paper-sunk">
              <motion.div
                className="h-full rounded-full"
                style={{ background: risk.color }}
                initial={{ width: 0 }}
                animate={{ width: `${Math.max(6, impact.risk_score * 100)}%` }}
                transition={{ duration: 0.7, ease: EASE_OUT }}
              />
            </div>
          </div>
        </div>

        <div className="mt-4">
          <p className="status-line mb-1.5">Change targets</p>
          <div className="flex flex-wrap gap-1.5">
            {impact.targets.map((t) => (
              <span key={t.id} className="num rounded-md border border-line bg-paper-sunk px-2 py-1 text-[11px] text-ink-soft">
                {t.label}
              </span>
            ))}
          </div>
        </div>

        {impact.paths_preview.length > 0 && (
          <div className="mt-4">
            <p className="status-line mb-1.5">Propagation</p>
            <ul className="space-y-1">
              {impact.paths_preview.map((chain, i) => (
                <li key={i} className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
                  {chain.map((label, j) => (
                    <span key={j} className="flex items-center gap-1.5">
                      {j > 0 && <ArrowRight size={11} className="text-faint" />}
                      <span className="num text-ink-soft">{label}</span>
                    </span>
                  ))}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {pending ? (
        <div className="flex items-center justify-between gap-3 border-t border-line bg-panel-2 px-5 py-3">
          <span className="text-xs text-muted">Review the impact, then decide.</span>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onCancel} className="px-3 py-1.5 text-xs">
              Cancel
            </Button>
            <Button onClick={onProceed} className="px-3 py-1.5 text-xs">
              Proceed <ArrowRight size={13} />
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-2 border-t border-line bg-panel-2 px-5 py-2.5 text-xs text-signal">
          <ShieldCheck size={14} />
          Approved — planning the change
        </div>
      )}
    </motion.div>
  );
}
