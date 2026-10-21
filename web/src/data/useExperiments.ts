import { useEffect, useState } from "react";
import { loadExperiment } from "./load";
import type { Experiment } from "./types";

export type ExpsState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; experiments: Experiment[] };

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

export function useExperiments(ids: string[]): ExpsState {
  const key = ids.join("|");
  const [state, setState] = useState<ExpsState>({ status: "loading" });
  useEffect(() => {
    let live = true;
    setState({ status: "loading" });
    Promise.all((key ? key.split("|") : []).map((id) => loadExperiment(id))).then(
      (experiments) => live && setState({ status: "ready", experiments }),
      (e: unknown) => live && setState({ status: "error", message: msg(e) }),
    );
    return () => {
      live = false;
    };
  }, [key]);
  return state;
}
