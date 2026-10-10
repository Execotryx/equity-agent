import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { isStageError, type AnalystView, type CompsTable as Comps, type FinancialProfile, type RiskReport, type StreamEvent } from "@/lib/events";
import { initialState, reduce, reduceAll } from "@/lib/reportState";
import { FIXTURES, finalState, reportOf } from "@/test/fixtures";

import { AgentProgress } from "./AgentProgress";
import { CompsTable } from "./CompsTable";
import { KeyFinancials } from "./KeyFinancials";
import { Narrative } from "./Narrative";
import { PriceChart, priceSummary } from "./PriceChart";
import { PriceHeader } from "./PriceHeader";
import { ReportBody } from "./ReportView";
import { RiskList } from "./RiskList";
import { SignalCard } from "./SignalCard";
import { TickerForm } from "./TickerForm";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const aapl = reportOf(FIXTURES.aapl);
const jpm = reportOf(FIXTURES.jpm);
const noop = () => {};

describe("TickerForm", () => {
  it("navigates to a native KASE report without changing the underscore", () => {
    render(<TickerForm />);
    fireEvent.change(screen.getByLabelText("Ticker symbol"), { target: { value: " frhc_kz " } });
    fireEvent.submit(screen.getByRole("search"));
    expect(push).toHaveBeenCalledWith("/report/FRHC_KZ");
  });
  it("rejects invalid input inline without navigating", () => {
    render(<TickerForm />);
    fireEvent.change(screen.getByLabelText("Ticker symbol"), { target: { value: "$$$" } });
    fireEvent.submit(screen.getByRole("search"));
    expect(screen.getByRole("alert").textContent).toMatch(/look like a ticker/);
    expect(push).not.toHaveBeenCalled();
  });

  it("opens the upper-cased report page", () => {
    render(<TickerForm />);
    fireEvent.change(screen.getByLabelText("Ticker symbol"), { target: { value: " nvda " } });
    fireEvent.submit(screen.getByRole("search"));
    expect(push).toHaveBeenCalledWith("/report/NVDA");
  });
});

describe("AgentProgress", () => {
  it("follows stage events", () => {
    const events: StreamEvent[] = [
      { event: "stage", data: { stage: "comps", status: "started" } },
      { event: "stage", data: { stage: "risk", status: "started" } },
      { event: "stage", data: { stage: "comps", status: "done", ms: 8400, cached: false } },
      { event: "stage", data: { stage: "risk", status: "failed", ms: 1200 } },
      { event: "stage", data: { stage: "news", status: "done", ms: 300, cached: true } },
    ];
    render(<AgentProgress stages={reduceAll(events).stages} />);
    const comps = within(screen.getByTestId("stage-comps"));
    expect(comps.getByText("Done")).toBeTruthy();
    expect(comps.getByText("8.4 s")).toBeTruthy();
    expect(within(screen.getByTestId("stage-risk")).getByText("Failed")).toBeTruthy();
    expect(within(screen.getByTestId("stage-news")).getByText("cached")).toBeTruthy();
    expect(within(screen.getByTestId("stage-writer")).getByText("Queued")).toBeTruthy();
  });

  it("shows the model once the report names it", () => {
    render(<AgentProgress stages={finalState(FIXTURES.aapl).stages} usage={aapl.llm_usage} />);
    expect(within(screen.getByTestId("stage-writer")).getByText("sonnet-5-5")).toBeTruthy();
  });
});

