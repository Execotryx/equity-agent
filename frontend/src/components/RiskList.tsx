import { isStageError, type RiskReport, type StageError } from "@/lib/events";

import { SectionError } from "./Section";

const SEVERITY = {
  3: { label: "High", className: "border-sell text-sell" },
  2: { label: "Medium", className: "border-hold text-hold" },
  1: { label: "Low", className: "border-rule text-muted" },
} as const;

/** The Risk Agent's selection from the latest annual filing, most severe first. */
export function RiskList({ risks }: { risks: RiskReport | StageError }) {
  if (isStageError(risks)) return <SectionError message={risks.message} />;
  const sorted = [...risks.risks].sort((a, b) => b.severity - a.severity);
  const filing = risks.filing;
  return (
    <div className="arrive">
      <ol className="divide-y divide-rule">
        {sorted.map((risk) => {
          const severity = SEVERITY[risk.severity];
          return (
            <li key={risk.title} className="py-3 first:pt-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded-sm border px-1.5 font-mono text-[0.62rem] uppercase tracking-wider ${severity.className}`}>
                  {severity.label}
                  <span className="sr-only"> severity</span>
                </span>
                <span className="font-mono text-[0.62rem] uppercase tracking-wider text-muted">
                  {risk.category.replace("_", " ")}
                </span>
              </div>
              <h3 className="mt-1 font-medium leading-snug">{risk.title}</h3>
              <p className="mt-0.5 text-sm leading-relaxed text-muted">{risk.explanation}</p>
            </li>
          );
        })}
      </ol>
      <p className="mt-2 text-xs text-muted">
        From the{" "}
        <a className="underline decoration-rule underline-offset-2 hover:text-accent" href={filing.url} target="_blank" rel="noreferrer">
          {filing.form} filed {filing.filing_date}
        </a>
        {risks.headings_truncated ? " (risk headings truncated to fit the agent's budget)" : ""}.
      </p>
    </div>
  );
}
