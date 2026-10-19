# Using an LLM with Loopforge (Stage 4)

The LLM proposer asks a model for an improved version of a program. Everything after that
(sandbox, validator, scoring, archive, held-out test set) is unchanged, so the model gets no
special treatment: its programs must survive exactly the same checks as random mutations.
Without an API key, Loopforge still runs with the offline `mutation` proposer.

## 1. Get a free API key (pick one)

| Provider | Where | Env variable | Notes |
|---|---|---|---|
| `gemini` (default) | https://aistudio.google.com/apikey | `GEMINI_API_KEY` | free tier, no card; rate limits apply |
| `groq` | https://console.groq.com/keys | `GROQ_API_KEY` | free tier, fast |
| `openrouter` | https://openrouter.ai/keys | `OPENROUTER_API_KEY` | has `:free` models |
| `ollama` | https://ollama.com | none | runs on your own machine, costs nothing |
| `openai`, `anthropic` | their consoles | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | paid; use the spending caps below |

Free-tier limits and model names change often. If a call fails with "model not found" or HTTP 429,
check the provider's current docs and pass `--model <name>`. The built-in defaults are only starting points.

## 2. Give Loopforge the key (never put it in code)

Create a file named `.env` in the project folder (it is already git-ignored):

```
GEMINI_API_KEY=paste-your-key-here
```

or set it in your terminal for the current session (Mac/Linux `export GEMINI_API_KEY=...`,
Windows PowerShell `$env:GEMINI_API_KEY="..."`). The key is read only from the environment. It is not
written to configs, run logs, the reply cache or error messages, and the sandbox hides it from candidate code.

## 3. Try it in three steps (cheap first)

```
loopforge llm-check --show-prompt         # no key, no cost: see exactly what the model is asked
loopforge llm-check                       # ONE real call; shows tokens and whether the program is valid
loopforge search --proposer llm --budget 30 --strategy hill_climb
```

Use another provider with `--provider groq`, another model with `--model ...`, or set
`LOOPFORGE_PROVIDER` / `LOOPFORGE_MODEL` once.

## 4. Controlling cost

| Control | How |
|---|---|
| Free tiers | Default prices are 0, so the cost shows as $0; token counts are still tracked. |
| Token cap per run | `--max-tokens 200000`: the run stops early and says so. |
| Dollar cap per run | `--max-cost 0.50 --price-in 0.15 --price-out 0.60` (USD per million tokens, from your provider's price list). Loopforge does not guess prices. |
| Reply cache | Every reply is stored in `.loopforge_cache/`. Re-running the same search replays it for free and gets identical results. Disable with `--no-cache`. |
| Rate limits | Calls are spaced per provider (`--min-interval` to change); 429/5xx errors are retried with backoff. |
| Bad keys | A rejected key stops the run immediately instead of wasting the budget. |

Caps apply per run. An experiment of 3 strategies x 5 seeds x 60 proposals is 900 calls, so run the
small search first and check your provider's daily quota. If an experiment stops, run the same command again: finished
calls are served from the cache.

`loopforge report <dir>` prints calls, tokens, cost and cost per improvement. These come from
`Program.info` in `programs.jsonl`, so they can be recomputed from the logs at any time.

## 5. What the model sees, and what it does not

It sees: the task description, the scoring rule (ratio against 2-opt), the parent program with its dev score,
the best two other programs in the archive, the last few error messages, and optionally a one-line
suggested direction. It does not see the instances, the test set, or the evaluator code.

**Hints are a confound.** The suggested directions ("try Or-opt", "add local search") put TSP knowledge in the prompt.
That is fine for building the best program, but for the research question ("does the model alone beat blind
mutation?") run once with `--no-hints` as well and report both.

## 6. Reproducibility and honest limits

- Hints and parent choice depend on `--seed`; the model's replies do not. Exact reruns are reproducible only
  through the cache (commit or archive the cache folder with a published experiment).
- Model providers change models silently. `config.json` and every program record the model name; treat results
  as "this model, this month".
- A single model, one task, dev scores optimized on 12 instances: report the held-out test numbers, and run several seeds.
