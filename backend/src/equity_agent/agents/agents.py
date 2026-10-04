"""The five research agents (IMPLEMENTATION_PLAN.md §4.3).

Financial Data is deterministic. Comps, Risk and Analyst make one structured Claude call each (plus at most one
re-ask). The Writer streams markdown and is checked after the fact (sections, length, number grounding).
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from equity_agent.agents.base import ClaudeAgent, StageFailed, load_prompt, word_count
from equity_agent.agents.payloads import (
    comps_payload,
    compact_json,
    news_payload,
    profile_payload,
    risks_payload,
    scorecard_payload,
    search_payload,
)
from equity_agent.config import AgentName
from equity_agent.llm import LlmClient, LlmError
from equity_agent.data.market import try_normalize_ticker
from equity_agent.models import (
    AnalystOutput,
    CompRow,
    CompsTable,
    FinancialProfile,
    History,
    LlmUsage,
    NewsItem,
    PeerExclusion,
    PeerPicks,
    PeerRationales,
    Quote,
    ReportNarrative,
    RiskItem,
    RiskSelection,
    Scorecard,
    SearchResult,
    Signal,
    Snapshot,
)

SIGNAL_STEPS: dict[Signal, int] = {"SELL": -1, "HOLD": 0, "BUY": 1}
PEERS_FALLBACK = json.loads((Path(__file__).parent / "peers_fallback.json").read_text(encoding="utf-8"))

# ---- Financial Data Agent (no LLM) ----------------------------------------------------------------------------


def build_profile(quote: Quote, history: History) -> FinancialProfile:
    return FinancialProfile(
        snapshot=quote.snapshot,
        multiples=quote.multiples,
        revenue_history=history.revenue,
        ebitda_history=history.ebitda,
        net_income_history=history.net_income,
        price_history=history.prices,
        analyst_target_mean=quote.analyst_target_mean,
        analyst_recommendation=quote.analyst_recommendation,
    )


# ---- Comps Agent -----------------------------------------------------------------------------------------------


@dataclass
class CompsInput:
    snapshot: Snapshot
    search: list[SearchResult]
    rejected: list[PeerExclusion] = field(default_factory=list)


class CompsAgent(ClaudeAgent[CompsInput, PeerPicks]):
    name: ClassVar[AgentName] = "comps"
    output_model = PeerPicks

    def payload(self, data: CompsInput) -> dict[str, Any]:
        snap = data.snapshot
        payload: dict[str, Any] = {
            "company": {
                "ticker": snap.ticker,
                "name": snap.name,
                "sector": snap.sector,
                "industry": snap.industry,
                "business_summary": snap.business_summary,
            },
            "search_results": search_payload(data.search),
        }
        if data.rejected:
            payload["rejected_peers"] = [{"ticker": e.ticker, "reason": e.reason} for e in data.rejected]
        return payload

    def validate(self, out: PeerPicks, data: CompsInput) -> list[str]:
        problems: list[str] = []
        normalized = [(p.ticker, try_normalize_ticker(p.ticker)) for p in out.peers]
        tickers = [t for _, t in normalized if t is not None]
        bad = [raw for raw, t in normalized if t is None]
        if bad:
            problems.append(f"invalid ticker symbols: {', '.join(bad)}")
        if not 3 <= len(out.peers) <= 5:
            problems.append(f"return 3 to 5 peers (got {len(out.peers)})")
        if len(set(tickers)) != len(tickers):
            problems.append("peer tickers must be distinct")
        if data.snapshot.ticker in tickers:
            problems.append(f"do not include the target {data.snapshot.ticker}")
        return problems


@dataclass
class ExplainInput:
    """The explain call's evidence: the target, the included peers' own descriptions, and the search snippets."""

    target: Snapshot
    peers: list[CompRow]
    search: list[SearchResult]


def _company(ticker: str, name: str, sector: str | None, industry: str | None, summary: str) -> dict[str, Any]:
    return {"ticker": ticker, "name": name, "sector": sector, "industry": industry, "business_summary": summary}


class CompsExplainAgent(ClaudeAgent[ExplainInput, PeerRationales]):
    """Second Comps call: why each included peer is comparable, from the peers' business summaries."""

    name: ClassVar[AgentName] = "comps"
    prompt_name: ClassVar[str | None] = "comps_explain"
    output_model = PeerRationales

    def payload(self, data: ExplainInput) -> dict[str, Any]:
        t = data.target
        return {
            "company": _company(t.ticker, t.name, t.sector, t.industry, t.business_summary),
            "peers": [_company(p.ticker, p.name, p.sector, p.industry, p.business_summary) for p in data.peers],
            "search_results": search_payload(data.search),
        }

    def validate(self, out: PeerRationales, data: ExplainInput) -> list[str]:
        problems: list[str] = []
        expected = [p.ticker for p in data.peers]
        given = [try_normalize_ticker(r.ticker) or r.ticker for r in out.rationales]
        if sorted(given) != sorted(expected):
            problems.append(f"give exactly one rationale for each of {', '.join(expected)} (got {', '.join(given) or 'none'})")
        long = [r.ticker for r in out.rationales if word_count(r.rationale) > 20]
        if long:
            problems.append(f"rationales must be at most 20 words ({', '.join(long)})")
        empty = [r.ticker for r in out.rationales if not r.rationale.strip()]
        if empty:
            problems.append(f"rationales must not be empty ({', '.join(empty)})")
        return problems


