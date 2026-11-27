"""Run the Hammor Co. daily pipeline: fetch → Sharia screen → score → advisors → email.

    python -m hammor.main --dry-run            # build output/report.html, don't send
    python -m hammor.main --send-at 09:00      # build now, email at 09:00 UAE time
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import advisors, analysis, data, emailer, report, sharia
from .universe import UNIVERSE

UAE = ZoneInfo("Asia/Dubai")
log = logging.getLogger("hammor")


def sharia_summary(results: dict[str, sharia.ShariaResult]) -> dict:
    counts: dict[str, int] = {}
    for r in results.values():
        counts[r.status] = counts.get(r.status, 0) + 1
    return {
        "standard": "AAOIFI Shari'ah Standard No. 21",
        "counts": counts,
        "borderline": [s for s, r in results.items() if r.borderline],
        "needs_review": [s for s, r in results.items() if r.status == sharia.REVIEW],
        "non_compliant": {s: "; ".join(r.reasons) for s, r in results.items()
                          if r.status == sharia.NON_COMPLIANT},
    }


def _noop(_event: dict) -> None:
    pass


def run_pipeline(fetch=data.fetch_all, on_event=_noop) -> dict:
    """Fetch → screen → score → morning meeting. Returns the full meeting record
    (also what the desktop app replays). on_event receives live progress events."""
    now = datetime.now(UAE)
    date_str = now.strftime("%A, %d %B %Y")

    log.info("Fetching %d stocks", len(UNIVERSE))
    on_event({"type": "stage", "stage": "data", "text": "Collecting market data"})

    def progress(i, n, company):
        on_event({"type": "progress", "done": i, "total": n, "text": company.name})

    stocks = fetch(UNIVERSE, progress=progress)
    failed = [s.company.symbol for s in stocks if not s.ok]
    good = [s for s in stocks if s.ok]
    if not good:
        raise RuntimeError("No market data could be fetched for any stock")

    on_event({"type": "stage", "stage": "screen", "text": "Running the Sharia screen and scoring"})
    results = {s.company.symbol: sharia.screen(s) for s in good}
    df = analysis.build_table(good, results)
    market = analysis.market_summary(df)
    summary = sharia_summary(results)
    on_event({"type": "market", "market": market, "sharia": summary})

    log.info("Holding the morning team meeting")
    out, transcript, ai_used = advisors.run_team(df, market, summary, date_str, on_event=on_event)
    record = {
        "date": now.strftime("%Y-%m-%d"),
        "date_label": date_str,
        "generated_at": now.isoformat(timespec="seconds"),
        "ai_used": ai_used,
        "decision": out,
        "transcript": transcript,
        "market": market,
        "sharia": summary,
        "failed": failed,
        "screen": json.loads(df.to_json(orient="records")),
        "_df": df,  # not serialised; used to build the email
    }
    on_event({"type": "decision", "decision": out, "ai_used": ai_used})
    return record


def meeting_json(record: dict) -> str:
    return json.dumps({k: v for k, v in record.items() if not k.startswith("_")},
                      ensure_ascii=False, default=str)


def build(fetch=data.fetch_all) -> tuple[str, str, bytes, dict]:
    record = run_pipeline(fetch)
    df, out = record["_df"], record["decision"]
    html = report.render(record["date_label"], out, record["transcript"], df, record["market"],
                         record["failed"], record["ai_used"])
    now = datetime.now(UAE)
    subject = f"Hammor Co. Daily Report – {now:%a %d %b %Y} – {out['headline']}"[:180]
    return subject, html, df.to_csv(index=False).encode(), record


def wait_until(hhmm: str) -> None:
    h, m = map(int, hhmm.split(":"))
    now = datetime.now(UAE)
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if target > now and target - now < timedelta(hours=3):
        secs = (target - now).total_seconds()
        log.info("Waiting %.0f s until %s UAE time", secs, hhmm)
        time.sleep(secs)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="write the report to output/, don't email")
    p.add_argument("--send-at", help="HH:MM UAE time to send at (waits if early)")
    p.add_argument("--force", action="store_true", help="run even on a Saturday or Sunday")
    a = p.parse_args()

    if datetime.now(UAE).weekday() >= 5 and not a.force:
        log.info("Weekend in the UAE, so no report today")
        return

    subject, html, csv, record = build()
    outdir = Path(os.environ.get("HAMMOR_OUTPUT", "output"))
    outdir.mkdir(exist_ok=True)
    (outdir / "report.html").write_text(html, encoding="utf-8")
    (outdir / "screen.csv").write_bytes(csv)
    (outdir / "meeting.json").write_text(meeting_json(record), encoding="utf-8")
    log.info("Report written to %s", outdir / "report.html")

    if a.dry_run:
        return
    if a.send_at:
        wait_until(a.send_at)
    stamp = datetime.now(UAE).strftime("%Y-%m-%d")
    emailer.send(subject, html, {f"hammor_screen_{stamp}.csv": csv})
    log.info("Email sent")


if __name__ == "__main__":
    main()
