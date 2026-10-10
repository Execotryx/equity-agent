"""Compact, pre-formatted agent inputs. Numbers arrive formatted ("27.6%", "$4.87T", "34.8") so agents never do
arithmetic and every figure they may quote exists verbatim in their input. JSON is byte-stable (sorted keys)."""

from __future__ import annotations

import json
from typing import Any

from equity_agent.models import CompsTable, FinancialProfile, NewsItem, RiskItem, Scorecard, SearchResult
from equity_agent.formatting import METRIC_LABELS, metric_text, money, pct_change


def compact_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def profile_payload(profile: FinancialProfile) -> dict[str, Any]:
    snap, cur = profile.snapshot, profile.snapshot.currency
    multiples = {
        METRIC_LABELS[k]: v for k in METRIC_LABELS if (v := metric_text(k, getattr(profile.multiples, k))) is not None
    }
    financial_cur = profile.financial_currency
    payload = {
        "ticker": snap.ticker,
        "name": snap.name,
        "sector": snap.sector,
        "industry": snap.industry,
        "business_summary": snap.business_summary,
        "price": f"{snap.price:.2f}",
        "currency": cur,
        "market_cap": money(snap.market_cap, cur),
        "week52_range": f"{snap.week52_low:.2f}-{snap.week52_high:.2f}" if snap.week52_low and snap.week52_high else None,
        "analyst_mean_target": f"{profile.analyst_target_mean:.2f}" if profile.analyst_target_mean else None,
        "analyst_recommendation": profile.analyst_recommendation,
        "multiples": multiples,
        "revenue_by_fiscal_year": {str(y.year): money(y.value, financial_cur) for y in profile.revenue_history} if financial_cur else {},
        "net_income_by_fiscal_year": {str(y.year): money(y.value, financial_cur) for y in profile.net_income_history} if financial_cur else {},
    }
    if snap.quote_provenance is not None:
        payload["quote_provenance"] = snap.quote_provenance.model_dump()
        payload["financial_currency"] = financial_cur
        payload["enrichment_provenance"] = profile.enrichment_provenance.model_dump() if profile.enrichment_provenance else None
    if financial_cur is None:
        payload["financial_history_note"] = "Reporting currency unknown; monetary history omitted."
    return payload


def comps_payload(table: CompsTable) -> dict[str, Any]:
    def row_values(values: Any) -> dict[str, str | None]:
        return {METRIC_LABELS[m]: metric_text(m, getattr(values, m)) for m in table.metrics}

    return {
        "metric_set": table.metric_set,
        "primary_multiple": METRIC_LABELS[table.primary_metric],
        "target": {"ticker": table.target.ticker, **row_values(table.target.multiples)},
        "peers": [
            {"ticker": r.ticker, "name": r.name, "market_cap": money(r.market_cap), **row_values(r.multiples)}
            for r in table.peers
        ],
        "peer_median": row_values(table.median),
        "target_vs_peer_median": {METRIC_LABELS[m]: pct_change(v) for m, v in table.target_vs_median_pct.items()},
    }


def risks_payload(risks: list[RiskItem]) -> list[dict[str, Any]]:
    return [{"title": r.title, "category": r.category, "severity": r.severity, "explanation": r.explanation} for r in risks]


def news_payload(news: list[NewsItem]) -> list[dict[str, Any]]:
    return [{"headline": n.title, "source": n.domain, "published": n.published} for n in news[:5]]


def scorecard_payload(card: Scorecard) -> dict[str, Any]:
    return {
        "factors": [{"factor": f.name, "score": f.score, "detail": f.detail} for f in card.factors],
        "total": card.total,
        "preliminary_signal": card.preliminary_signal,
    }


def search_payload(results: list[SearchResult]) -> list[dict[str, str]]:
    return [{"title": r.title, "source": r.domain, "snippet": r.snippet} for r in results]
