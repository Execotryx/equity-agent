import { describe, expect, it } from "vitest";

import { isStageError, type CompsTable, type StreamEvent } from "./events";
import { initialState, reduce, reduceAll } from "./reportState";
import { FIXTURES, finalState, reportOf, stateBefore } from "@/test/fixtures";

const isComps = (e: StreamEvent) => e.event === "partial" && e.data.key === "comps";

describe("fresh run (AAPL)", () => {
  const state = finalState(FIXTURES.aapl);

  it("ends with a report and every step done", () => {
    expect(state.report?.ticker).toBe("AAPL");
    expect(state.fatal).toBeUndefined();
    expect(Object.values(state.stages).every((s) => s.status === "done")).toBe(true);
    expect(state.stages.comps.ms).toBeTypeOf("number");
  });

  it("replaces the comps section when the rationales arrive", () => {
    const comps = FIXTURES.aapl.filter(isComps);
    expect(comps).toHaveLength(2);
    const first = reduceAll(FIXTURES.aapl.slice(0, FIXTURES.aapl.indexOf(comps[0]) + 1));
    expect((first.comps as CompsTable).peer_rationales).toEqual({});
    const second = reduceAll(FIXTURES.aapl.slice(0, FIXTURES.aapl.indexOf(comps[1]) + 1));
    expect(Object.keys((second.comps as CompsTable).peer_rationales ?? {})).toHaveLength(
      (second.comps as CompsTable).rows.filter((r) => !r.is_target).length,
    );
  });

  it("shows comps before any narrative", () => {
    const before = stateBefore(FIXTURES.aapl, (e) => e.event === "narrative");
    expect(before.comps).toBeDefined();
    expect(before.narrative).toBe("");
  });

  it("grows the narrative fragment by fragment", () => {
    const fragments = FIXTURES.aapl.filter((e) => e.event === "narrative");
    let state = initialState();
    const lengths: number[] = [];
    for (const event of fragments) {
      state = reduce(state, { type: "event", event });
      lengths.push(state.narrative.length);
    }
    expect(lengths.length).toBeGreaterThan(1);
    expect(lengths).toEqual([...lengths].sort((a, b) => a - b));
    expect(state.narrative).toContain("## Company overview");
  });
});

describe("cached report", () => {
  it.each([
    ["comps", "comps"], ["risk", "risks"], ["analyst", "analyst"], ["writer", "narrative"],
  ] as const)("keeps a failed %s section visibly failed when served from cache", (stage, section) => {
    const report = structuredClone(reportOf(FIXTURES.aapl));
    report[section] = { kind: "error", stage, message: "Section unavailable" };
    const state = reduceAll([{ event: "report", data: { ...report, from_cache: true } }]);
    expect(state.stages[stage]).toMatchObject({ status: "failed", cached: true });
    expect(state.stages.financials).toMatchObject({ status: "done", cached: true });
  });

  it("keeps a cached news failure visible", () => {
    const report = { ...reportOf(FIXTURES.aapl), news_error: "service error" };
    const state = reduceAll([{ event: "report", data: { ...report, from_cache: true } }]);
    expect(state.stages.news).toMatchObject({ status: "failed", cached: true });
  });

  const state = finalState(FIXTURES.aaplCached);

  it("arrives as validation stages and one report, and fills every section", () => {
    expect(FIXTURES.aaplCached.map((e) => e.event)).toEqual(["stage", "stage", "report"]);
    expect(state.fromCache).toBe(true);
    for (const key of ["snapshot", "financials", "comps", "risks", "news", "scorecard", "analyst"] as const) {
      expect(state[key], key).toBeDefined();
    }
    expect(state.narrative).toContain("## Risk commentary");
  });

  it("marks every step as cached", () => {
    expect(Object.values(state.stages).every((s) => s.status === "done" && s.cached)).toBe(true);
  });
});

describe("failures", () => {
  it("makes an unknown ticker a fatal validation error", () => {
    const state = finalState(FIXTURES.unknownTicker);
    expect(state.fatal).toEqual({ stage: "validate", message: "ticker not found" });
    expect(state.validate).toBe("failed");
    expect(state.report).toBeUndefined();
  });

  it("keeps a failed risk section as a section error and renders the rest", () => {
    const state = finalState(FIXTURES.aaplRiskFailed);
    expect(isStageError(state.risks)).toBe(true);
    expect(state.stages.risk.status).toBe("failed");
    expect(state.comps && !isStageError(state.comps)).toBe(true);
    expect(state.fatal).toBeUndefined();
  });

  it("marks peer rationales skipped when no explain stage ran", () => {
    const withoutExplain = FIXTURES.aapl.filter(
      (e) => !(e.event === "stage" && e.data.stage === "comps_explain"),
    );
    expect(finalState(withoutExplain).stages.comps_explain.status).toBe("skipped");
  });

  it("starts over on reset", () => {
    const state = reduce(finalState(FIXTURES.aapl), { type: "reset" });
    expect(state).toEqual(initialState());
  });
});
