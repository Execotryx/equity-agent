"use client";

import Link from "next/link";

import { isStageError } from "@/lib/events";
import type { ReportState } from "@/lib/reportState";
import { useResearchStream } from "@/lib/useResearchStream";

import { AgentProgress } from "./AgentProgress";
import { CompsTable } from "./CompsTable";
import { Diagnostics } from "./Diagnostics";
import { KeyFinancials } from "./KeyFinancials";
import { Disclaimer, Narrative } from "./Narrative";
import { NewsList } from "./NewsList";
import { OfflineBadge } from "./OfflineBadge";
import { PriceChart } from "./PriceChart";
import { PriceHeader } from "./PriceHeader";
import { RiskList } from "./RiskList";
import { Placeholder, Section, SectionError } from "./Section";
import { SignalCard } from "./SignalCard";
import { ValuationChart } from "./ValuationChart";

export function ReportView({ ticker }: { ticker: string }) {
  const { state, retry, refresh } = useResearchStream(ticker);
  return <ReportBody ticker={ticker} state={state} onRetry={retry} onRefresh={refresh} />;
}

function generatedAt(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function Masthead({ ticker, state, onRefresh }: { ticker: string; state: ReportState; onRefresh: () => void }) {
  const running = !state.report && !state.fatal && state.connection !== "unreachable" && state.connection !== "lost";
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-rule-strong pb-3">
      <Link href="/" className="font-display text-2xl leading-none hover:text-accent">
        Equity Research <span className="italic text-accent">Desk</span>
      </Link>
      <div className="flex flex-wrap items-center gap-3 font-mono text-xs text-muted">
        <OfflineBadge />
        <span aria-live="polite">
          {state.report
            ? `${state.fromCache ? "Cached report" : "Report"} · generated ${generatedAt(state.report.generated_at)}`
            : state.fatal
              ? "Run stopped"
              : running
                ? state.validate === "running"
                  ? `Checking ${ticker}…`
                  : "Research in progress…"
                : ""}
        </span>
        <button
          type="button"
          onClick={onRefresh}
          disabled={running}
          className="border border-ink px-3 py-1.5 font-mono text-xs uppercase tracking-wider text-ink transition-colors hover:bg-ink hover:text-paper disabled:cursor-not-allowed disabled:border-rule disabled:text-muted disabled:hover:bg-transparent"
        >
          ↻ Refresh
        </button>
      </div>
    </div>
  );
}

function Notice({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div role="alert" className="arrive mx-auto my-16 max-w-xl border border-rule-strong bg-surface p-8 text-center">
      <p className="font-mono text-[0.68rem] uppercase tracking-[0.18em] text-accent">Stop press</p>
      <h1 className="mt-2 font-display text-4xl leading-tight">{title}</h1>
      <div className="mt-4 space-y-4 text-sm text-muted">{children}</div>
    </div>
  );
}

