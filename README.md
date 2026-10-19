# Loopforge

An evolutionary loop that uses an LLM to improve algorithms, scored by a strict evaluator.

Loopforge starts from a simple heuristic for the Euclidean Traveling Salesman Problem,
asks a language model to propose better versions of the code, runs every proposal against
a benchmark (**correctness first, then tour quality**), keeps the good ones in an archive,
and repeats. It is a small-scale version of the idea behind FunSearch and AlphaEvolve.

> **Status: Stage 4 of 6 (LLM proposer built; real LLM experiments not run yet).** Everything runs
> offline with the mutation proposer; the LLM proposer works with free-tier providers or a local model.
> There are **no LLM results yet**, and none are claimed. See [docs/RESULTS.md](docs/RESULTS.md) for what exists.

## What works today

- A TSP task with deterministic, reproducible instances and separate **dev** and **test** sets
- A strict tour validator (rejects duplicates, floats, bools, out-of-range cities, wrong length)
- Three baseline algorithms stored as plain source files: random order, nearest neighbor, 2-opt
- An evaluator that scores any `solve(points)` function against the 2-opt reference
- A **sandbox** that runs candidate code in an isolated subprocess with time and memory limits
  (see [docs/SANDBOX.md](docs/SANDBOX.md))
- A **search loop** with an archive of every program and its lineage, three strategies (`random`,
  `hill_climb`, `evolve`) and two interchangeable proposers (see [docs/SEARCH.md](docs/SEARCH.md)):
  - `mutation`: offline random edits to the syntax tree, no key needed (the blind baseline)
  - `llm`: asks a model for a complete improved program (Gemini, Groq, OpenRouter, Ollama, OpenAI or Anthropic)
- **Cost control** for LLM runs: token and dollar caps, an on-disk reply cache (re-runs are free and exactly
  reproducible), rate-limit spacing and retries, per-program token logging, cost per improvement in reports
  (see [docs/LLM.md](docs/LLM.md))
- **Safe key handling:** keys come only from environment variables or a git-ignored `.env`; never logged or cached
- **Honest evaluation:** equal budgets, a held-out test set touched once at the end, a determinism
  check on every new best, and full logs including failures
- An experiment runner that compares strategies over many seeds and writes a report
- A command-line tool and a pytest suite (165 tests; LLM tests use fake replies, never the network)

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

loopforge baselines                # score the built-in algorithms
loopforge eval path/to/my_solver.py
loopforge doctor                   # which sandbox protections does this machine enforce?
loopforge search --budget 100      # one offline search; logs go to runs/
loopforge experiment --budget 300 --seeds 10 --out runs/exp1   # compare strategies
loopforge report runs/exp1         # print the comparison table
pytest                             # run the tests
```

### With an LLM (optional)

```bash
# 1. put GEMINI_API_KEY=... in a file named .env (or choose another provider; see docs/LLM.md)
loopforge llm-check --show-prompt  # no key, no cost: see what the model is asked
loopforge llm-check                # one real call, scored end to end
loopforge search --proposer llm --budget 30 --strategy hill_climb --max-tokens 300000
loopforge report runs/llm-hill_climb-s0   # shows tokens, cost, and cost per improvement
```

Useful flags: `--provider`, `--model`, `--max-tokens`, `--max-cost` (with `--price-in/--price-out`),
`--no-hints` (cleaner "model alone" comparison), `--no-cache`. Add `--seed-program two_opt` to start from the strong algorithm.

Example output of `loopforge baselines`:

```
candidate         valid   fitness   mean sec
----------------------------------------------
nearest_neighbor  True    1.152     0.0005
random_order      True    4.456     0.0000
two_opt           True    1.000     0.0047
```

Fitness is the mean of `tour length / 2-opt tour length`, so lower is better and 1.000 ties 2-opt.

## Results so far

Offline only: 9,000 blind mutations from nearest neighbor found **0** improvements
([docs/RESULTS.md](docs/RESULTS.md)). That is the baseline an LLM must beat. LLM experiments are the next step and
will be reported whatever they show.

## How a candidate looks

```python
def solve(points):
    # points: list of (x, y) tuples in the unit square
    # return: a list containing every index 0..len(points)-1 exactly once
    return list(range(len(points)))
```

## Project layout

```
src/loopforge/
  tasks/tsp.py        instances, validator, tour length
  evaluator.py        validates tours and scores candidates
  sandbox.py          runs candidate code in an isolated subprocess (parent side)
  sandbox_runner.py   the code that runs inside that subprocess
  search.py           the search loop and the three strategies
  archive.py          every program found, with its lineage
  proposers/          mutation.py (offline), llm.py (prompting, parsing, caps), base.py, scripted.py (tests)
  llmclient.py        stdlib-only HTTP clients, retries, key handling, reply cache
  usage.py            token/cost accounting from the logs
  runlog.py           writes and reads run logs
  experiment.py       runs many searches and builds the comparison report
  sourcetools.py      normalizing and fingerprinting source code
  seeds/tsp/          baseline algorithms (plain .py files)
  cli.py              command-line interface
tests/                pytest suite
docs/ARCHITECTURE.md  design decisions and roadmap
docs/SANDBOX.md       what the sandbox does, and honestly what it does not
docs/SEARCH.md        strategies, budget accounting, honesty guards, log format
docs/LLM.md           API keys, cost control, what the model sees, limits
docs/RESULTS.md       experiment results so far, including the unflattering ones
```

## Roadmap

| Stage | Contents | Status |
|---|---|---|
| 1-3 | Task, sandbox, evaluator, archive, strategies, offline baselines | done |
| 4 | LLM proposer, cost tracking, reply cache | code done |
| 4b | Real LLM experiments, write-up | next |
| 5 | FastAPI backend + React UI (replay, lineage tree, live evaluator) | |
| 6 | CI, deployment, final README with real results | |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the pieces fit together.
