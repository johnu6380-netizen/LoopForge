# Manual experiments: protocol, archive and replay format

These experiments replace the automated API pipeline. A person carries each prompt to an AI
website and carries the reply back. Everything after that (parsing, safety check, sandbox,
scoring, archive, held-out test) is the normal Loopforge machinery, so the AI's programs face
exactly the same checks as random mutations did.

They are **case studies, not statistics**: a handful of runs, each with one model, one task and
a small instance set. The write-up must say so.

## Rules (fixed before the first real run)

1. At most **6 turns** per experiment. A bad reply (no code, wrong tour, rejected, duplicate) still uses a turn.
2. **A new chat for every turn.** The first and only message is exactly the generated `prompt.md`.
3. Turn **code execution / tools and memory off** on the site. The prompt also says not to run code.
4. **First reply only.** No regenerating, no follow-up messages, no "try again".
5. Paste the reply **verbatim** into `response.md`. Never edit the reply or the code.
6. **Only dev results** are ever shown to the AI. The held-out test set is used once, at `finalize`.
7. The next parent is chosen by the hill-climb rule (best so far, ties accepted). No human judgment.
8. Do not look at any `test` numbers or change seeds, limits or instance sizes between experiments.
   The time limit is **10 seconds per instance** (`--time-limit`, recorded in `meta.json`, and stated in every prompt). The reference 2-opt needs about 5 ms, so this is very generous; a better algorithm legitimately does more work. Use the same limit for every experiment you compare.
9. Safety: skim the code in `response.md` before `ingest`. The sandbox stops buggy code, not malicious
   code, and `ingest` refuses programs that import `os`/`subprocess`/`socket`, use `open`/`eval`/`exec`/`getattr`
   or reflection tricks (they are recorded as failures and never run). Never run AI code any other way.

Before the first real run: `git add -A`, commit, and `git tag experiments-v1`.

## The experiment set

| id | seed | model | hints | what it tests |
|---|---|---|---|---|
| `e1-nn-chatgpt` | nearest_neighbor | ChatGPT | off | Can the model beat blind mutation (0 improvements in 9,000)? |
| `e2-nn-chatgpt-hints` | nearest_neighbor | ChatGPT | on | Do TSP hints in the prompt matter? |
| `e3-nn-claude` | nearest_neighbor | Claude | off | Does a different model behave differently on the identical task? |
| `e4-2opt-chatgpt` | two_opt | ChatGPT | off | The headline: can it get **below 1.000**, i.e. beat the reference? |
| `e5-2opt-claude` | two_opt | Claude | off | Same, second model. |
| `e6-random-chatgpt` | random_order | ChatGPT | off | How fast does it climb from the worst baseline (4.456)? |

Add more later (a repeat of e1 shows run-to-run variance). Use the **exact model name shown on the site**
for `--model`.

Note: the offline blind-mutation runs used a 1-second limit. Blind mutants of these seeds run in milliseconds, so the limit never mattered for them, but say so in the write-up.

Optional but recommended **before e4/e5**: give the 2-opt seed a blind-mutation baseline too (about 3 minutes):

```
loopforge experiment --seed-program two_opt --budget 300 --seeds 10 --workers 2 --out runs/offline-2opt
```

## Commands, one turn at a time

```
loopforge exp new e1-nn-chatgpt --seed-program nearest_neighbor --site ChatGPT --model "<exact model name>" --title "Cold start from nearest neighbor"
loopforge exp prompt e1-nn-chatgpt          # writes experiments/e1-nn-chatgpt/turn-01/prompt.md
#   open prompt.md, copy ALL, paste into a NEW chat as the only message, copy the whole reply
#   create experiments/e1-nn-chatgpt/turn-01/response.md, paste, save (UTF-8)
loopforge exp ingest e1-nn-chatgpt          # checks, runs in the sandbox, records the result
loopforge exp prompt e1-nn-chatgpt          # turn 2 ... repeat up to 6 turns
loopforge exp status e1-nn-chatgpt          # table of all turns
loopforge exp finalize e1-nn-chatgpt        # held-out test, once. Closes the experiment.
loopforge report experiments/e1-nn-chatgpt  # the usual run report works too
```

Add `--hints` to `exp new` for e2, and `--seed-program two_opt` for e4/e5. Everything is deterministic:
the same archive always produces the same prompt.

Do a **throwaway dry run** first (`loopforge exp new dry-run ...`) and delete `experiments/dry-run` afterwards.

## Archive layout (committed to git)

```
experiments/<id>/
  meta.json           site, model, settings, seed, hints, max turns   (what you told `exp new`)
  config.json         search settings in the usual run format
  programs.jsonl      every program, valid or not, with lineage (the usual run format)
  summary.json        written by finalize (the usual run format)
  best.py             best program
  final.json          held-out test results for best and seed (existence = "test set already used")
  turn-00/            the seed: candidate.py, eval_dev.json
  turn-NN/            prompt.md, prompt.json, response.md, candidate.py, eval_dev.json
```

`eval_dev.json` holds the full evaluation, including every tour, so a route can be drawn and every
length recomputed. Do not edit anything in these folders after the fact.

## Replay data (static JSON for the website)

`loopforge exp export` writes (default `web/public/data`, plus raw folders into `web/public/evidence`):

| file | contents |
|---|---|
| `index.json` | `schema_version`, git `commit`, one card per experiment (counts, seed/best fitness on dev and test, blind-mutation baseline) |
| `instances.json` | exact `dev` and `test` points (full-precision floats), so tours can be redrawn and lengths recomputed |
| `baselines.json` | nearest_neighbor, two_opt, random_order on dev/test **with tours**; blind-mutation results |
| `experiments/<id>.json` | `meta`, `config`, `turns[]`, `curve`, `summary`, `final`, `evidence` path |

Each entry of `turns[]`: `turn`, `program_id`, `parent_id`, `status` (`valid`/`invalid`/`duplicate`), `error`,
`description`, `fitness`, `by_size`, `mean_seconds`, `duplicate_of`, `hint`, `prompt`, `response`, `code`,
`eval` (per-instance `n`, `valid`, `length`, `ratio`, `seconds`, `error`, `tour`), `improved`, `best_so_far`,
and `hashes` (sha256 of the raw files, checkable with `sha256sum`). Turn 0 is the seed and has no prompt or response.

Pass `--blind runs/offline-2opt` to `exp export` to include the 2-opt blind-mutation baseline. The nearest-neighbor
and random_order baselines come from `docs/RESULTS.md`.

## What the replay may and may not claim

It plays back recorded files. The response text appears as "recorded from `<model>`", never as a live call, and
evaluation results are the stored ones. The "recompute" button re-derives every tour length in the browser from the
stored points and tours. Nothing in the replay is generated or estimated.
