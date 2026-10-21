import type { ReactNode } from "react";
import { useCore } from "../data/DataContext";
import { shortCommit } from "../lib/format";
import { TourPlot } from "./TourPlot";

export const NAV = [
  { path: "", label: "Overview" },
  { path: "results", label: "Results" },
  { path: "explorer", label: "Explorer" },
  { path: "methods", label: "Methods" },
] as const;

// The brand mark is a real tour: the 2-opt reference route for the first 25-city dev instance.
function BrandMark() {
  const core = useCore();
  const tour = core.status === "ready" ? core.baselines.references.two_opt.dev.instances[0].tour : null;
  if (core.status !== "ready" || !tour) return <svg aria-hidden="true" viewBox="0 0 1 1" />;
  return <TourPlot points={core.instances.dev.instances[0].points} tour={tour} />;
}

export function Layout({ current, children }: { current: string; children: ReactNode }) {
  const core = useCore();
  return (
    <div className="shell">
      <a className="skip-link" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>
        Skip to content
      </a>
      <header className="rail">
        <a className="brand" href="#/" aria-label="Loopforge home">
          <BrandMark />
          <span className="brand-name">Loopforge</span>
        </a>
        <nav className="nav" aria-label="Main">
          {NAV.map((item) => (
            <a key={item.path} href={`#/${item.path}`} aria-current={current === item.path ? "page" : undefined}>
              {item.label}
            </a>
          ))}
        </nav>
        <div className="rail-foot">
          {core.status === "ready" && <p>Data exported from commit <code>{shortCommit(core.index.commit)}</code></p>}
        </div>
      </header>
      <main id="main" className="main" tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}
