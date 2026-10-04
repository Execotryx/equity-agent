"""Data contracts shared by the data layer, scoring, agents and API (IMPLEMENTATION_PLAN.md §5).

Percent-like values (margins, growth, yields, ROE) are fractions: 0.10 means 10 %. Missing values are None, never 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Snapshot(BaseModel):
    ticker: str
    name: str
    sector: str | None = None
    industry: str | None = None
    currency: str = "USD"
    price: float
    market_cap: float | None = None
    week52_low: float | None = None
    week52_high: float | None = None
    business_summary: str = ""  # at most 600 characters


class Multiples(BaseModel):
    pe_ttm: float | None = None
    pe_fwd: float | None = None
    ev_ebitda: float | None = None
    ev_revenue: float | None = None
    price_to_book: float | None = None
    net_margin: float | None = None
    roe: float | None = None
    revenue_growth: float | None = None
    debt_to_equity: float | None = None  # ratio: 0.78 means debt is 78 % of equity
    dividend_yield: float | None = None


class Quote(BaseModel):
    """Everything taken from one quote lookup: snapshot, valuation inputs and the analyst view."""

    snapshot: Snapshot
    multiples: Multiples
    analyst_target_mean: float | None = None
    analyst_recommendation: str | None = None


class YearValue(BaseModel):
    year: int
    value: float


class PricePoint(BaseModel):
    date: date
    close: float


class History(BaseModel):
    revenue: list[YearValue] = Field(default_factory=list)  # oldest first, up to 4 fiscal years
    ebitda: list[YearValue] = Field(default_factory=list)
    net_income: list[YearValue] = Field(default_factory=list)
    prices: list[PricePoint] = Field(default_factory=list)  # 1 year of daily closes, oldest first


class FinancialProfile(BaseModel):
    snapshot: Snapshot
    multiples: Multiples
    revenue_history: list[YearValue]
    ebitda_history: list[YearValue]
    net_income_history: list[YearValue]
    price_history: list[PricePoint]
    analyst_target_mean: float | None = None
    analyst_recommendation: str | None = None


class PeerBatch(BaseModel):
    quotes: dict[str, Quote]  # in request order
    failed: dict[str, str]  # ticker -> reason


class FilingRef(BaseModel):
    ticker: str
    form: str
    filing_date: date
    accession_no: str
    url: str


class RiskHeadings(BaseModel):
    filing: FilingRef
    headings: list[str]
    truncated: bool = False


class Unavailable(BaseModel):
    """An expected absence (no filing, no risk section, search not possible) with a readable reason."""

    kind: Literal["unavailable"] = "unavailable"
    reason: str


class SearchResult(BaseModel):
    title: str
    url: str
    domain: str
    snippet: str  # at most 600 characters


class NewsItem(BaseModel):
    title: str
    url: str
    domain: str
    published: str | None = None


class SearchResults(BaseModel, Generic[T]):
    """A search that ran (possibly with no hits). A search that could not run is `Unavailable` instead."""

    items: list[T] = Field(default_factory=list)


@dataclass(frozen=True)
class Fetched(Generic[T]):
    """A data-layer result plus the cache keys it was served from, so reports can list their cache hits.

    Composite lookups (a peer batch, a filing and its headings) merge the keys of their inner lookups.
    """

    value: T
    hits: list[str] = field(default_factory=list)

    @property
    def hit(self) -> bool:
        return bool(self.hits)


# ---- comps and scoring (assembled in code, never by an LLM) ----------------------------------------------------

MetricSet = Literal["general", "financials", "real_estate"]
Signal = Literal["BUY", "HOLD", "SELL"]
PeerOrigin = Literal["agent", "fallback", "user"]


class PeerExclusion(BaseModel):
    ticker: str
    reason: str  # "is the target", "duplicate share class", "ticker not found", ...


class CompRow(BaseModel):
    ticker: str
    name: str
    market_cap: float | None = None
    multiples: Multiples
    is_target: bool = False
    sector: str | None = None
    industry: str | None = None
    business_summary: str = ""  # the evidence the Comps Agent's explain call used for this row


class PeerChoice(BaseModel):
    """The peers a run settled on and why, cached for 7 days per ticker and Comps model.

    Built from a comps table and applied back to one, so these fields are listed in one place.
    """

    tickers: list[str]
    rationales: dict[str, str] = Field(default_factory=dict)
    origin: dict[str, PeerOrigin] = Field(default_factory=dict)
    sources: list[str] = Field(default_factory=list)

    @classmethod
    def from_table(cls, table: CompsTable) -> PeerChoice:
        return cls(
            tickers=[r.ticker for r in table.peers],
            rationales=table.peer_rationales,
            origin=table.peer_origin,
            sources=table.sources,
        )

    def table_kwargs(self) -> dict[str, Any]:
        """Keyword arguments for building a comps table from this choice."""
        return {"rationales": self.rationales, "origin": self.origin, "sources": self.sources}


class CompsTable(BaseModel):
    metric_set: MetricSet
    metrics: list[str]  # the Multiples fields shown as columns, in display order
    primary_metric: str  # the valuation multiple used by the scorecard
    rows: list[CompRow]  # target first, then peers in selection order
    median: Multiples  # peer median per metric; missing when no peer has a meaningful value
    target_vs_median_pct: dict[str, float | None]  # per shown metric: target / median - 1
    peer_rationales: dict[str, str] = Field(default_factory=dict)
    peer_origin: dict[str, PeerOrigin] = Field(default_factory=dict)
    exclusions: list[PeerExclusion] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)  # URLs used for peer discovery
    insufficient: bool = False  # fewer than the minimum number of eligible peers

    @property
    def target(self) -> CompRow:
        return next(row for row in self.rows if row.is_target)

    @property
    def peers(self) -> list[CompRow]:
        return [row for row in self.rows if not row.is_target]


class FactorScore(BaseModel):
    name: Literal["valuation", "growth", "profitability", "analyst_upside", "momentum"]
    score: Literal[-1, 0, 1]
    detail: str


class Scorecard(BaseModel):
    factors: list[FactorScore]
    total: int
    preliminary_signal: Signal


# ---- Claude output schemas (passed as output_format; limits are enforced by each agent's validate()) ------------

RiskCategory = Literal[
    "macro", "competition", "supply_chain", "regulatory", "legal", "technology", "financial", "operational", "other"
]


class PeerPick(BaseModel):
    ticker: str
    name: str


class PeerPicks(BaseModel):
    """The Comps Agent's pick call: tickers and names only."""

    peers: list[PeerPick]


