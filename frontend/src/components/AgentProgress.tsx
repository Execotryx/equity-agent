import { STAGE_NAMES, type LlmUsage, type StageName } from "@/lib/events";
import { seconds } from "@/lib/format";
import type { StageState } from "@/lib/reportState";

export const STAGE_LABELS: Record<StageName, string> = {
  financials: "Financial data",
  comps: "Comps",
  comps_explain: "Peer rationales",
  risk: "Risk",
  news: "News",
  analyst: "Analyst",
  writer: "Writer",
};

// Which agent's usage records belong to a step (the explain call is billed to the Comps agent).
const STAGE_AGENT: Partial<Record<StageName, string>> = {
  comps: "comps",
  comps_explain: "comps",
  risk: "risk",
  analyst: "analyst",
  writer: "writer",
};

const STATUS_TEXT = { pending: "Queued", running: "Running", done: "Done", failed: "Failed", skipped: "Skipped" };

const STATUS_MARK = {
  pending: "text-muted",
  running: "text-accent",
  done: "text-buy",
  failed: "text-sell",
  skipped: "text-muted",
};

function model(usage: LlmUsage[] | undefined, stage: StageName): string | undefined {
  const agent = STAGE_AGENT[stage];
  const record = usage?.find((u) => u.agent === agent);
  return record?.model.replace(/^claude-/, "");
}

/** The pipeline as a wire strip: one cell per step, updated as stage events arrive. */
export function AgentProgress({ stages, usage }: { stages: Record<StageName, StageState>; usage?: LlmUsage[] }) {
  return (
    <ol aria-label="Agent progress" className="grid grid-cols-2 border-y border-rule sm:grid-cols-4 lg:grid-cols-7">
      {STAGE_NAMES.map((name, index) => {
        const stage = stages[name];
        const used = model(usage, name);
        return (
          <li
            key={name}
            data-testid={`stage-${name}`}
            className={`relative overflow-hidden border-rule px-3 py-2.5 ${index > 0 ? "border-l" : ""} ${
              stage.status === "running" ? "wire-run bg-accent-soft" : ""
            } ${index % 2 === 1 ? "" : "max-sm:border-l-0"}`}
          >
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-[0.8rem] font-medium">{STAGE_LABELS[name]}</span>
              <span className="font-mono text-[0.7rem] tabular text-muted">
                {stage.ms !== undefined ? seconds(stage.ms) : ""}
              </span>
            </div>
            <div className="mt-0.5 flex items-center gap-1.5 font-mono text-[0.68rem] uppercase tracking-wider">
              <span aria-hidden className={STATUS_MARK[stage.status]}>
                {stage.status === "done" ? "■" : stage.status === "failed" ? "✕" : stage.status === "running" ? "▶" : "□"}
              </span>
              <span className={STATUS_MARK[stage.status]}>{STATUS_TEXT[stage.status]}</span>
              {stage.cached ? <span className="rounded-sm border border-rule px-1 text-muted">cached</span> : null}
            </div>
            {used ? <div className="mt-0.5 truncate font-mono text-[0.65rem] text-muted">{used}</div> : null}
          </li>
        );
      })}
    </ol>
  );
}
