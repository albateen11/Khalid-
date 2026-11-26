"""The Hammor Co. morning meeting, run on Claude.

Each team member (see team.py) is a separate Claude call with their own persona.
They speak in turn and each one hears everything said before them:

  Round 1 – Pitches     Omar (ADX) and Layla (DFM) research the news and pitch ideas
  Round 2 – Challenge   Yousef (risk), Mariam (dividends) and Abdullah (Sharia)
                        question the pitches and respond to one another
  Round 3 – Rebuttal    Omar and Layla defend, adjust or drop their ideas
  Decision              Saeed (Chief) weighs the discussion and issues the final
                        recommendations as structured JSON

If ANTHROPIC_API_KEY is not set, or the API fails, a rules-based committee is
used, so the daily email still goes out.
"""

from __future__ import annotations

import json
import logging
import os

import pandas as pd

from .team import ABDULLAH, LAYLA, MARIAM, OMAR, SAEED, YOUSEF, Member

log = logging.getLogger(__name__)

MODEL = os.environ.get("HAMMOR_MODEL", "claude-opus-5-5")
BETAS = ["server-side-fallback-2026-07-01"]


def web_search(max_uses: int) -> dict:
    return {"type": "web_search_20260209", "name": "web_search", "max_uses": max_uses}


FIRM_CONTEXT = """You work at Hammor Co., an investment research firm focused only on
Sharia-compliant equities listed on the Abu Dhabi Securities Exchange (ADX) and the
Dubai Financial Market (DFM). The client is a private investor who wants ideas on
three horizons: long-term (1+ years, quality and value), medium-term growth
(3–12 months, momentum and earnings), and income (dividends).
Prices are in AED. Sharia screening follows AAOIFI Shari'ah Standard No. 21.
Only stocks whose sharia_status is "Compliant" may be recommended. The quantitative
data comes from free, delayed sources and may have gaps: be honest about uncertainty
and never invent figures."""

MEETING_STYLE = """You are speaking at the team's morning meeting. Talk naturally in the
first person, as in a real meeting: address colleagues by name, agree or disagree with
specific points they made, and refer to stock names and numbers. Plain text only: no
headings, no bullet lists, no markdown. Stay strictly in character."""

DATA_BLOCK = """TODAY: {date}

MARKET SNAPSHOT:
{market}

SHARIA SCREENING SUMMARY:
{sharia}

CANDIDATES (Sharia-compliant, highest quant scores; ratios are fractions, so 0.12 = 12%):
{screen}"""

PITCH = """It's {date}, and you open the meeting for {exchange}. First use web search to
check the latest news (the last 1–2 weeks) on your best {exchange} candidates and on the
{exchange} market: results, dividends, contracts, index changes, regulation, oil and rates.
Then pitch to the team in at most 230 words: the market tone, your 2–4 best ideas (say which
horizon each one suits and why, citing the news and the numbers), and one stock from the
list you would NOT buy now."""

CHALLENGE = {
    "risk": """Respond to the pitches so far in at most 200 words. Challenge the
riskiest ideas: valuation, stretched RSI, volatility, liquidity, concentration, macro.
You may web search for current macro risks. Say which ideas you are comfortable with and
what would make the others acceptable.""",
    "income": """Respond in at most 180 words. Review the income angle: which pitched
or listed stocks have the most sustainable dividends, any yield traps, and upcoming
ex-dividend dates (you may web search for recent dividend announcements). Respond to
Yousef's points where relevant, and suggest your top income names.""",
    "sharia": """Respond in at most 170 words. Review every stock mentioned so far
for Sharia compliance using the data: flag borderline ratios, names that need scholar
review, and the dividend purification percentage the client should give to charity.
Object clearly if a colleague mentioned a non-compliant or doubtful stock.""",
}

