import type { FinancialProfile } from "@/lib/events";
import { metricLabel, metricText, money, type MetricKey } from "@/lib/format";

const SHOWN: MetricKey[] = [
  "pe_ttm",
  "pe_fwd",
  "ev_ebitda",
  "price_to_book",
  "net_margin",
  "roe",
  "revenue_growth",
  "debt_to_equity",
  "dividend_yield",
];

/** A horizontal bar on its own track, with the value in a fixed slot so it never overflows a narrow column. */
function Bar({ share, label, thin = false }: { share: number; label: string; thin?: boolean }) {
  return (
    <div className="grid grid-cols-[1fr_5.5rem] items-center gap-2">
      <span className="block">
        <span className={`block ${thin ? "h-1.5 bg-accent" : "h-2.5 bg-ink"}`} style={{ width: `${share * 100}%` }} />
      </span>
      <span className={`text-right font-mono tabular ${thin ? "text-[0.68rem] text-muted" : "text-xs"}`}>{label}</span>
    </div>
  );
}

/** The target's multiples as a figure grid, plus revenue and EBITDA by fiscal year. */
export function KeyFinancials({ profile }: { profile: FinancialProfile }) {
  const currency = profile.snapshot.currency;
  const years = [...profile.revenue_history].sort((a, b) => a.year - b.year).slice(-4);
  const ebitda = new Map(profile.ebitda_history.map((y) => [y.year, y.value]));
  const top = Math.max(1, ...years.map((y) => y.value));
  return (
    <div className="arrive grid gap-8 lg:grid-cols-[3fr_2fr]">
      <dl className="grid grid-cols-2 gap-px overflow-hidden border border-rule bg-rule sm:grid-cols-3">
        {SHOWN.map((metric) => (
          <div key={metric} className="bg-surface px-3 py-2.5">
            <dt className="text-xs text-muted">{metricLabel(metric)}</dt>
            <dd className="font-mono text-xl tabular">{metricText(metric, profile.multiples[metric])}</dd>
          </div>
        ))}
        {profile.analyst_target_mean !== null ? (
          <div className="col-span-2 bg-surface px-3 py-2.5 sm:col-span-3">
            <dt className="text-xs text-muted">Wall Street mean target</dt>
            <dd className="font-mono text-xl tabular">
              {money(profile.analyst_target_mean, currency)}
              {profile.analyst_recommendation ? (
                <span className="ml-2 text-sm uppercase text-muted">({profile.analyst_recommendation})</span>
              ) : null}
            </dd>
          </div>
        ) : null}
      </dl>
      {years.length > 0 ? (
        <figure>
          <figcaption className="mb-2 font-mono text-[0.68rem] uppercase tracking-wider text-muted">
            Revenue <span className="text-ink">■</span> and EBITDA <span className="text-accent">■</span> by fiscal year
          </figcaption>
          <ul className="space-y-2.5">
            {years.map((y) => {
              const e = ebitda.get(y.year);
              return (
                <li key={y.year} className="grid grid-cols-[3rem_1fr] items-center gap-2">
                  <span className="font-mono text-xs tabular text-muted">FY{String(y.year).slice(-2)}</span>
                  <div className="space-y-1">
                    <Bar share={y.value / top} label={money(y.value, currency)} />
                    {e !== undefined ? <Bar share={Math.max(0, e) / top} label={money(e, currency)} thin /> : null}
                  </div>
                </li>
              );
            })}
          </ul>
        </figure>
      ) : null}
    </div>
  );
}
