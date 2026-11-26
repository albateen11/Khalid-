"""The Hammor Co. research team, run on Claude.

  * ADX Equity Analyst   – reviews Abu Dhabi candidates and searches the latest news
  * DFM Equity Analyst   – does the same for Dubai
  * Investment Committee – the Chief Investment Advisor and the Sharia Compliance
                           Officer turn the desk notes and quant scores into
                           final recommendations (structured JSON)

If ANTHROPIC_API_KEY is not set, or the API fails, a rules-based committee is
used, so the daily email still goes out.
"""

from __future__ import annotations

import json
import logging
import os

import pandas as pd

log = logging.getLogger(__name__)

MODEL = os.environ.get("HAMMOR_MODEL", "claude-opus-5-5")
BETAS = ["server-side-fallback-2026-07-01"]
WEB_SEARCH = {"type": "web_search_20260209", "name": "web_search", "max_uses": 6}

FIRM_CONTEXT = """You work at Hammor Co., an investment research firm focused only on
Sharia-compliant equities listed on the Abu Dhabi Securities Exchange (ADX) and the
Dubai Financial Market (DFM). The client is a private investor who wants ideas on
three horizons: long-term (1+ years, quality and value), medium-term growth
(3–12 months, momentum and earnings), and income (dividends).
Prices are in AED. Sharia screening follows AAOIFI Shari'ah Standard No. 21.
Recommend ONLY stocks whose sharia_status is "Compliant". Be specific, concise and
honest about uncertainty: the quantitative data comes from free, delayed sources
and may have gaps."""

ANALYST_PROMPT = """You are the {exchange} Equity Analyst at Hammor Co.
Today is {date}. Below is the quantitative screen for today's best-scoring
Sharia-compliant {exchange} candidates, plus a market snapshot.

Use web search to check the latest news (the last 1–2 weeks) that matters for these
names and for the {exchange} market: earnings, dividends, guidance, contracts, index
inclusions, regulatory changes, oil prices, and rates.

Write a desk note for the Investment Committee of at most 450 words:
1. Market tone (2–3 sentences)
2. For each candidate you would back: one line of thesis plus the news that supports it
3. Candidates you would NOT back now, and why
4. Upcoming catalysts or events this week

Use plain text with short headings. Don't invent figures; if you couldn't verify
something, say so.

DATA:
{data}"""

COMMITTEE_PROMPT = """You are the Hammor Co. Investment Committee: the Chief Investment
Advisor and the Sharia Compliance Officer. Today is {date}.

You have the quantitative screen of Sharia-compliant stocks, today's market snapshot,
the Sharia screening summary, and the desk notes from the ADX and DFM analysts.

Produce today's recommendations for the client:
- picks.long_term: 3–4 stocks (1+ year horizon, quality and value)
- picks.medium_term: 3–4 stocks (3–12 months, growth and momentum)
- picks.income: 3–4 stocks (dividend income)
Prefer a mix of ADX and DFM stocks, and avoid concentrating in one sector.
A stock may appear on more than one list only if it is clearly the best fit.
For each pick give an entry_zone as a price range in AED, based on the current price,
the 50/200-day averages and the 52-week range. target_price is your 12-month view
for long-term and income picks, and your horizon view for medium-term picks.
action is one of Buy / Accumulate / Hold / Watch.
watchlist: compliant stocks that are close to a buy signal.
avoid: stocks the client should stay away from right now (compliant or not), with a reason.
sharia_officer_note: 3–5 sentences on today's compliance picture, including borderline
names, stocks that need scholar review, and dividend purification guidance.
risks: 3–5 key market risks.
Use ONLY symbols that appear in the data, and choose picks only from stocks with
sharia_status "Compliant".

QUANT SCREEN (Compliant stocks):
{screen}

MARKET SNAPSHOT:
{market}

SHARIA SCREENING SUMMARY:
{sharia}

ADX DESK NOTE:
{adx_note}

DFM DESK NOTE:
{dfm_note}"""

