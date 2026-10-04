import { isStageError, type AnalystView, type FactorScore, type Scorecard, type Signal, type StageError } from "@/lib/events";
import { percent } from "@/lib/format";

const SIGNAL_COLOR: Record<Signal, string> = { BUY: "text-buy", HOLD: "text-hold", SELL: "text-sell" };

const FACTOR_LABELS: Record<FactorScore["name"], string> = {
  valuation: "Valuation",
  growth: "Growth",
  profitability: "Profitability",
  analyst_upside: "Analyst upside",
  momentum: "Momentum",
};

function Stamp({ signal, size = "lg" }: { signal: Signal; size?: "lg" | "sm" }) {
  return (
    <span
      className={`stamp inline-block font-mono font-medium tracking-[0.2em] ${SIGNAL_COLOR[signal]} ${
        size === "lg" ? "px-4 py-1.5 text-3xl" : "px-1.5 py-0 text-xs tracking-[0.12em]"
      }`}
    >
      {signal}
    </span>
  );
}

function Factors({ scorecard }: { scorecard: Scorecard }) {
  return (
    <div>
      <ul className="divide-y divide-rule border-y border-rule">
        {scorecard.factors.map((factor) => (
          <li key={factor.name} className="grid grid-cols-[1fr_auto] gap-x-3 py-2">
            <span className="text-sm font-medium">{FACTOR_LABELS[factor.name]}</span>
            <span
              className={`font-mono text-sm tabular ${factor.score > 0 ? "text-buy" : factor.score < 0 ? "text-sell" : "text-muted"}`}
              aria-label={`score ${factor.score}`}
            >
              {factor.score > 0 ? "+1" : factor.score < 0 ? "−1" : "0"}
            </span>
            <span className="col-span-2 text-xs leading-relaxed text-muted">{factor.detail}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 flex items-center justify-between font-mono text-xs uppercase tracking-wider text-muted">
        <span>Scorecard total {scorecard.total > 0 ? `+${scorecard.total}` : scorecard.total}</span>
        <span className="flex items-center gap-2">
          Preliminary <Stamp signal={scorecard.preliminary_signal} size="sm" />
        </span>
      </p>
    </div>
  );
}

/** The rating: preliminary from the scorecard first, then the analyst's reviewed signal. */
export function SignalCard({ scorecard, analyst }: { scorecard: Scorecard; analyst?: AnalystView | StageError }) {
  const reviewed = analyst && !isStageError(analyst) ? analyst : undefined;
  const signal = reviewed?.signal ?? scorecard.preliminary_signal;
  let status: string;
  if (reviewed) status = reviewed.changed_from_preliminary ? `Changed from ${reviewed.preliminary_signal}` : "Confirmed by the analyst";
  else if (isStageError(analyst)) status = "Not reviewed by the analyst";
  else status = "Preliminary · awaiting the analyst";

  return (
    <div className="arrive">
      <div className="flex items-center justify-between gap-4 border border-rule-strong bg-surface p-5">
        <div>
          <p className="font-mono text-[0.68rem] uppercase tracking-[0.18em] text-muted">Signal</p>
          <p className="mt-1 text-sm font-medium" data-testid="signal-status">
            {status}
          </p>
          {reviewed ? (
            <p className="mt-0.5 font-mono text-xs text-muted">confidence {percent(reviewed.confidence)}</p>
          ) : null}
        </div>
        <span data-testid="signal">
          <Stamp signal={signal} />
        </span>
      </div>

      {reviewed?.changed_from_preliminary && reviewed.change_reason ? (
        <p className="mt-3 border-l-2 border-accent pl-3 text-sm leading-relaxed">
          <span className="font-medium">Why it changed: </span>
          {reviewed.change_reason}
        </p>
      ) : null}
      {isStageError(analyst) ? (
        <p className="mt-3 border-l-2 border-sell pl-3 text-sm text-muted">{analyst.message}</p>
      ) : null}

      <div className="mt-5">
        <Factors scorecard={scorecard} />
      </div>

      {reviewed ? (
        <div className="mt-5 space-y-4 text-sm leading-relaxed">
          <p>{reviewed.valuation_summary}</p>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
            <div>
              <h3 className="font-mono text-[0.68rem] uppercase tracking-wider text-buy">Thesis</h3>
              <ul className="mt-1 list-disc space-y-1 pl-4">
                {reviewed.thesis.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="font-mono text-[0.68rem] uppercase tracking-wider text-sell">Counterpoints</h3>
              <ul className="mt-1 list-disc space-y-1 pl-4">
                {reviewed.counterpoints.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
            </div>
          </div>
          <p className="text-muted">
            <span className="font-medium text-ink">Reasoning: </span>
            {reviewed.signal_reasoning}
          </p>
        </div>
      ) : null}
    </div>
  );
}
