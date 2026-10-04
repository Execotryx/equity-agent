import type { ResearchReport } from "@/lib/events";
import { seconds, usd } from "@/lib/format";

/** Collapsible run details: stage timings, model usage and cost, cache hits and quality warnings. */
export function Diagnostics({ report, fromCache }: { report: ResearchReport; fromCache?: boolean }) {
  const usage = report.llm_usage ?? [];
  const timings = Object.entries(report.timings_ms ?? {});
  const cost = usage.reduce((sum, u) => sum + u.cost_usd, 0);
  const warnings = report.quality_warnings ?? [];
  const hits = report.cache_hits ?? [];
  return (
    <details className="group border border-rule bg-surface">
      <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-2 px-4 py-3 font-mono text-xs uppercase tracking-wider">
        <span>
          <span className="mr-2 inline-block transition-transform group-open:rotate-90" aria-hidden>
            ▸
          </span>
          Diagnostics
        </span>
        <span className="text-muted">
          {usage.length} model calls · {usd(cost)}
          {report.timings_ms?.total !== undefined ? ` · ${seconds(report.timings_ms.total)}` : ""}
          {fromCache ? " · served from cache" : ""}
          {warnings.length > 0 ? ` · ${warnings.length} warning${warnings.length > 1 ? "s" : ""}` : ""}
        </span>
      </summary>
      <div className="grid gap-6 border-t border-rule px-4 py-4 text-xs md:grid-cols-2">
        <div className="min-w-0">
          <h3 className="mb-1 font-mono uppercase tracking-wider text-muted">Stage timings</h3>
          <table className="w-full font-mono tabular">
            <tbody>
              {timings.map(([stage, ms]) => (
                <tr key={stage} className="border-b border-rule last:border-0">
                  <th scope="row" className="py-1 text-left font-normal">{stage}</th>
                  <td className="py-1 text-right">{seconds(ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="min-w-0 overflow-x-auto">
          <h3 className="mb-1 font-mono uppercase tracking-wider text-muted">Model calls</h3>
          <table className="w-full font-mono tabular">
            <thead>
              <tr className="text-muted">
                <th scope="col" className="py-1 text-left font-normal">agent</th>
                <th scope="col" className="py-1 text-left font-normal">model</th>
                <th scope="col" className="py-1 text-right font-normal">in/out</th>
                <th scope="col" className="py-1 text-right font-normal">time</th>
                <th scope="col" className="py-1 text-right font-normal">cost</th>
              </tr>
            </thead>
            <tbody>
              {usage.map((u, i) => (
                <tr key={i} className="border-t border-rule">
                  <td className="py-1 pr-2">{u.agent}</td>
                  <td className="py-1 pr-2">{u.model.replace(/^claude-/, "")}</td>
                  <td className="py-1 text-right">
                    {u.input_tokens}/{u.output_tokens}
                  </td>
                  <td className="py-1 text-right">{seconds(u.ms)}</td>
                  <td className="py-1 text-right">{u.error ? "error" : usd(u.cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {hits.length > 0 ? (
          <div className="min-w-0">
            <h3 className="mb-1 font-mono uppercase tracking-wider text-muted">Cache hits</h3>
            <ul className="space-y-0.5 font-mono break-all text-muted">
              {hits.map((hit) => (
                <li key={hit}>{hit}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {warnings.length > 0 ? (
          <div className="min-w-0">
            <h3 className="mb-1 font-mono uppercase tracking-wider text-hold">Quality warnings</h3>
            <ul className="list-disc space-y-0.5 pl-4">
              {warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </details>
  );
}
