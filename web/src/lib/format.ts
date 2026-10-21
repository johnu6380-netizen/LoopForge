export const fitness = (v: number | null | undefined): string => (v == null ? "n/a" : v.toFixed(4));
export const shortCommit = (c: string | null): string => (c ? c.slice(0, 7) : "unknown");
export const seconds = (v: number | null | undefined): string =>
  v == null ? "n/a" : v < 1 ? `${(v * 1000).toFixed(0)} ms` : `${v.toFixed(2)} s`;
export const pct = (v: number): string => `${(v * 100).toFixed(1)}%`;
