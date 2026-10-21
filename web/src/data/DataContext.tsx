import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { loadCore, loadExperiment, type CoreData } from "./load";
import type { Experiment } from "./types";

export type CoreState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | ({ status: "ready" } & CoreData);

const Ctx = createContext<CoreState>({ status: "loading" });
const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

export function DataProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<CoreState>({ status: "loading" });
  useEffect(() => {
    let live = true;
    loadCore().then(
      (d) => live && setState({ status: "ready", ...d }),
      (e: unknown) => live && setState({ status: "error", message: msg(e) }),
    );
    return () => {
      live = false;
    };
  }, []);
  return <Ctx.Provider value={state}>{children}</Ctx.Provider>;
}

export function useCore(): CoreState {
  return useContext(Ctx);
}

export type ExpState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; experiment: Experiment };

// Used by the explorer in Stage 5.
export function useExperiment(id: string | undefined): ExpState {
  const [state, setState] = useState<ExpState>({ status: "loading" });
  useEffect(() => {
    if (!id) return;
    let live = true;
    setState({ status: "loading" });
    loadExperiment(id).then(
      (experiment) => live && setState({ status: "ready", experiment }),
      (e: unknown) => live && setState({ status: "error", message: msg(e) }),
    );
    return () => {
      live = false;
    };
  }, [id]);
  return state;
}
