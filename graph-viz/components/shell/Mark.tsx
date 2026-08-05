/*
  Codexa identity mark — a small constellation of three linked nodes: the knowledge graph, reduced
  to a glyph. One node carries the signal teal. Simple geometry, meaningful, used as the app mark
  and in load states.
*/
export function Mark({ size = 28, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      aria-hidden
    >
      <path
        d="M6.4 7.2 L17 5.8 M6.4 7.2 L12 16.6 M17 5.8 L12 16.6"
        stroke="currentColor"
        strokeWidth="1.25"
        strokeLinecap="round"
        opacity="0.5"
      />
      <circle cx="6.4" cy="7.2" r="2.1" fill="currentColor" />
      <circle cx="17" cy="5.8" r="1.7" fill="currentColor" opacity="0.75" />
      <circle cx="12" cy="16.6" r="2.4" fill="var(--color-signal)" />
    </svg>
  );
}
