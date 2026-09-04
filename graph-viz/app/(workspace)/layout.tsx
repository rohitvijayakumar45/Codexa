import { Rail } from "@/components/shell/Rail";

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="workspace-ambient relative flex h-[100dvh] overflow-hidden">
      {/* Pinned to the rail's own box (12px inset, 68px wide — matches Rail.tsx exactly), not a
          viewport-relative gradient position: a viewport-% guess can miss depending on window size
          and gave zero visible color through the glass last round. This is deliberately strong —
          the glass panel's translucency is what tones it down, not the blob itself. */}
      <div
        aria-hidden
        className="pointer-events-none absolute left-3 top-3 h-[calc(100%-1.5rem)] w-[68px] overflow-visible"
      >
        <div
          className="absolute left-1/2 top-1/2 h-[220%] w-[420%] -translate-x-1/2 -translate-y-1/2"
          style={{
            background:
              "radial-gradient(circle at 30% 22%, rgba(15,125,113,0.85) 0%, transparent 55%), " +
              "radial-gradient(circle at 68% 80%, rgba(156,125,51,0.7) 0%, transparent 55%)",
            filter: "blur(36px)",
          }}
        />
      </div>
      <Rail />
      <main className="relative flex min-w-0 flex-1 flex-col">{children}</main>
    </div>
  );
}
