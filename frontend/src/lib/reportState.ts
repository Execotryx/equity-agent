// Pure reducer from stream events to report state. Components only read this state.
//
// A partial replaces its section (comps arrive twice: without, then with rationales). The final `report` event
// replaces every section, so a cached report (validation events plus one `report`) renders completely.

import {
  STAGE_NAMES,
  isStageError,
  type AnalystView,
  type CompsTable,
  type FinancialProfile,
  type NewsItem,
  type ResearchReport,
  type RiskReport,
  type Scorecard,
  type Snapshot,
  type StageError,
  type StageName,
  type StreamEvent,
} from "./events";

export type StageStatus = "pending" | "running" | "done" | "failed" | "skipped";
export type StageState = { status: StageStatus; ms?: number; cached?: boolean };
export type Connection = "connecting" | "open" | "closed" | "unreachable" | "lost";

export type ReportState = {
  validate: "running" | "done" | "failed";
  stages: Record<StageName, StageState>;
  snapshot?: Snapshot;
  financials?: FinancialProfile;
  comps?: CompsTable | StageError;
  risks?: RiskReport | StageError;
  news?: NewsItem[];
  newsError?: string;
  scorecard?: Scorecard;
  analyst?: AnalystView | StageError;
  narrative: string;
  narrativeError?: string;
  report?: ResearchReport;
  fromCache?: boolean;
  fatal?: { stage: string; message: string };
  connection: Connection;
  events: number;
};

export type Action =
  | { type: "event"; event: StreamEvent }
  | { type: "connection"; status: Connection }
  | { type: "reset" };

export function initialState(): ReportState {
  const stages = Object.fromEntries(STAGE_NAMES.map((name) => [name, { status: "pending" }])) as Record<
    StageName,
    StageState
  >;
  return { validate: "running", stages, narrative: "", connection: "connecting", events: 0 };
}

function isStage(name: string): name is StageName {
  return (STAGE_NAMES as readonly string[]).includes(name);
}

function withStage(state: ReportState, name: string, stage: StageState): ReportState {
  if (!isStage(name)) return state;
  return { ...state, stages: { ...state.stages, [name]: stage } };
}

function sectionError(state: ReportState, stage: string, message: string): ReportState {
  const error: StageError = { kind: "error", stage, message };
  switch (stage) {
    case "comps":
      return { ...state, comps: error };
    case "risk":
      return { ...state, risks: error };
    case "analyst":
      return { ...state, analyst: error };
    case "news":
      return { ...state, newsError: message };
    case "writer":
      return { ...state, narrativeError: message };
    default:
      return state;
  }
}

function fromReport(state: ReportState, report: ResearchReport, fromCache: boolean): ReportState {
  const stages = { ...state.stages };
  const failed: Partial<Record<StageName, boolean>> = {
    comps: isStageError(report.comps),
    risk: isStageError(report.risks),
    analyst: isStageError(report.analyst),
    writer: isStageError(report.narrative),
    news: report.news_error != null,
  };
  for (const name of STAGE_NAMES) {
    const current = stages[name];
    if (failed[name]) stages[name] = { ...current, status: "failed", cached: fromCache || current.cached };
    else if (fromCache) stages[name] = { status: "done", cached: true };
    else if (current.status === "pending" || current.status === "running") stages[name] = { status: "skipped" };
  }
  return {
    ...state,
    validate: "done",
    stages,
    snapshot: report.financials.snapshot,
    financials: report.financials,
    comps: report.comps,
    risks: report.risks,
    news: report.news ?? [],
    newsError: report.news_error ?? undefined,
    scorecard: report.scorecard,
    analyst: report.analyst,
    narrative: report.narrative_markdown || state.narrative,
    narrativeError: isStageError(report.narrative) ? report.narrative.message : undefined,
    report,
    fromCache,
    connection: "closed",
  };
}

function applyEvent(state: ReportState, event: StreamEvent): ReportState {
  switch (event.event) {
    case "stage": {
      const { stage, status } = event.data;
      if (stage === "validate") return { ...state, validate: status === "started" ? "running" : "done" };
      if (event.data.status === "started") return withStage(state, stage, { status: "running" });
      if (event.data.status === "done")
        return withStage(state, stage, { status: "done", ms: event.data.ms, cached: event.data.cached });
      return withStage(state, stage, { status: "failed", ms: event.data.ms });
    }
    case "partial": {
      const p = event.data;
      switch (p.key) {
        case "snapshot":
          return { ...state, snapshot: p.value };
        case "financials":
          return { ...state, financials: p.value, snapshot: p.value.snapshot };
        case "comps":
          return { ...state, comps: p.value };
        case "risks":
          return { ...state, risks: p.value };
        case "news":
          return { ...state, news: p.value };
        case "scorecard":
          return { ...state, scorecard: p.value };
        case "analyst":
          return { ...state, analyst: p.value };
      }
      return state;
    }
    case "narrative":
      return { ...state, narrative: state.narrative + event.data.delta };
    case "error": {
      const { stage, message, terminal } = event.data;
      if (terminal) {
        return {
          ...state,
          validate: stage === "validate" ? "failed" : state.validate,
          fatal: { stage, message },
          connection: "closed",
        };
      }
      const current = isStage(stage) ? state.stages[stage] : undefined;
      const failed = current ? withStage(state, stage, { ...current, status: "failed" }) : state;
      return sectionError(failed, stage, message);
    }
    case "report": {
      const { from_cache: fromCache, ...report } = event.data;
      return fromReport(state, report, fromCache);
    }
  }
}

export function reduce(state: ReportState, action: Action): ReportState {
  switch (action.type) {
    case "reset":
      return initialState();
    case "connection":
      return { ...state, connection: action.status };
    case "event":
      return { ...applyEvent(state, action.event), events: state.events + 1 };
  }
}

/** Fold a whole event list (tests, and replaying fixtures). */
export function reduceAll(events: StreamEvent[], state: ReportState = initialState()): ReportState {
  return events.reduce((s, event) => reduce(s, { type: "event", event }), state);
}
