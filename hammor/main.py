"""Run the Hammor Co. daily pipeline: fetch → Sharia screen → score → advisors → email.

    python -m hammor.main --dry-run            # build output/report.html, don't send
    python -m hammor.main --send-at 09:00      # build now, email at 09:00 UAE time
"""

from __future__ import annotations

import argparse
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


def build(fetch=data.fetch_all) -> tuple[str, str, bytes]:
    now = datetime.now(UAE)
    date_str = now.strftime("%A, %d %B %Y")

    log.info("Fetching %d stocks", len(UNIVERSE))
    stocks = fetch(UNIVERSE)
    failed = [s.company.symbol for s in stocks if not s.ok]
    good = [s for s in stocks if s.ok]
    if not good:
        raise RuntimeError("No market data could be fetched for any stock")

    results = {s.company.symbol: sharia.screen(s) for s in good}
    df = analysis.build_table(good, results)
    market = analysis.market_summary(df)
    summary = sharia_summary(results)

    log.info("Holding the morning team meeting")
    out, transcript, ai_used = advisors.run_team(df, market, summary, date_str)
    html = report.render(date_str, out, transcript, df, market, failed, ai_used)
    subject = f"Hammor Co. Daily Report – {now:%a %d %b %Y} – {out['headline']}"[:180]
    return subject, html, df.to_csv(index=False).encode()


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

    subject, html, csv = build()
    outdir = Path(os.environ.get("HAMMOR_OUTPUT", "output"))
    outdir.mkdir(exist_ok=True)
    (outdir / "report.html").write_text(html, encoding="utf-8")
    (outdir / "screen.csv").write_bytes(csv)
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
