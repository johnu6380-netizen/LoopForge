import type { CoreState } from "../data/DataContext";

// Loading and error states for the core data. Renders nothing once data is ready.
export function Status({ core }: { core: CoreState }) {
  if (core.status === "loading") return <p role="status">Loading results…</p>;
  if (core.status === "error")
    return (
      <div className="notice error" role="alert">
        <strong>The results could not be loaded.</strong>
        <p>{core.message}</p>
      </div>
    );
  return null;
}
