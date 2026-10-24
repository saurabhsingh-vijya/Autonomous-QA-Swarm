"""LLM adapter interface.

The deterministic adapter is **not** an LLM and is never presented as one. ``OllamaAdapter``
talks to a local Ollama server over HTTP; it is used only when ``AQS_LLM_PROVIDER=ollama``.
External hosted providers are not implemented and are disabled by default.
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol

from qaswarm.agents.base import AgentFailure
from qaswarm.domain.enums import ErrorClass


@dataclass(frozen=True)
class Completion:
    text: str
    model_ref: str
    tokens_in: int
    tokens_out: int
    duration_ms: int


class LLMAdapter(Protocol):
    name: str
    is_llm: bool

    def complete_json(
        self, prompt: str, *, schema_hint: dict[str, Any]
    ) -> tuple[dict[str, Any], Completion]: ...


class NoLLM:
    """Marker adapter: no model configured. Agents must fall back to deterministic logic."""

    name = "none"
    is_llm = False

    def complete_json(
        self, prompt: str, *, schema_hint: dict[str, Any]
    ) -> tuple[dict[str, Any], Completion]:
        raise AgentFailure(
            "No LLM provider is configured (AQS_LLM_PROVIDER=none).",
            error_code="E-MODEL-001",
            error_class=ErrorClass.INFRASTRUCTURE_ERROR,
        )


_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


def parse_json_object(text: str) -> dict[str, Any]:
    """Extract one JSON object from model text; raise a retryable failure when malformed."""
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        candidate = candidate.split("\n", 1)[1] if "\n" in candidate else candidate
    match = _JSON_BLOCK.search(candidate)
    if not match:
        raise AgentFailure(
            "Model output did not contain a JSON object.",
            error_code="E-MODEL-003",
            retryable=True,
            error_class=ErrorClass.CONTRACT_ERROR,
        )
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise AgentFailure(
            f"Model output was not valid JSON: {exc.msg}",
            error_code="E-MODEL-003",
            retryable=True,
            error_class=ErrorClass.CONTRACT_ERROR,
        ) from exc
    if not isinstance(parsed, dict):
        raise AgentFailure(
            "Model output JSON was not an object.",
            error_code="E-MODEL-003",
            retryable=True,
            error_class=ErrorClass.CONTRACT_ERROR,
        )
    return parsed


class RateLimiter:
    """Simple per-process limiter: at most ``per_minute`` calls per rolling minute."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = max(1, per_minute)
        self._calls: list[float] = []
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            self._calls = [t for t in self._calls if now - t < 60]
            if len(self._calls) >= self.per_minute:
                raise AgentFailure(
                    "Local LLM rate limit reached; retry scheduled.",
                    error_code="E-MODEL-001",
                    retryable=True,
                    error_class=ErrorClass.INFRASTRUCTURE_ERROR,
                )
            self._calls.append(now)


class OllamaAdapter:
    """Local Ollama HTTP adapter (http://localhost:11434 by default). Never sends data off-host
    unless the operator points it elsewhere on purpose."""

    name = "ollama"
    is_llm = True

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout_seconds: float = 60.0,
        per_minute: int = 30,
        transport: Any | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout_seconds
        self.limiter = RateLimiter(per_minute)
        self._transport = transport  # test seam: callable(url, payload, timeout) -> dict

    def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._transport is not None:
            result: dict[str, Any] = self._transport(url, payload, self.timeout)
            return result
        import httpx

        try:
            resp = httpx.post(url, json=payload, timeout=self.timeout)
        except httpx.TimeoutException as exc:
            raise AgentFailure(
                "Local model call timed out.",
                error_code="E-MODEL-001",
                retryable=True,
                error_class=ErrorClass.INFRASTRUCTURE_ERROR,
            ) from exc
        except httpx.HTTPError as exc:
            raise AgentFailure(
                f"Local model unreachable: {exc.__class__.__name__}",
                error_code="E-MODEL-001",
                retryable=True,
                error_class=ErrorClass.INFRASTRUCTURE_ERROR,
            ) from exc
        if resp.status_code == 429:
            raise AgentFailure(
                "Local model rate limited (429).",
                error_code="E-MODEL-001",
                retryable=True,
                error_class=ErrorClass.INFRASTRUCTURE_ERROR,
            )
        if resp.status_code >= 400:
            raise AgentFailure(
                f"Local model returned HTTP {resp.status_code}.",
                error_code="E-MODEL-001",
                retryable=resp.status_code >= 500,
                error_class=ErrorClass.INFRASTRUCTURE_ERROR,
            )
        data: dict[str, Any] = resp.json()
        return data

    def complete_json(
        self, prompt: str, *, schema_hint: dict[str, Any]
    ) -> tuple[dict[str, Any], Completion]:
        self.limiter.acquire()
        started = time.monotonic()
        data = self._post(
            f"{self.base_url}/api/generate",
            {
                "model": self.model,
                "prompt": prompt
                + "\n\nRespond with one JSON object matching: "
                + json.dumps(schema_hint),
                "stream": False,
                "format": "json",
            },
        )
        text = str(data.get("response", ""))
        parsed = parse_json_object(text)
        completion = Completion(
            text=text,
            model_ref=f"ollama/{self.model}",
            tokens_in=int(data.get("prompt_eval_count", 0) or 0),
            tokens_out=int(data.get("eval_count", 0) or 0),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return parsed, completion


def build_adapter(
    provider: str, *, base_url: str, model: str, timeout_seconds: float, per_minute: int
) -> LLMAdapter:
    if provider == "ollama":
        return OllamaAdapter(
            base_url, model, timeout_seconds=timeout_seconds, per_minute=per_minute
        )
    if provider in ("", "none"):
        return NoLLM()
    raise ValueError(
        f"Unsupported AQS_LLM_PROVIDER '{provider}'. Only 'none' and 'ollama' are implemented; "
        "hosted providers are disabled by default."
    )
