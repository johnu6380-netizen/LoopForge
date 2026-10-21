import type { BaselinesFile, Experiment, IndexFile, InstancesFile } from "./types";

const DATA_ROOT = `${import.meta.env.BASE_URL}data/`;
const SUPPORTED_SCHEMA = 1;

async function getJson<T extends { schema_version: number }>(path: string): Promise<T> {
  const url = DATA_ROOT + path;
  let res: Response;
  try {
    res = await fetch(url);
  } catch {
    throw new Error(`Could not reach ${url}. Check your connection and reload.`);
  }
  if (!res.ok) {
    throw new Error(`Could not load ${path} (HTTP ${res.status}). Run "loopforge exp export" to regenerate web/public/data.`);
  }
  const body = (await res.json()) as T;
  if (body.schema_version !== SUPPORTED_SCHEMA) {
    throw new Error(`${path} has schema_version ${body.schema_version}; this site reads version ${SUPPORTED_SCHEMA}.`);
  }
  return body;
}

export interface CoreData {
  index: IndexFile;
  baselines: BaselinesFile;
  instances: InstancesFile;
}

export function loadCore(): Promise<CoreData> {
  return Promise.all([
    getJson<IndexFile>("index.json"),
    getJson<BaselinesFile>("baselines.json"),
    getJson<InstancesFile>("instances.json"),
  ]).then(([index, baselines, instances]) => ({ index, baselines, instances }));
}

// Experiment files are large (every prompt, reply and tour), so they load on demand.
const experimentCache = new Map<string, Promise<Experiment>>();

export function loadExperiment(id: string): Promise<Experiment> {
  let p = experimentCache.get(id);
  if (!p) {
    p = getJson<Experiment>(`experiments/${encodeURIComponent(id)}.json`);
    p.catch(() => experimentCache.delete(id)); // allow retry after a failure
    experimentCache.set(id, p);
  }
  return p;
}
