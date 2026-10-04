"""Turn a saved ResearchReport into Ragas samples: each pairs an agent's text with the exact input that agent saw.

Contexts are rebuilt with the agent's own `build_user()` and split into one string per top-level JSON key, so the
judge verifies statements against what the generator actually received (there is no retriever in this app).
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel

from equity_agent.agents.agents import (
    AnalystAgent,
    AnalystInput,
    CompsExplainAgent,
    ExplainInput,
    RiskAgent,
    RiskInput,
    WriterAgent,
    WriterInput,
)
from equity_agent.agents.payloads import compact_json
from equity_agent.models import AnalystView, CompsTable, ReportNarrative, ResearchReport, RiskReport

EvalAgent = Literal["writer", "analyst", "risk", "comps"]
WRITER_SECTIONS = {
    "company_overview": "company overview",
    "financial_commentary": "financial commentary",
    "comps_commentary": "comps commentary",
    "risk_commentary": "risk commentary",
}
RELEVANCY_AGENTS: set[str] = {"writer", "analyst"}


class EvalSample(BaseModel):
    ticker: str
    agent: EvalAgent
    section: str
    user_input: str
    response: str
    contexts: list[str]


class Skipped(BaseModel):
    ticker: str
    agent: EvalAgent
    section: str
    reason: str


def split_contexts(user_message: str) -> list[str]:
    payload = json.loads(user_message)
    return [compact_json({key: payload[key]}) for key in sorted(payload)]


def build_samples(report: ResearchReport) -> tuple[list[EvalSample], list[Skipped]]:
    samples: list[EvalSample] = []
    skipped: list[Skipped] = []
    snap = report.financials.snapshot
    company = f"{snap.name} ({report.ticker})"
    comps = report.comps if isinstance(report.comps, CompsTable) else None
    risks = report.risks if isinstance(report.risks, RiskReport) else None
    risk_items = risks.risks if risks else None

    def add(agent: EvalAgent, section: str, task: str, response: str, user_message: str) -> None:
        samples.append(
            EvalSample(
                ticker=report.ticker,
                agent=agent,
                section=section,
                user_input=task,
                response=response.strip(),
                contexts=split_contexts(user_message),
            )
        )

    # Writer: one sample per section
    if isinstance(report.narrative, ReportNarrative):
        writer_user = WriterAgent().build_user(WriterInput(report.financials, comps, risk_items, report.news))
        for key, title in WRITER_SECTIONS.items():
            text = getattr(report.narrative, key)
            if not text:
                skipped.append(Skipped(ticker=report.ticker, agent="writer", section=key, reason="section missing"))
                continue
            task = f"Write the {title} section of an equity research report on {company} using only the provided data."
            add("writer", key, task, text, writer_user)
    else:
        for key in WRITER_SECTIONS:
            skipped.append(Skipped(ticker=report.ticker, agent="writer", section=key, reason="narrative unavailable"))

    # Analyst
    if isinstance(report.analyst, AnalystView):
        view = report.analyst
        analyst_user = AnalystAgent().build_user(
            AnalystInput(report.financials, comps, risk_items, report.scorecard, report.news)
        )
        # The final signal itself is the Analyst's decision, not a claim about its input, so it is not scored;
        # a stated reason for changing it is.
        change = [f"Reason for changing the signal: {view.change_reason}"] if view.changed_from_preliminary else []
        response = "\n".join(
            [
                *change,
                f"Valuation: {view.valuation_summary}",
                "Thesis: " + " ".join(view.thesis),
                "Counterpoints: " + " ".join(view.counterpoints),
                f"Signal reasoning: {view.signal_reasoning}",
            ]
        )
        task = (
            f"Review the preliminary {view.preliminary_signal} signal for {company}: summarise the valuation, give a "
            "thesis and counterpoints, and explain the final signal using only the provided data."
        )
        add("analyst", "view", task, response, analyst_user)
    else:
        skipped.append(Skipped(ticker=report.ticker, agent="analyst", section="view", reason="analyst unavailable"))

    # Risk Agent
    if risks is not None:
        risk_user = RiskAgent().build_user(RiskInput(snap.name, report.ticker, risks.filing.form, risks.headings))
        response = "\n".join(f"{r.title}: {r.explanation}" for r in risks.risks)
        task = f"Summarise the six most material risks of {company} from the risk-factor headings of its {risks.filing.form}."
        add("risk", "risks", task, response, risk_user)
    else:
        skipped.append(Skipped(ticker=report.ticker, agent="risk", section="risks", reason="risk section unavailable"))

    # Comps Agent explain call: only when this run wrote the rationales from this run's search results
    peers_cached = any(key.startswith(f"peers:{report.ticker}:") for key in report.cache_hits)
    explained = [r for r in comps.peers if comps.peer_rationales.get(r.ticker)] if comps else []
    if comps is None:
        skipped.append(Skipped(ticker=report.ticker, agent="comps", section="peers", reason="comps unavailable"))
    elif peers_cached:
        skipped.append(Skipped(ticker=report.ticker, agent="comps", section="peers", reason="peers came from the cache"))
    elif not explained:
        skipped.append(Skipped(ticker=report.ticker, agent="comps", section="peers", reason="no peer rationales"))
    else:
        comps_user = CompsExplainAgent().build_user(ExplainInput(snap, comps.peers, report.competitor_search))
        response = "\n".join(f"{r.ticker} ({r.name}): {comps.peer_rationales[r.ticker]}" for r in explained)
        task = f"Explain why each chosen peer is comparable to {company}."
        add("comps", "peers", task, response, comps_user)
    return samples, skipped
