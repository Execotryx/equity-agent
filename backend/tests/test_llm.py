"""Gateway tests against a mock HTTP transport (no network, no key)."""

import asyncio
import json

import anthropic
import httpx2
import pytest

from equity_agent.config import load_settings
from equity_agent.llm import Gateway, LlmError, cost_usd
from equity_agent.models import PeerPicks

SETTINGS = load_settings({"ANTHROPIC_API_KEY": "sk-test", "TAVILY_API_KEY": "t", "EDGAR_IDENTITY": "A a@b.c"})
PICKS = {"peers": [{"ticker": "MSFT", "name": "Microsoft"}]}


def message(text: str, stop_reason: str = "end_turn", model: str = "claude-opus-5-5", **extra) -> dict:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 1000, "output_tokens": 200},
        **extra,
    }


def gateway(handler, **kwargs) -> tuple[Gateway, list[httpx2.Request]]:
    seen: list[httpx2.Request] = []

    async def record(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        result = handler(request, len(seen))
        if asyncio.iscoroutine(result):
            result = await result
        return result

    client = anthropic.AsyncAnthropic(
        api_key="sk-test",
        max_retries=kwargs.pop("max_retries", 2),
        http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(record)),
    )
    return Gateway(SETTINGS, client, **kwargs), seen


def test_success_returns_typed_object_and_usage():
    gw, seen = gateway(lambda r, n: httpx2.Response(200, json=message(json.dumps(PICKS))))
    picks, usage = asyncio.run(gw.parse("comps", PeerPicks, "system", "user"))
    assert isinstance(picks, PeerPicks) and picks.peers[0].ticker == "MSFT"
    assert (usage.model, usage.input_tokens, usage.output_tokens) == ("claude-opus-5-5", 1000, 200)
    assert usage.cost_usd == pytest.approx(cost_usd("claude-opus-5-5", 1000, 200)) == pytest.approx(0.008)
    body = json.loads(seen[0].content)
    assert body["model"] == "claude-opus-5-5" and body["output_config"]["effort"] == "low"
    assert body["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in seen[0].headers["anthropic-beta"]
    assert not {"temperature", "top_p", "top_k"} & set(body)
    assert body.get("thinking", {}).get("type") != "disabled"


def test_refusal_is_a_readable_failure():
    refusal = message("", stop_reason="refusal", stop_details={"type": "refusal", "category": "cyber", "explanation": None})
    gw, _ = gateway(lambda r, n: httpx2.Response(200, json=refusal))
    with pytest.raises(LlmError, match=r"model declined the request \(cyber\)") as caught:
        asyncio.run(gw.parse("risk", PeerPicks, "s", "u"))
    assert caught.value.kind == "refusal" and caught.value.usage is not None


def test_truncated_output_fails_without_partial_object():
    gw, _ = gateway(lambda r, n: httpx2.Response(200, json=message('{"peers": [', stop_reason="max_tokens")))
    with pytest.raises(LlmError, match="truncated") as caught:
        asyncio.run(gw.parse("comps", PeerPicks, "s", "u"))
    assert caught.value.kind == "truncated"


def test_rate_limit_then_success_is_retried():
    def handler(request, n):
        if n == 1:
            return httpx2.Response(429, json={"type": "error", "error": {"type": "rate_limit_error", "message": "slow"}}, headers={"retry-after-ms": "10"})
        return httpx2.Response(200, json=message(json.dumps(PICKS)))

    gw, seen = gateway(handler)
    picks, _ = asyncio.run(gw.parse("comps", PeerPicks, "s", "u"))
    assert picks.peers and len(seen) == 2


def test_unknown_model_names_the_setting_without_retry():
    gw, seen = gateway(lambda r, n: httpx2.Response(404, json={"type": "error", "error": {"type": "not_found_error", "message": "model"}}))
    with pytest.raises(LlmError, match="ANALYST_MODEL") as caught:
        asyncio.run(gw.parse("analyst", PeerPicks, "s", "u"))
    assert caught.value.kind == "not_found" and len(seen) == 1


def test_hung_call_times_out_within_deadline():
    async def hang(request, n):
        await asyncio.sleep(5)
        return httpx2.Response(200, json=message(json.dumps(PICKS)))

    gw, _ = gateway(hang, max_retries=0, attempt_timeout_s=0.2, deadline_s=0.3)
    with pytest.raises(LlmError) as caught:
        asyncio.run(gw.parse("analyst", PeerPicks, "s", "u"))
    assert caught.value.kind == "timeout"


def test_one_client_serves_several_calls():
    gw, seen = gateway(lambda r, n: httpx2.Response(200, json=message(json.dumps(PICKS))))
    client = gw.client

    async def three():
        for _ in range(3):
            await gw.parse("comps", PeerPicks, "s", "u")

    asyncio.run(three())
    assert gw.client is client and len(seen) == 3


def test_concurrency_is_bounded():
    active = 0
    peak = 0

    async def slow(request, n):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.05)
        active -= 1
        return httpx2.Response(200, json=message(json.dumps(PICKS)))

    gw, seen = gateway(slow, concurrency=4)

    async def burst():
        await asyncio.gather(*(gw.parse("comps", PeerPicks, "s", "u") for _ in range(6)))

    asyncio.run(burst())
    assert peak <= 4 and len(seen) == 6


def test_warm_retrieves_each_configured_model_once():
    gw, seen = gateway(lambda r, n: httpx2.Response(200, json={"id": "m", "type": "model", "display_name": "m", "created_at": "2026-01-01T00:00:00Z"}))
    asyncio.run(gw.warm())
    paths = sorted(r.url.path for r in seen)
    assert paths == ["/v1/models/claude-opus-5-5", "/v1/models/claude-sonnet-5-5"]


@pytest.mark.parametrize("stop,kind", [("max_tokens", "truncated"), ("refusal", "refusal")])
def test_stream_partial_then_terminal_failure_records_usage_once(stop, kind):
    initial = message("")
    initial["content"] = []
    initial["usage"]["output_tokens"] = 0
    events = [
        ("message_start", {"type": "message_start", "message": initial}),
        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "partial"}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None}, "usage": {"output_tokens": 20}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    body = "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events).encode()
    gw, _ = gateway(lambda r, n: httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=body))
    chunks, usages = [], []
    async def scenario():
        try:
            with pytest.raises(LlmError) as caught:
                async for chunk in gw.stream("writer", "s", "u", usages.append):
                    chunks.append(chunk)
            assert caught.value.kind == kind
            assert chunks == ["partial"] and len(usages) == 1
            assert usages[0].output_tokens == 20 and usages[0].error
        finally:
            await gw.close()
    asyncio.run(scenario())
