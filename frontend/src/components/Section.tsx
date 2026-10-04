import type { ReactNode } from "react";

/** A report section under a double rule, with a small-caps kicker and a serif title. */
export function Section({
  kicker,
  title,
  aside,
  children,
  className = "",
  id,
}: {
  kicker: string;
  title: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section aria-labelledby={id} className={`double-rule pt-3 ${className}`}>
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div>
          <p className="font-mono text-[0.68rem] uppercase tracking-[0.18em] text-accent">{kicker}</p>
          <h2 id={id} className="font-display text-[1.75rem] leading-tight">
            {title}
          </h2>
        </div>
        {aside ? <div className="text-sm text-muted">{aside}</div> : null}
      </div>
      {children}
    </section>
  );
}

/** Shimmering lines shown until a section's data arrives. */
export function Placeholder({ label, lines = 3 }: { label: string; lines?: number }) {
  return (
    <div role="status" aria-label={label} className="space-y-2.5 py-1">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="placeholder-line h-3 rounded-sm" style={{ width: `${92 - i * 17}%` }} />
      ))}
      <p className="pt-1 font-mono text-xs text-muted">{label}</p>
    </div>
  );
}

/** A section that failed: its reason in place of the content. */
export function SectionError({ message }: { message: string }) {
  return (
    <p role="note" className="border-l-2 border-sell bg-accent-soft px-3 py-2 text-sm">
      <span className="font-mono text-xs uppercase tracking-wider text-sell">Unavailable · </span>
      {message}
    </p>
  );
}
