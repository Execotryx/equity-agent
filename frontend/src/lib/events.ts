// Typed stream events on top of the generated schema types (lib/types.ts, `npm run gen:types`).
// The API sends `event: <name>` and `data: <json>`; PipelineEvent.data is untyped in the schema, so it is typed here.

import type { components } from "./types";

type S = components["schemas"];

export type Snapshot = S["Snapshot"];
export type Multiples = S["Multiples"];
export type FinancialProfile = S["FinancialProfile"];
export type CompsTable = S["CompsTable"];
export type CompRow = S["CompRow"];
export type RiskReport = S["RiskReport"];
export type RiskItem = S["RiskItem"];
export type NewsItem = S["NewsItem"];
export type Scorecard = S["Scorecard"];
export type FactorScore = S["FactorScore"];
export type AnalystView = S["AnalystView"];
export type ResearchReport = S["ResearchReport"];
export type StageError = S["StageError"];
export type LlmUsage = S["LlmUsage"];
export type Signal = ResearchReport["signal"];

export const STAGE_NAMES = ["financials", "comps", "comps_explain", "risk", "news", "analyst", "writer"] as const;
export type StageName = (typeof STAGE_NAMES)[number];

export type StageEventData =
  | { stage: string; status: "started" }
  | { stage: string; status: "done"; ms: number; cached: boolean }
  | { stage: string; status: "failed"; ms: number };

export type PartialEventData =
  | { key: "snapshot"; value: Snapshot }
  | { key: "financials"; value: FinancialProfile }
  | { key: "comps"; value: CompsTable }
  | { key: "risks"; value: RiskReport }
  | { key: "news"; value: NewsItem[] }
  | { key: "scorecard"; value: Scorecard }
  | { key: "analyst"; value: AnalystView };

export type PartialKey = PartialEventData["key"];

export type ErrorEventData = { stage: string; message: string; terminal: boolean };

export type ReportEventData = ResearchReport & { from_cache: boolean };

export type StreamEvent =
  | { event: "stage"; data: StageEventData }
  | { event: "partial"; data: PartialEventData }
  | { event: "narrative"; data: { delta: string } }
  | { event: "error"; data: ErrorEventData }
  | { event: "report"; data: ReportEventData };

export const EVENT_NAMES = ["stage", "partial", "narrative", "error", "report"] as const;

export function isStageError(value: unknown): value is StageError {
  return typeof value === "object" && value !== null && (value as { kind?: unknown }).kind === "error";
}

export function isFinal(event: StreamEvent): boolean {
  return event.event === "report" || (event.event === "error" && event.data.terminal);
}