_PICK = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string"},
        "name": {"type": "string"},
        "exchange": {"type": "string", "enum": ["ADX", "DFM"]},
        "action": {"type": "string", "enum": ["Buy", "Accumulate", "Hold", "Watch"]},
        "conviction": {"type": "string", "enum": ["High", "Medium", "Low"]},
        "entry_zone": {"type": "string"},
        "target_price": {"type": "number"},
        "rationale": {"type": "string"},
        "key_risk": {"type": "string"},
    },
    "required": ["symbol", "name", "exchange", "action", "conviction",
                 "entry_zone", "target_price", "rationale", "key_risk"],
    "additionalProperties": False,
}
_REASON = {
    "type": "object",
    "properties": {"symbol": {"type": "string"}, "reason": {"type": "string"}},
    "required": ["symbol", "reason"],
    "additionalProperties": False,
}
COMMITTEE_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "market_overview": {"type": "string"},
        "picks": {
            "type": "object",
            "properties": {
                "long_term": {"type": "array", "items": _PICK},
                "medium_term": {"type": "array", "items": _PICK},
                "income": {"type": "array", "items": _PICK},
            },
            "required": ["long_term", "medium_term", "income"],
            "additionalProperties": False,
        },
        "watchlist": {"type": "array", "items": _REASON},
        "avoid": {"type": "array", "items": _REASON},
        "sharia_officer_note": {"type": "string"},
        "risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["headline", "market_overview", "picks", "watchlist", "avoid",
                 "sharia_officer_note", "risks"],
    "additionalProperties": False,
}

SCREEN_COLS = ["symbol", "name", "exchange", "sector", "sharia_status", "sharia_borderline",
               "price", "chg_1d", "ret_1m", "ret_3m", "ret_6m", "ret_12m", "sma50", "sma200",
               "rsi14", "volatility", "high_52w", "low_52w", "pe", "pb", "div_yield", "payout",
               "roe", "margin", "rev_growth", "eps_growth", "debt_ratio", "cash_ratio",
               "purification_pct", "liquid", "long_term_score", "growth_score", "income_score"]


def _records(df: pd.DataFrame) -> str:
    d = df[[c for c in SCREEN_COLS if c in df.columns]].copy()
    for c in d.select_dtypes("number").columns:
        d[c] = d[c].round(4)
    return d.to_json(orient="records")


def _candidates(df: pd.DataFrame, exchange: str | None = None, n: int = 6) -> pd.DataFrame:
    d = df[df["sharia_status"] == "Compliant"]
    if exchange:
        d = d[d["exchange"] == exchange]
    syms = set()
    for col in ("long_term_score", "growth_score", "income_score"):
        syms |= set(d.nlargest(n, col)["symbol"])
    return d[d["symbol"].isin(syms)]


# --------------------------------------------------------------------- Claude calls

def _client():
    import anthropic
    return anthropic.Anthropic(max_retries=4)


def _text(resp) -> str:
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def _call(messages, *, tools=None, output_config=None, max_tokens=32000):
    client = _client()
    kwargs = dict(model=MODEL, max_tokens=max_tokens, betas=BETAS, fallbacks="default",
                  system=FIRM_CONTEXT, messages=messages)
    if tools:
        kwargs["tools"] = tools
    if output_config:
        kwargs["output_config"] = output_config
    for _ in range(5):  # resume server-tool turns that pause
        with client.beta.messages.stream(**kwargs) as stream:
            resp = stream.get_final_message()
        if resp.stop_reason == "pause_turn":
            messages = messages + [{"role": "assistant", "content": resp.content}]
            kwargs["messages"] = messages
            continue
        break
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"model declined: {getattr(resp.stop_details, 'category', None)}")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("response truncated at max_tokens")
    return resp


def analyst_note(exchange: str, df: pd.DataFrame, market: dict, date: str) -> str:
    cands = _candidates(df, exchange)
    if cands.empty:
        return f"No Sharia-compliant {exchange} candidates with data today."
    data = json.dumps({"market": market.get(exchange, {}), "candidates": json.loads(_records(cands))},
                      default=str)
    prompt = ANALYST_PROMPT.format(exchange=exchange, date=date, data=data)
    resp = _call([{"role": "user", "content": prompt}], tools=[WEB_SEARCH],
                 output_config={"effort": "medium"})
    return _text(resp)