REBUTTAL = """Your colleagues have challenged the ideas. Respond in at most 130 words:
defend the ideas you still believe in with evidence, accept fair criticism, and say
clearly which ideas you drop or adjust (for example a lower entry price or a smaller size)."""

DECISION = """You have heard the whole morning meeting (transcript below). As Chief Investment
Advisor, make the final decision for the client.

- picks.long_term: 3–4 stocks (1+ year horizon, quality and value)
- picks.medium_term: 3–4 stocks (3–12 months, growth and momentum)
- picks.income: 3–4 stocks (dividend income)
Prefer a mix of ADX and DFM, and avoid concentrating in one sector. Respect valid
objections from Yousef and Abdullah: never pick a stock Abdullah objected to on Sharia grounds.
For each pick give an entry_zone as an AED price range (use the current price, the 50/200-day
averages and the 52-week range), a target_price, an action (Buy / Accumulate / Hold / Watch),
and team_view: one sentence on who backed the idea and who raised concerns.
watchlist: compliant stocks that are close to a buy signal. avoid: stocks to stay away from now.
sharia_officer_note: Abdullah's compliance conclusions in 3–5 sentences, including purification.
risks: 3–5 key risks, building on Yousef's points.
closing_remarks: what you say to close the meeting, in at most 120 words, in your own voice,
explaining the main decisions and whose argument won where the team disagreed.
headline: one line summarising today's view. market_overview: 3–5 sentences.
Use ONLY symbols from the data, and pick only stocks whose sharia_status is "Compliant".

MEETING TRANSCRIPT:
{transcript}"""

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
        "team_view": {"type": "string"},
    },
    "required": ["symbol", "name", "exchange", "action", "conviction", "entry_zone",
                 "target_price", "rationale", "key_risk", "team_view"],
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
        "closing_remarks": {"type": "string"},
    },
    "required": ["headline", "market_overview", "picks", "watchlist", "avoid",
                 "sharia_officer_note", "risks", "closing_remarks"],
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


def _call(system: str, user: str, *, tools=None, output_config=None, max_tokens=32000):
    client = _client()
    messages = [{"role": "user", "content": user}]
    kwargs = dict(model=MODEL, max_tokens=max_tokens, betas=BETAS, fallbacks="default",
                  system=system, messages=messages)
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


def _system(member: Member) -> str:
    return (f"{FIRM_CONTEXT}\n\nYou are {member.name}, {member.role} at Hammor Co. "
            f"{member.persona}\n\n{MEETING_STYLE}")


def _transcript_text(transcript: list[dict]) -> str:
    return "\n\n".join(f"{t['name']} ({t['role']}): {t['text']}" for t in transcript)


