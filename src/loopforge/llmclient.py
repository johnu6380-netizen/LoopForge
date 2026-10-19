"""Minimal LLM clients built on the standard library only (no SDKs, no extra installs).

Two wire formats cover almost every provider:

* "openai":    the OpenAI chat-completions format. Also spoken by Gemini, Groq,
               OpenRouter and Ollama (local), so one client serves all of them.
* "anthropic": the Anthropic messages format.

API keys are read from environment variables (or a git-ignored ``.env`` file) and
are never written to logs, configs, caches or error messages.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


class LLMError(Exception):
    """An LLM call failed (network, rate limit, unusable response)."""


class LLMConfigError(LLMError):
    """The LLM is not set up (missing key, unknown provider)."""


class LLMAuthError(LLMError):
    """The provider rejected the key. Never retried: retrying cannot help."""


@dataclass
class LLMResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached: bool = False


class LLMClient(Protocol):
    def complete(self, system: str, user: str, *, temperature: float, max_tokens: int) -> LLMResponse: ...


@dataclass(frozen=True)
class Preset:
    name: str
    kind: str  # "openai" or "anthropic" wire format
    base_url: str
    key_env: str  # environment variable holding the key ("" = no key needed)
    default_model: str  # a default only: model names change, override with --model
    min_interval: float  # seconds between calls, to stay under typical free-tier rate limits


PRESETS: dict[str, Preset] = {
    p.name: p
    for p in (
        Preset("gemini", "openai", "https://generativelanguage.googleapis.com/v1beta/openai",
               "GEMINI_API_KEY", "gemini-2.5-flash", 6.5),
        Preset("groq", "openai", "https://api.groq.com/openai/v1",
               "GROQ_API_KEY", "llama-3.3-70b-versatile", 2.5),
        Preset("openrouter", "openai", "https://openrouter.ai/api/v1",
               "OPENROUTER_API_KEY", "meta-llama/llama-3.3-70b-instruct:free", 3.5),
        Preset("openai", "openai", "https://api.openai.com/v1",
               "OPENAI_API_KEY", "gpt-4o-mini", 0.0),
        Preset("anthropic", "anthropic", "https://api.anthropic.com/v1",
               "ANTHROPIC_API_KEY", "claude-haiku-5-5", 0.0),
        Preset("ollama", "openai", "http://localhost:11434/v1",
               "", "qwen2.5-coder:7b", 0.0),
    )
}

RETRYABLE = {408, 409, 429, 500, 502, 503, 504}

Transport = Callable[[str, dict, dict, float], dict]


def load_dotenv(path: str | Path = ".env") -> None:
    """Load KEY=VALUE lines from a .env file into os.environ (existing variables win)."""
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def urllib_transport(url: str, headers: dict, payload: dict, timeout: float) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", "replace").strip()
    except Exception:  # noqa: BLE001 - best effort only
        return ""


def _retry_after(exc: urllib.error.HTTPError) -> float | None:
    try:
        return min(float(exc.headers.get("Retry-After")), 60.0)
    except (AttributeError, TypeError, ValueError):
        return None


class HTTPClient:
    def __init__(
        self,
        preset: Preset,
        model: str,
        api_key: str,
        *,
        base_url: str | None = None,
        transport: Transport | None = None,
        timeout: float = 120.0,
        max_retries: int = 4,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.preset = preset
        self.model = model
        self._api_key = api_key
        self.base_url = (base_url or preset.base_url).rstrip("/")
        self.transport = transport or urllib_transport
        self.timeout = timeout
        self.max_retries = max_retries
        self._sleep = sleep

    def __repr__(self) -> str:  # never show the key
        return f"HTTPClient({self.preset.name}, model={self.model!r})"

    # -- request / response shapes --

    def _request(self, system: str, user: str, temperature: float, max_tokens: int):
        if self.preset.kind == "anthropic":
            headers = {"x-api-key": self._api_key, "anthropic-version": "2023-06-01"}
            payload = {
                "model": self.model, "system": system, "temperature": temperature,
                "max_tokens": max_tokens, "messages": [{"role": "user", "content": user}],
            }
            return f"{self.base_url}/messages", headers, payload
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        payload = {
            "model": self.model, "temperature": temperature, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        return f"{self.base_url}/chat/completions", headers, payload

    def _parse(self, data: dict) -> LLMResponse:
        try:
            if self.preset.kind == "anthropic":
                text = "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
                usage = data.get("usage") or {}
                tokens = (usage.get("input_tokens", 0), usage.get("output_tokens", 0))
            else:
                content = data["choices"][0]["message"]["content"]
                if isinstance(content, list):  # some providers return content parts
                    content = "".join(part.get("text", "") for part in content)
                text = content or ""
                usage = data.get("usage") or {}
                tokens = (usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
        except (KeyError, IndexError, TypeError, AttributeError):
            raise LLMError(f"unexpected response shape from {self.preset.name}") from None
        if not text.strip():
            raise LLMError("empty reply (the model may have used up max_tokens while 'thinking')")
        return LLMResponse(text, int(tokens[0] or 0), int(tokens[1] or 0))

    # -- the call, with retries --

    def complete(self, system: str, user: str, *, temperature: float, max_tokens: int) -> LLMResponse:
        url, headers, payload = self._request(system, user, temperature, max_tokens)
        delay = 2.0
        name = self.preset.name
        for attempt in range(self.max_retries + 1):
            last = attempt == self.max_retries
            try:
                return self._parse(self.transport(url, headers, payload, self.timeout))
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403):
                    hint = f" Check {self.preset.key_env}." if self.preset.key_env else ""
                    raise LLMAuthError(f"{name} rejected the request (HTTP {exc.code}).{hint}") from None
                if exc.code not in RETRYABLE or last:
                    raise LLMError(f"HTTP {exc.code} from {name}: {_error_body(exc)[:200]}") from None
                wait = _retry_after(exc) or delay
            except ValueError:  # includes JSON decoding errors
                raise LLMError(f"unreadable (non-JSON) reply from {name}") from None
            except OSError as exc:  # network down, DNS, timeout
                if last:
                    raise LLMError(f"network error talking to {name}: {type(exc).__name__}") from None
                wait = delay
            self._sleep(wait)
            delay = min(delay * 2, 30.0)
        raise LLMError("unreachable")  # pragma: no cover


def resolve_model(provider: str, model: str | None = None) -> str | None:
    """The model that will be used: explicit > LOOPFORGE_MODEL > the provider's default."""
    preset = PRESETS.get(provider)
    return model or os.environ.get("LOOPFORGE_MODEL") or (preset.default_model if preset else None)


