"""KASE test matrix, verified against the exchange's instrument lists on 2026-10-10.

These are test inputs, not a production ticker-routing table. Cross-listing cases
explicitly research a US venue; they never claim to validate a KASE quote.
"""

from dataclasses import dataclass
from typing import Literal

from equity_agent.acceptance import Check, Kind
from equity_agent.models import Quote

SHARES_SOURCE = "https://kase.kz/en/investors/instruments/shares"
GLOBAL_SOURCE = "https://kase.kz/en/markets/kase-global"


@dataclass(frozen=True)
class KaseCase:
    company: str
    kase_ticker: str
    input_ticker: str
    currency: str
    name_fragment: str
    scope: Literal["native", "us_listing"] = "native"
    kind: Kind = "standard"
    source_url: str | None = None
    instrument_type: str = "ordinary share"

    @property
    def id(self) -> str:
        return f"{self.scope}-{self.kase_ticker}"

    @property
    def source(self) -> str:
        return self.source_url or (SHARES_SOURCE if self.scope == "native" else GLOBAL_SOURCE)


NATIVE_CASES = (
    KaseCase("Halyk Bank", "HSBK", "HSBK", "KZT", "halyk", kind="bank"),
    KaseCase("Kaspi.kz", "KSPI", "KSPI", "KZT", "kaspi"),
    KaseCase("Kazatomprom", "KZAP", "KZAP", "KZT", "kazatomprom"),
    KaseCase("KazMunayGas", "KMGZ", "KMGZ", "KZT", "kazmunay"),
    KaseCase("KEGOC", "KEGC", "KEGC", "KZT", "kegoc"),
    KaseCase("Kcell", "KCEL", "KCEL", "KZT", "kcell"),
)

US_LISTING_CASES = (
    KaseCase("Apple", "AAPL_KZ", "AAPL", "USD", "apple", "us_listing"),
    KaseCase("NVIDIA", "NVDA_KZ", "NVDA", "USD", "nvidia", "us_listing"),
    KaseCase("JPMorgan Chase", "JPM_KZ", "JPM", "USD", "jpmorgan", "us_listing", "bank"),
)

# The lowercase `d` identifies KASE's USD depositary receipt, not the KZT
# ordinary share. The app uppercases input; keep the official symbol separately.
USD_NATIVE_CASES = (
    KaseCase("Halyk Bank", "HSBKd", "HSBKD", "USD", "halyk", kind="bank", instrument_type="depositary receipt"),
    KaseCase("Kaspi.kz", "KSPId", "KSPID", "USD", "kaspi", instrument_type="depositary receipt"),
    KaseCase("Kazatomprom", "KZAPd", "KZAPD", "USD", "kazatomprom", instrument_type="depositary receipt"),
    KaseCase("Freedom Holding", "FRHC_KZ", "FRHC_KZ", "USD", "freedom"),
    KaseCase("Solidcore Resources", "CORE_KZ", "CORE_KZ", "USD", "solidcore"),
)

USD_US_LISTING_CASES = (
    KaseCase("Kaspi.kz", "KSPId", "KSPI", "USD", "kaspi", "us_listing", source_url=SHARES_SOURCE,
             instrument_type="US-listed depositary share"),
    KaseCase("Freedom Holding", "FRHC_KZ", "FRHC", "USD", "freedom", "us_listing", "bank",
             source_url=SHARES_SOURCE),
)


def quote_checks(case: KaseCase, quote: Quote, exchange: str) -> list[Check]:
    snapshot = quote.snapshot
    venue = exchange.casefold()
    correct_venue = (
        "kase" in venue or "kazakhstan" in venue
        if case.scope == "native"
        else "nasdaq" in venue or "nyse" in venue
    )
    return [
        Check("requested ticker retained", snapshot.ticker == case.input_ticker, snapshot.ticker),
        Check("expected company", case.name_fragment in snapshot.name.casefold(), snapshot.name),
        Check("positive price", snapshot.price > 0, str(snapshot.price)),
        Check("expected quote currency", snapshot.currency == case.currency, f"expected {case.currency}; got {snapshot.currency}"),
        Check("expected trading venue", correct_venue, exchange or "provider did not identify the venue"),
    ]
