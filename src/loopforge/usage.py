"""Token and cost accounting for LLM runs, computed from the logged programs.

Every LLM proposal stores its token counts in ``Program.info``, so spend can be
recomputed from ``programs.jsonl`` at any time. Replies served from the on-disk
cache are counted as calls but cost nothing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .archive import Program


def summarize_usage(programs: Iterable[Program]) -> dict:
    calls = cached = input_tokens = output_tokens = 0
    cost = seconds = 0.0
    for p in programs:
        info = p.info or {}
        if "input_tokens" not in info:
            continue
        calls += 1
        if info.get("cached"):
            cached += 1
            continue
        input_tokens += int(info.get("input_tokens", 0))
        output_tokens += int(info.get("output_tokens", 0))
        cost += float(info.get("cost_usd", 0.0))
        seconds += float(info.get("latency_s", 0.0))
    return {
        "llm_calls": calls, "cached_calls": cached, "input_tokens": input_tokens,
        "output_tokens": output_tokens, "cost_usd": round(cost, 6), "api_seconds": round(seconds, 2),
    }


def merge_usage(usages: Iterable[dict]) -> dict:
    total = summarize_usage([])
    for u in usages:
        for key in total:
            total[key] += u.get(key, 0)
    total["cost_usd"] = round(total["cost_usd"], 6)
    total["api_seconds"] = round(total["api_seconds"], 2)
    return total


def experiment_usage(out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    runs = json.loads((out_dir / "experiment.json").read_text())["runs"]
    usages = []
    for name in runs:
        path = out_dir / name / "summary.json"
        if path.exists():
            usages.append(json.loads(path.read_text()).get("usage", {}))
    return merge_usage(usages)


def format_usage(usage: dict, improvements: int | None = None) -> str:
    """A short human-readable block, or '' when no LLM calls were made."""
    if not usage or not usage.get("llm_calls"):
        return ""
    paid = usage["llm_calls"] - usage["cached_calls"]
    lines = [
        "LLM usage:",
        f"  calls: {usage['llm_calls']} ({paid} billed, {usage['cached_calls']} replayed from cache)",
        f"  tokens: {usage['input_tokens']:,} in, {usage['output_tokens']:,} out",
        f"  cost: ${usage['cost_usd']:.4f} (0 unless you set --price-in/--price-out)",
        f"  time waiting on the API: {usage['api_seconds']:.0f}s",
    ]
    if improvements:
        lines.append(f"  cost per improvement: ${usage['cost_usd'] / improvements:.4f}")
    return "\n".join(lines)
