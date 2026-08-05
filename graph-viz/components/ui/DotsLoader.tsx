// Pulsing-dots "thinking" indicator shown while a model is generating.
export function DotsLoader({ size = 9 }: { size?: number }) {
  return (
    <div className="flex items-center" role="status" aria-label="Generating">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="dot-pulse rounded-full"
          style={{
            width: size,
            height: size,
            marginRight: i < 2 ? size * 0.7 : 0,
            animationDelay: `${-0.3 + i * 0.15}s`,
          }}
        />
      ))}
    </div>
  );
}