class Meeting:
    """Runs the morning meeting turn by turn and keeps the transcript."""

    def __init__(self, df: pd.DataFrame, market: dict, sharia_summary: dict, date: str):
        self.df, self.market, self.sharia, self.date = df, market, sharia_summary, date
        self.transcript: list[dict] = []

    def _data(self, exchange: str | None = None, full: bool = False) -> str:
        compliant = self.df[self.df["sharia_status"] == "Compliant"]
        return DATA_BLOCK.format(
            date=self.date,
            market=json.dumps(self.market if exchange is None else self.market.get(exchange, {}),
                              default=str),
            sharia=json.dumps(self.sharia, default=str),
            screen=_records(compliant if full else _candidates(self.df, exchange)),
        )

    def speak(self, member: Member, instruction: str, *, exchange=None, tools=None,
              effort="medium") -> str:
        so_far = _transcript_text(self.transcript) or "(You are the first to speak.)"
        user = (f"{self._data(exchange)}\n\nMEETING SO FAR:\n{so_far}\n\n"
                f"YOUR TURN, {member.name}:\n{instruction}")
        try:
            text = _text(_call(_system(member), user, tools=tools,
                               output_config={"effort": effort}))
        except Exception as e:
            log.exception("%s could not speak", member.name)
            text = f"(Unavailable this morning: {e})"
        self.transcript.append({"key": member.key, "name": member.name,
                                "role": member.role, "text": text})
        return text

    def run(self) -> dict:
        # Round 1 – pitches, with web research
        self.speak(OMAR, PITCH.format(date=self.date, exchange="ADX"),
                   exchange="ADX", tools=[web_search(5)])
        self.speak(LAYLA, PITCH.format(date=self.date, exchange="DFM"),
                   exchange="DFM", tools=[web_search(5)])
        # Round 2 – challenge
        self.speak(YOUSEF, CHALLENGE["risk"], tools=[web_search(3)])
        self.speak(MARIAM, CHALLENGE["income"], tools=[web_search(3)])
        self.speak(ABDULLAH, CHALLENGE["sharia"])
        # Round 3 – rebuttal
        self.speak(OMAR, REBUTTAL, exchange="ADX")
        self.speak(LAYLA, REBUTTAL, exchange="DFM")
        # Decision
        user = (f"{self._data(full=True)}\n\n"
                f"{DECISION.format(transcript=_transcript_text(self.transcript))}")
        system = f"{FIRM_CONTEXT}\n\nYou are {SAEED.name}, {SAEED.role} at Hammor Co. {SAEED.persona}"
        resp = _call(system, user, output_config={
            "effort": "high", "format": {"type": "json_schema", "schema": COMMITTEE_SCHEMA}})
        out = json.loads(_text(resp))
        self.transcript.append({"key": SAEED.key, "name": SAEED.name, "role": SAEED.role,
                                "text": out.get("closing_remarks", "")})
        return out


# ------------------------------------------------------------- rules-based fallback

def rules_committee(df: pd.DataFrame) -> dict:
    comp = df[df["sharia_status"] == "Compliant"]

    def pick(row, horizon):
        price = row["price"]
        support = row["sma50"] if pd.notna(row["sma50"]) else price * 0.97
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
            "action": "Accumulate", "conviction": "Medium", "entry_zone": f"{lo:.2f} – {hi:.2f}",
            "target_price": round(price * (1 + upside), 2),
            "rationale": "Top quantitative score. " + ", ".join(parts) + ".",
            "key_risk": "Rules-based pick: no analyst review today.",
            "team_view": "",
        }

    picks = {}
    for horizon, col in (("long_term", "long_term_score"), ("medium_term", "growth_score"),
                         ("income", "income_score")):
        top = comp.dropna(subset=[col]).nlargest(3, col)
        picks[horizon] = [pick(r, horizon) for _, r in top.iterrows()]
    return {
        "headline": "Quantitative screen (the team didn't meet today)",
        "market_overview": "The AI research team didn't run today, so these picks come "
                           "from the quantitative screen only.",
        "picks": picks,
        "watchlist": [],
        "avoid": [],
        "sharia_officer_note": "Screened under AAOIFI Standard 21. Debt and cash are measured "
                               "conservatively (all treated as interest-bearing).",
        "risks": ["Picks are model-generated without analyst review."],
        "closing_remarks": "",
    }


def run_team(df: pd.DataFrame, market: dict, sharia_summary: dict, date: str) -> tuple[dict, list, bool]:
    """Returns (decision, meeting_transcript, ai_used)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        log.warning("ANTHROPIC_API_KEY not set — using the rules-based committee")
        return rules_committee(df), [], False
    meeting = Meeting(df, market, sharia_summary, date)
    try:
        out = meeting.run()
    except Exception:
        log.exception("Morning meeting failed — falling back to rules")
        return rules_committee(df), meeting.transcript, False

    # Guard: never pass on a pick that isn't Sharia-compliant in our own screen.
    compliant = set(df.loc[df["sharia_status"] == "Compliant", "symbol"])
    for horizon, picks in out["picks"].items():
        out["picks"][horizon] = [p for p in picks if p["symbol"] in compliant]
    return out, meeting.transcript, True
