// Runtime checks at the network boundary. Generated types alone cannot validate JSON.
import { normalizeTicker } from "./api";
import { STAGE_NAMES, type StreamEvent } from "./events";

type Guard = (value: unknown) => boolean;
const object = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const string: Guard = (v) => typeof v === "string";
const number: Guard = (v) => typeof v === "number" && Number.isFinite(v);
const positive: Guard = (v) => number(v) && (v as number) > 0;
const integer: Guard = (v) => number(v) && Number.isInteger(v);
const nonnegative: Guard = (v) => number(v) && (v as number) >= 0;
const boolean: Guard = (v) => typeof v === "boolean";
const optional = (guard: Guard): Guard => (v) => v == null || guard(v);
const array = (guard: Guard): Guard => (v) => Array.isArray(v) && v.every(guard);
const dictionary = (guard: Guard): Guard => (v) => object(v) && Object.values(v).every(guard);
const oneOf = (...values: unknown[]): Guard => (v) => values.includes(v);
const shape = (fields: Record<string, Guard>): Guard => (v) => object(v) && Object.entries(fields).every(([k, guard]) => guard(v[k]));
const strings = array(string);
const signal = oneOf("BUY", "HOLD", "SELL");
const metricNames = ["pe_ttm", "pe_fwd", "ev_ebitda", "ev_revenue", "price_to_book", "net_margin", "roe", "revenue_growth", "debt_to_equity", "dividend_yield"];
const multiples = shape(Object.fromEntries(metricNames.map((key) => [key, optional(number)])));
const date: Guard = (v) => {
  if (typeof v !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(v)) return false;
  const parsed = new Date(v);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === v;
};
const canonical = (ticker: string) => normalizeTicker(ticker)?.replaceAll(".", "-");
const native = (ticker: string) => ticker.endsWith("_KZ") || ["HSBKD", "KSPID", "KZAPD"].includes(ticker);
const provenance = shape({ provider: string, exchange: string, source_symbol: string, source_url: string, timestamp: optional(string) });
const enrichment = shape({ provider: optional(string), source_symbol: string, source_url: string, native_isin: string,
  native_shares_per_unit: positive, source_shares_per_unit: positive, identity_source_url: string, analyst_target_basis: optional(string) });
const yearValue = shape({ year: integer, value: number });
const pricePoint = shape({ date, close: positive });
const stageError = shape({ kind: oneOf("error"), stage: string, message: string });
const filing = shape({ ticker: string, form: string, filing_date: date, accession_no: string, url: string });
const risk = shape({ title: string, category: oneOf("macro", "competition", "supply_chain", "regulatory", "legal", "technology", "financial", "operational", "other"),
  severity: oneOf(1, 2, 3), explanation: string, source_heading: string });
const risks = shape({ filing, headings: strings, headings_truncated: optional(boolean), risks: array(risk) });
const newsItem = shape({ title: string, url: string, domain: string, published: optional(string) });
const searchResult = shape({ title: string, url: string, domain: string, snippet: string });
const scorecard = shape({ factors: array(shape({ name: oneOf("valuation", "growth", "profitability", "analyst_upside", "momentum"),
  score: oneOf(-1, 0, 1), detail: string })), total: integer, preliminary_signal: signal });
const analyst = shape({ signal, confidence: (v) => number(v) && (v as number) >= 0 && (v as number) <= 1,
  changed_from_preliminary: boolean, change_reason: optional(string), valuation_summary: string, thesis: strings,
  counterpoints: strings, signal_reasoning: string, preliminary_signal: signal, reviewed: optional(boolean) });
const narrative = shape({ company_overview: optional(string), financial_commentary: optional(string), comps_commentary: optional(string), risk_commentary: optional(string) });
const usage = shape({ agent: string, model: string, input_tokens: optional(nonnegative), output_tokens: optional(nonnegative),
  ms: optional(nonnegative), cost_usd: optional(nonnegative), request_id: optional(string), error: optional(string) });
