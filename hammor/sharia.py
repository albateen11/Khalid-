"""AAOIFI Shari'ah Standard No. 21 (Financial Paper: Shares and Bonds) screen.

Stage 1, business activity: the company's core business must be permissible
(see universe.py classification).

Stage 2, financial ratios, measured against market capitalisation:
  * Interest-bearing debt                 < 30% of market cap
  * Interest-bearing cash & deposits      < 30% of market cap
  * Non-permissible income                <  5% of total revenue

Islamic banks, takaful and Islamic finance houses are governed by their own
Sharia supervisory boards, so the debt and cash ratios are not applied to them.

Data limits (stated in every report):
  * Yahoo reports *total* debt and *total* cash. It doesn't separate Islamic
    (sukuk/murabaha, Islamic deposits) from conventional (interest-bearing).
    We conservatively treat all of it as interest-bearing, so a "Fail" may be
    a false negative. A "Pass" is reliable.
  * Interest income is used as a proxy for non-permissible income.
  * Purification: the share of dividends to give to charity is estimated as
    non-permissible income / total revenue.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .data import StockData

DEBT_LIMIT = 0.30
CASH_LIMIT = 0.30
INCOME_LIMIT = 0.05
BORDERLINE = 0.83  # within 83% of a limit, i.e. 25%/30% or 4.15%/5%

COMPLIANT = "Compliant"
NON_COMPLIANT = "Non-compliant"
REVIEW = "Needs Sharia review"
NO_DATA = "Insufficient data"


@dataclass
class ShariaResult:
    status: str
    debt_ratio: float | None = None
    cash_ratio: float | None = None
    income_ratio: float | None = None
    purification_pct: float | None = None
    reasons: list[str] = field(default_factory=list)
    borderline: bool = False

    @property
    def investable(self) -> bool:
        return self.status == COMPLIANT


def _ratio(num, den):
    if num is None or den in (None, 0):
        return None
    try:
        return float(num) / float(den)
    except (TypeError, ValueError):
        return None


def screen(stock: StockData) -> ShariaResult:
    c = stock.company
    if c.activity == "excluded":
        return ShariaResult(NON_COMPLIANT, reasons=[c.note or "Impermissible core business"])

    if c.activity == "islamic_fin":
        return ShariaResult(
            COMPLIANT,
            reasons=["Islamic financial institution, supervised by its own Sharia board"],
        )

    info = stock.info or {}
    mcap = info.get("marketCap")
    debt = _ratio(info.get("totalDebt"), mcap)
    cash = _ratio(info.get("totalCash"), mcap)
    income = _ratio(stock.interest_income, stock.total_revenue)
    if income is not None:
        income = abs(income)

    res = ShariaResult(COMPLIANT, debt, cash, income, purification_pct=income)
    failures, missing = [], []

    for label, value, limit in (
        ("Debt/market cap", debt, DEBT_LIMIT),
        ("Cash/market cap", cash, CASH_LIMIT),
        ("Interest income/revenue", income, INCOME_LIMIT),
    ):
        if value is None:
            missing.append(label)
        elif value >= limit:
            failures.append(f"{label} {value:.1%} ≥ {limit:.0%} limit")
        elif value >= limit * BORDERLINE:
            res.borderline = True
            res.reasons.append(f"Borderline: {label} {value:.1%} (limit {limit:.0%})")

    if failures:
        res.status = NON_COMPLIANT
        res.reasons = failures + res.reasons
    elif debt is None or cash is None:
        # The debt and cash tests are mandatory; without them we can't certify the stock.
        res.status = NO_DATA
        res.reasons.append("Missing: " + ", ".join(missing))
    elif missing:
        res.reasons.append("Not verified (no data): " + ", ".join(missing))

    if c.activity == "review" and res.status == COMPLIANT:
        res.status = REVIEW
        res.reasons.insert(0, c.note or "Mixed business activities")
    elif c.activity == "review" and c.note:
        res.reasons.append(c.note)

    if c.note and c.activity == "ok":
        res.reasons.append(c.note)
    return res