export function ReportBody({
  ticker,
  state,
  onRetry,
  onRefresh,
}: {
  ticker: string;
  state: ReportState;
  onRetry: () => void;
  onRefresh: () => void;
}) {
  const shell = (content: React.ReactNode) => (
    <div className="flex min-h-screen flex-col">
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 pb-16 pt-5 sm:px-8">
        <Masthead ticker={ticker} state={state} onRefresh={onRefresh} />
        {content}
      </main>
      <Disclaimer />
    </div>
  );

  if (state.fatal && state.fatal.stage === "validate") {
    return shell(
      <Notice title={`${ticker}: ${state.fatal.message}`}>
        <p>
          {state.fatal.message === "not available offline"
            ? "The offline demo only replays the tickers recorded before the demo (AAPL, NVDA, JPM, COST, TSLA, BRK-B, TSM)."
            : "Check the symbol and try again. Only individual US-listed stocks are covered."}
        </p>
        <Link href="/" className="inline-block border border-ink px-4 py-2 font-mono text-xs uppercase tracking-wider text-ink hover:bg-ink hover:text-paper">
          Try another ticker
        </Link>
      </Notice>,
    );
  }
  if (state.connection === "unreachable") {
    return shell(
      <Notice title="The research backend is unreachable">
        <p>
          Start it with <code className="font-mono text-ink">npm run start:all</code> and wait for “Application startup
          complete”.
        </p>
        <button type="button" onClick={onRetry} className="border border-ink px-4 py-2 font-mono text-xs uppercase tracking-wider text-ink hover:bg-ink hover:text-paper">
          Retry
        </button>
      </Notice>,
    );
  }

  const comps = state.comps;
  const writerRunning = state.stages.writer.status === "running";
  return shell(
    <>
      {state.connection === "lost" || state.fatal ? (
        <div role="alert" className="mt-4 flex flex-wrap items-center justify-between gap-3 border-l-2 border-sell bg-accent-soft px-4 py-3 text-sm">
          <span>
            {state.fatal ? `The run stopped: ${state.fatal.message}.` : "The connection to the backend was lost before the report finished."}
          </span>
          <button type="button" onClick={onRetry} className="font-mono text-xs uppercase tracking-wider underline underline-offset-4 hover:text-accent">
            Retry
          </button>
        </div>
      ) : null}

      <div className="mt-6">
        {state.snapshot ? <PriceHeader snapshot={state.snapshot} /> : <Placeholder label={`Loading ${ticker}…`} lines={2} />}
      </div>

      <div className="mt-6">
        <AgentProgress stages={state.stages} usage={state.report?.llm_usage} />
      </div>

      <div className="mt-10 grid gap-x-12 gap-y-12 lg:grid-cols-[minmax(0,1fr)_22rem] xl:grid-cols-[minmax(0,1fr)_25rem]">
        <div className="min-w-0 space-y-12">
          <Section kicker="Financial data agent" title="Key financials" id="financials">
            {state.financials ? (
              <div className="space-y-8">
                <KeyFinancials profile={state.financials} />
                <PriceChart profile={state.financials} />
              </div>
            ) : (
              <Placeholder label="Fetching statements and price history…" />
            )}
          </Section>

          <Section
            kicker="Comps agent"
            title="Comparable companies"
            id="comps"
            aside={comps && !isStageError(comps) ? `${comps.metric_set.replace("_", " ")} metrics` : undefined}
          >
            {!comps ? (
              <Placeholder label="Choosing peers and pulling their multiples…" lines={4} />
            ) : isStageError(comps) ? (
              <SectionError message={comps.message} />
            ) : (
              <div className="space-y-8">
                <CompsTable table={comps} />
                <ValuationChart table={comps} />
              </div>
            )}
          </Section>

          <Section kicker="Writer agent" title="Research note" id="narrative">
            <Narrative text={state.narrative} streaming={writerRunning} error={state.narrativeError} />
          </Section>
        </div>

        <aside className="min-w-0 space-y-12">
          <Section kicker="Analyst agent" title="Rating" id="signal">
            {state.scorecard ? (
              <SignalCard scorecard={state.scorecard} analyst={state.analyst} />
            ) : (
              <Placeholder label="Scoring once comps and financials are in…" lines={4} />
            )}
          </Section>

          <Section kicker="Risk agent" title="Key risks" id="risks">
            {state.risks ? <RiskList risks={state.risks} /> : <Placeholder label="Reading the annual filing…" lines={4} />}
          </Section>

          <Section kicker="News search" title="Recent news" id="news">
            {state.news || state.newsError ? (
              <NewsList items={state.news ?? []} error={state.newsError} />
            ) : (
              <Placeholder label="Searching the news…" />
            )}
          </Section>
        </aside>
      </div>

      {state.report ? (
        <div className="mt-12">
          <Diagnostics report={state.report} fromCache={state.fromCache} />
        </div>
      ) : null}
    </>,
  );
}
