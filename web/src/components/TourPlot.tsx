interface Props {
  points: [number, number][];
  tour: number[];
  /** Accessible description; omit only when the plot is decorative. */
  label?: string;
  className?: string;
}

// Draws a closed tour in the unit square, y flipped so (0,0) is bottom-left as in the Python task.
export function TourPlot({ points, tour, label, className }: Props) {
  const pad = 0.04;
  const sx = (x: number) => pad + x * (1 - 2 * pad);
  const sy = (y: number) => 1 - (pad + y * (1 - 2 * pad));
  const path =
    tour.map((c, i) => `${i === 0 ? "M" : "L"}${sx(points[c][0]).toFixed(4)} ${sy(points[c][1]).toFixed(4)}`).join("") + "Z";
  return (
    <svg viewBox="0 0 1 1" className={className} role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      <path d={path} fill="none" stroke="currentColor" strokeWidth={0.018} strokeLinejoin="round" />
      {points.map(([x, y], i) => (
        <circle key={i} cx={sx(x)} cy={sy(y)} r={0.03} fill="currentColor" />
      ))}
    </svg>
  );
}
