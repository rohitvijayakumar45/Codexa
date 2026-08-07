const DOTS = [0, 1, 2];

// Bouncing-circle "thinking" indicator shown before the first token streams in.
export function ThinkingLoader() {
  return (
    <div className="bounce-loader" role="status" aria-label="Generating">
      {DOTS.map((i) => (
        <span key={`c${i}`} className="circle" style={{ left: `${i * 20}px`, animationDelay: `${i * 0.12}s` }} />
      ))}
      {DOTS.map((i) => (
        <span key={`s${i}`} className="shadow" style={{ left: `${i * 20}px`, animationDelay: `${i * 0.12}s` }} />
      ))}
    </div>
  );
}
