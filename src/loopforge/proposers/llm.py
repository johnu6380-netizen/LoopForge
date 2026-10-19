"""The LLM proposer: asks a language model for an improved version of a program.

It implements the same interface as the mutation proposer, so the search loop,
sandbox and evaluator treat its output exactly like any other candidate. The
model never sees the instances or the scoring code, only a description of the task
and the source of a few programs from the archive.

Cost controls: every reply is cached on disk, calls are spaced to respect free-tier
rate limits, and a run can be capped by dollars and/or tokens.
"""

from __future__ import annotations

import os
import random
import re
import time
from dataclasses import dataclass
from typing import Callable

from ..archive import INVALID, Archive, Program
from ..llmclient import (
    PRESETS, LLMAuthError, LLMClient, LLMError, LLMResponse, ResponseCache, make_client,
)
from .base import Proposal, ProposalError


class LLMProposalError(ProposalError):
    """A proposal failed; ``info`` still carries token usage so spend is never lost."""

    def __init__(self, message: str, info: dict | None = None) -> None:
        super().__init__(message)
        self.info = info or {}


@dataclass(frozen=True)
class Pricing:
    """USD per million tokens. Leave at 0 for free tiers and local models."""

    input_per_million: float = 0.0
    output_per_million: float = 0.0

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.input_per_million + output_tokens * self.output_per_million) / 1e6


SYSTEM_PROMPT = (
    "You are an expert in combinatorial optimization and Python. You improve heuristics for the "
    "Euclidean Traveling Salesman Problem. You reply with one complete Python program and nothing "
    "else except a one-line description."
)

# Optional nudges, one picked at random per proposal. They add domain knowledge, so the
# experiment can switch them off (--no-hints) for a cleaner "model alone" comparison.
HINTS = [
    "Add a local-search improvement pass after the tour is built.",
    "Try a different construction method (for example greedy edge matching or cheapest insertion).",
    "Try moves other than 2-opt, such as relocating a short segment elsewhere (Or-opt).",
    "Make the existing improvement steps cheaper (precomputed distances, neighbor lists, early exits).",
    "Try several starting cities and keep the best tour (it must stay deterministic).",
    "Fix whatever weakness you see in the current program; use your own judgement.",
]

TASK = """\
## Task
Improve a heuristic for the Euclidean Traveling Salesman Problem.
The program must define `solve(points)`. `points` is a list of (x, y) tuples in the unit square.
Return a list containing every city index 0..n-1 exactly once (a closed tour). Shorter is better.

## Scoring
Score = mean over many instances (n from about 25 to 100) of
(your tour length) / (tour length of a plain 2-opt reference). 1.0 ties 2-opt; lower is better.
A program that returns an invalid tour, raises an exception, or takes more than about one
second on an instance is INVALID and scores nothing.

## Rules
- Python standard library only. Imports such as math, random, itertools, heapq are fine;
  os, sys, io, files and network access are blocked.
- Deterministic: the same input must give the same tour (seed any randomness, e.g. random.Random(0)).
- Return plain Python ints. Define everything in one file with a top-level `solve`.
"""

FORMAT = """\
## Answer format
First line: `DESCRIPTION: <one sentence: what you changed and why>`
Then ONE ```python code block with the COMPLETE new program (not a diff).
"""

_FENCE = re.compile(r"```[ \t]*(?:python|py)?[ \t]*\r?\n(.*?)```", re.S | re.I)
_DESC = re.compile(r"^\s*DESCRIPTION:\s*(.+)$", re.M | re.I)


def _fmt_score(program: Program) -> str:
    sizes = ", ".join(f"n={n}: {v:.3f}" for n, v in program.by_size.items())
    return f"score {program.fitness:.4f}" + (f"; by size: {sizes}" if sizes else "")


def _clip(source: str, limit: int) -> str:
    return source if len(source) <= limit else source[:limit] + "\n# ... (truncated)"


def build_prompt(
    parent: Program,
    archive: Archive | None,
    *,
    hint: str | None = None,
    n_inspirations: int = 2,
    n_failures: int = 3,
    max_source_chars: int = 6000,
) -> tuple[str, str]:
    """Return (system, user) prompts for improving ``parent``."""
    parts = [TASK, f"## Current program ({_fmt_score(parent) if parent.fitness is not None else 'unscored'})",
             f"```python\n{_clip(parent.source, max_source_chars)}\n```"]

    if archive is not None and n_inspirations > 0:
        others = sorted(
            (p for p in archive.valid() if p.id != parent.id and p.fitness is not None),
            key=lambda p: p.fitness,
        )[:n_inspirations]
        if others:
            parts.append("## Other programs found so far (for inspiration)")
            for p in others:
                parts.append(f"Program with {_fmt_score(p)}:\n```python\n{_clip(p.source, max_source_chars)}\n```")

    if archive is not None and n_failures > 0:
        seen: list[str] = []
        for p in reversed(list(archive)):
            if p.status == INVALID and p.error and not p.error.startswith("proposal failed"):
                msg = " ".join(p.error.split())[:150]
                if msg not in seen:
                    seen.append(msg)
            if len(seen) >= n_failures:
                break
        if seen:
            parts.append("## Recent failed attempts (avoid these mistakes)\n" + "\n".join(f"- {m}" for m in seen))

    if hint:
        parts.append(f"## Suggested direction\n{hint}")
    parts.append(FORMAT)
    return SYSTEM_PROMPT, "\n".join(parts)


