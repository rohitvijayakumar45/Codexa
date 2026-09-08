const DOTS = [0, 1, 2];

// Bouncing-circle "thinking" indicator shown before the first token streams in. `label` overrides
// the generic "Generating" with a specific status (e.g. "Writing app.py") when the backend has sent
// one — most models never emit reasoning_content, so this is often the ONLY signal of real work
// happening between tool calls, not just decoration.
export function ThinkingLoader({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className="bounce-loader" role="status" aria-label={label ?? "Generating"}>
        {DOTS.map((i) => (
          <span key={`c${i}`} className="circle" style={{ left: `${i * 20}px`, animationDelay: `${i * 0.12}s` }} />
        ))}
        {DOTS.map((i) => (
          <span key={`s${i}`} className="shadow" style={{ left: `${i * 20}px`, animationDelay: `${i * 0.12}s` }} />
        ))}
      </div>
      {label && <span className="text-xs text-ink-soft/60">{label}</span>}
    </div>
  );
}
