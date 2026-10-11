import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FIXTURES } from "@/test/fixtures";
import type { StreamEvent } from "./events";
import { useResearchStream } from "./useResearchStream";

// EventTarget dispatches the same named error to the application listener and the onerror handler.
class TestEventSource extends EventTarget {
  static instances: TestEventSource[] = [];
  onopen: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  close = vi.fn();

  constructor(public url: string) {
    super();
    TestEventSource.instances.push(this);
    this.addEventListener("open", (event) => this.onopen?.(event));
    this.addEventListener("error", (event) => this.onerror?.(event));
  }

  send(event: StreamEvent) {
    this.dispatchEvent(new MessageEvent(event.event, { data: JSON.stringify(event.data) }));
  }
}

beforeEach(() => {
  TestEventSource.instances = [];
  vi.stubGlobal("EventSource", TestEventSource);
});
afterEach(() => vi.unstubAllGlobals());

describe("research stream transport", () => {
  it.each([
    ["report", {}],
    ["partial", { key: "financials", value: null }],
    ["partial", { key: "news", value: [null] }],
    ["narrative", { delta: 17 }],
    ["stage", { stage: "risk", status: "done", ms: "fast", cached: false }],
    ["error", { stage: "risk", message: "bad", terminal: "false" }],
  ])("closes cleanly for malformed %s objects", (name, data) => {
    const { result } = renderHook(() => useResearchStream("AAPL"));
    const source = TestEventSource.instances[0];
    act(() => source.dispatchEvent(new MessageEvent(name as string, { data: JSON.stringify(data) })));
    expect(result.current.state.fatal?.stage).toBe("stream");
    expect(result.current.state.connection).toBe("closed");
    expect(source.close).toHaveBeenCalledTimes(1);
    act(() => source.send(FIXTURES.aapl[0]));
    expect(result.current.state.events).toBe(1);
  });

  it("rejects another ticker's otherwise valid report", () => {
    const { result } = renderHook(() => useResearchStream("MSFT"));
    act(() => TestEventSource.instances[0].send(FIXTURES.aaplCached.at(-1)!));
    expect(result.current.state.fatal?.stage).toBe("stream");
    expect(result.current.state.report).toBeUndefined();
  });

  it("unmounts the old ticker before mounting its successor", () => {
    const first = renderHook(() => useResearchStream("AAPL"));
    const oldSource = TestEventSource.instances[0];
    first.unmount();
    const next = renderHook(() => useResearchStream("JPM"));
    act(() => oldSource.send(FIXTURES.aaplCached.at(-1)!));
    expect(next.result.current.state.events).toBe(0);
    act(() => FIXTURES.jpm.forEach((event) => TestEventSource.instances[1].send(event)));
    expect(next.result.current.state.report?.ticker).toBe("JPM");
  });
  it("keeps native KASE symbols in initial and refreshed EventSource requests", () => {
    const { result, unmount } = renderHook(() => useResearchStream("FRHC_KZ"));
    const first = TestEventSource.instances[0];
    expect(new URL(first.url).searchParams.get("ticker")).toBe("FRHC_KZ");
    act(() => result.current.refresh());
    const second = new URL(TestEventSource.instances[1].url);
    expect(second.searchParams.get("ticker")).toBe("FRHC_KZ");
    expect(second.searchParams.get("refresh")).toBe("true");
    expect(first.close).toHaveBeenCalledTimes(1);
    unmount();
    expect(TestEventSource.instances[1].close).toHaveBeenCalledTimes(1);
  });
  it("continues through a nonterminal section error and receives the final report", () => {
    const { result } = renderHook(() => useResearchStream("AAPL"));
    const source = TestEventSource.instances[0];
    act(() => source.dispatchEvent(new Event("open")));
    act(() => source.send({ event: "error", data: { stage: "risk", message: "unavailable", terminal: false } }));
    expect(source.close).not.toHaveBeenCalled();
    expect(result.current.state.connection).toBe("open");
    act(() => FIXTURES.aaplRiskFailed.forEach((event) => source.send(event)));
    expect(result.current.state.report?.ticker).toBe("AAPL");
    expect(result.current.state.connection).toBe("closed");
    expect(source.close).toHaveBeenCalledTimes(1);
  });

  it("closes on a terminal application error without replacing it with a connection error", () => {
    const { result } = renderHook(() => useResearchStream("ZZZZQX"));
    act(() => FIXTURES.unknownTicker.forEach((event) => TestEventSource.instances[0].send(event)));
    expect(result.current.state.fatal?.message).toBe("ticker not found");
    expect(result.current.state.connection).toBe("closed");
    expect(TestEventSource.instances[0].close).toHaveBeenCalledTimes(1);
  });

  it.each([false, true])("handles a transport error after receiving events: %s", (received) => {
    const { result } = renderHook(() => useResearchStream("AAPL"));
    const source = TestEventSource.instances[0];
    if (received) act(() => source.send(FIXTURES.aapl[0]));
    act(() => source.dispatchEvent(new Event("error")));
    act(() => source.send(FIXTURES.aapl[0]));
    expect(result.current.state.connection).toBe(received ? "lost" : "unreachable");
    expect(result.current.state.events).toBe(received ? 1 : 0);
    expect(source.close).toHaveBeenCalledTimes(1);
  });

  it("resets state, requests refresh, and closes the previous stream", () => {
    const { result, unmount } = renderHook(() => useResearchStream("AAPL"));
    const first = TestEventSource.instances[0];
    act(() => first.send(FIXTURES.aapl[0]));
    act(() => result.current.refresh());
    expect(first.close).toHaveBeenCalledTimes(1);
    expect(result.current.state.events).toBe(0);
    expect(new URL(TestEventSource.instances[1].url).searchParams.get("refresh")).toBe("true");
    unmount();
    expect(TestEventSource.instances[1].close).toHaveBeenCalledTimes(1);
  });

  it.each(["{", "null", "42", "[]"])("stops with a clear error for invalid event data: %s", (data) => {
    const { result } = renderHook(() => useResearchStream("AAPL"));
    const source = TestEventSource.instances[0];
    act(() => source.dispatchEvent(new MessageEvent("partial", { data })));
    expect(result.current.state.fatal?.stage).toBe("stream");
    expect(result.current.state.connection).toBe("closed");
    expect(source.close).toHaveBeenCalledTimes(1);
  });

  it("ignores events from a closed stream after retry", () => {
    const { result } = renderHook(() => useResearchStream("AAPL"));
    const first = TestEventSource.instances[0];
    act(() => result.current.retry());
    act(() => first.send(FIXTURES.aapl[0]));
    act(() => first.dispatchEvent(new Event("error")));
    expect(result.current.state.events).toBe(0);
    expect(result.current.state.connection).toBe("connecting");
  });
});
