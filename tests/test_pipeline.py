"""Offline tests using synthetic market data (no network or API key needed)."""

import numpy as np
import pandas as pd
import pytest

from hammor import advisors, main, sharia
from hammor.data import StockData
from hammor.universe import UNIVERSE, Company


def fake_stock(company: Company, seed: int, **info) -> StockData:
    rng = np.random.default_rng(seed)
    n = 250
    close = 5 * np.exp(np.cumsum(rng.normal(0.0004, 0.015, n)))
    idx = pd.bdate_range(end="2026-11-25", periods=n)
    hist = pd.DataFrame({"Close": close, "Volume": rng.integers(200_000, 3_000_000, n)}, index=idx)
    base = {"marketCap": 10e9, "totalDebt": 1e9, "totalCash": 0.5e9, "trailingPE": 12 + seed % 10,
            "priceToBook": 1.5, "trailingAnnualDividendRate": 0.2, "payoutRatio": 0.55,
            "returnOnEquity": 0.12, "profitMargins": 0.2, "revenueGrowth": 0.08,
            "earningsGrowth": 0.1, "beta": 0.8}
    base.update(info)
    return StockData(company, hist, base, interest_income=1e7, total_revenue=1e9)


def fake_fetch(companies):
    return [fake_stock(c, i) for i, c in enumerate(companies)]


def co(activity="ok", note=""):
    return Company("TEST.AE", "Test Co", "DFM", "Real Estate", activity, note)


def test_sharia_ratios():
    assert sharia.screen(fake_stock(co(), 1)).status == sharia.COMPLIANT
    high_debt = sharia.screen(fake_stock(co(), 1, totalDebt=4e9))
    assert high_debt.status == sharia.NON_COMPLIANT and "Debt" in high_debt.reasons[0]
    assert sharia.screen(fake_stock(co(), 1, totalCash=3.5e9)).status == sharia.NON_COMPLIANT
    assert sharia.screen(fake_stock(co(), 1, totalDebt=2.8e9)).borderline


def test_sharia_activity_and_missing_data():
    assert sharia.screen(fake_stock(co("excluded", "bank"), 1)).status == sharia.NON_COMPLIANT
    assert sharia.screen(fake_stock(co("islamic_fin"), 1, totalDebt=9e9)).status == sharia.COMPLIANT
    assert sharia.screen(fake_stock(co("review"), 1)).status == sharia.REVIEW
    assert sharia.screen(fake_stock(co(), 1, totalDebt=None)).status == sharia.NO_DATA


def test_universe_symbols_unique():
    syms = [c.symbol for c in UNIVERSE]
    assert len(syms) == len(set(syms))
    assert all(c.symbol.endswith(".AD" if c.exchange == "ADX" else ".AE") for c in UNIVERSE)


def test_full_pipeline_rules_mode(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    subject, html, csv = main.build(fetch=fake_fetch)
    assert "Hammor Co." in subject
    assert "Long-term opportunities" in html and "Income and dividends" in html
    # Excluded companies (conventional banks) must never be recommended.
    picks_html = html.split("Full Sharia screen")[0]
    for c in UNIVERSE:
        if c.activity in ("excluded", "review"):
            assert f"· {c.symbol} ·" not in picks_html
    (tmp_path / "report.html").write_text(html)
    assert b"sharia_status" in csv


def test_committee_guard_drops_noncompliant(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    stocks = fake_fetch(UNIVERSE)
    results = {s.company.symbol: sharia.screen(s) for s in stocks}
    from hammor import analysis
    df = analysis.build_table(stocks, results)
    fake = advisors.rules_committee(df)
    fake["picks"]["long_term"].append({**fake["picks"]["long_term"][0], "symbol": "FAB.AD"})
    monkeypatch.setattr(advisors, "analyst_note", lambda *a, **k: "note")
    monkeypatch.setattr(advisors, "committee", lambda *a, **k: fake)
    out, notes, ai = advisors.run_team(df, {}, {}, "today")
    assert ai and all(p["symbol"] != "FAB.AD" for p in out["picks"]["long_term"])


class _Block:
    def __init__(self, text):
        self.type, self.text = "text", text


class _Resp:
    def __init__(self, stop, text):
        self.stop_reason, self.content, self.stop_details = stop, [_Block(text)], None


class _FakeClient:
    """Mimics client.beta.messages.stream(...) with one pause_turn before finishing."""

    def __init__(self):
        self.calls = []
        self.beta = self
        self.messages = self

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        resp = _Resp("pause_turn", "") if len(self.calls) == 1 else _Resp("end_turn", "desk note")
        client = self

        class _Ctx:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

            def get_final_message(self_inner):
                return resp
        return _Ctx()


def test_analyst_call_resumes_pause_turn(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(advisors, "_client", lambda: fake)
    stocks = fake_fetch(UNIVERSE)
    results = {s.company.symbol: sharia.screen(s) for s in stocks}
    from hammor import analysis
    df = analysis.build_table(stocks, results)
    note = advisors.analyst_note("DFM", df, analysis.market_summary(df), "today")
    assert note == "desk note" and len(fake.calls) == 2
    assert fake.calls[0]["model"] == "claude-opus-5-5"
    assert fake.calls[0]["fallbacks"] == "default"
    assert fake.calls[1]["messages"][-1]["role"] == "assistant"
