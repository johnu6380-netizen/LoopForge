"""Tests for the LLM proposer. No test touches the network: replies come from fakes."""

import io
import json
import urllib.error

import pytest

from loopforge.archive import INVALID, VALID, Archive, Program
from loopforge.cli import main
from loopforge.llmclient import (
    HTTPClient, LLMAuthError, LLMConfigError, LLMError, LLMResponse, PRESETS, ResponseCache,
    load_dotenv, make_client,
)
from loopforge.proposers import MutationProposer, get_proposer
from loopforge.proposers.llm import (
    HINTS, LLMProposalError, LLMProposer, Pricing, build_llm_proposer, build_prompt, parse_response,
)
from loopforge.search import Search, SearchConfig
from loopforge.seeds import load_tsp_seed_source
from loopforge.usage import format_usage, summarize_usage

TINY = dict(sizes=(8, 14), per_size=2)
TWO_OPT = load_tsp_seed_source("two_opt")


def reply(code=TWO_OPT, desc="add 2-opt"):
    return f"DESCRIPTION: {desc}\n```python\n{code}\n```"


class FakeClient:
    """Returns canned replies in order and counts calls."""

    def __init__(self, replies, tokens=(100, 50)):
        self.replies, self.tokens, self.calls = list(replies), tokens, 0

    def complete(self, system, user, *, temperature, max_tokens):
        self.calls += 1
        if not self.replies:
            raise LLMError("fake client out of replies")
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return LLMResponse(item, *self.tokens)


def proposer(replies, **kw):
    kw.setdefault("model", "fake")
    return LLMProposer(FakeClient(replies), **kw)


def run(prop, budget=3, **kw):
    cfg = SearchConfig(**{**TINY, "budget": budget, **kw})
    return Search(cfg, prop).run()


# ---------- parsing ----------


def test_parse_extracts_code_and_description():
    source, desc = parse_response("Sure!\nDESCRIPTION: swapped to 2-opt\n```python\ndef solve(p):\n    return []\n```\nbye")
    assert source == "def solve(p):\n    return []\n" and desc == "swapped to 2-opt"


def test_parse_prefers_the_block_that_defines_solve():
    text = "```python\nprint('example')\n```\n```python\ndef solve(p):\n    return []\n```"
    assert "def solve" in parse_response(text)[0]


@pytest.mark.parametrize("bad", ["no code here", "```python\nx = 1\n```", "```python\ndef solve(p):\n    return []"])
def test_parse_rejects_unusable_replies(bad):
    with pytest.raises(ValueError):
        parse_response(bad)


# ---------- prompt ----------


def test_prompt_contains_parent_best_others_and_recent_errors():
    a = Archive()
    a.add(Program("p0000", None, 0, "def solve(p): return 'PARENT'", VALID, 1.15, {"25": 1.1}))
    a.add(Program("p0001", "p0000", 1, "def solve(p): return 'GOOD'", VALID, 1.05))
    a.add(Program("p0002", "p0000", 2, "", INVALID, error="invalid tour: city 3 appears more than once"))
    system, user = build_prompt(a.get("p0000"), a, hint="HINT-TEXT")
    assert "PARENT" in user and "GOOD" in user and "1.1500" in user
    assert "appears more than once" in user and "HINT-TEXT" in user
    assert "solve" in system or "Python" in system


def test_prompt_works_without_an_archive():
    parent = Program("p0", None, 0, "def solve(p): return []", VALID, 1.0)
    assert "def solve" in build_prompt(parent, None)[1]


# ---------- the proposer inside the real search loop ----------


def test_llm_proposals_flow_through_sandbox_and_evaluator():
    prop = proposer([reply(), reply(code="def solve(p):\n    return [0] * len(p)"), "I cannot help"])
    result = run(prop, budget=3)
    progs = list(result.archive)[1:]
    assert progs[0].status == VALID and progs[0].fitness < result.archive.get("p0000").fitness
    assert progs[1].status == INVALID and "more than once" in progs[1].error
    assert progs[2].status == INVALID and "unusable reply" in progs[2].error
    assert progs[0].description == "add 2-opt" and progs[0].proposer == "llm"
    assert result.archive.best().id == "p0001"


