# Results so far

**Status: offline baselines only.** These numbers are for the no-LLM mutation proposer. The LLM
experiments come in Stage 4 and will be added here whatever they show.

Fitness = mean(tour length / 2-opt tour length) over the instances. Lower is better; 1.000 ties 2-opt.
Dev is what the search optimized; test is a held-out set it never saw.

## Experiment 1: blind mutation from nearest neighbor

```
loopforge experiment --budget 300 --seeds 10 --out runs/offline-nn
```

3 strategies x 10 seeds x 300 proposals = 9,000 proposals (about 3 minutes on 2 cores).

| Strategy | Runs | Best dev | Best test | Valid / invalid / dup % | Improvements |
|---|---|---|---|---|---|
| random | 10 | 1.1524 ± 0.0000 | 1.1504 ± 0.0000 | 20 / 41 / 39 | 0.0 |
| hill_climb | 10 | 1.1524 ± 0.0000 | 1.1504 ± 0.0000 | 40 / 54 / 6 | 0.0 |
| evolve | 10 | 1.1524 ± 0.0000 | 1.1504 ± 0.0000 | 34 / 59 / 7 | 0.0 |

Reference: nearest neighbor 1.1524 dev / 1.1504 test; 2-opt 1.0000.

**Result: not one of the 9,000 blind mutations beat nearest neighbor.**

This is not a bug. Of the 2,836 unique valid mutants, 907 scored exactly the same as the seed,
1,929 were worse, and 0 were better; they spread over 341 distinct fitness values, so the mutator
was producing real variety. The other proposals failed in many different ways (invalid tour, type
errors, undefined names, index errors, timeouts), all caught by the sandbox. Nearest neighbor
is a local optimum under small random code edits: getting from it to something better requires
*adding a new idea* (such as a local-search pass), which no single random edit can do.

## Experiment 2: sanity check from the worst baseline

```
loopforge experiment --seed-program random_order --budget 300 --seeds 5 --out runs/offline-random
```

Starting from `random_order` (fitness 4.456), all three strategies again found 0 improvements in
4,500 proposals. The seed is only a few lines long, so there are very few places to edit: 77% of the
memoryless strategy's proposals were duplicates of earlier ones.

## What these results do and do not say

- They show that **blind code mutation is a weak baseline here**, which is the point of having one.
  Any improvement the LLM makes is improvement that random edits could not find.
- They do **not** show that the three strategies are equivalent. The proposer gave them nothing to
  choose between. Strategy comparisons become meaningful only once a proposer can make progress.
- They do not show the search loop is broken: the loop's tests check that it finds, records and
  traces improvements when a proposer supplies them.
- Fair criticism: a mutator that knows nothing about TSP is a deliberately blind baseline. A tougher
  non-LLM baseline (hand-written TSP moves) would make the eventual comparison harder to dismiss.

Exact counts may differ slightly on other Python versions, because `ast.unparse` formatting changes
which proposals count as duplicates. The conclusion should not.

## Experiment 3: LLM-guided search

**Not run yet.** The LLM proposer is implemented and tested with fake replies, but no real model has
been evaluated, so there are no LLM numbers in this document. Planned: the same strategies, seeds and budget as
Experiment 1, with and without prompt hints (see [LLM.md](LLM.md)), reporting held-out test fitness, valid rate, tokens
and cost per improvement, whatever they show.
