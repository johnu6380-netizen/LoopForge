# Loopforge architecture

## The loop

```
   +-----------+     +------------+     +-----------+     +-----------+
   |  Archive  | --> |  Proposer  | --> |  Sandbox  | --> | Evaluator |
   | (best     |     | (LLM or    |     | (limits   |     | (validate |
   |  programs)|     |  mutation) |     |  time/mem)|     |  + score) |
   +-----------+     +------------+     +-----------+     +-----------+
         ^                                                       |
         +-------------------- keep if good ---------------------+
```

1. Pick a parent program from the archive.
2. The **proposer** returns a modified version of its source code.
3. The **sandbox** runs it in an isolated subprocess with time and memory limits.
4. The **evaluator** validates the tours and computes fitness.
5. If it is valid and good, it enters the archive. Everything is logged.

## Design decisions (and why)

**Candidates are source code, not functions.** Seeds, LLM output and archive entries are all
plain strings. That makes them storable, diffable, replayable and sandboxable.

**All-or-nothing validity.** One bad instance makes the whole candidate invalid. A heuristic
that sometimes returns garbage is not usable, and partial credit would let the search exploit it.

**Strict validator.** `type(city) is int` rejects `True`/`False`; floats, duplicates, and
out-of-range indices are all rejected. The evaluator never trusts the candidate.

**Dev vs. test sets.** The search only sees the dev set. Final reported numbers use the test
set (disjoint seeds), so the results are not inflated by overfitting.

**Fitness relative to 2-opt.** `mean(length / 2-opt length)`. This is easy to interpret:
below 1.0 beats 2-opt. For random uniform instances the true optimum is roughly 5% below
2-opt, so there is real headroom but not unlimited.

**The parent never trusts the child.** The sandbox returns raw tours only; the parent validates
them and computes every score. A candidate cannot grade itself. Details and honest limits in
[SANDBOX.md](SANDBOX.md).

**Fail fast.** Evaluation stops at the first invalid instance, since the candidate is already
disqualified. This keeps broken LLM proposals cheap.

**Strategy and proposer are separate.** The strategy picks which program to improve; the proposer
produces the new program. Either can be swapped without touching the other, which is what makes
"is it the search or the model?" a question we can actually answer. See [SEARCH.md](SEARCH.md).

**Budget counts proposals.** Invalid proposals, duplicates and proposer failures all cost one unit,
so strategies and proposers are compared at equal cost, the way API calls would be billed.

**The LLM is a plug-in.** A deterministic mutation proposer makes tests, CI, and baseline
comparisons work offline. The LLM proposer is another implementation of the same interface, built
on the standard library only, working with free-tier providers. Its tests use fake replies, never the network.

**Spend is a first-class output.** Token counts are stored per program, replies are cached on disk, and
runs can be capped by tokens or dollars, so comparisons can be made at equal cost as well as equal proposals.

**Honest comparison.** Planned experiment: LLM-guided search vs. random mutation vs.
hill-climbing, same evaluation budget, several seeds, final numbers on the test set. If the
LLM does not win, we report that.

## Roadmap

| Stage | Contents | Status |
|-------|----------|--------|
| 1 | Task, validator, scoring, baselines, tests | done |
| 2 | Sandbox: subprocess isolation, timeouts, memory limits | done |
| 3 | Archive, parent selection, baseline searchers, run logging | done |
| 4 | LLM proposer (free tiers), cost tracking, reply cache | code done; see [LLM.md](LLM.md) |
| 4b | Real LLM experiments and write-up in RESULTS.md | next |
| 5 | FastAPI backend + React UI (replay, lineage tree, live evaluator) | |
| 6 | CI, deployment, final README with real results | |

## Known limitations

- The sandbox contains buggy code, not malicious code. Python-level restrictions can be bypassed
  (verified; see SANDBOX.md). Deployment will add a container.
- OS memory/CPU limits are Linux-only in practice.
- `compile_candidate` and `evaluate(..., sandboxed=False)` run in-process and are for trusted
  seed code only.
