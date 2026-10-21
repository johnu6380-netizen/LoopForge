import type { InstanceResult } from "../data/types";

export function meanRatioBySize(instances: InstanceResult[]): Map<number, number> {
  const acc = new Map<number, { sum: number; n: number }>();
  for (const i of instances) {
    if (i.ratio == null) continue;
    const a = acc.get(i.n) ?? { sum: 0, n: 0 };
    a.sum += i.ratio;
    a.n += 1;
    acc.set(i.n, a);
  }
  return new Map([...acc].map(([k, v]) => [k, v.sum / v.n]));
}

export function axisTicks(values: number[], step: number, pad: number): number[] {
  const lo = Math.floor((Math.min(...values) - pad) / step) * step;
  const hi = Math.ceil((Math.max(...values) + pad) / step) * step;
  const out: number[] = [];
  for (let v = lo; v <= hi + 1e-9; v += step) out.push(Math.round(v * 1e6) / 1e6);
  return out;
}

export const modelColor = (site: string): string => (site === "Claude" ? "var(--model-claude)" : "var(--model-gpt)");
export const modelMarker = (site: string): "circle" | "square" => (site === "Claude" ? "square" : "circle");
