// Types for the JSON written by `loopforge exp export` (schema_version 1).
// Keep these in sync with src/loopforge/manual.py. Every field below appears in web/public/data/*.json.

export type Status = "valid" | "invalid" | "duplicate";

export interface InstanceResult {
  n: number;
  valid: boolean;
  length: number | null;
  ratio: number | null; // length / 2-opt reference length
  seconds: number;
  error: string | null;
  tour: number[] | null;
}

export interface EvalResult {
  valid: boolean;
  fitness: number | null; // mean ratio; null when invalid
  mean_seconds: number;
  error: string | null;
  sandbox_limits: string[];
  instances: InstanceResult[];
}

export interface BlindMutation {
  runs: number;
  proposals: number;
  improvements: number;
  source: string;
}

export interface ExperimentCard {
  id: string;
  title: string;
  site: string;
  model: string;
  seed_program: string;
  hints: boolean;
  proposals: number;
  improvements: number;
  valid: number;
  invalid: number;
  duplicate: number;
  seed_dev: number;
  best_dev: number;
  seed_test: number;
  best_test: number;
  blind_mutation: BlindMutation | null;
}

export interface IndexFile {
  schema_version: 1;
  commit: string | null;
  experiments: ExperimentCard[];
}

export interface BaselineEval {
  dev: EvalResult;
  test: EvalResult;
}

export interface BaselinesFile {
  schema_version: 1;
  references: {
    nearest_neighbor: BaselineEval;
    two_opt: BaselineEval;
    random_order: BaselineEval;
  };
  blind_mutation: Record<string, BlindMutation>;
}

export interface InstanceSet {
  name: string;
  instances: { n: number; points: [number, number][] }[];
}

export interface InstancesFile {
  schema_version: 1;
  dev: InstanceSet;
  test: InstanceSet;
}

export interface Turn {
  turn: number; // 0 = the seed program, 1..6 = AI replies
  program_id: string;
  parent_id: string | null;
  status: Status;
  error: string | null;
  description: string; // always "LLM edit": DESCRIPTION lines were not recorded
  fitness: number | null;
  by_size: Record<string, number>;
  mean_seconds: number | null;
  duplicate_of: string | null;
  hint: string | null;
  prompt: string | null; // null for the seed
  response: string | null;
  code: string;
  eval: EvalResult | null;
  note: string | null;
  improved: boolean;
  best_so_far: number | null;
  hashes: Record<string, string>; // sha256 of saved evidence files
}

export interface ExperimentMeta {
  id: string;
  title: string;
  site: string;
  model: string;
  settings: string;
  seed_program: string;
  hints: boolean;
  max_turns: number;
  time_limit_seconds: number;
  notes: string;
  loopforge_version: string;
}

export interface Experiment {
  schema_version: 1;
  id: string;
  title: string;
  meta: ExperimentMeta;
  turns: Turn[];
  curve: number[];
  summary: {
    counts: { proposals: number; valid: number; invalid: number; duplicate: number; improvements: number };
    seed: { id: string; dev_fitness: number; test_fitness: number };
    best: { id: string; iteration: number; dev_fitness: number; test_fitness: number; lineage: string[] };
  };
  final: {
    best: { program_id: string; dev_fitness: number; test: EvalResult };
    seed: { program_id: string; dev_fitness: number; test: EvalResult };
  };
  evidence: string; // e.g. "evidence/claude-01/"
}
