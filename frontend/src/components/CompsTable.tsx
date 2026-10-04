import type { CompRow, CompsTable as Comps } from "@/lib/events";
import { MISSING, metricLabel, metricText, money } from "@/lib/format";

function value(row: { multiples: Comps["median"] } | Comps["median"], metric: string): number | null {
  const multiples = "multiples" in row ? row.multiples : row;
  return (multiples as Record<string, number | null>)[metric] ?? null;
}

function versusMedian(pct: number | null | undefined) {
  if (pct === null || pct === undefined) return <span className="text-muted">{MISSING}</span>;
  const up = pct > 0;
  const text = `${up ? "▲" : pct < 0 ? "▼" : "■"} ${Math.abs(pct * 100).toFixed(0)}%`;
  return (
    <span className={up ? "text-accent" : "text-ink"}>
      {text}
      <span className="sr-only">{up ? " premium to the median" : " discount to the median"}</span>
    </span>
  );
}

/** The peer's name with its rationale on hover or keyboard focus. */
function PeerName({ row, rationale, pending, fallback }: { row: CompRow; rationale?: string; pending: boolean; fallback: boolean }) {
  const note = rationale ?? (pending ? "Rationale pending…" : undefined);
  const id = `rationale-${row.ticker}`;
  return (
    <div className="group relative">
      <button
        type="button"
        aria-describedby={note ? id : undefined}
        className="cursor-help text-left underline decoration-rule decoration-dotted underline-offset-4 hover:decoration-accent focus-visible:decoration-accent"
      >
        <span className="font-mono font-medium">{row.ticker}</span>
        <span className="ml-2 hidden text-muted sm:inline">{row.name}</span>
      </button>
      {fallback ? (
        <span className="ml-2 rounded-sm border border-rule px-1 font-mono text-[0.6rem] uppercase tracking-wider text-muted">
          sector list
        </span>
      ) : null}
      {note ? (
        <span
          id={id}
          role="tooltip"
          className="pointer-events-none invisible absolute left-0 top-full z-20 mt-1 w-72 max-w-[80vw] border border-rule bg-surface p-2.5 text-xs leading-relaxed text-ink opacity-0 shadow-lg transition-opacity group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100"
        >
          {rationale ?? <em className="text-muted">Rationale pending…</em>}
        </span>
      ) : null}
    </div>
  );
}

/** Target, peers, the peer median and the target's premium or discount to it, per metric. */
export function CompsTable({ table }: { table: Comps }) {
  const rationales = table.peer_rationales ?? {};
  const pending = Object.keys(rationales).length === 0;
  const origin = table.peer_origin ?? {};
  const sources = table.sources ?? [];
  return (
    <div className="arrive">
      {/* relative: the cells' visually hidden labels are absolutely positioned and must stay inside this scroll box */}
      <div className="relative overflow-x-auto border-y border-rule" tabIndex={0} aria-label="Comparable companies table, scrollable">
        <table className="w-full min-w-[36rem] border-collapse text-sm">
          <caption className="sr-only">
            Comparable companies by {table.metrics.map(metricLabel).join(", ")}; the first row is the target.
          </caption>
          <thead>
            <tr className="border-b border-rule-strong text-left">
              <th scope="col" className="py-2 pr-3 font-mono text-[0.68rem] font-normal uppercase tracking-wider text-muted">
                Company
              </th>
              <th scope="col" className="px-3 py-2 text-right font-mono text-[0.68rem] font-normal uppercase tracking-wider text-muted">
                Mkt cap
              </th>
              {table.metrics.map((metric) => (
                <th
                  key={metric}
                  scope="col"
                  className={`px-3 py-2 text-right font-mono text-[0.68rem] font-normal uppercase tracking-wider ${
                    metric === table.primary_metric ? "text-accent" : "text-muted"
                  }`}
                >
                  {metricLabel(metric)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row) => (
              <tr
                key={row.ticker}
                className={row.is_target ? "bg-accent-soft font-medium" : "border-b border-rule last:border-b-0"}
              >
                <th scope="row" className="py-2 pr-3 text-left font-normal">
                  {row.is_target ? (
                    <span>
                      <span className="font-mono font-semibold">{row.ticker}</span>
                      <span className="ml-2 hidden text-muted sm:inline">{row.name}</span>
                      <span className="ml-2 font-mono text-[0.6rem] uppercase tracking-wider text-accent">target</span>
                    </span>
                  ) : (
                    <PeerName
                      row={row}
                      rationale={rationales[row.ticker]}
                      pending={pending}
                      fallback={origin[row.ticker] === "fallback"}
                    />
                  )}
                </th>
                <td className="px-3 py-2 text-right font-mono tabular text-muted">{money(row.market_cap)}</td>
                {table.metrics.map((metric) => (
                  <td key={metric} className="px-3 py-2 text-right font-mono tabular">
                    {metricText(metric, value(row, metric))}
                  </td>
                ))}
              </tr>
            ))}
            <tr className="border-t border-rule-strong">
              <th scope="row" className="py-2 pr-3 text-left font-mono text-xs font-normal uppercase tracking-wider">
                Peer median
              </th>
              <td />
              {table.metrics.map((metric) => (
                <td key={metric} className="px-3 py-2 text-right font-mono tabular font-medium">
                  {metricText(metric, value(table.median, metric))}
                </td>
              ))}
            </tr>
            <tr>
              <th scope="row" className="py-2 pr-3 text-left font-mono text-xs font-normal uppercase tracking-wider text-muted">
                Target vs median
              </th>
              <td />
              {table.metrics.map((metric) => (
                <td key={metric} className="px-3 py-2 text-right font-mono text-xs tabular">
                  {versusMedian(table.target_vs_median_pct[metric])}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
      <div className="mt-2 flex flex-wrap items-baseline justify-between gap-2 text-xs text-muted">
        <p>{pending ? "Peer rationales are being written…" : "Hover or focus a peer for why it was chosen."}</p>
        {sources.length > 0 ? (
          <p className="min-w-0">
            Peer discovery:{" "}
            {sources.slice(0, 5).map((url, i) => (
              <span key={url}>
                {i > 0 ? " · " : ""}
                <a className="underline decoration-rule underline-offset-2 hover:text-accent" href={url} target="_blank" rel="noreferrer">
                  {new URL(url).hostname.replace(/^www\./, "")}
                </a>
              </span>
            ))}
          </p>
        ) : null}
      </div>
      {table.exclusions && table.exclusions.length > 0 ? (
        <p className="mt-1 text-xs text-muted">
          Excluded: {table.exclusions.map((e) => `${e.ticker} (${e.reason})`).join("; ")}
        </p>
      ) : null}
    </div>
  );
}
