"use client";

import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { CompsTable } from "@/lib/events";
import { meaningful, metricLabel, metricText } from "@/lib/format";

export function valuationSummary(table: CompsTable): string {
  const metric = table.primary_metric;
  const label = metricLabel(metric);
  const target = table.rows.find((r) => r.is_target);
  const median = (table.median as Record<string, number | null>)[metric];
  const own = target ? (target.multiples as Record<string, number | null>)[metric] : null;
  const pct = table.target_vs_median_pct[metric];
  const relation =
    pct === null || pct === undefined ? "" : `, a ${Math.abs(pct * 100).toFixed(0)}% ${pct >= 0 ? "premium" : "discount"}`;
  return `${label}: ${target?.ticker ?? "target"} ${metricText(metric, own)} vs a peer median of ${metricText(metric, median)}${relation}.`;
}

/** The primary valuation multiple for the target and each peer, with the peer median as a reference line. */
export function ValuationChart({ table }: { table: CompsTable }) {
  const metric = table.primary_metric;
  const data = table.rows
    .map((row) => ({
      ticker: row.ticker,
      target: row.is_target,
      value: meaningful(metric, (row.multiples as Record<string, number | null>)[metric]),
    }))
    .filter((d): d is { ticker: string; target: boolean; value: number } => d.value !== null);
  const median = meaningful(metric, (table.median as Record<string, number | null>)[metric]);
  const summary = valuationSummary(table);
  return (
    <figure className="arrive">
      <div className="h-48 w-full" aria-hidden>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart accessibilityLayer={false} data={data} margin={{ top: 14, right: 8, bottom: 0, left: 0 }}>
            <XAxis
              dataKey="ticker"
              tick={{ fontSize: 11, fill: "var(--muted)", fontFamily: "var(--font-plex-mono)" }}
              axisLine={{ stroke: "var(--rule)" }}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "var(--muted)", fontFamily: "var(--font-plex-mono)" }}
              axisLine={false}
              tickLine={false}
              width={40}
            />
            <Tooltip
              cursor={{ fill: "var(--accent-soft)" }}
              contentStyle={{ background: "var(--surface)", border: "1px solid var(--rule)", fontFamily: "var(--font-plex-mono)", fontSize: 12 }}
              formatter={(v) => [metricText(metric, Number(v)), metricLabel(metric)]}
            />
            {median !== null ? (
              <ReferenceLine
                y={median}
                stroke="var(--accent)"
                strokeDasharray="4 3"
                label={{ value: `median ${metricText(metric, median)}`, position: "insideTopRight", fontSize: 11, fill: "var(--accent)" }}
              />
            ) : null}
            <Bar dataKey="value" isAnimationActive={false} radius={[1, 1, 0, 0]}>
              {data.map((d) => (
                <Cell key={d.ticker} fill={d.target ? "var(--accent)" : "var(--ink)"} fillOpacity={d.target ? 1 : 0.75} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="mt-1 text-xs text-muted">{summary}</figcaption>
    </figure>
  );
}
