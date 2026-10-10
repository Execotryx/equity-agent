import type { Snapshot } from "@/lib/events";
import { money } from "@/lib/format";

/** Company, price, market cap and where the price sits in its 52-week range. */
export function PriceHeader({ snapshot }: { snapshot: Snapshot }) {
  const { week52_low: low, week52_high: high, price } = snapshot;
  const position = low !== null && high !== null && high > low ? Math.min(1, Math.max(0, (price - low) / (high - low))) : null;
  return (
    <header className="arrive grid gap-6 md:grid-cols-[1fr_auto] md:items-end">
      <div className="min-w-0">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-muted">
          {[snapshot.sector, snapshot.industry].filter(Boolean).join(" · ") || "Equity"}
        </p>
        <h1 className="mt-1 font-display text-[2.6rem] leading-[1.02] sm:text-6xl">
          {snapshot.name}{" "}
          <span className="font-mono text-xl tracking-normal text-accent align-middle sm:text-2xl">{snapshot.ticker}</span>
        </h1>
      </div>
      <dl className="grid grid-cols-2 gap-x-8 gap-y-3 md:text-right">
        <div>
          <dt className="font-mono text-[0.68rem] uppercase tracking-wider text-muted">Price</dt>
          <dd className="font-mono text-3xl tabular">{money(price, snapshot.currency)}</dd>
          {snapshot.quote_provenance ? (
            <dd className="mt-1 text-xs text-muted">
              <a href={snapshot.quote_provenance.source_url} target="_blank" rel="noreferrer" className="underline">
                {snapshot.quote_provenance.provider} · {snapshot.quote_provenance.exchange} · {snapshot.quote_provenance.source_symbol}
              </a>
              <span className="block">Source timestamp: {snapshot.quote_provenance.timestamp ?? "unavailable"}</span>
            </dd>
          ) : null}
        </div>
        <div>
          <dt className="font-mono text-[0.68rem] uppercase tracking-wider text-muted">Market cap</dt>
          <dd className="font-mono text-3xl tabular">{money(snapshot.market_cap, snapshot.currency)}</dd>
        </div>
        {position !== null ? (
          <div className="col-span-2">
            <dt className="sr-only">52-week range</dt>
            <dd>
              <div className="flex items-center gap-2 font-mono text-[0.7rem] tabular text-muted">
                <span>{money(low, snapshot.currency)}</span>
                <span className="relative h-1.5 flex-1 rounded-full bg-rule md:w-56 md:flex-none" aria-hidden>
                  <span
                    className="absolute top-1/2 h-3.5 w-1 -translate-x-1/2 -translate-y-1/2 bg-accent"
                    style={{ left: `${position * 100}%` }}
                  />
                </span>
                <span>{money(high, snapshot.currency)}</span>
              </div>
              <p className="mt-0.5 font-mono text-[0.65rem] uppercase tracking-wider text-muted">
                52-week range · {Math.round(position * 100)}% of the way up
              </p>
            </dd>
          </div>
        ) : null}
      </dl>
    </header>
  );
}
