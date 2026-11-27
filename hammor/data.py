"""Market-data collection from Yahoo Finance (free, delayed data)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import pandas as pd

from .universe import Company

log = logging.getLogger(__name__)


@dataclass
class StockData:
    company: Company
    history: pd.DataFrame  # daily OHLCV, index = date
    info: dict = field(default_factory=dict)
    interest_income: float | None = None  # latest annual, AED
    total_revenue: float | None = None  # latest annual, AED
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and not self.history.empty


def _latest_row_value(df: pd.DataFrame | None, names: list[str]) -> float | None:
    if df is None or df.empty:
        return None
    for name in names:
        if name in df.index:
            series = df.loc[name].dropna()
            if not series.empty:
                return float(series.iloc[0])
    return None


def fetch_one(company: Company, retries: int = 2) -> StockData:
    import yfinance as yf

    last_err = None
    for attempt in range(retries + 1):
        try:
            t = yf.Ticker(company.symbol)
            hist = t.history(period="1y", auto_adjust=False)
            if hist.empty:
                raise ValueError("no price history returned")
            info = t.info or {}
            try:
                inc = t.income_stmt
            except Exception:  # fundamentals are often missing for UAE listings
                inc = None
            interest = _latest_row_value(
                inc, ["Interest Income", "Interest Income Non Operating"]
            )
            revenue = _latest_row_value(inc, ["Total Revenue", "Operating Revenue"])
            return StockData(company, hist, info, interest, revenue)
        except Exception as e:  # network hiccups, delisted symbols, etc.
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    log.warning("Could not fetch %s: %s", company.symbol, last_err)
    return StockData(company, pd.DataFrame(), error=str(last_err))


def fetch_all(companies: list[Company], progress=None) -> list[StockData]:
    out = []
    for i, c in enumerate(companies, 1):
        out.append(fetch_one(c))
        if progress:
            progress(i, len(companies), c)
    return out
