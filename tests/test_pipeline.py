"""Offline tests using synthetic market data (no network or API key needed)."""

import json

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


def fake_fetch(companies, progress=None):
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
    subject, html, csv, record = main.build(fetch=fake_fetch)
    assert '"transcript"' in main.meeting_json(record)
    assert "Hammor Co." in subject
    assert "Long-term opportunities" in html and "Income and dividends" in html
    assert "Our advice to you" in html
    # Excluded companies (conventional banks) must never be recommended.
    picks_html = html.split("Full Sharia screen")[0]
    for c in UNIVERSE:
        if c.activity in ("excluded", "review"):
            assert f"· {c.symbol} ·" not in picks_html
    (tmp_path / "report.html").write_text(html)
    assert b"sharia_status" in csv


def _table():
    from hammor import analysis
    stocks = fake_fetch(UNIVERSE)
    results = {s.company.symbol: sharia.screen(s) for s in stocks}
    df = analysis.build_table(stocks, results)
    return df, analysis.market_summary(df)


class _Block:
    def __init__(self, text):
        self.type, self.text = "text", text


class _Resp:
    def __init__(self, stop, text):
        self.stop_reason, self.content, self.stop_details = stop, [_Block(text)], None


class _FakeClient:
    """Mimics client.beta.messages.stream(...). The first call pauses once (pause_turn);
    calls asking for JSON get a decision that also sneaks in a non-compliant bank."""

    def __init__(self, decision):
        self.calls, self.decision = [], decision
        self.beta = self
        self.messages = self

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            resp = _Resp("pause_turn", "")
        elif "format" in kwargs.get("output_config", {}):
            resp = _Resp("end_turn", json.dumps(self.decision))
        else:
            resp = _Resp("end_turn", f"turn {len(self.calls)} speaking")

        class _Ctx:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

            def __iter__(self_inner):
                return iter([])

            def get_final_message(self_inner):
                return resp
        return _Ctx()


def test_meeting_runs_in_order_and_guards_sharia(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    df, market = _table()
    decision = advisors.rules_committee(df)
    decision["closing_remarks"] = "Meeting closed."
    decision["picks"]["long_term"].append({**decision["picks"]["long_term"][0], "symbol": "FAB.AD"})
    fake = _FakeClient(decision)
    monkeypatch.setattr(advisors, "_client", lambda: fake)

    out, transcript, ai = advisors.run_team(df, market, {}, "today")

    assert ai
    assert [t["name"] for t in transcript] == [
        "Saeed", "Omar", "Layla", "Yousef", "Mariam", "Abdullah", "Omar", "Layla", "Saeed"]
    assert transcript[0]["round"] == "review"
    assert transcript[-1]["text"] == "Meeting closed."
    # Later speakers hear earlier ones.
    assert "Omar (ADX Equity Analyst)" in fake.calls[-2]["messages"][0]["content"]
    assert "You are Yousef" in fake.calls[4]["system"]
    assert "TRACK RECORD" in fake.calls[4]["messages"][0]["content"]
    # pause_turn was resumed, and the defaults are right.
    assert fake.calls[1]["messages"][-1]["role"] == "assistant"
    assert fake.calls[0]["model"] == "claude-opus-5-5" and fake.calls[0]["fallbacks"] == "default"
    # The non-compliant bank was dropped by the guard.
    assert all(p["symbol"] != "FAB.AD" for p in out["picks"]["long_term"])

    from hammor import report
    html = report.render("today", out, transcript, df, market, [], ai)
    assert "team meeting" in html and "Meet the Hammor Co. team" in html


def test_desktop_selftest(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from hammor.desktop import server
    assert server.selftest() == 0
    server.save_settings({"github_token": "ghp-secret"})
    assert server.public_settings()["has_github_token"]
    assert "ghp-secret" not in json.dumps(server.public_settings())


def test_track_record(tmp_path):
    from datetime import date
    from hammor import analysis, track
    df, _ = _table()
    price = dict(zip(df["symbol"], df["price"]))
    sym_up, sym_down = "DEWA.AE", "TAQA.AD"
    old_screen = [
        {"symbol": sym_up, "price": price[sym_up] / 1.10, "sharia_status": "Compliant"},
        {"symbol": sym_down, "price": price[sym_down] / 0.85, "sharia_status": "Compliant"},
    ]
    def meeting(day, picks):
        return {"date": day, "screen": old_screen,
                "decision": {"picks": {"long_term": picks, "medium_term": [], "income": []}}}
    up = {"symbol": sym_up, "name": "DEWA", "action": "Buy", "target_price": price[sym_up] * 2}
    down = {"symbol": sym_down, "name": "TAQA", "action": "Buy", "target_price": price[sym_down] * 2}
    (tmp_path / "2026-11-20.json").write_text(json.dumps(meeting("2026-11-20", [up, down])))
    (tmp_path / "2026-11-24.json").write_text(json.dumps(meeting("2026-11-24", [up])))
    (tmp_path / "2026-11-27.json").write_text(json.dumps(meeting("2026-11-27", [up])))  # today: ignored
    hist = track.load_meetings(tmp_path, today=date(2026, 11, 27))
    assert [m["date"] for m in hist] == ["2026-11-20", "2026-11-24"]
    t = track.build_track_record(hist, df, today=date(2026, 11, 27))
    assert t["count"] == 2 and t["winners"] == 1  # DEWA counted once, from its first day
    rows = {r["symbol"]: r for r in t["positions"]}
    assert abs(rows[sym_up]["return"] - 0.10) < 1e-9 and rows[sym_up]["date"] == "2026-11-20"
    assert rows[sym_up]["status"] == "Still recommended"
    assert rows[sym_down]["status"] == "Under review"
    assert "summary" in track.for_prompt(t)
    from hammor import report
    html = report.render("today", advisors.rules_committee(df), [], df, {}, [], False, t, "Sam")
    assert "Our track record" in html and "Our advice to you, Sam" in html
