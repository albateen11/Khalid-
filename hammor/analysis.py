"""Quantitative analysis: technical + fundamental metrics and horizon scores."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .data import StockData
from .sharia import ShariaResult

MIN_DAILY_VALUE_AED = 1_000_000  # below this we flag the stock as illiquid


def _ret(close: pd.Series, days: int) -> float | None:
    if len(close) <= days:
        return None
    return float(close.iloc[-1] / close.iloc[-days - 1] - 1)


def _rsi(close: pd.Series, period: int = 14) -> float | None:
    if len(close) <= period:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    if loss.iloc[-1] == 0:
        return 100.0
    rs = gain.iloc[-1] / loss.iloc[-1]
    return float(100 - 100 / (1 + rs))


def _num(v):
    try:
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return None


def metrics(stock: StockData) -> dict:
    h = stock.history
    close = h["Close"].dropna()
    vol = h["Volume"].fillna(0)
    info = stock.info or {}
    price = float(close.iloc[-1])
    daily = close.pct_change().dropna()
    sma50 = float(close.tail(50).mean()) if len(close) >= 50 else None
    sma200 = float(close.tail(200).mean()) if len(close) >= 200 else None
    hi52, lo52 = float(close.max()), float(close.min())

    div_rate = _num(info.get("trailingAnnualDividendRate")) or _num(info.get("dividendRate"))
    pe = _num(info.get("trailingPE"))
    return {
        "price": price,
        "chg_1d": _ret(close, 1),
        "ret_1m": _ret(close, 21),
        "ret_3m": _ret(close, 63),
        "ret_6m": _ret(close, 126),
        "ret_12m": _ret(close, len(close) - 1) if len(close) > 200 else None,
        "sma50": sma50,
        "sma200": sma200,
        "above_sma50": None if sma50 is None else price > sma50,
        "above_sma200": None if sma200 is None else price > sma200,
        "rsi14": _rsi(close),
        "volatility": float(daily.std() * np.sqrt(252)) if len(daily) > 20 else None,
        "high_52w": hi52,
        "low_52w": lo52,
        "from_high": price / hi52 - 1 if hi52 else None,
        "avg_value_20d": float((close.tail(20) * vol.tail(20)).mean()),
        "market_cap": _num(info.get("marketCap")),
        "pe": pe if pe and pe > 0 else None,
        "pb": _num(info.get("priceToBook")),
        "div_yield": div_rate / price if div_rate and price else None,
        "payout": _num(info.get("payoutRatio")),
        "roe": _num(info.get("returnOnEquity")),
        "margin": _num(info.get("profitMargins")),
        "rev_growth": _num(info.get("revenueGrowth")),
        "eps_growth": _num(info.get("earningsGrowth")),
        "beta": _num(info.get("beta")),
    }


def _pct_rank(s: pd.Series, ascending: bool = True) -> pd.Series:
    """Percentile rank in [0, 1]; missing values get a neutral 0.5."""
    r = s.astype(float).rank(pct=True, ascending=ascending)
    return r.fillna(0.5)


def build_table(stocks: list[StockData], sharia: dict[str, ShariaResult]) -> pd.DataFrame:
    rows = []
    for s in stocks:
        if not s.ok:
            continue
        sh = sharia[s.company.symbol]
        rows.append({
            "symbol": s.company.symbol,
            "name": s.company.name,
            "exchange": s.company.exchange,
            "sector": s.company.sector,
            "sharia_status": sh.status,
            "sharia_borderline": sh.borderline,
            "sharia_notes": "; ".join(sh.reasons),
            "debt_ratio": sh.debt_ratio,
            "cash_ratio": sh.cash_ratio,
            "impure_income": sh.income_ratio,
            "purification_pct": sh.purification_pct,
            **metrics(s),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["liquid"] = df["avg_value_20d"] >= MIN_DAILY_VALUE_AED
    inv = df["sharia_status"] == "Compliant"
    df["long_term_score"] = np.nan
    df["growth_score"] = np.nan
    df["income_score"] = np.nan
    if inv.sum() == 0:
        return df

    d = df[inv].copy()
    rsi_fit = -(d["rsi14"] - 55).abs()  # best around 50-60: trending, not overbought
    payout_fit = -(d["payout"] - 0.6).abs()  # sustainable payout near 60%
    trend = d["above_sma200"].map({True: 1.0, False: 0.0})
    trend50 = d["above_sma50"].map({True: 1.0, False: 0.0})
    growth = d[["rev_growth", "eps_growth"]].mean(axis=1, skipna=True)

    long_term = (
        0.22 * _pct_rank(d["roe"]) + 0.13 * _pct_rank(d["margin"])
        + 0.20 * _pct_rank(d["pe"], ascending=False) + 0.10 * _pct_rank(d["pb"], ascending=False)
        + 0.10 * trend.fillna(0.5) + 0.10 * _pct_rank(d["ret_12m"])
        + 0.15 * _pct_rank(d["volatility"], ascending=False)
    )
    growth_s = (
        0.28 * _pct_rank(d["ret_3m"]) + 0.17 * _pct_rank(d["ret_6m"])
        + 0.20 * _pct_rank(growth) + 0.15 * trend50.fillna(0.5)
        + 0.20 * _pct_rank(rsi_fit)
    )
    income = (
        0.45 * _pct_rank(d["div_yield"]) + 0.20 * _pct_rank(payout_fit)
        + 0.20 * _pct_rank(d["volatility"], ascending=False) + 0.15 * _pct_rank(d["roe"])
    )
    # Penalise illiquid names so we don't recommend stocks that are hard to trade.
    penalty = np.where(d["liquid"], 1.0, 0.75)
    df.loc[inv, "long_term_score"] = (long_term * penalty * 100).round(1)
    df.loc[inv, "growth_score"] = (growth_s * penalty * 100).round(1)
    df.loc[inv, "income_score"] = (income * penalty * 100).round(1)
    # A stock that pays no dividend can't be an income pick.
    no_div = inv & (df["div_yield"].isna() | (df["div_yield"] <= 0))
    df.loc[no_div, "income_score"] = np.nan
    return df


def market_summary(df: pd.DataFrame) -> dict:
    out = {}
    for ex in ("ADX", "DFM"):
        d = df[df["exchange"] == ex]
        if d.empty:
            continue
        out[ex] = {
            "stocks_covered": int(len(d)),
            "advancers": int((d["chg_1d"] > 0).sum()),
            "decliners": int((d["chg_1d"] < 0).sum()),
            "avg_change_1d": float(d["chg_1d"].mean()),
            "avg_change_1m": float(d["ret_1m"].mean()),
            "top_gainers": d.nlargest(3, "chg_1d")[["symbol", "name", "chg_1d"]].to_dict("records"),
            "top_losers": d.nsmallest(3, "chg_1d")[["symbol", "name", "chg_1d"]].to_dict("records"),
        }
    return out
