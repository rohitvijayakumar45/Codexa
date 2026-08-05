"use client";

import { motion } from "framer-motion";
import { Mark } from "./Mark";
import { Button, DUR, EASE_OUT } from "@/components/ui/primitives";

export function CenteredLoading({ label }: { label: string }) {
  return (
    <div className="grid flex-1 place-items-center">
      <div className="flex flex-col items-center gap-5">
        <div className="animate-pulse">
          <Mark size={38} className="text-ink" />
        </div>
        <p className="status-line">{label}</p>
      </div>
    </div>
  );
}

export function CenteredError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="grid flex-1 place-items-center p-6">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: DUR.base, ease: EASE_OUT }}
        className="max-w-md rounded-xl border border-danger/25 bg-panel p-6 text-center shadow-sm"
      >
        <h2 className="display text-base font-semibold text-danger">Something didn&apos;t load</h2>
        <p className="mt-2 text-sm text-muted">{message}</p>
        {onRetry && (
          <Button onClick={onRetry} className="mt-4">
            Try again
          </Button>
        )}
      </motion.div>
    </div>
  );
}

export function CenteredEmpty({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="grid flex-1 place-items-center p-6">
      <div className="max-w-md text-center">
        <h2 className="display text-base font-semibold text-ink">{title}</h2>
        {children && <div className="mt-2 text-sm text-muted">{children}</div>}
      </div>
    </div>
  );
}