def make_client(
    provider: str,
    model: str | None = None,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    transport: Transport | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[HTTPClient, str, Preset]:
    preset = PRESETS.get(provider)
    if preset is None:
        raise LLMConfigError(f"unknown provider {provider!r}; choose one of {sorted(PRESETS)}")
    load_dotenv()
    key = api_key or (os.environ.get(preset.key_env, "") if preset.key_env else "")
    if preset.key_env and not key:
        raise LLMConfigError(
            f"No API key found for {provider}. Set the {preset.key_env} environment variable "
            "or put it in a .env file (see docs/LLM.md)."
        )
    chosen = resolve_model(provider, model)
    url = base_url or os.environ.get("LOOPFORGE_BASE_URL")
    client = HTTPClient(preset, chosen, key, base_url=url, transport=transport, sleep=sleep)  # type: ignore[arg-type]
    return client, chosen, preset  # type: ignore[return-value]


class ResponseCache:
    """Replies stored on disk, keyed by a hash of everything that shaped the request.

    Re-running an identical search replays the stored replies: free, instant, and
    exactly reproducible. The key never includes the API key.
    """

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)

    @staticmethod
    def key(*parts: object) -> str:
        return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()

    def get(self, key: str) -> LLMResponse | None:
        path = self.directory / f"{key}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return LLMResponse(data["text"], int(data["input_tokens"]), int(data["output_tokens"]))
        except (OSError, ValueError, KeyError):
            return None

    def put(self, key: str, response: LLMResponse) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        tmp = self.directory / f"{key}.tmp"
        tmp.write_text(json.dumps(
            {"text": response.text, "input_tokens": response.input_tokens,
             "output_tokens": response.output_tokens}))
        tmp.replace(self.directory / f"{key}.json")
