"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "framer-motion";
import { useState, type ReactNode } from "react";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 15_000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );

  /*
    reducedMotion="user" is not optional politeness — without it the app was silently ignoring the
    setting entirely. globals.css has a blanket prefers-reduced-motion block, but it only zeroes CSS
    animation and transition durations, and every Framer Motion animation here is driven in
    JavaScript where that rule cannot reach. Springs, layout animations and every enter/exit ran at
    full amplitude for a user who had explicitly asked them not to.

    "user" rather than "always": transform and layout animation collapse to instant, while opacity
    fades are kept, because a cross-fade is the non-vestibular equivalent that still communicates
    that something changed.
  */
  return (
    <MotionConfig reducedMotion="user">
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </MotionConfig>
  );
}
