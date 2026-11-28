"""Render the daily report as an email-safe HTML document (inline styles only)."""

from __future__ import annotations

import html
import math

import pandas as pd

from .team import BY_KEY, TEAM

NAVY = "#0b2545"
GOLD = "#b08d3c"
GREEN = "#1b7f4b"
RED = "#b3261e"
MUTED = "#5f6b7a"
BORDER = "#e3e7ee"

ACTION_COLORS = {"Buy": GREEN, "Accumulate": "#2e7d32", "Hold": "#8a6d1d", "Watch": MUTED}


def e(x) -> str:
    return html.escape(str(x)) if x is not None else ""


def _isnum(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def pct(v, signed=True) -> str:
    if not _isnum(v):
        return "–"
    s = f"{v:+.1%}" if signed else f"{v:.1%}"
    color = GREEN if v > 0 else RED if v < 0 else MUTED
    return f'<span style="color:{color}">{s}</span>' if signed else s


def num(v, d=2) -> str:
    return f"{v:,.{d}f}" if _isnum(v) else "–"


def _paras(text: str) -> str:
    return "".join(f'<p style="margin:0 0 10px">{e(p)}</p>' for p in str(text).split("\n") if p.strip())


def _section(title: str, body: str) -> str:
    return (f'<h2 style="font-size:17px;color:{NAVY};border-bottom:2px solid {GOLD};'
            f'padding-bottom:6px;margin:28px 0 12px">{e(title)}</h2>{body}')


def _pick_cards(picks: list[dict], df: pd.DataFrame) -> str:
    if not picks:
        return f'<p style="color:{MUTED}">No pick met the bar today.</p>'
    by_sym = df.set_index("symbol")
    cards = []
    for p in picks:
        row = by_sym.loc[p["symbol"]] if p["symbol"] in by_sym.index else None
        price = row["price"] if row is not None else None
        upside = (p["target_price"] / price - 1) if price else None
        purif = row["purification_pct"] if row is not None else None
        color = ACTION_COLORS.get(p["action"], MUTED)
        cards.append(f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
 style="border:1px solid {BORDER};border-radius:8px;margin:0 0 12px;border-collapse:separate">
<tr><td style="padding:12px 14px">
  <div style="font-size:15px;font-weight:bold;color:{NAVY}">{e(p['name'])}
    <span style="font-weight:normal;color:{MUTED};font-size:13px">· {e(p['symbol'])} · {e(p['exchange'])}</span></div>
  <div style="margin:6px 0 8px;font-size:13px">
    <span style="background:{color};color:#fff;padding:2px 8px;border-radius:10px">{e(p['action'])}</span>
    &nbsp;Conviction: <b>{e(p['conviction'])}</b>
    &nbsp;|&nbsp; Price: <b>{num(price)}</b> AED
    &nbsp;|&nbsp; Entry: <b>{e(p['entry_zone'])}</b>
    &nbsp;|&nbsp; Target: <b>{num(p['target_price'])}</b> ({pct(upside)})
  </div>
  <div style="font-size:14px;line-height:1.5">{e(p['rationale'])}</div>
  {f'<div style="font-size:13px;margin-top:6px;font-style:italic;color:#34495e">Team view: {e(p["team_view"])}</div>' if p.get("team_view") else ""}
  <div style="font-size:13px;color:{MUTED};margin-top:6px"><b>Key risk:</b> {e(p['key_risk'])}
  {f" &nbsp;|&nbsp; <b>Purification:</b> ~{purif:.2%} of dividends" if _isnum(purif) and purif > 0 else ""}</div>
</td></tr></table>""")
    return "".join(cards)


def _market_block(market: dict) -> str:
    cells = []
    for ex, m in market.items():
        g = ", ".join(f"{e(x['name'])} {pct(x['chg_1d'])}" for x in m["top_gainers"])
        l = ", ".join(f"{e(x['name'])} {pct(x['chg_1d'])}" for x in m["top_losers"])
        cells.append(f"""<td valign="top" style="padding:10px;border:1px solid {BORDER};width:50%">
<div style="font-weight:bold;color:{NAVY}">{ex}</div>
<div style="font-size:13px">Last session (coverage avg): {pct(m['avg_change_1d'])} · 1-month: {pct(m['avg_change_1m'])}</div>
<div style="font-size:13px">Advancers {m['advancers']} / Decliners {m['decliners']} of {m['stocks_covered']}</div>
<div style="font-size:12px;color:{MUTED};margin-top:4px">▲ {g}<br>▼ {l}</div></td>""")
    return f'<table role="presentation" width="100%" cellspacing="0" style="border-collapse:collapse"><tr>{"".join(cells)}</tr></table>'


def _screen_table(df: pd.DataFrame) -> str:
    rows = []
    for _, r in df.sort_values(["exchange", "name"]).iterrows():
        st = r["sharia_status"]
        color = GREEN if st == "Compliant" else RED if st == "Non-compliant" else "#8a6d1d"
        flag = " ⚠" if r.get("sharia_borderline") else ""
        rows.append(
            f'<tr><td style="padding:4px 6px">{e(r["name"])}<br><span style="color:{MUTED}">{e(r["symbol"])}</span></td>'
            f'<td style="padding:4px 6px">{num(r["price"])}</td><td style="padding:4px 6px">{pct(r["chg_1d"])}</td>'
            f'<td style="padding:4px 6px">{pct(r["ret_3m"])}</td>'
            f'<td style="padding:4px 6px">{pct(r["debt_ratio"], False)}</td>'
            f'<td style="padding:4px 6px">{pct(r["cash_ratio"], False)}</td>'
            f'<td style="padding:4px 6px;color:{color}">{e(st)}{flag}</td></tr>')
    head = "".join(f'<th align="left" style="padding:4px 6px;background:{NAVY};color:#fff">{h}</th>'
                   for h in ("Company", "Price", "1D", "3M", "Debt/MC", "Cash/MC", "Sharia"))
    return (f'<table role="presentation" width="100%" cellspacing="0" style="border-collapse:collapse;'
            f'font-size:12px"><tr>{head}</tr>{"".join(rows)}</table>')


def _meeting(transcript: list[dict]) -> str:
    if not transcript:
        return ""
    labels = {"review": "Track record", "pitches": "Pitches", "challenge": "Challenge", "response": "Response",
              "decision": "Decision"}
    parts, last = [], None
    for t in transcript:
        rnd = t.get("round")
        if rnd and rnd != last:
            parts.append(f'<div style="font-size:11px;letter-spacing:1px;text-transform:uppercase;'
                         f'color:{MUTED};margin:14px 0 6px">{labels.get(rnd, rnd)}</div>')
            last = rnd
        m = BY_KEY.get(t["key"])
        color = m.color if m else NAVY
        parts.append(f"""<table role="presentation" width="100%" cellspacing="0" style="margin:0 0 10px">
<tr><td width="40" valign="top"><div style="width:32px;height:32px;border-radius:16px;background:{color};
color:#fff;font-weight:bold;text-align:center;line-height:32px">{e(t['name'][0])}</div></td>
<td valign="top" style="background:#f7f8fa;border-left:3px solid {color};padding:8px 12px;border-radius:4px">
<div style="font-size:13px"><b style="color:{color}">{e(t['name'])}</b>
<span style="color:{MUTED}"> · {e(t['role'])}</span></div>
<div style="font-size:13px;line-height:1.5;margin-top:4px">{_paras(t['text'])}</div></td></tr></table>""")
    return _section("This morning's team meeting", "".join(parts))


def _roster() -> str:
    cells = "".join(
        f'<td valign="top" style="padding:6px;font-size:12px;width:33%"><b style="color:{m.color}">'
        f'{e(m.name)}</b><br><span style="color:{MUTED}">{e(m.role)}</span></td>'
        + ("</tr><tr>" if i % 3 == 2 and i < len(TEAM) - 1 else "")
        for i, m in enumerate(TEAM))
    return (f'<table role="presentation" width="100%" cellspacing="0" style="border:1px solid {BORDER};'
            f'border-radius:8px;margin-top:24px"><tr><td colspan="3" style="padding:8px 6px 0;'
            f'font-weight:bold;color:{NAVY};font-size:13px">Meet the Hammor Co. team</td></tr>'
            f'<tr>{cells}</tr></table>')


def _track_block(track: dict | None, review: str) -> str:
    if not track or not track.get("count"):
        msg = ("The team keeps a record of every recommendation it makes. From the next meeting on, "
               "this section shows how each one has performed since it was made.")
        return _section("Our track record", f'<p style="color:{MUTED}">{e(msg)}</p>')
    t = track
    bench = (f" vs {pct(t['avg_benchmark'])} for the average Sharia-compliant stock"
             if t.get("avg_benchmark") is not None else "")
    summary = (f'<p style="margin:0 0 8px"><b>{t["count"]}</b> recommendations since {e(t["since"])}: '
               f'<b>{t["winners"]}</b> up ({t["win_rate"]:.0%}), average {pct(t["avg_return"])}{bench}. '
               f'Targets reached: <b>{t["targets_hit"]}</b>.</p>')
    head = "".join(f'<th align="left" style="padding:4px 6px;background:{NAVY};color:#fff">{h}</th>'
                   for h in ("Stock", "Horizon", "Since", "Then", "Now", "Return", "Status"))
    rows = []
    for r in t["positions"][:15]:
        color = GREEN if r["status"] == "Target reached" else RED if r["status"] == "Under review" else "#1d2733"
        rows.append(f'<tr><td style="padding:4px 6px">{e(r["name"])}</td><td style="padding:4px 6px">{e(r["horizon_label"])}</td>'
                    f'<td style="padding:4px 6px">{e(r["date"])}</td><td style="padding:4px 6px">{num(r["entry"])}</td>'
                    f'<td style="padding:4px 6px">{num(r["price"])}</td><td style="padding:4px 6px">{pct(r["return"])}</td>'
                    f'<td style="padding:4px 6px;color:{color}">{e(r["status"])}</td></tr>')
    table = (f'<table role="presentation" width="100%" cellspacing="0" style="border-collapse:collapse;font-size:12px">'
             f'<tr>{head}</tr>{"".join(rows)}</table>'
             f'<p style="font-size:11px;color:{MUTED}">Price returns since the first day each stock was recommended '
             f'(dividends not included). Past performance does not guarantee future results.</p>')
    return _section("Our track record", (_paras(review) if review else "") + summary + table)


def render(date_str: str, out: dict, transcript: list[dict], df: pd.DataFrame, market: dict,
           failed: list[str], ai_used: bool, track: dict | None = None, client_name: str = "") -> str:
    advice = out.get("client_advice")
    sections = [
        (f'<div style="background:#fbf6e9;border:1px solid {GOLD};border-radius:10px;padding:14px 18px;margin:18px 0 0">'
         f'<div style="font-size:16px;font-weight:bold;color:{NAVY};margin-bottom:6px">Our advice to you{", " + e(client_name) if client_name else ""}</div>'
         f'<div style="font-size:14.5px;line-height:1.6">{_paras(advice)}</div>'
         f'<div style="font-size:12px;color:{MUTED}">From Saeed and the Hammor Co. team</div></div>') if advice else "",
        _section("Market overview", _paras(out["market_overview"]) + _market_block(market)),
        _section("Long-term opportunities (1+ years)", _pick_cards(out["picks"]["long_term"], df)),
        _section("Medium-term growth (3–12 months)", _pick_cards(out["picks"]["medium_term"], df)),
        _section("Income and dividends", _pick_cards(out["picks"]["income"], df)),
        _track_block(track, out.get("track_review", "")),
    ]
    if out.get("watchlist"):
        items = "".join(f"<li><b>{e(w['symbol'])}</b> – {e(w['reason'])}</li>" for w in out["watchlist"])
        sections.append(_section("Watchlist", f"<ul style='padding-left:18px'>{items}</ul>"))
    if out.get("avoid"):
        items = "".join(f"<li><b>{e(w['symbol'])}</b> – {e(w['reason'])}</li>" for w in out["avoid"])
        sections.append(_section("Stocks to avoid now", f"<ul style='padding-left:18px'>{items}</ul>"))
    sections.append(_section("Sharia Compliance Officer" + (" – Abdullah" if ai_used else ""), _paras(out["sharia_officer_note"])))
    if out.get("risks"):
        items = "".join(f"<li>{e(r)}</li>" for r in out["risks"])
        sections.append(_section("Key risks", f"<ul style='padding-left:18px'>{items}</ul>"))
    sections.append(_meeting(transcript))
    sections.append(_section("Full Sharia screen (AAOIFI Standard 21)",
                             _screen_table(df) + f'<p style="font-size:12px;color:{MUTED}">⚠ = within 17% of an '
                             'AAOIFI limit. Debt and cash use total balances (all treated as interest-bearing), '
                             'so a stock that fails may still pass once Islamic sukuk and deposits are separated out.</p>'))
    if failed:
        sections.append(f'<p style="font-size:12px;color:{MUTED}">No data today for: {e(", ".join(failed))}</p>')

    mode = "Saeed, Omar, Layla, Yousef, Mariam and Abdullah, plus the quantitative screen" if ai_used else "Quantitative screen only"
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Hammor Co. Daily Report</title></head>
<body style="margin:0;background:#f4f6f9;font-family:Arial,Helvetica,sans-serif;color:#1d2733">
<table role="presentation" width="100%" cellspacing="0" style="background:#f4f6f9"><tr><td align="center" style="padding:16px">
<table role="presentation" width="100%" cellspacing="0" style="max-width:720px;background:#fff;border-radius:10px;overflow:hidden">
<tr><td style="background:{NAVY};padding:20px 24px;color:#fff">
  <div style="font-size:24px;font-weight:bold;letter-spacing:1px">HAMMOR <span style="color:{GOLD}">CO.</span></div>
  <div style="font-size:13px;opacity:.85">Sharia-compliant UAE equity research · ADX &amp; DFM</div>
  <div style="font-size:13px;margin-top:8px">Daily report · {e(date_str)}</div>
</td></tr>
<tr><td style="padding:8px 24px 24px;font-size:14px;line-height:1.5">
  <h1 style="font-size:20px;color:{NAVY};margin:18px 0 4px">{e(out['headline'])}</h1>
  <div style="font-size:12px;color:{MUTED}">Prepared by: {mode}</div>
  {''.join(sections)}
  {_roster() if ai_used else ""}
  <p style="font-size:11px;color:{MUTED};margin-top:28px;border-top:1px solid {BORDER};padding-top:12px">
  This report is generated automatically for your personal information. It is not investment advice from an
  SCA-licensed adviser. Market data comes from free, delayed sources and may be incomplete or wrong. Check the
  prices and the Sharia status (for example with the company's Sharia board or a qualified scholar) before you
  invest. Past performance does not guarantee future results.</p>
</td></tr></table></td></tr></table></body></html>"""