def test_token_usage_is_recorded_even_for_unusable_replies():
    result = run(proposer([reply(), "no code"]), budget=2)
    usage = result.summary["usage"]
    assert usage["llm_calls"] == 2
    assert usage["input_tokens"] == 200 and usage["output_tokens"] == 100


def test_cost_is_computed_from_pricing():
    prop = proposer([reply()], pricing=Pricing(1.0, 2.0))  # $1 / $2 per million tokens
    result = run(prop, budget=1)
    assert result.summary["usage"]["cost_usd"] == pytest.approx((100 * 1.0 + 50 * 2.0) / 1e6)


def test_spending_cap_stops_the_run_early_and_says_so():
    prop = proposer([reply()] * 10, pricing=Pricing(10.0, 10.0), max_cost_usd=0.002)
    result = run(prop, budget=10)
    s = result.summary
    assert s["stopped_early"] and s["counts"]["proposals"] < 10
    assert prop.client.calls == s["counts"]["proposals"]


def test_token_cap_also_stops_the_run():
    result = run(proposer([reply()] * 10, max_total_tokens=250), budget=10)
    assert result.summary["counts"]["proposals"] == 2  # 150 tokens per call


def test_failed_calls_cost_budget_but_the_run_continues():
    prop = proposer([LLMError("rate limited"), reply()])
    result = run(prop, budget=2)
    progs = list(result.archive)[1:]
    assert "LLM call failed" in progs[0].error and progs[1].status == VALID


def test_auth_failure_aborts_instead_of_burning_the_budget():
    with pytest.raises(LLMAuthError):
        run(proposer([LLMAuthError("bad key")]), budget=3)


def test_repeated_failures_abort():
    prop = proposer([LLMError("down")] * 10, max_consecutive_failures=3)
    with pytest.raises(LLMError, match="3 LLM calls failed in a row"):
        run(prop, budget=10)


def test_same_seed_same_prompts_and_hints_are_seed_controlled():
    def prompts(seed):
        seen = []

        class Spy(FakeClient):
            def complete(self, system, user, **kw):
                seen.append(user)
                return super().complete(system, user, **kw)

        Search(SearchConfig(**TINY, budget=4, seed=seed), LLMProposer(Spy(["x"] * 4), model="m")).run()
        return seen

    assert prompts(1) == prompts(1)
    assert prompts(1) != prompts(2)


def test_hints_can_be_disabled():
    seen = []

    class Spy(FakeClient):
        def complete(self, system, user, **kw):
            seen.append(user)
            return super().complete(system, user, **kw)

    run(LLMProposer(Spy(["x"]), model="m", use_hints=False), budget=1)
    assert not any(h in seen[0] for h in HINTS)


# ---------- cache and throttle ----------


def test_cache_replays_identical_requests_for_free(tmp_path):
    def go():
        prop = LLMProposer(FakeClient([reply()]), model="m", cache=ResponseCache(tmp_path), pricing=Pricing(1, 1))
        return prop, run(prop, budget=1, seed=5)

    first, r1 = go()
    second, r2 = go()  # FakeClient has a reply queued, but must not be called
    assert first.client.calls == 1 and second.client.calls == 0
    assert r2.summary["usage"]["cached_calls"] == 1 and r2.summary["usage"]["cost_usd"] == 0
    assert list(r1.archive)[1].source == list(r2.archive)[1].source
    assert second.spent_usd == 0


def test_throttle_spaces_calls():
    now, sleeps = [0.0], []
    prop = LLMProposer(FakeClient([reply(), reply()]), model="m", min_interval=5.0,
                       clock=lambda: now[0], sleep=lambda s: sleeps.append(s))
    parent = Program("p0", None, 0, "def solve(p): return []", VALID, 1.0)
    import random

    prop.propose(parent, None, random.Random(0))
    now[0] = 2.0
    prop.propose(parent, None, random.Random(1))
    assert sleeps == [pytest.approx(3.0)]


