"""Team memory: the track record of Hammor Co.'s past recommendations.

Every morning meeting is saved in reports/YYYY-MM-DD.json (by the daily workflow).
Before the next meeting we reload the last 90 days of meetings and measure each
recommendation against today's prices:

  * Each (stock, horizon) pair counts once, from the first day it was recommended.
  * Return is the price return since that day (dividends are not included).
  * Benchmark is the average return of all Sharia-compliant stocks over the same days,
    so the team can see whether its picks beat simply "buying the market".
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

LOOKBACK_DAYS = 90
REVIEW_LOSS = -0.08  # a pick down 8% or more is flagged for review
HORIZON_LABEL = {"long_term": "Long-term", "medium_term": "Growth", "income": "Income"}


def load_meetings(folder: str | Path = "reports", today: date | None = None,
                  days: int = LOOKBACK_DAYS) -> list[dict]:
    """Earlier meetings (not today's), oldest first."""
    today = today or date.today()
    out = []
    for p in sorted(Path(folder).glob("20*.json")):
        try:
            d = datetime.strptime(p.stem[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if not (0 < (today - d).days <= days):
            continue
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            log.warning("Skipping unreadable meeting %s: %s", p, e)
            continue
        if rec.get("decision") and rec.get("screen"):
            out.append(rec)
    return out


def build_track_record(meetings: list[dict], df: pd.DataFrame, today: date | None = None) -> dict:
    today = today or date.today()
    now = {r["symbol"]: r["price"] for r in df[["symbol", "price"]].to_dict("records")}
    latest_date = meetings[-1]["date"] if meetings else None

    positions: dict[tuple, dict] = {}
    for m in meetings:
        screen = m.get("screen", [])
        prices = {r["symbol"]: r.get("price") for r in screen}
        compliant = [r for r in screen if r.get("sharia_status") == "Compliant" and r.get("price")]
        for horizon, picks in (m["decision"].get("picks") or {}).items():
            for p in picks:
                key = (p["symbol"], horizon)
                if key in positions:
                    positions[key]["last_recommended"] = m["date"]
                    continue
                entry = prices.get(p["symbol"])
                if not entry:
                    continue
                # Benchmark: equal-weight compliant market from that day to today.
                rets = [now[r["symbol"]] / r["price"] - 1 for r in compliant if r["symbol"] in now]
                positions[key] = {
                    "symbol": p["symbol"], "name": p.get("name", p["symbol"]),
                    "horizon": horizon, "horizon_label": HORIZON_LABEL.get(horizon, horizon),
                    "action": p.get("action"), "date": m["date"], "last_recommended": m["date"],
                    "entry": float(entry), "target": p.get("target_price"),
                    "benchmark": sum(rets) / len(rets) if rets else None,
                }

    rows = []
    for pos in positions.values():
        price = now.get(pos["symbol"])
        if price is None:
            continue
        ret = price / pos["entry"] - 1
        target = pos.get("target")
        if target and price >= target:
            status = "Target reached"
        elif ret <= REVIEW_LOSS:
            status = "Under review"
        elif pos["last_recommended"] == latest_date:
            status = "Still recommended"
        else:
            status = "No longer on the list"
        days_held = (today - datetime.strptime(pos["date"], "%Y-%m-%d").date()).days
        rows.append({**pos, "price": float(price), "return": ret, "days": days_held, "status": status,
                     "beat_market": None if pos["benchmark"] is None else ret > pos["benchmark"]})

    rows.sort(key=lambda r: (r["date"], r["symbol"]), reverse=True)
    if not rows:
        return {"meetings_reviewed": len(meetings), "count": 0, "positions": []}

    rets = [r["return"] for r in rows]
    bench = [r["benchmark"] for r in rows if r["benchmark"] is not None]
    by_h = {}
    for h in HORIZON_LABEL:
        hr = [r["return"] for r in rows if r["horizon"] == h]
        if hr:
            by_h[h] = {"count": len(hr), "avg_return": sum(hr) / len(hr),
                       "winners": sum(1 for x in hr if x > 0)}
    best = max(rows, key=lambda r: r["return"])
    worst = min(rows, key=lambda r: r["return"])
    return {
        "meetings_reviewed": len(meetings),
        "since": meetings[0]["date"],
        "count": len(rows),
        "winners": sum(1 for x in rets if x > 0),
        "win_rate": sum(1 for x in rets if x > 0) / len(rets),
        "avg_return": sum(rets) / len(rets),
        "avg_benchmark": sum(bench) / len(bench) if bench else None,
        "beat_market": sum(1 for r in rows if r["beat_market"]),
        "targets_hit": sum(1 for r in rows if r["status"] == "Target reached"),
        "under_review": [r["symbol"] for r in rows if r["status"] == "Under review"],
        "by_horizon": by_h,
        "best": {"symbol": best["symbol"], "name": best["name"], "return": best["return"]},
        "worst": {"symbol": worst["symbol"], "name": worst["name"], "return": worst["return"]},
        "positions": rows,
    }


def for_prompt(track: dict, limit: int = 30) -> str:
    """Compact JSON of the track record for the team's prompts."""
    if not track or not track.get("count"):
        return json.dumps({"note": "No earlier recommendations yet: this is the team's first "
                                   "meeting (or the first in 90 days)."})
    keep = ("symbol", "name", "horizon_label", "date", "entry", "price", "return", "target",
            "status", "benchmark", "days")
    summary = {k: v for k, v in track.items() if k != "positions"}
    pos = [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items() if k in keep}
           for r in track["positions"][:limit]]
    return json.dumps({"summary": summary, "recommendations": pos}, default=str)
