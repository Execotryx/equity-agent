"""Native USD KASE quotes, with explicit issuer enrichment and no price fallback.

The public website JSON API is undocumented. Fail closed on changed schemas or identities.
urllib responses are scoped to each call; there is no persistent transport to shut down.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote as urlquote
from urllib.request import Request, urlopen

from equity_agent.data.market import (
    MarketSource, ProviderError, QuoteUnavailable, TickerNotFound, UnsupportedInstrument, YahooSource, _clean,
)
from equity_agent.models import EnrichmentProvenance, QuoteProvenance

API_ROOT = "https://kase.kz/api/instruments/securities/"
TIMEOUT = 10


@dataclass(frozen=True)
class IssuerMapping:
    alias: str
    isins: tuple[str, ...]
    issuer_names: tuple[str, ...]
    native_shares: float = 1
    alias_shares: float = 1
    sec_ticker: str | None = None
    identity_url: str = "https://kase.kz/en/investors/instruments/shares"


# Units and identities are verified against exchange/issuer sources, never inferred from a suffix.
MAPPINGS = {
    "FRHC_KZ": IssuerMapping("FRHC", ("US3563901046",),
                            ("Freedom Holding Corp.", "Freedom Holdings Corp."), sec_ticker="FRHC"),
    "KSPID": IssuerMapping("KSPI", ("US48581R2058", "US48581R1068"),
                           ("Kaspi.kz JSC", "Joint Stock Company Kaspi.kz"), sec_ticker="KSPI",
                           identity_url="https://ir.kaspi.kz/media/Form_20-F_2023.pdf"),
    "HSBKD": IssuerMapping("HSBK.IL", ("US46627J3023", "US46627J2033"),
                           ("Halyk Bank of Kazakhstan JSC", "Halyk Bank Kazakhstan Joint Stock Company"), 40, 40,
                           identity_url="https://halykbank.com/about-us"),
    "KZAPD": IssuerMapping("KAP.IL", ("US63253R2013",),
                           ('JSC "NAC Kazatomprom"', "National Atomic Company Kazatomprom JSC"),
                           identity_url="https://www.kazatomprom.kz/en/investors/faq"),
    "AAPL_KZ": IssuerMapping("AAPL", ("US0378331005",), ("Apple Inc.",), sec_ticker="AAPL"),
    "NVDA_KZ": IssuerMapping("NVDA", ("US67066G1040",), ("NVIDIA Corp.", "NVIDIA Corporation"), sec_ticker="NVDA"),
    "JPM_KZ": IssuerMapping("JPM", ("US46625H1005",), ("JPMorgan Chase & Co.",), sec_ticker="JPM"),
}


def matches_issuer(name: str, mapping: IssuerMapping) -> bool:
    def key(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", value.casefold())
    return key(name) in {key(expected) for expected in mapping.issuer_names}


def is_kase(ticker: str) -> bool:
    return ticker.endswith("_KZ") or ticker in {"HSBKD", "KSPID", "KZAPD"}


def issuer_key(ticker: str) -> str:
    for native, mapping in MAPPINGS.items():
        if ticker in {native, mapping.alias, mapping.alias.replace(".", "-")}:
            return mapping.alias
    return ticker


def sec_ticker(ticker: str) -> str | None:
    if not is_kase(ticker):
        return ticker
    mapping = MAPPINGS.get(ticker)
    return mapping.sec_ticker if mapping else None


def fetch_instrument(ticker: str) -> dict[str, Any]:
    url = API_ROOT + urlquote(ticker, safe="") + "/"
    try:
        with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=TIMEOUT) as response:
            raw = json.load(response)
    except HTTPError as error:
        error.close()
        if error.code == 404:
            raise TickerNotFound(ticker) from error
        raise ProviderError(ticker, f"KASE HTTP {error.code}") from error
    except Exception as error:
        raise ProviderError(ticker, f"KASE {type(error).__name__}") from error
    if not isinstance(raw, dict):
        raise ProviderError(ticker, "malformed KASE response")
    return raw


def validate_instrument(ticker: str, raw: dict[str, Any]) -> tuple[str, str, str | None]:
    code, issuer = raw.get("code"), raw.get("org_name_en")
    if not isinstance(code, str) or code.upper() != ticker or not isinstance(issuer, str) or not issuer.strip():
        raise ProviderError(ticker, "KASE instrument identity mismatch")
    if not isinstance(raw.get("sec_type"), str) or not isinstance(raw.get("currency_type"), str):
        raise ProviderError(ticker, "malformed KASE instrument")
    if raw["sec_type"] not in {"share", "dept"} or raw["currency_type"] != "USD":
        raise UnsupportedInstrument(ticker)
    security = raw.get("ticker")
    if not isinstance(security, dict):
        raise ProviderError(ticker, "missing KASE security identity")
    # A preferred share must not pass through the ordinary-share route.
    if raw["sec_type"] == "share":
        if not isinstance(security.get("typesec_en"), str):
            raise ProviderError(ticker, "missing KASE share type")
        if security["typesec_en"] != "ordinary":
            raise UnsupportedInstrument(ticker)
    isin: str | None = None
    mapping = MAPPINGS.get(ticker)
    if mapping:
        fields = ("nind", "nind2") if raw["sec_type"] == "dept" else ("nin", "nin2")
        isin = next((security.get(k) for k in fields if security.get(k) in mapping.isins), None)
        if not matches_issuer(issuer, mapping) or isin is None:
            raise ProviderError(ticker, "KASE mapped issuer/ISIN mismatch")
    elif ticker == "CORE_KZ":
        if (re.sub(r"[^a-z0-9]", "", issuer.casefold()) != "solidcoreresourcesplc"
                or security.get("nin") != "JE00B6T5S470"):
            raise ProviderError(ticker, "KASE quote-only issuer/ISIN mismatch")
    return code, issuer.strip(), isin


class RoutedSource:
    def __init__(self, yahoo: MarketSource | None = None,
                 fetch: Callable[[str], dict[str, Any]] = fetch_instrument) -> None:
        self.yahoo = yahoo or YahooSource()
        self.fetch = fetch

    def info(self, ticker: str) -> dict[str, Any]:
        if not is_kase(ticker):
            return self.yahoo.info(ticker)
        raw = self.fetch(ticker)
        code, issuer, isin = validate_instrument(ticker, raw)
        price = _clean(raw.get("price"))
        if price is None or price <= 0:
            raise QuoteUnavailable(ticker)
        timestamp = raw.get("date0")
        if timestamp is not None and not isinstance(timestamp, str):
            raise ProviderError(ticker, "malformed KASE timestamp")
        diagnostics = ["Native KASE annual price history and 52-week range unavailable; momentum is neutral."]
        result: dict[str, Any] = {
            "quoteType": "EQUITY", "longName": issuer, "currency": "USD", "currentPrice": price,
            "quoteProvenance": QuoteProvenance(provider="KASE", exchange="KASE", source_symbol=code,
                source_url=API_ROOT + code + "/", timestamp=timestamp).model_dump(),
            "diagnostics": diagnostics,
        }
        mapping = MAPPINGS.get(ticker)
        if mapping is None:
            diagnostics.append("No verified issuer enrichment mapping; financial currency unknown, monetary history omitted.")
            return result
        try:
            # Private provider identifiers bypass public class-share normalization (.IL is significant).
            alias = self.yahoo.info(mapping.alias)
            if (alias.get("symbol") != mapping.alias or alias.get("quoteType") != "EQUITY"
                    or not matches_issuer(str(alias.get("longName", "")), mapping)
                    or alias.get("currency") != "USD"
                    or (alias.get("isin") is not None and alias["isin"] not in mapping.isins)):
                raise ValueError("Yahoo listing identity or quote currency mismatch")
            alias_price = _clean(alias.get("currentPrice")) or _clean(alias.get("regularMarketPrice"))
            currency = alias.get("financialCurrency")
            if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha():
                currency = None
            else:
                currency = currency.upper()
            if (mapping.native_shares <= 0 or mapping.alias_shares <= 0
                    or _clean(mapping.native_shares) is None or _clean(mapping.alias_shares) is None):
                raise ValueError("unverified quoted-unit conversion")
            units = mapping.native_shares / mapping.alias_shares
            if _clean(units) is None or units <= 0:
                raise ValueError("unverified quoted-unit conversion")
            result["financialCurrency"] = currency
            for key in ("sector", "industry", "longBusinessSummary", "profitMargins", "returnOnEquity",
                        "revenueGrowth", "debtToEquity"):
                result[key] = alias.get(key)
            compatible = units > 0 and alias_price is not None and alias_price > 0
            equivalent_price = _clean(alias_price * units) if compatible and alias_price is not None else None
            ratio = _clean(price / equivalent_price) if equivalent_price is not None and equivalent_price > 0 else None
            if ratio is not None and ratio <= 0:
                ratio = None
            provenance = EnrichmentProvenance(source_symbol=mapping.alias,
                source_url="https://finance.yahoo.com/quote/" + mapping.alias + "/", native_isin=isin or "",
                native_shares_per_unit=mapping.native_shares, source_shares_per_unit=mapping.alias_shares,
                identity_source_url=mapping.identity_url)
            target = _clean(alias.get("targetMeanPrice"))
            target = _clean(target * units) if target is not None and target > 0 else None
            if target is not None and target > 0:
                result["targetMeanPrice"] = target
                result["recommendationKey"] = alias.get("recommendationKey")
                provenance.analyst_target_basis = "Cross-listing estimate in USD, adjusted by verified shares per quoted unit."
            if ratio is not None:
                # Yahoo marketCap is denominated in the verified USD quote currency, independently of accounts.
                cap = _clean(alias.get("marketCap"))
                result["marketCap"] = cap * ratio if cap is not None and cap > 0 else None
                if currency == "USD":
                    for key in ("trailingPE", "forwardPE", "priceToBook"):
                        value = _clean(alias.get(key))
                        result[key] = value * ratio if value is not None else None
                    dividend = _clean(alias.get("dividendYield"))
                    result["dividendYield"] = dividend / ratio if dividend is not None else None
            result["enrichmentProvenance"] = provenance.model_dump()
            if currency != "USD" or ratio is None:
                diagnostics.append("Price-sensitive valuation metrics unavailable: accounts are not verified USD or quote units/prices are incompatible; no FX conversion.")
            if currency is None:
                diagnostics.append("Financial reporting currency unknown; monetary history omitted.")
            diagnostics.append("EV-based multiples unavailable for native KASE instruments.")
        except Exception as error:
            diagnostics.append(f"Issuer enrichment unavailable ({type(error).__name__}); financial currency unknown, monetary history omitted.")
        return result

    def income(self, ticker: str) -> dict[str, dict[str, float | None]]:
        if not is_kase(ticker):
            return self.yahoo.income(ticker)
        mapping = MAPPINGS.get(ticker)
        if mapping is None:
            return {}
        validate_instrument(ticker, self.fetch(ticker))
        return self.yahoo.income(mapping.alias)

    def closes(self, ticker: str) -> list[tuple[str, float]]:
        return [] if is_kase(ticker) else self.yahoo.closes(ticker)