# ---------- HTTP client (fake transport, no network) ----------


def http_error(code, body=b"", headers=None):
    return urllib.error.HTTPError("http://x", code, "err", headers or {}, io.BytesIO(body))


def client_with(transport, provider="groq", **kw):
    return HTTPClient(PRESETS[provider], "m", "sk-SECRET", transport=transport, sleep=lambda s: None, **kw)


OPENAI_OK = {"choices": [{"message": {"content": "hello"}}], "usage": {"prompt_tokens": 7, "completion_tokens": 3}}
ANTHROPIC_OK = {"content": [{"type": "text", "text": "hi"}], "usage": {"input_tokens": 4, "output_tokens": 2}}


def test_openai_format_request_and_response():
    seen = {}

    def transport(url, headers, payload, timeout):
        seen.update(url=url, headers=headers, payload=payload)
        return OPENAI_OK

    r = client_with(transport).complete("sys", "usr", temperature=0.5, max_tokens=99)
    assert (r.text, r.input_tokens, r.output_tokens) == ("hello", 7, 3)
    assert seen["url"].endswith("/chat/completions") and seen["headers"]["Authorization"] == "Bearer sk-SECRET"
    assert seen["payload"]["messages"][0] == {"role": "system", "content": "sys"}


def test_anthropic_format_request_and_response():
    seen = {}

    def transport(url, headers, payload, timeout):
        seen.update(url=url, headers=headers, payload=payload)
        return ANTHROPIC_OK

    r = client_with(transport, "anthropic").complete("sys", "usr", temperature=0.5, max_tokens=99)
    assert (r.text, r.input_tokens, r.output_tokens) == ("hi", 4, 2)
    assert seen["url"].endswith("/messages") and seen["headers"]["x-api-key"] == "sk-SECRET"
    assert seen["payload"]["system"] == "sys"


def test_rate_limit_is_retried_with_backoff():
    calls, sleeps = [], []

    def transport(*a):
        calls.append(1)
        if len(calls) < 3:
            raise http_error(429, headers={"Retry-After": "7"})
        return OPENAI_OK

    c = HTTPClient(PRESETS["groq"], "m", "k", transport=transport, sleep=sleeps.append)
    assert c.complete("s", "u", temperature=0, max_tokens=1).text == "hello"
    assert len(calls) == 3 and sleeps == [7.0, 7.0]


def test_gives_up_after_max_retries():
    c = client_with(lambda *a: (_ for _ in ()).throw(http_error(503)), max_retries=2)
    with pytest.raises(LLMError, match="HTTP 503"):
        c.complete("s", "u", temperature=0, max_tokens=1)


def test_auth_errors_are_not_retried():
    calls = []

    def transport(*a):
        calls.append(1)
        raise http_error(401)

    with pytest.raises(LLMAuthError):
        client_with(transport).complete("s", "u", temperature=0, max_tokens=1)
    assert len(calls) == 1


def test_network_errors_and_garbage_replies_become_llm_errors():
    with pytest.raises(LLMError, match="network"):
        client_with(lambda *a: (_ for _ in ()).throw(TimeoutError()), max_retries=1).complete("s", "u", temperature=0, max_tokens=1)
    with pytest.raises(LLMError, match="shape"):
        client_with(lambda *a: {"nope": 1}).complete("s", "u", temperature=0, max_tokens=1)
    with pytest.raises(LLMError, match="empty"):
        client_with(lambda *a: {"choices": [{"message": {"content": ""}}]}).complete("s", "u", temperature=0, max_tokens=1)


def test_the_api_key_never_leaks_into_errors_or_repr():
    c = client_with(lambda *a: (_ for _ in ()).throw(http_error(400, b"bad request")))
    with pytest.raises(LLMError) as exc:
        c.complete("s", "u", temperature=0, max_tokens=1)
    assert "sk-SECRET" not in str(exc.value) and "sk-SECRET" not in repr(c)