def fallback_peers(sector: str | None, exclude: set[str]) -> list[str]:
    return [t for t in PEERS_FALLBACK.get(sector or "", []) if t not in exclude]


# ---- Risk Agent ------------------------------------------------------------------------------------------------


@dataclass
class RiskInput:
    company: str
    ticker: str
    form: str
    headings: list[str]


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


class RiskAgent(ClaudeAgent[RiskInput, RiskSelection]):
    name: ClassVar[AgentName] = "risk"
    output_model = RiskSelection

    def payload(self, data: RiskInput) -> dict[str, Any]:
        return {"company": data.company, "ticker": data.ticker, "filing": data.form, "risk_headings": data.headings}

    def validate(self, out: RiskSelection, data: RiskInput) -> list[str]:
        problems: list[str] = []
        if len(out.risks) != 6:
            problems.append(f"return exactly 6 risks (got {len(out.risks)})")
        known = {_norm(h) for h in data.headings}
        missing = [r.title for r in out.risks if _norm(r.source_heading) not in known]
        if missing:
            problems.append("source_heading must be copied verbatim from risk_headings for: " + "; ".join(missing))
        long = [r.title for r in out.risks if word_count(r.explanation) > 30]
        if long:
            problems.append("explanations must be at most 30 words for: " + "; ".join(long))
        return problems


# ---- Analyst Agent ---------------------------------------------------------------------------------------------


@dataclass
class AnalystInput:
    profile: FinancialProfile
    comps: CompsTable | None
    risks: list[RiskItem] | None
    scorecard: Scorecard
    news: list[NewsItem]


class AnalystAgent(ClaudeAgent[AnalystInput, AnalystOutput]):
    name: ClassVar[AgentName] = "analyst"
    output_model = AnalystOutput

    def payload(self, data: AnalystInput) -> dict[str, Any]:
        return {
            "company": profile_payload(data.profile),
            "comps": comps_payload(data.comps) if data.comps else "unavailable",
            "risks": risks_payload(data.risks) if data.risks is not None else "unavailable",
            "scorecard": scorecard_payload(data.scorecard),
            "news": news_payload(data.news),
        }

    def validate(self, out: AnalystOutput, data: AnalystInput) -> list[str]:
        problems: list[str] = []
        preliminary = data.scorecard.preliminary_signal
        step = abs(SIGNAL_STEPS[out.signal] - SIGNAL_STEPS[preliminary])
        if step > 1:
            problems.append(f"the signal may move at most one step from the preliminary {preliminary}")
        changed = out.signal != preliminary
        if out.changed_from_preliminary != changed:
            problems.append("changed_from_preliminary must be true exactly when signal differs from the preliminary")
        if changed and not (out.change_reason or "").strip():
            problems.append("a change from the preliminary signal needs a change_reason")
        if not 0 <= out.confidence <= 1:
            problems.append("confidence must be between 0 and 1")
        if len(out.thesis) != 3 or len(out.counterpoints) != 3:
            problems.append("give exactly 3 thesis points and exactly 3 counterpoints")
        if word_count(out.valuation_summary) > 60:
            problems.append("valuation_summary must be at most 60 words")
        if word_count(out.signal_reasoning) > 80:
            problems.append("signal_reasoning must be at most 80 words")
        return problems


