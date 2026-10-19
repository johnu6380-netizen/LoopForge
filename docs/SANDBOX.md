# The sandbox: what it does and what it does not

Loopforge runs code written by a language model. Models write buggy code, so every
candidate runs in a separate process that cannot hang or crash the main program.

## How it works

```
 parent (trusted)                          child process (untrusted code)
 ----------------                          ------------------------------
 loopforge.sandbox  --- source+instances -->  sandbox_runner.py
                    <--- raw tours --------   runs solve() on each instance
 validate tours
 compute scores
```

1. **Separate process.** `python -I -B sandbox_runner.py`, in an empty temp directory, with an
   almost empty environment (so your API keys never reach candidate code).
2. **OS limits, applied by the child on itself** (Linux; partial on macOS; none on Windows):
   CPU seconds, address-space memory, no file writes, no core dumps.
3. **Per-instance alarm.** A timer interrupts runaway pure-Python loops after
   `per_instance_seconds` (default 2.0).
4. **Wall-clock backstop.** If the child does not finish within the total budget, the parent
   kills its whole process group. This also catches code that swallows the alarm.
5. **Quiet channel.** stdin/stdout/stderr point at /dev/null while candidate code runs, so
   `print` spam cannot corrupt results.
6. **Restricted namespace.** No `open`, `exec`, `eval`; imports of `os`, `sys`, `subprocess`,
   `socket`, etc. are refused.
7. **The parent trusts nothing.** The child only returns raw tours. The parent re-validates
   each tour and computes every length and score itself. A candidate cannot report its own
   score, and forged output lines just produce an invalid tour.

Run `loopforge doctor` to see which protections your machine actually enforces.

## What this is NOT

**It is not a security boundary against a determined attacker.** Items 5 and 6 are speed bumps.
For example, this candidate reaches the runner's own `os` module by climbing the call stack:

```python
def solve(points):
    try:
        raise ValueError
    except ValueError as e:
        g = e.__traceback__.tb_frame.f_back.f_globals   # the runner's globals
    ...                                                  # g["os"] is now reachable
```

This is a fundamental limit of sandboxing Python from inside Python. We verified it and
chose not to pretend otherwise.

## Threat model and why it is still reasonable

| Situation | Risk | Protection |
|-----------|------|------------|
| Searching with LLM-generated code on your own machine | The model writes a bug (infinite loop, huge allocation, noisy print). It is not trying to attack you. | Everything above. This is what the sandbox is built for. |
| Public demo, recruiters pick a candidate | Only candidates from our own recorded archive can be run. Visitors cannot submit code. | No untrusted code ever reaches the sandbox. |
| Public demo that accepts visitor code (not planned) | Real attackers | Would require a container or VM with no network, read-only filesystem, non-root user. Not built, and not claimed. |

When we deploy (Stage 6) the evaluator will also run in a container with no outbound
network, which closes the gaps above for the cases we actually support.

## Known limitations

- Memory and CPU limits are Linux-only in practice; Windows has only the wall-clock backstop.
- Timing is wall-clock, so a heavily loaded machine can make a borderline candidate look slow.
  The default limits are generous (2s per instance; 2-opt takes about 0.005s).
- Candidate code that uses `random` without a fixed seed can score slightly differently
  between runs. The search loop will re-evaluate winners to guard against this.