class PeerRationale(BaseModel):
    ticker: str
    rationale: str


class PeerRationales(BaseModel):
    """The Comps Agent's explain call: one rationale per included peer, written from the peers' summaries."""

    rationales: list[PeerRationale]


class RiskItem(BaseModel):
    title: str
    category: RiskCategory
    severity: Literal[1, 2, 3]
    explanation: str
    source_heading: str


class RiskSelection(BaseModel):
    risks: list[RiskItem]


class AnalystOutput(BaseModel):
    signal: Signal
    confidence: float
    changed_from_preliminary: bool
    change_reason: str | None
    valuation_summary: str
    thesis: list[str]
    counterpoints: list[str]
    signal_reasoning: str


# ---- report ----------------------------------------------------------------------------------------------------

DISCLAIMER = "Educational project - not investment advice."


class StageError(BaseModel):
    kind: Literal["error"] = "error"
    stage: str
    message: str


class LlmUsage(BaseModel):
    agent: str
    model: str  # the model that served the call (differs from the configured one after a fallback)
    input_tokens: int = 0
    output_tokens: int = 0
    ms: int = 0
    cost_usd: float = 0.0
    request_id: str | None = None
    error: str | None = None


class RiskReport(BaseModel):
    filing: FilingRef
    headings: list[str]  # the Risk Agent's input, kept so the report is self-describing (and evaluable)
    headings_truncated: bool = False
    risks: list[RiskItem]


class AnalystView(AnalystOutput):
    preliminary_signal: Signal
    reviewed: bool = True  # False when the analyst failed and the preliminary signal stands


class ReportNarrative(BaseModel):
    company_overview: str = ""
    financial_commentary: str = ""
    comps_commentary: str = ""
    risk_commentary: str = ""


class ResearchReport(BaseModel):
    generated_at: str  # ISO timestamp
    ticker: str
    financials: FinancialProfile
    comps: CompsTable | StageError
    competitor_search: list[SearchResult] = Field(default_factory=list)
    risks: RiskReport | StageError
    news: list[NewsItem] = Field(default_factory=list)
    news_error: str | None = None
    scorecard: Scorecard
    analyst: AnalystView | StageError
    signal: Signal
    signal_reviewed: bool
    narrative: ReportNarrative | StageError
    narrative_markdown: str = ""
    timings_ms: dict[str, int] = Field(default_factory=dict)
    llm_usage: list[LlmUsage] = Field(default_factory=list)
    cache_hits: list[str] = Field(default_factory=list)
    quality_warnings: list[str] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER


class PipelineEvent(BaseModel):
    """One progress event. `event` maps to an SSE event name: stage, partial, narrative, report or error."""

    event: Literal["stage", "partial", "narrative", "report", "error"]
    data: dict[str, Any]