const union = (a: Guard, b: Guard): Guard => (v) => a(v) || b(v);

export function parseStreamEvent(name: StreamEvent["event"], data: unknown, expectedTicker: string): StreamEvent {
  const expected = canonical(expectedTicker);
  const matches: Guard = (v) => typeof v === "string" && expected !== undefined && canonical(v) === expected;
  const snapshot: Guard = (v) => {
    if (!shape({ ticker: matches, name: string, currency: string, price: positive, sector: optional(string), industry: optional(string),
      market_cap: optional(number), week52_low: optional(number), week52_high: optional(number), business_summary: optional(string),
      quote_provenance: optional(provenance) })(v) || !object(v)) return false;
    if (!expected || !native(expected)) return true;
    const source = v.quote_provenance;
    return object(source) && source.provider === "KASE" && source.exchange === "KASE" && matches(source.source_symbol)
      && v.currency === "USD" && v.week52_low == null && v.week52_high == null;
  };
  const financials: Guard = (v) => shape({ snapshot, multiples, revenue_history: array(yearValue), ebitda_history: array(yearValue),
    net_income_history: array(yearValue), price_history: array(pricePoint), analyst_target_mean: optional(number),
    analyst_recommendation: optional(string), financial_currency: optional(string), enrichment_provenance: optional(enrichment) })(v)
    && object(v) && (!expected || !native(expected) || (v.price_history as unknown[]).length === 0);
  const row = shape({ ticker: string, name: string, market_cap: optional(number), multiples, is_target: boolean,
    sector: optional(string), industry: optional(string), business_summary: optional(string) });
  const comps: Guard = (v) => {
    if (!shape({ metric_set: oneOf("general", "financials", "real_estate"), metrics: array(oneOf(...metricNames)),
      primary_metric: oneOf(...metricNames), rows: array(row), median: multiples, target_vs_median_pct: dictionary(optional(number)),
      peer_rationales: optional(dictionary(string)), peer_origin: optional(dictionary(oneOf("agent", "fallback", "user"))),
      exclusions: optional(array(shape({ ticker: string, reason: string }))), sources: optional(strings), insufficient: optional(boolean) })(v)
      || !object(v)) return false;
    const targets = (v.rows as Record<string, unknown>[]).filter((r) => r.is_target);
    return targets.length === 1 && matches(targets[0].ticker);
  };
  const report = shape({ generated_at: string, ticker: matches, financials, comps: union(stageError, comps),
    competitor_search: optional(array(searchResult)), risks: union(stageError, risks), news: optional(array(newsItem)),
    news_error: optional(string), scorecard, analyst: union(stageError, analyst), signal, signal_reviewed: boolean,
    narrative: union(stageError, narrative), narrative_markdown: optional(string), timings_ms: optional(dictionary(nonnegative)),
    llm_usage: optional(array(usage)), cache_hits: optional(strings), quality_warnings: optional(strings), disclaimer: optional(string), from_cache: boolean });
  const sections: Record<string, Guard> = { snapshot, financials, comps, risks, news: array(newsItem), scorecard, analyst };
  let valid = false;
  if (object(data)) {
    switch (name) {
      case "stage":
        valid = string(data.stage) && ["validate", ...STAGE_NAMES].includes(data.stage as string)
          && (data.status === "started" || ((data.status === "done" || data.status === "failed") && nonnegative(data.ms)
            && (data.status === "failed" || boolean(data.cached))));
        break;
      case "partial":
        valid = typeof data.key === "string" && Object.hasOwn(sections, data.key) && sections[data.key](data.value);
        break;
      case "narrative": valid = string(data.delta); break;
      case "error": valid = shape({ stage: string, message: string, terminal: boolean })(data); break;
      case "report": valid = report(data); break;
    }
  }
  if (!valid) throw new Error("Invalid research event");
  return { event: name, data } as StreamEvent;
}