def parse_response(text: str) -> tuple[str, str]:
    """Pull (source, description) out of a model reply. Raises ValueError if unusable."""
    blocks = [b for b in _FENCE.findall(text) if re.search(r"^\s*(def solve\b|solve\s*=)", b, re.M)]
    if not blocks:
        raise ValueError("no ```python block defining solve() (reply may have been cut off)")
    source = max(blocks, key=len).strip() + "\n"
    match = _DESC.search(text)
    description = match.group(1).strip().strip("`")[:200] if match else "LLM edit"
    return source, description


class LLMProposer:
    name = "llm"

    def __init__(
        self,
        client: LLMClient,
        *,
        model: str,
        provider: str = "custom",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        pricing: Pricing = Pricing(),
        max_cost_usd: float | None = None,
        max_total_tokens: int | None = None,
        cache: ResponseCache | None = None,
        min_interval: float = 0.0,
        use_hints: bool = True,
        n_inspirations: int = 2,
        max_consecutive_failures: int = 5,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.client = client
        self.model = model
        self.provider = provider
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.pricing = pricing
        self.max_cost_usd = max_cost_usd
        self.max_total_tokens = max_total_tokens
        self.cache = cache
        self.min_interval = min_interval
        self.use_hints = use_hints
        self.n_inspirations = n_inspirations
        self.max_consecutive_failures = max_consecutive_failures
        self._sleep = sleep
        self._clock = clock
        self._last_call: float | None = None
        self._failures = 0
        self.spent_usd = 0.0
        self.billed_tokens = 0

    @property
    def exhausted(self) -> bool:
        """True once a spending cap is hit; the search loop stops asking for proposals."""
        return (
            (self.max_cost_usd is not None and self.spent_usd >= self.max_cost_usd)
            or (self.max_total_tokens is not None and self.billed_tokens >= self.max_total_tokens)
        )

    def _throttle(self) -> None:
        if self._last_call is not None and self.min_interval > 0:
            wait = self.min_interval - (self._clock() - self._last_call)
            if wait > 0:
                self._sleep(wait)

    def _call(self, system: str, user: str) -> tuple[LLMResponse, float]:
        key = ResponseCache.key(self.provider, self.model, self.temperature, self.max_tokens, system, user)
        if self.cache is not None:
            hit = self.cache.get(key)
            if hit is not None:
                hit.cached = True
                return hit, 0.0
        self._throttle()
        start = self._clock()
        response = self.client.complete(system, user, temperature=self.temperature, max_tokens=self.max_tokens)
        self._last_call = self._clock()
        self.spent_usd += self.pricing.cost(response.input_tokens, response.output_tokens)
        self.billed_tokens += response.input_tokens + response.output_tokens
        if self.cache is not None:
            self.cache.put(key, response)
        return response, self._last_call - start

    def propose(self, parent: Program, archive: Archive | None, rng: random.Random) -> Proposal:
        if self.exhausted:
            raise LLMProposalError("spending cap reached")
        hint = rng.choice(HINTS) if self.use_hints else None
        system, user = build_prompt(parent, archive, hint=hint, n_inspirations=self.n_inspirations)
        try:
            response, latency = self._call(system, user)
        except LLMAuthError:
            raise
        except LLMError as exc:
            self._failures += 1
            if self._failures >= self.max_consecutive_failures:
                raise LLMError(f"{self._failures} LLM calls failed in a row; last error: {exc}") from None
            raise LLMProposalError(f"LLM call failed: {exc}") from None
        self._failures = 0

        cost = 0.0 if response.cached else self.pricing.cost(response.input_tokens, response.output_tokens)
        info = {
            "provider": self.provider, "model": self.model, "hint": hint,
            "input_tokens": response.input_tokens, "output_tokens": response.output_tokens,
            "cost_usd": cost, "cached": response.cached, "latency_s": round(latency, 3),
        }
        try:
            source, description = parse_response(response.text)
        except ValueError as exc:
            raise LLMProposalError(f"unusable reply: {exc}", info) from None
        return Proposal(source, description, info)


def build_llm_proposer(options: dict | None = None, *, transport=None, sleep=time.sleep) -> LLMProposer:
    """Create the proposer from plain options (as stored in config.json; never contains secrets)."""
    o = dict(options or {})
    provider = o.get("provider") or os.environ.get("LOOPFORGE_PROVIDER") or "gemini"
    client, model, preset = make_client(provider, o.get("model"), transport=transport, sleep=sleep)
    use_cache = o.get("cache", True)
    cache = ResponseCache(o.get("cache_dir") or os.environ.get("LOOPFORGE_CACHE_DIR") or ".loopforge_cache") if use_cache else None
    interval = o.get("min_interval")
    return LLMProposer(
        client,
        model=model,
        provider=provider,
        temperature=float(o.get("temperature", 0.7)),
        max_tokens=int(o.get("max_tokens", 4096)),
        pricing=Pricing(float(o.get("price_in", 0.0)), float(o.get("price_out", 0.0))),
        max_cost_usd=o.get("max_cost_usd"),
        max_total_tokens=o.get("max_total_tokens"),
        cache=cache,
        min_interval=preset.min_interval if interval is None else float(interval),
        use_hints=bool(o.get("use_hints", True)),
        sleep=sleep,
    )


__all__ = ["HINTS", "LLMProposer", "LLMProposalError", "Pricing", "build_llm_proposer",
           "build_prompt", "parse_response", "PRESETS"]
