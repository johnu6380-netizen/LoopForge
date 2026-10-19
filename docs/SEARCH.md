# The search loop

## One iteration

```
parent   = strategy.select(archive)          # which program to improve?
proposal = proposer.propose(parent, archive) # what is the new program?
result   = sandbox + evaluator(proposal)     # does it work, how good is it?
archive.add(result)                          # keep it, valid or not
```

The **strategy** and the **proposer** are separate on purpose. A strategy only decides *which*
parent to build on; a proposer only decides *what* the child looks like. That lets us test them
independently: three strategies x two proposers (mutation now, LLM in Stage 4).

## Strategies

| Name | Parent choice | What it tests |
|------|---------------|---------------|
| `random` | Always the original seed program | The no-memory baseline: how good is a single blind edit? |
| `hill_climb` | The current program; move to a child only if it is at least as good | Does accumulating improvements help? (Ties are accepted so the search can drift across plateaus, like a (1+1) evolutionary algorithm.) |
| `evolve` | Tournament selection: sample 3 valid programs, take the best | Does keeping a whole population alive help? Better programs are picked more often, but weaker ones still get a chance. |

## Proposers

- **`mutation`** (offline, no API key): random edits to the program's syntax tree. Eleven
  operators: change a constant, swap an arithmetic operator, flip a comparison, swap `and`/`or`,
  negate a condition, swap `min`/`max`, swap/delete/duplicate a statement, swap a variable for
  another, swap call arguments. It knows nothing about TSP. Every edit is syntactically valid, but
  most change nothing or break the program. This is the "no intelligence" baseline the LLM must beat.
- **`llm`** (Stage 4, needs an API key or a local model; see [LLM.md](LLM.md)) implements the same interface
  (`proposers/base.py`). The model proposes a complete new program from the parent's source, its score,
  a few other good programs and recent errors. Its output goes through the same duplicate check, sandbox and evaluator.

## Honesty guards

1. **Budget counts proposals, not evaluations.** An invalid proposal, a duplicate and a proposer
   failure each cost one unit, exactly as an LLM call would. Strategies and proposers are compared
   at equal budget.
2. **Dev vs. test.** The search only ever sees the dev set. The held-out test set is evaluated once,
   at the end, on the best program (and the seed, for reference). It never influences a decision.
3. **Determinism check.** When a program would become the new best, it is evaluated a second time.
   If its score changes (unseeded randomness, timing luck), it is rejected as non-deterministic.
4. **Duplicates are detected, not trusted.** Programs are compared after normalizing (comments,
   spacing and quote style removed), so a reformatted copy of a known program is recognized, counted
   against the budget, and not evaluated again.
5. **Everything is logged, including failures**, so valid/invalid rates are reported rather than hidden.
6. **Reproducible.** One integer seed controls every random choice. Same seed, same run (exact
   programs may differ slightly between Python versions because of how `ast.unparse` formats code).

## Run logs

Each run writes a folder (default `runs/<proposer>-<strategy>-s<seed>`):

| File | Contents |
|------|----------|
| `config.json` | the settings the run started with |
| `programs.jsonl` | one JSON line per program, written and flushed as it is produced |
| `summary.json` | best program, held-out test score, counts, best-so-far curve |
| `best.py` | source code of the best program (try `loopforge eval runs/.../best.py`) |

A program record has: `id`, `parent_id` (the lineage), `iteration`, `source`, `status`
(`valid` / `invalid` / `duplicate`), `fitness`, `by_size` (mean ratio per instance size), `error`,
`description` (what the proposer says it changed), `proposer`, `duplicate_of`, and `info` (room for
token counts in Stage 4). The web app in Stage 5 reads exactly these files.

## Commands

```
loopforge search --strategy evolve --budget 200 --seed 0     # one run
loopforge experiment --budget 300 --seeds 10 --out runs/exp1 # all strategies x seeds, then a report
loopforge report runs/exp1                                   # the comparison table
loopforge report runs/mutation-evolve-s0                     # improvement timeline of one run
```

Add `--seed-program two_opt` to start from the strong algorithm instead of nearest neighbor.

## Questions to be able to answer in an interview

- *Why separate the strategy from the proposer?* So each can be evaluated alone, and the LLM is just
  one pluggable component.
- *How do you know a gain is real?* Held-out test instances, multiple seeds, equal budgets, and a
  determinism re-check on every new best.
- *Why accept equal-fitness children in hill climbing?* Neutral edits are common; refusing them
  would trap the search on a plateau.
- *What does a duplicate cost?* One budget unit, no evaluation time.