# ---------- configuration ----------


def test_missing_key_gives_a_helpful_error(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(LLMConfigError, match="GEMINI_API_KEY"):
        get_proposer("llm", {"provider": "gemini"})


def test_key_comes_from_the_environment_and_model_can_be_overridden(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GROQ_API_KEY", "k")
    p = build_llm_proposer({"provider": "groq", "model": "my-model", "cache": False})
    assert p.model == "my-model" and p.cache is None and p.min_interval == PRESETS["groq"].min_interval


def test_dotenv_is_loaded_but_never_overrides_the_environment(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("# comment\nFOO_KEY='abc'\nBAR_KEY=real\n")
    monkeypatch.setenv("BAR_KEY", "from-env")
    monkeypatch.delenv("FOO_KEY", raising=False)
    load_dotenv(tmp_path / ".env")
    import os

    assert os.environ["FOO_KEY"] == "abc" and os.environ["BAR_KEY"] == "from-env"
    monkeypatch.delenv("FOO_KEY")


def test_ollama_needs_no_key(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    client, model, _ = make_client("ollama")
    assert model


def test_unknown_provider_and_unknown_proposer():
    with pytest.raises(LLMConfigError, match="unknown provider"):
        make_client("nope")
    with pytest.raises(ValueError, match="unknown proposer"):
        get_proposer("nope")


def test_offline_proposer_still_works_without_any_key(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for k in PRESETS.values():
        monkeypatch.delenv(k.key_env or "X", raising=False)
    assert get_proposer("mutation").name == "mutation"
    assert isinstance(get_proposer("mutation", {}), MutationProposer)
    assert run(MutationProposer(), budget=3)  # the whole loop, no key anywhere


def test_config_with_proposer_options_round_trips_and_has_no_secrets():
    cfg = SearchConfig(**TINY, proposer="llm", proposer_options={"provider": "groq", "model": "m"})
    data = json.loads(json.dumps(cfg.to_dict()))
    assert SearchConfig.from_dict(data).proposer_options == {"provider": "groq", "model": "m"}


# ---------- usage + CLI ----------


def test_usage_summary_and_format():
    progs = [
        Program("a", None, 0, "", VALID, 1.0),  # seed: no LLM info
        Program("b", "a", 1, "", VALID, 1.0, info={"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.5, "latency_s": 1.0}),
        Program("c", "a", 2, "", VALID, 1.0, info={"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.0, "cached": True}),
    ]
    u = summarize_usage(progs)
    assert u["llm_calls"] == 2 and u["cached_calls"] == 1 and u["input_tokens"] == 10 and u["cost_usd"] == 0.5
    assert "1 billed, 1 replayed" in format_usage(u)
    assert format_usage(summarize_usage([])) == ""


def test_cli_show_prompt_needs_no_key(capsys):
    assert main(["llm-check", "--show-prompt"]) == 0
    assert "## Task" in capsys.readouterr().out


def test_cli_search_with_llm_and_no_key_fails_politely(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    code = main(["search", "--proposer", "llm", "--budget", "2", "--out", str(tmp_path / "runs"),
                 "--sizes", "8,14", "--per-size", "2"])
    assert code == 2 and "GEMINI_API_KEY" in capsys.readouterr().err


def test_cli_llm_check_end_to_end_with_a_fake_transport(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GROQ_API_KEY", "k")
    fake = {"choices": [{"message": {"content": reply()}}], "usage": {"prompt_tokens": 9, "completion_tokens": 4}}
    import loopforge.llmclient as lc

    monkeypatch.setattr(lc, "urllib_transport", lambda *a: fake)
    assert main(["llm-check", "--provider", "groq"]) == 0
    out = capsys.readouterr().out
    assert "Program is valid" in out and "9 in, 4 out" in out