def committee(df: pd.DataFrame, market: dict, sharia_summary: dict, notes: dict, date: str) -> dict:
    prompt = COMMITTEE_PROMPT.format(
        date=date,
        screen=_records(df[df["sharia_status"] == "Compliant"]),
        market=json.dumps(market, default=str),
        sharia=json.dumps(sharia_summary, default=str),
        adx_note=notes.get("ADX", "n/a"),
        dfm_note=notes.get("DFM", "n/a"),
    )
    resp = _call([{"role": "user", "content": prompt}],
                 output_config={"effort": "high",
                                "format": {"type": "json_schema", "schema": COMMITTEE_SCHEMA}})
    return json.loads(_text(resp))


# ------------------------------------------------------------- rules-based fallback

def _fmt_range(lo, hi):
    return f"{lo:.2f} – {hi:.2f}"


def rules_committee(df: pd.DataFrame) -> dict:
    comp = df[df["sharia_status"] == "Compliant"]

    def pick(row, horizon):
        price = row["price"]
        support = row["sma50"] or price * 0.97
        lo, hi = min(price, support) * 0.99, price * 1.01
        upside = {"long_term": 0.15, "medium_term": 0.10, "income": 0.08}[horizon]
        parts = []
        if pd.notna(row.get("pe")):
            parts.append(f"P/E {row['pe']:.1f}")
        if pd.notna(row.get("div_yield")):
            parts.append(f"dividend yield {row['div_yield']:.1%}")
        if pd.notna(row.get("ret_3m")):
            parts.append(f"3-month return {row['ret_3m']:+.1%}")
        if pd.notna(row.get("roe")):
            parts.append(f"ROE {row['roe']:.1%}")
        return {
            "symbol": row["symbol"], "name": row["name"], "exchange": row["exchange"],
            "action": "Accumulate", "conviction": "Medium", "entry_zone": _fmt_range(lo, hi),
            "target_price": round(price * (1 + upside), 2),
            "rationale": "Top quantitative score. " + ", ".join(parts) + ".",
            "key_risk": "Rules-based pick: no analyst review today.",
        }

    picks = {}
    for horizon, col in (("long_term", "long_term_score"), ("medium_term", "growth_score"),
                         ("income", "income_score")):
        top = comp.dropna(subset=[col]).nlargest(3, col)
        picks[horizon] = [pick(r, horizon) for _, r in top.iterrows()]
    return {
        "headline": "Quantitative screen (AI advisors unavailable today)",
        "market_overview": "The AI research team didn't run today, so these picks come "
                           "from the quantitative screen only.",
        "picks": picks,
        "watchlist": [],
        "avoid": [],
        "sharia_officer_note": "Screened under AAOIFI Standard 21. Debt and cash are measured "
                               "conservatively (all treated as interest-bearing).",
        "risks": ["Picks are model-generated without analyst review."],
    }


def run_team(df: pd.DataFrame, market: dict, sharia_summary: dict, date: str) -> tuple[dict, dict, bool]:
    """Returns (committee_output, desk_notes, ai_used)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        log.warning("ANTHROPIC_API_KEY not set — using the rules-based committee")
        return rules_committee(df), {}, False
    notes = {}
    for ex in ("ADX", "DFM"):
        try:
            notes[ex] = analyst_note(ex, df, market, date)
        except Exception as e:
            log.exception("%s analyst failed", ex)
            notes[ex] = f"(Desk note unavailable: {e})"
    try:
        out = committee(df, market, sharia_summary, notes, date)
    except Exception:
        log.exception("Investment Committee failed — falling back to rules")
        return rules_committee(df), notes, False

    # Guard: never pass on a pick that isn't Sharia-compliant in our own screen.
    compliant = set(df.loc[df["sharia_status"] == "Compliant", "symbol"])
    for horizon, picks in out["picks"].items():
        out["picks"][horizon] = [p for p in picks if p["symbol"] in compliant]
    return out, notes, True
