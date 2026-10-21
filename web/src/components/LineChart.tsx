export interface ChartPoint {
  x: number;
  y: number | null; // null draws an "invalid" cross on the bottom axis
}
export interface ChartSeries {
  id: string;
  label: string;
  color: string;
  marker: "circle" | "square" | "none";
  line: "straight" | "step" | "none";
  points: ChartPoint[];
}
interface Props {
  series: ChartSeries[];
  xTicks: number[];
  xLabel: string;
  yLabel: string;
  yTicks: number[];
  yScale?: "linear" | "log";
  formatY: (v: number) => string;
  refLines?: { y: number; label: string }[];
  /** Accessible description of what the chart shows. */
  label: string;
}

const W = 640, H = 340, ML = 64, MR = 24, MT = 16, MB = 52;

export function LineChart({ series, xTicks, xLabel, yLabel, yTicks, yScale = "linear", formatY, refLines = [], label }: Props) {
  const tf = (v: number) => (yScale === "log" ? Math.log10(v) : v);
  const x0 = xTicks[0] - 0.5;
  const x1 = xTicks[xTicks.length - 1] + 0.5;
  const y0 = yTicks[0];
  const y1 = yTicks[yTicks.length - 1];
  const sx = (x: number) => ML + ((x - x0) / (x1 - x0)) * (W - ML - MR);
  const sy = (y: number) => MT + (1 - (tf(y) - tf(y0)) / (tf(y1) - tf(y0))) * (H - MT - MB);
  const f = (n: number) => n.toFixed(1);

  const pathFor = (s: ChartSeries): string => {
    const pts = s.points.filter((p): p is { x: number; y: number } => p.y != null);
    if (pts.length === 0) return "";
    let d = `M${f(sx(pts[0].x))} ${f(sy(pts[0].y))}`;
    for (const p of pts.slice(1)) {
      d += s.line === "step" ? `H${f(sx(p.x))}V${f(sy(p.y))}` : `L${f(sx(p.x))} ${f(sy(p.y))}`;
    }
    return d;
  };

  return (
    <div>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={ML} x2={W - MR} y1={sy(t)} y2={sy(t)} style={{ stroke: "var(--rule)" }} strokeWidth={1} />
            <text x={ML - 8} y={sy(t) + 4} textAnchor="end">{formatY(t)}</text>
          </g>
        ))}
        {xTicks.map((t) => (
          <text key={t} x={sx(t)} y={H - MB + 20} textAnchor="middle">{t}</text>
        ))}
        <text className="axis-title" x={(ML + W - MR) / 2} y={H - 8} textAnchor="middle">{xLabel}</text>
        <text className="axis-title" transform={`translate(14 ${(MT + H - MB) / 2}) rotate(-90)`} textAnchor="middle">{yLabel}</text>

        {refLines.map((r) => (
          <g key={r.label}>
            <line x1={ML} x2={W - MR} y1={sy(r.y)} y2={sy(r.y)} style={{ stroke: "var(--bad)" }} strokeWidth={1.5} strokeDasharray="6 4" />
            <text x={W - MR - 4} y={sy(r.y) + 15} textAnchor="end" style={{ fill: "var(--bad)" }}>{r.label}</text>
          </g>
        ))}

        {series.map((s) => (
          <g key={s.id}>
            {s.line !== "none" && (
              <path d={pathFor(s)} fill="none" style={{ stroke: s.color }} strokeWidth={2} strokeOpacity={0.55} strokeLinejoin="round" />
            )}
            {s.points.map((p) => {
              const cx = sx(p.x);
              if (p.y == null) {
                const cy = sy(y0) - 14;
                return (
                  <g key={p.x} style={{ stroke: s.color }} strokeWidth={2.5}>
                    <line x1={cx - 6} y1={cy - 6} x2={cx + 6} y2={cy + 6} />
                    <line x1={cx - 6} y1={cy + 6} x2={cx + 6} y2={cy - 6} />
                    <text x={cx} y={cy - 12} textAnchor="middle" style={{ fill: s.color, stroke: "none" }}>invalid</text>
                  </g>
                );
              }
              const cy = sy(p.y);
              if (s.marker === "circle") return <circle key={p.x} cx={cx} cy={cy} r={5.5} style={{ fill: s.color }} />;
              if (s.marker === "square") return <rect key={p.x} x={cx - 5} y={cy - 5} width={10} height={10} style={{ fill: s.color }} />;
              return null;
            })}
          </g>
        ))}
      </svg>
      <ul className="legend">
        {series.map((s) => (
          <li key={s.id}>
            <svg width="28" height="14" viewBox="0 0 28 14" aria-hidden="true">
              {s.line !== "none" && <line x1="0" x2="28" y1="7" y2="7" style={{ stroke: s.color }} strokeWidth="2" strokeOpacity="0.55" />}
              {s.marker === "circle" && <circle cx="14" cy="7" r="5" style={{ fill: s.color }} />}
              {s.marker === "square" && <rect x="9" y="2" width="10" height="10" style={{ fill: s.color }} />}
            </svg>
            {s.label}
          </li>
        ))}
      </ul>
    </div>
  );
}
