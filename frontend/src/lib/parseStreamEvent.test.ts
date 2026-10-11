import { describe, expect, it } from "vitest";

import { FIXTURES } from "@/test/fixtures";
import { parseStreamEvent } from "./parseStreamEvent";
import type { StreamEvent } from "./events";

function reportData(): Record<string, unknown> {
  return structuredClone(FIXTURES.aaplCached.at(-1)!.data) as Record<string, unknown>;
}

describe("research event boundary", () => {
  it("accepts all recorded successful and degraded events", () => {
    for (const [key, events] of Object.entries(FIXTURES)) {
      const ticker = key === "jpm" ? "JPM" : key === "unknownTicker" ? "ZZZZQX" : "AAPL";
      for (const event of events) expect(parseStreamEvent(event.event, event.data, ticker)).toEqual(event);
    }
  });

  it("accepts old optional fields and unknown additions", () => {
    const data = reportData();
    const financials = data.financials as Record<string, unknown>;
    delete financials.financial_currency;
    delete financials.enrichment_provenance;
    delete (financials.snapshot as Record<string, unknown>).quote_provenance;
    data.new_provider_field = { ignored: true };
    expect(parseStreamEvent("report", data, " aapl ").event).toBe("report");
  });

  it.each([
    (v: Record<string, unknown>) => { v.scorecard = { factors: [null], total: 0, preliminary_signal: "HOLD" }; },
    (v: Record<string, unknown>) => { v.news = [{ title: 17, url: "x", domain: "x" }]; },
    (v: Record<string, unknown>) => { (v.financials as Record<string, unknown>).revenue_history = [{ year: 2025, value: Infinity }]; },
    (v: Record<string, unknown>) => { ((v.financials as Record<string, unknown>).snapshot as Record<string, unknown>).ticker = "MSFT"; },
    (v: Record<string, unknown>) => { v.analyst = { kind: "error", stage: "analyst", message: 17 }; },
    (v: Record<string, unknown>) => { (v.comps as Record<string, unknown>).rows = []; },
  ])("rejects malformed nested report values", (change) => {
    const data = reportData();
    change(data);
    expect(() => parseStreamEvent("report", data, "AAPL")).toThrow("Invalid research event");
  });

  it("rejects foreign quote provenance and history for native KASE", () => {
    const data = reportData();
    data.ticker = "FRHC_KZ";
    const financials = data.financials as Record<string, unknown>;
    const snapshot = financials.snapshot as Record<string, unknown>;
    snapshot.ticker = "FRHC_KZ";
    expect(() => parseStreamEvent("partial", { key: "snapshot", value: snapshot }, "FRHC_KZ")).toThrow();
    snapshot.quote_provenance = { provider: "KASE", exchange: "KASE", source_symbol: "FRHC_KZ", source_url: "https://kase.kz/" };
    snapshot.week52_low = snapshot.week52_high = null;
    expect(parseStreamEvent("partial", { key: "snapshot", value: snapshot }, "frhc_kz").event).toBe("partial");
    expect(() => parseStreamEvent("partial", { key: "financials", value: financials }, "FRHC_KZ")).toThrow();
    financials.price_history = [];
    expect(parseStreamEvent("partial", { key: "financials", value: financials }, "FRHC_KZ").event).toBe("partial");
  });

  it("uses the backend's class-share identity when comparing reports", () => {
    const data = reportData();
    data.ticker = "BRK-B";
    ((data.financials as Record<string, unknown>).snapshot as Record<string, unknown>).ticker = "BRK-B";
    const rows = (data.comps as Record<string, unknown>).rows as Record<string, unknown>[];
    rows[0].ticker = "BRK-B";
    expect(parseStreamEvent("report", data, "brk.b").event).toBe("report");
  });

  it("rejects numeric overflow in valid JSON", () => {
    expect(() => parseStreamEvent("stage", JSON.parse('{"stage":"risk","status":"failed","ms":1e400}'), "AAPL")).toThrow();
  });

  it.each(["stage", "partial", "narrative", "error", "report"] as StreamEvent["event"][])("rejects missing fields in %s", (name) => {
    expect(() => parseStreamEvent(name, {}, "AAPL")).toThrow();
  });
});