describe("header, financials and chart (AAPL)", () => {
  it("shows KASE quote provenance, timestamp and official casing", () => {
    render(<PriceHeader snapshot={{ ...aapl.financials.snapshot, quote_provenance: {
      provider: "KASE", exchange: "KASE", source_symbol: "KSPId", source_url: "https://kase.kz/api/instruments/securities/KSPId/",
      timestamp: "2026-10-09T17:31:02",
    } }} />);
    expect(screen.getByRole("link", { name: "KASE · KASE · KSPId" }).getAttribute("href")).toContain("KSPId/");
    expect(screen.getByText("Source timestamp: 2026-10-09T17:31:02")).toBeTruthy();
  });

  it("labels KZT accounts independently of a USD price and analyst estimate", () => {
    const { container } = render(<KeyFinancials profile={{ ...aapl.financials, financial_currency: "KZT", enrichment_provenance: {
      provider: "Yahoo Finance", source_symbol: "KSPI", source_url: "https://finance.yahoo.com/quote/KSPI/",
      native_isin: "US48581R2058", native_shares_per_unit: 1, source_shares_per_unit: 1,
      identity_source_url: "https://kase.kz/en/investors/depts/KSPId",
      analyst_target_basis: "Cross-listing estimate in USD, adjusted by verified shares per quoted unit.",
    } }} />);
    expect(screen.getByText(/Reporting currency: KZT/)).toBeTruthy();
    expect(container.querySelector("figure")?.textContent).toContain("KZT ");
    expect(container.querySelector("figure")?.textContent).not.toContain("$");
    expect(screen.getByText("Cross-listing mean target estimate")).toBeTruthy();
  });

  it("omits monetary history when native reporting currency is unknown", () => {
    const { container } = render(<KeyFinancials profile={{ ...aapl.financials, financial_currency: null,
      snapshot: { ...aapl.financials.snapshot, quote_provenance: {
        provider: "KASE", exchange: "KASE", source_symbol: "CORE_KZ", source_url: "https://kase.kz/", timestamp: null,
      } },
    }} />);
    expect(container.querySelector("figure")).toBeNull();
    expect(screen.getByText("Reporting currency unknown; monetary history omitted.")).toBeTruthy();
  });

  it.each(["null", "missing"])("omits legacy monetary history without a reporting currency: %s", (currency) => {
    const legacy: Partial<FinancialProfile> = { ...aapl.financials, financial_currency: null };
    if (currency === "missing") delete legacy.financial_currency;
    const { container } = render(<KeyFinancials profile={legacy as FinancialProfile} />);
    expect(container.querySelector("figure")).toBeNull();
    expect(screen.getByText("Reporting currency unknown; monetary history omitted.")).toBeTruthy();
  });
  it("renders the snapshot", () => {
    render(<PriceHeader snapshot={aapl.financials.snapshot} />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("AAPL");
    expect(screen.getByText("Market cap")).toBeTruthy();
    expect(screen.getByText(/52-week range ·/)).toBeTruthy();
  });

  it("renders the multiples grid", () => {
    render(<KeyFinancials profile={aapl.financials} />);
    expect(screen.getByText("P/E (ttm)")).toBeTruthy();
    expect(screen.getByText(/by fiscal year/)).toBeTruthy();
  });

  it("has a text alternative for the price chart", () => {
    const { container } = render(<PriceChart profile={aapl.financials} />);
    const caption = container.querySelector("figcaption")?.textContent;
    expect(caption).toBe(priceSummary(aapl.financials.price_history, aapl.financials.snapshot.currency));
    expect(caption).toMatch(/^Closing price from .* low .* high/);
  });
});

describe("CompsTable", () => {
  it("highlights the target and shows a median and versus-median row (general metrics)", () => {
    render(<CompsTable table={aapl.comps as Comps} />);
    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toContain("EV/EBITDA");
    expect(screen.getByText("target")).toBeTruthy();
    expect(screen.getByText("Peer median")).toBeTruthy();
    expect(screen.getAllByText(/[▲▼]/).length).toBeGreaterThan(0);
  });

  it("uses P/B and ROE and no EV/EBITDA for the financials metric set (JPM)", () => {
    render(<CompsTable table={jpm.comps as Comps} />);
    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(expect.arrayContaining(["P/B", "ROE"]));
    expect(headers).not.toContain("EV/EBITDA");
  });

  it("shows a missing metric as an em dash", () => {
    const table = structuredClone(aapl.comps as Comps);
    table.rows[1].multiples.ev_ebitda = null;
    render(<CompsTable table={table} />);
    const row = screen.getByRole("rowheader", { name: new RegExp(table.rows[1].ticker) }).closest("tr")!;
    const cells = row.querySelectorAll("td"); // market cap first, then one cell per metric
    expect(cells[1 + table.metrics.indexOf("ev_ebitda")].textContent).toBe("—");
  });

  it("fills in rationales when the second comps partial arrives, without re-mounting", () => {
    const partials = FIXTURES.aapl.filter((e) => e.event === "partial" && e.data.key === "comps");
    const [first, second] = partials.map((e) => (e.data as { value: Comps }).value);
    const { rerender } = render(<CompsTable table={first} />);
    const peer = first.rows.find((r) => !r.is_target)!.ticker;
    const button = screen.getByRole("button", { name: new RegExp(peer) });
    expect(document.getElementById(`rationale-${peer}`)?.textContent).toBe("Rationale pending…");
    rerender(<CompsTable table={second} />);
    expect(screen.getByRole("button", { name: new RegExp(peer) })).toBe(button);
    expect(document.getElementById(`rationale-${peer}`)?.textContent).toBe(second.peer_rationales?.[peer]);
  });
});

describe("RiskList", () => {
  it("lists risks most severe first with a filing link", () => {
    const risks = aapl.risks as RiskReport;
    render(<RiskList risks={risks} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(risks.risks.length);
    expect(screen.getByRole("link").getAttribute("href")).toBe(risks.filing.url);
  });

  it("shows the reason when the section failed", () => {
    const failed = reportOf(FIXTURES.aaplRiskFailed).risks;
    if (!isStageError(failed)) throw new Error("expected a failed risk section");
    render(<RiskList risks={failed} />);
    expect(screen.getByRole("note").textContent).toContain(failed.message);
  });
});

describe("SignalCard", () => {
  const analyst = aapl.analyst as AnalystView;

  it("shows a confirmed signal with its confidence", () => {
    render(<SignalCard scorecard={aapl.scorecard} analyst={analyst} />);
    expect(screen.getByTestId("signal").textContent).toBe(analyst.signal);
    expect(screen.getByTestId("signal-status").textContent).toBe("Confirmed by the analyst");
    expect(screen.getByText(/confidence 60%/)).toBeTruthy();
  });

  it("shows a changed signal with the reason", () => {
    const changed: AnalystView = {
      ...analyst,
      preliminary_signal: "HOLD",
      signal: "BUY",
      changed_from_preliminary: true,
      change_reason: "Momentum and upside outweigh the premium.",
    };
    render(<SignalCard scorecard={{ ...aapl.scorecard, preliminary_signal: "HOLD" }} analyst={changed} />);
    expect(screen.getByTestId("signal").textContent).toBe("BUY");
    expect(screen.getByTestId("signal-status").textContent).toBe("Changed from HOLD");
    expect(screen.getByText("Momentum and upside outweigh the premium.")).toBeTruthy();
  });

  it("shows the preliminary signal while awaiting the analyst", () => {
    render(<SignalCard scorecard={aapl.scorecard} />);
    expect(screen.getByTestId("signal-status").textContent).toBe("Preliminary · awaiting the analyst");
    expect(screen.getByTestId("signal").textContent).toBe(aapl.scorecard.preliminary_signal);
  });

  it("labels the preliminary signal as not reviewed when the analyst failed", () => {
    render(
      <SignalCard scorecard={aapl.scorecard} analyst={{ kind: "error", stage: "analyst", message: "analyst unavailable" }} />,
    );
    expect(screen.getByTestId("signal-status").textContent).toBe("Not reviewed by the analyst");
  });
});

describe("Narrative", () => {
  it("grows as fragments arrive", () => {
    let state = initialState();
    const { rerender } = render(<Narrative text={state.narrative} streaming />);
    expect(screen.getByRole("status")).toBeTruthy();
    const lengths: number[] = [];
    for (const event of FIXTURES.aapl.filter((e) => e.event === "narrative")) {
      state = reduce(state, { type: "event", event });
      act(() => rerender(<Narrative text={state.narrative} streaming />));
      lengths.push(screen.getByTestId("narrative").textContent?.length ?? 0);
    }
    expect(lengths[lengths.length - 1]).toBeGreaterThan(lengths[0]);
    expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual([
      "Company overview",
      "Financial commentary",
      "Comps commentary",
      "Risk commentary",
    ]);
  });
});

describe("ReportBody", () => {
  it("renders a cached report completely, with the disclaimer", () => {
    render(<ReportBody ticker="AAPL" state={finalState(FIXTURES.aaplCached)} onRetry={noop} onRefresh={noop} />);
    expect(screen.queryAllByRole("status")).toHaveLength(0); // no placeholders left
    expect(screen.getByText(/Cached report · generated/)).toBeTruthy();
    expect(screen.getByText("Educational project - not investment advice.")).toBeTruthy();
    expect(screen.getByText("Diagnostics")).toBeTruthy();
  });

  it("shows comps while the narrative is still a placeholder", () => {
    const events = FIXTURES.aapl;
    const before = reduceAll(events.slice(0, events.findIndex((e) => e.event === "narrative")));
    render(<ReportBody ticker="AAPL" state={before} onRetry={noop} onRefresh={noop} />);
    expect(screen.getByText("Peer median")).toBeTruthy();
    expect(screen.getByRole("status", { name: /writer starts/ })).toBeTruthy();
  });

  it("replaces the report with the validation error", () => {
    render(<ReportBody ticker="ZZZZQX" state={finalState(FIXTURES.unknownTicker)} onRetry={noop} onRefresh={noop} />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("ZZZZQX: ticker not found");
    expect(screen.getByRole("link", { name: "Try another ticker" }).getAttribute("href")).toBe("/");
  });

  it("offers a retry when the backend is unreachable", () => {
    const onRetry = vi.fn();
    const state = reduce(initialState(), { type: "connection", status: "unreachable" });
    render(<ReportBody ticker="AAPL" state={state} onRetry={onRetry} onRefresh={noop} />);
    expect(screen.getByText("The research backend is unreachable")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalled();
  });

  it("keeps rendering the rest when the risk section failed", () => {
    render(<ReportBody ticker="AAPL" state={finalState(FIXTURES.aaplRiskFailed)} onRetry={noop} onRefresh={noop} />);
    expect(screen.getByText(/Unavailable ·/)).toBeTruthy();
    expect(screen.getByText("Peer median")).toBeTruthy();
    expect(screen.getByTestId("signal")).toBeTruthy();
  });
});

describe("OfflineBadge", () => {
  it("shows only when the API reports offline mode", async () => {
    const { OfflineBadge } = await import("./OfflineBadge");
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ offline: true })));
    vi.stubGlobal("fetch", fetchMock);
    render(<OfflineBadge />);
    expect(await screen.findByText("Offline demo")).toBeTruthy();
    cleanup();
    fetchMock.mockImplementation(async () => new Response(JSON.stringify({ offline: false })));
    const { container } = render(<OfflineBadge />);
    await act(async () => {});
    expect(container.textContent).toBe("");
    vi.unstubAllGlobals();
  });
});
