export const fitness = (v: number | null | undefined): string => (v == null ? "n/a" : v.toFixed(4));
export const shortCommit = (c: string | null): string => (c ? c.slice(0, 7) : "unknown");
