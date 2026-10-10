"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { QUICK_PICKS, normalizeTicker } from "@/lib/api";

export function TickerForm() {
  const router = useRouter();
  const [value, setValue] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const open = (raw: string) => {
    const ticker = normalizeTicker(raw);
    if (!ticker) {
      setMessage(raw.trim() ? "That doesn't look like a ticker: use up to 10 letters, digits, “.”, “_” or “-”, starting with a letter." : "Enter a ticker, for example AAPL.");
      return;
    }
    setMessage(null);
    router.push(`/report/${encodeURIComponent(ticker)}`);
  };

  return (
    <div>
      <form
        role="search"
        onSubmit={(event) => {
          event.preventDefault();
          open(value);
        }}
        className="flex items-stretch border-2 border-ink bg-surface focus-within:border-accent"
      >
        <label htmlFor="ticker" className="sr-only">
          Ticker symbol
        </label>
        <input
          id="ticker"
          name="ticker"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="Ticker, e.g. AAPL"
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          maxLength={12}
          aria-invalid={message ? true : undefined}
          aria-describedby={message ? "ticker-message" : undefined}
          className="min-w-0 flex-1 bg-transparent px-4 py-3.5 font-mono text-2xl uppercase tracking-wider placeholder:normal-case placeholder:tracking-normal placeholder:text-muted/70 focus:outline-none"
        />
        <button type="submit" className="bg-ink px-5 font-mono text-sm uppercase tracking-wider text-paper transition-colors hover:bg-accent">
          Research →
        </button>
      </form>
      <p id="ticker-message" role="alert" className="mt-2 min-h-5 text-sm text-sell">
        {message}
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="mr-1 font-mono text-[0.68rem] uppercase tracking-[0.18em] text-muted">Quick picks</span>
        {QUICK_PICKS.map((ticker) => (
          <button
            key={ticker}
            type="button"
            onClick={() => open(ticker)}
            className="border border-rule px-3 py-1 font-mono text-sm tracking-wider transition-colors hover:border-ink hover:bg-ink hover:text-paper"
          >
            {ticker}
          </button>
        ))}
      </div>
    </div>
  );
}
