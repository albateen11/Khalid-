# Hammor Co.

**Sharia-compliant equity research for the UAE markets: ADX (Abu Dhabi) and DFM (Dubai).**

Every Monday to Friday at **09:00 UAE time**, an hour before the market opens, Hammor Co.
emails you a research report with:

- **Market overview** for ADX and DFM: breadth, top gainers and losers
- **Long-term opportunities** (1+ years): quality and value
- **Medium-term growth** (3–12 months): momentum and earnings
- **Income and dividends**: sustainable dividend payers
- For each pick: action (Buy / Accumulate / Hold / Watch), conviction, entry zone, target price, rationale, key risk,
  and the **dividend purification** percentage
- A watchlist, stocks to avoid, a key-risks list, and a note from the **Sharia Compliance Officer**
- Desk notes from the ADX and DFM analysts, including the latest news found on the web
- The full **AAOIFI Standard 21** Sharia screen of every stock covered, plus a CSV attachment

## The team

| Role | What it does |
|---|---|
| Quant screen | Pulls prices and fundamentals for about 65 ADX/DFM stocks and scores every Sharia-compliant stock on three horizons |
| Sharia screen | AAOIFI Std. 21: business-activity filter, then debt < 30%, cash < 30% of market cap, and non-permissible income < 5% |
| ADX Equity Analyst | Reviews the top Abu Dhabi candidates and searches the web for the latest news (Claude) |
| DFM Equity Analyst | Does the same for Dubai (Claude) |
| Investment Committee | The Chief Investment Advisor and the Sharia Compliance Officer make the final picks (Claude) |

A safety rule in the code drops any pick that didn't pass our own Sharia screen, whatever the AI says.
Companies with mixed activities (conglomerates, supermarkets, exchange houses) are marked
**"Needs Sharia review"** and are never recommended until you or a scholar confirm them.

## One-time setup (about 10 minutes)

### 1. Gmail App Password
1. Turn on 2-Step Verification for the Gmail account that will **send** the report.
2. Go to <https://myaccount.google.com/apppasswords> and create an app password named "Hammor".
3. Copy the 16-character password.

### 2. Anthropic API key
Create a key at <https://console.anthropic.com/settings/keys>. The three AI calls cost roughly
**US$0.30–1.00 per report**; the web searches add about $0.01 each.

### 3. Add the secrets to GitHub
In this repository go to **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret | Value |
|---|---|
| `ANTHROPIC_API_KEY` | your Anthropic API key |
| `GMAIL_ADDRESS` | the Gmail address that sends the report |
| `GMAIL_APP_PASSWORD` | the 16-character app password |
| `REPORT_TO` | where to send the report (separate several addresses with commas) |

### 4. Test it
Go to **Actions → Hammor Co. daily report → Run workflow**. The email arrives within a few minutes.
Each run also saves the report (HTML + CSV) as a downloadable artifact.

After that it runs on its own every weekday. The job starts at 08:15, builds the report, and sends it at 09:00 UAE time.
> GitHub only runs scheduled jobs from the repository's **default branch**, and it pauses them
> after 60 days with no activity in the repository. If that happens, re-enable the job from the Actions tab.

## Customising

- **Add or remove stocks:** edit `hammor/universe.py`. Each company has a business-activity
  classification (`ok`, `islamic_fin`, `review`, `excluded`); review these yourself.
- **Scoring weights:** `hammor/analysis.py`
- **Sharia thresholds:** `hammor/sharia.py`
- **Advisor instructions:** `hammor/advisors.py`
- **Send time:** the `cron` line in `.github/workflows/daily-report.yml` and `--send-at`

## Run locally

```bash
pip install -r requirements.txt
python -m hammor.main --dry-run --force   # writes output/report.html, no email
python -m pytest -q                       # offline tests with simulated data
```

## Important limits

- Market data comes from Yahoo Finance: it is free and delayed, and fundamentals for UAE stocks are sometimes missing.
  A stock without debt or cash data is marked "Insufficient data" and is not recommended.
- Yahoo reports *total* debt and cash, without separating sukuk or Islamic deposits from
  interest-bearing ones, so the screen is deliberately conservative.
- The reports are not advice from an SCA-licensed adviser. Check prices and the Sharia status before you invest.