# ---- Writer Agent ----------------------------------------------------------------------------------------------

SECTIONS = {
    "company overview": "company_overview",
    "financial commentary": "financial_commentary",
    "comps commentary": "comps_commentary",
    "risk commentary": "risk_commentary",
}
MAX_WORDS = 450
_NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")
_SIGNAL_WORDS = re.compile(r"\b(BUY|SELL|HOLD)\b|\b(buy|sell|hold) (rating|recommendation)\b")


@dataclass
class WriterInput:
    """Everything the Analyst sees except the scorecard and signal, so the prose cannot contradict the signal."""

    profile: FinancialProfile
    comps: CompsTable | None
    risks: list[RiskItem] | None
    news: list[NewsItem]


class WriterAgent:
    name: ClassVar[AgentName] = "writer"

    def __init__(self) -> None:
        self.system = load_prompt(self.name)

    def payload(self, data: WriterInput) -> dict[str, Any]:
        return {
            "company": profile_payload(data.profile),
            "comps": comps_payload(data.comps) if data.comps else "unavailable",
            "risks": risks_payload(data.risks) if data.risks is not None else "unavailable",
            "news": news_payload(data.news),
        }

    def build_user(self, data: WriterInput) -> str:
        return compact_json(self.payload(data))

    async def stream(
        self, llm: LlmClient, data: WriterInput, on_usage: Callable[[LlmUsage], None]
    ) -> AsyncIterator[str]:
        """Stream the narrative. A model failure surfaces as StageFailed, like every other agent."""
        try:
            async for text in llm.stream(self.name, self.system, self.build_user(data), on_usage):
                yield text
        except LlmError as error:
            raise StageFailed(str(error), []) from error  # its usage already went through on_usage


def parse_sections(markdown: str) -> tuple[ReportNarrative, list[str]]:
    """Split the Writer's markdown on its four `##` headings. Returns the narrative and any problems."""
    parts: dict[str, list[str]] = {}
    current: str | None = None
    for line in markdown.splitlines():
        heading = re.match(r"^#{1,3}\s+(.+?)\s*$", line)
        if heading and heading.group(1).strip().lower() in SECTIONS:
            current = SECTIONS[heading.group(1).strip().lower()]
            parts[current] = []
        elif current is not None:
            parts[current].append(line)
    narrative = ReportNarrative(**{k: "\n".join(v).strip() for k, v in parts.items()})
    problems = [f"missing section: {title}" for title, key in SECTIONS.items() if not getattr(narrative, key)]
    words = word_count(markdown)
    if words > MAX_WORDS:
        problems.append(f"narrative is {words} words (limit {MAX_WORDS})")
    if _SIGNAL_WORDS.search(markdown):
        problems.append("narrative mentions a buy/hold/sell recommendation")
    return narrative, problems


def _to_float(token: str) -> float | None:
    try:
        return float(token.replace(",", ""))
    except ValueError:
        return None


def _decimals(token: str) -> int:
    return len(token.split(".")[1]) if "." in token else 0


def ungrounded_numbers(prose: str, source: str) -> list[str]:
    """Numbers in the prose that match no number in the source, allowing rounding (34.82 -> 34.8 or 35).

    Years (1990-2039), small counts (0-12) and hyphenated terms ("52-week") are allowed.
    """
    available = [v for t in _NUMBER.findall(source) if (v := _to_float(t)) is not None]
    unmatched: list[str] = []
    for match in _NUMBER.finditer(prose):
        token = match.group()
        if re.match(r"-[A-Za-z]", prose[match.end() : match.end() + 2]):
            continue  # part of a term such as "52-week", "10-K" or "200-day"
        value = _to_float(token)
        if value is None or (value.is_integer() and (0 <= value <= 12 or 1990 <= value <= 2039)):
            continue
        places = _decimals(token)
        if not any(abs(round(abs(x), places) - abs(value)) < 1e-9 for x in available):
            unmatched.append(token)
    return list(dict.fromkeys(unmatched))
