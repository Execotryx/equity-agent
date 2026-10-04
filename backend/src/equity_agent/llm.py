"""The one guarded way to call Claude (IMPLEMENTATION_PLAN.md §4.3, §4.7).

Rules enforced here for every call: the agent's configured model and explicit effort; no sampling parameters; never
`thinking: disabled` (rejected by Opus 5.5 and Sonnet 5.5); server-side refusal fallback; `stop_reason` checked
before any output is read; bounded concurrency; per-call timeouts; usage and cost recorded.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any, Literal, Protocol, TypeVar

import anthropic
from pydantic import BaseModel

from equity_agent.config import AgentName, Settings
from equity_agent.models import LlmUsage

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

FALLBACK_BETA = "server-side-fallback-2026-07-01"
# USD per million tokens (input, output); used only for cost estimates.
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
DEFAULT_CONCURRENCY = 4
STRUCTURED_ATTEMPT_TIMEOUT_S = 30.0
STRUCTURED_DEADLINE_S = 60.0
STREAM_TIMEOUT = anthropic.Timeout(90.0, read=60.0)
STRUCTURED_MAX_TOKENS = 4000
STREAM_MAX_TOKENS = 4000

ErrorKind = Literal["refusal", "truncated", "invalid", "timeout", "not_found", "auth", "rate_limit", "api", "connection"]


class LlmError(Exception):
    def __init__(self, kind: ErrorKind, message: str, usage: LlmUsage | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.usage = usage


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    key = next((m for m in PRICES if model.startswith(m)), None)
    if key is None:
        return 0.0
    price_in, price_out = PRICES[key]
    return round((input_tokens * price_in + output_tokens * price_out) / 1_000_000, 6)


class LlmClient(Protocol):
    """Implemented by `Gateway` (live) and by test/offline replay clients."""

    async def parse(self, agent: AgentName, output_model: type[T], system: str, user: str) -> tuple[T, LlmUsage]: ...

    def stream(
        self, agent: AgentName, system: str, user: str, on_usage: Callable[[LlmUsage], None]
    ) -> AsyncIterator[str]: ...

    async def warm(self) -> None: ...

    async def close(self) -> None: ...


def _map_error(error: Exception, agent: AgentName, model: str) -> tuple[ErrorKind, str]:
    """Most specific first: a timeout is also a connection error, a 404 is also a status error."""
    if isinstance(error, anthropic.NotFoundError):
        return "not_found", f"model {model!r} not found: check the {agent.upper()}_MODEL setting"
    if isinstance(error, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
        return "auth", "the Anthropic API key was rejected"
    if isinstance(error, anthropic.RateLimitError):
        return "rate_limit", "rate limited by the Anthropic API"
    if isinstance(error, anthropic.APITimeoutError | TimeoutError):
        return "timeout", f"{agent} call timed out"
    if isinstance(error, anthropic.APIStatusError):
        return "api", f"Anthropic API error {error.status_code}"
    if isinstance(error, anthropic.APIConnectionError):
        return "connection", "could not reach the Anthropic API"
    return "api", f"{type(error).__name__}"


class Gateway:
    def __init__(
        self,
        settings: Settings,
        client: anthropic.AsyncAnthropic | None = None,
        *,
        concurrency: int = DEFAULT_CONCURRENCY,
        attempt_timeout_s: float = STRUCTURED_ATTEMPT_TIMEOUT_S,
        deadline_s: float = STRUCTURED_DEADLINE_S,
        stream_timeout: anthropic.Timeout | float = STREAM_TIMEOUT,
    ) -> None:
        self.settings = settings
        # One client per process: its connection pool is reused by every agent call.
        self.client = client or anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, max_retries=2)
        self.semaphore = asyncio.Semaphore(concurrency)
        self.attempt_timeout_s = attempt_timeout_s
        self.deadline_s = deadline_s
        self.stream_timeout = stream_timeout

    async def warm(self) -> None:
        """Open the connection and check every configured model exists; costs no tokens."""
        for model in sorted({cfg.model for cfg in self.settings.agents.values()}):
            await self.client.models.retrieve(model)

    async def close(self) -> None:
        await self.client.close()

    def _usage(
        self, agent: AgentName, model: str, start: float, response: Any = None, error: str | None = None, cause: Any = None
    ) -> LlmUsage:
        served = getattr(response, "model", None) or model
        usage = getattr(response, "usage", None)
        tokens_in = getattr(usage, "input_tokens", 0) or 0
        tokens_out = getattr(usage, "output_tokens", 0) or 0
        return LlmUsage(
            agent=agent,
            model=served,
            input_tokens=tokens_in,
            output_tokens=tokens_out,
            ms=int((time.perf_counter() - start) * 1000),
            cost_usd=cost_usd(served, tokens_in, tokens_out),
            request_id=(getattr(response, "_request_id", None) or getattr(cause, "request_id", None)) if error else None,
            error=error,
        )

    @staticmethod
    def _check_stop(response: Any, agent: AgentName) -> tuple[ErrorKind, str] | None:
        reason = getattr(response, "stop_reason", None)
        if reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None)
            return "refusal", "model declined the request" + (f" ({category})" if category else "")
        if reason == "max_tokens":
            return "truncated", f"{agent} output was truncated (output token limit reached)"
        return None

    @staticmethod
    def _schema(output_model: type[BaseModel]) -> dict[str, Any]:
        # The same strict-schema transform `messages.parse()` applies. `parse()` itself is not used: it validates the
        # JSON before `stop_reason` can be checked, so a refusal or truncation would surface as a ValidationError.
        return {"type": "json_schema", "schema": anthropic.transform_schema(output_model.model_json_schema())}

    async def parse(self, agent: AgentName, output_model: type[T], system: str, user: str) -> tuple[T, LlmUsage]:
        cfg = self.settings.agent(agent)
        start = time.perf_counter()
        async with self.semaphore:
            try:
                async with asyncio.timeout(self.deadline_s):
                    response = await self.client.with_options(timeout=self.attempt_timeout_s).beta.messages.create(
                        model=cfg.model,
                        max_tokens=STRUCTURED_MAX_TOKENS,
                        system=system,
                        messages=[{"role": "user", "content": user}],
                        output_config={"effort": cfg.effort, "format": self._schema(output_model)},  # type: ignore[typeddict-item]
                        betas=[FALLBACK_BETA],
                        fallbacks="default",
                    )
            except Exception as error:  # noqa: BLE001 - mapped to a typed LlmError below
                kind, message = _map_error(error, agent, cfg.model)
                logger.warning("%s call failed: %s", agent, message)
                raise LlmError(kind, message, self._usage(agent, cfg.model, start, error=message, cause=error)) from error
        problem = self._check_stop(response, agent)
        if problem is None:
            text = "".join(block.text for block in response.content if block.type == "text")
            try:
                return output_model.model_validate_json(text), self._usage(agent, cfg.model, start, response)
            except ValueError:
                problem = ("invalid", f"{agent} output did not match its schema")
        raise LlmError(problem[0], problem[1], self._usage(agent, cfg.model, start, response, error=problem[1]))

    async def stream(
        self, agent: AgentName, system: str, user: str, on_usage: Callable[[LlmUsage], None]
    ) -> AsyncIterator[str]:
        """Yield text as it arrives. Usage is reported through `on_usage` once the stream ends (or fails)."""
        cfg = self.settings.agent(agent)
        start = time.perf_counter()
        async with self.semaphore:
            try:
                async with self.client.with_options(timeout=self.stream_timeout).beta.messages.stream(
                    model=cfg.model,
                    max_tokens=STREAM_MAX_TOKENS,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                    output_config={"effort": cfg.effort},
                    betas=[FALLBACK_BETA],
                    fallbacks="default",
                ) as stream:
                    async for text in stream.text_stream:
                        yield text
                    final = await stream.get_final_message()
            except Exception as error:  # noqa: BLE001 - mapped to a typed LlmError below
                kind, message = _map_error(error, agent, cfg.model)
                usage = self._usage(agent, cfg.model, start, error=message, cause=error)
                on_usage(usage)
                raise LlmError(kind, message, usage) from error
        problem = self._check_stop(final, agent)
        usage = self._usage(agent, cfg.model, start, final, error=problem[1] if problem else None)
        on_usage(usage)
        if problem is not None:
            raise LlmError(problem[0], problem[1], usage)
