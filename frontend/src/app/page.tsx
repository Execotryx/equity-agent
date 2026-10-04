import { DISCLAIMER } from "@/components/Narrative";
import { OfflineBadge } from "@/components/OfflineBadge";
import { TickerForm } from "@/components/TickerForm";

const DESK = [
  ["Financial data", "Quote, statements and a year of prices"],
  ["Comps", "Picks peers, then explains each choice"],
  ["Risk", "Reads the latest 10-K's risk factors"],
  ["News", "Recent coverage from the web"],
  ["Analyst", "Reviews the five-factor scorecard"],
  ["Writer", "Streams the research note"],
];

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col px-4 py-8 sm:px-8 sm:py-12">
      <div className="flex items-baseline justify-between border-b-[3px] border-double border-rule-strong pb-2 font-mono text-[0.68rem] uppercase tracking-[0.18em] text-muted">
        <span>Equity Research Desk</span>
        <span className="flex items-center gap-3">
          <OfflineBadge />
          Vol. 1 · Local edition
        </span>
      </div>

      <div className="grid flex-1 gap-12 py-12 lg:grid-cols-[1.25fr_1fr] lg:items-end lg:py-20">
        <div className="arrive">
          <h1 className="font-display text-[3.4rem] leading-[0.95] sm:text-7xl lg:text-[6.5rem]">
            A research note,
            <br />
            <span className="italic text-accent">written live</span> by six agents.
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-relaxed text-muted">
            Enter a US stock. Tables arrive in seconds, the rating and the written note follow, each section the moment
            its agent finishes.
          </p>
          <div className="mt-10 max-w-xl">
            <TickerForm />
          </div>
        </div>

        <ol className="arrive border-t border-rule-strong [animation-delay:150ms]" aria-label="The research desk">
          {DESK.map(([name, role], i) => (
            <li key={name} className="grid grid-cols-[2.5rem_1fr] items-baseline gap-2 border-b border-rule py-3">
              <span className="font-mono text-xs text-accent tabular">{String(i + 1).padStart(2, "0")}</span>
              <span>
                <span className="font-display text-2xl">{name}</span>
                <span className="block text-sm text-muted">{role}</span>
              </span>
            </li>
          ))}
        </ol>
      </div>

      <p className="border-t border-rule pt-3 text-center font-mono text-[0.7rem] uppercase tracking-[0.14em] text-muted">
        {DISCLAIMER}
      </p>
    </main>
  );
}
