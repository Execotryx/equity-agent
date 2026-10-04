// Event sequences exported from the real pipeline (recorded data, FakeClaude) by
// backend/scripts/export_ui_fixtures.py. Re-run that script after changing the backend's event payloads.

import type { ResearchReport, StreamEvent } from "@/lib/events";
import { reduceAll, type ReportState } from "@/lib/reportState";

import aapl from "./fixtures/aapl.json";
import aaplCached from "./fixtures/aapl-cached.json";
import aaplRiskFailed from "./fixtures/aapl-risk-failed.json";
import jpm from "./fixtures/jpm.json";
import unknownTicker from "./fixtures/unknown-ticker.json";

export const FIXTURES = {
  aapl: aapl as StreamEvent[],
  aaplCached: aaplCached as StreamEvent[],
  aaplRiskFailed: aaplRiskFailed as StreamEvent[],
  jpm: jpm as StreamEvent[],
  unknownTicker: unknownTicker as StreamEvent[],
};

export function finalState(events: StreamEvent[]): ReportState {
  return reduceAll(events);
}

export function reportOf(events: StreamEvent[]): ResearchReport {
  const report = finalState(events).report;
  if (!report) throw new Error("fixture has no report");
  return report;
}

/** State after the events before the first one matching `stop`. */
export function stateBefore(events: StreamEvent[], stop: (event: StreamEvent) => boolean): ReportState {
  const index = events.findIndex(stop);
  return reduceAll(index === -1 ? events : events.slice(0, index));
}
