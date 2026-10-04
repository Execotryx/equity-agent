"use client";

import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { FinancialProfile } from "@/lib/events";
import { money, pctChange } from "@/lib/format";

type Point = { date: string; close: number };

/** Every fifth trading day plus the last one: a year of daily closes as about 52 weekly points. */
export function weekly(points: Point[]): Point[] {
  return points.filter((_, i) => i % 5 === 0 || i === points.length - 1);
}

export function priceSummary(points: Point[], currency: string): string {
  if (points.length < 2) return "Not enough price history to chart.";
  const first = points[0];
  const last = points[points.length - 1];
  const closes = points.map((p) => p.close);
  return (
    `Closing price from ${first.date} to ${last.date}: ${money(first.close, currency)} to ${money(last.close, currency)} ` +
    `(${pctChange(last.close / first.close - 1)}), low ${money(Math.min(...closes), currency)}, ` +
    `high ${money(Math.max(...closes), currency)}.`
  );
}

export function PriceChart({ profile }: { profile: FinancialProfile }) {
  const data = weekly(profile.price_history);
  const currency = profile.snapshot.currency;
  const summary = priceSummary(profile.price_history, currency);
  if (data.length < 2) return <p className="text-sm text-muted">{summary}</p>;
  return (
    <figure className="arrive">
      <div className="h-56 w-full text-muted" aria-hidden>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart accessibilityLayer={false} data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <XAxis
              dataKey="date"
              tickFormatter={(d: string) => d.slice(5, 7) + "/" + d.slice(2, 4)}
              tick={{ fontSize: 11, fill: "var(--muted)", fontFamily: "var(--font-plex-mono)" }}
              axisLine={{ stroke: "var(--rule)" }}
              tickLine={false}
              minTickGap={28}
            />
            <YAxis
              domain={["auto", "auto"]}
              tick={{ fontSize: 11, fill: "var(--muted)", fontFamily: "var(--font-plex-mono)" }}
              axisLine={false}
              tickLine={false}
              width={48}
              tickFormatter={(v: number) => v.toFixed(0)}
            />
            <Tooltip
              contentStyle={{ background: "var(--surface)", border: "1px solid var(--rule)", fontFamily: "var(--font-plex-mono)", fontSize: 12 }}
              formatter={(v) => [money(Number(v), currency), "Close"]}
            />
            <Line type="monotone" dataKey="close" stroke="var(--ink)" strokeWidth={1.6} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="sr-only">{summary}</figcaption>
    </figure>
  );
}
