# Insider-buying screener

A Python script for screening recorded SEC Form 4 purchases through the [AlphAI API](https://alphai.io/developers?utm_source=github&utm_medium=readme&utm_campaign=insider_buying). It keeps the purchase value, holding-change percentage, reporting role and filing date together in a Markdown report and CSV.

Python 3.10 or newer. Standard library only. No install step.

## Reproduce the article's results without a key

```bash
git clone https://github.com/makeev/alphai-insider-buying.git
cd alphai-insider-buying
python3 insider_buying.py \
  --replay samples/2026-09-18/examples/snapshot.json.gz \
  --out out/saved-example
```

Open `out/saved-example/report.md` or `candidates.csv`. The captured window is August 20 through September 18, 2026, inclusive. It contains 36 events, including 34 purchases. Fourteen purchase events meet the default $100,000 threshold; two have an unknown holding-change percentage.

Each output directory must be new. Change `--out` for another run.

## Screen a live watchlist

Create a [free API key](https://alphai.io/account/api-keys?utm_source=github&utm_medium=readme&utm_campaign=insider_buying) and set `ALPHAI_API_KEY` in your environment. The script does not load `.env` files.

```bash
python3 insider_buying.py TENX XBP DLPN ALP INBX RVSB MNR \
  --days 30 --min-usd 100000 --out out/live
```

Omit the tickers to use the script's default 25-name watchlist. A live run ends on today's UTC date, so it will not reproduce the historical sample. `--days` accepts 1–90.

One request per ticker fetches `/api/symbols/{ticker}/insider-trades/?page_size=1`. The first page includes `chart_events`, the recorded trailing twelve months independently of pagination and the `side` filter. The script screens that array locally and ignores the overlapping `events` array.

The Free tier allows 20 requests/minute and 100/day as checked September 20, 2026. Calls are spaced by 3.2 seconds. Other work on the account shares the quota. HTTP errors stop the run and print the status and `Retry-After`; successful responses already received stay in an incomplete snapshot, with no finished report. There are no automatic retries.

## Change filters offline

```bash
python3 insider_buying.py \
  --replay samples/2026-09-18/examples/snapshot.json.gz \
  --leadership-only --exclude-plans --out out/leadership

python3 insider_buying.py \
  --replay samples/2026-09-18/examples/snapshot.json.gz \
  --min-usd 0 --out out/all-purchases
```

These produce 9 and 34 candidates respectively. Replay accepts `.json` and `.json.gz`, uses saved tickers and dates, and makes no network requests. It rejects incomplete snapshots.

`--leadership-only` keeps officers or directors, including those who are also 10% owners. `--exclude-plans` removes marked 10b5-1 events. A false plan flag does not establish a buyer's motive.

## What the numbers mean

- Code `P` includes private purchases as well as purchases on an exchange. This is not an open-market-only screen. See the [SEC's transaction-code guide](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-69).
- The threshold applies to one API event: a filing's transaction-code and ownership-form group. ALP's saved filing has $67,856.30 direct and $41,131.07 indirect groups; neither passes a $100,000 event threshold.
- Unknown percentages remain unknown. Unknown dollar values cannot pass the dollar threshold. Values sum priced tranches and can be lower bounds.
- Holding change describes the reported holding associated with the transaction, not personal wealth or necessarily the owner's entire stake.
- `news_uid` deduplicates events exposed through multiple share classes. The script does not reconcile amendments or purchases reported across multiple filings.
- The date filter uses `transaction_date`. A grouped event uses its last transaction date. The CSV retains `filed_at`, but these current snapshots do not reconstruct what was knowable on an earlier day.

## Saved evidence

All samples were captured September 18, 2026. The seven example tickers were selected from a feed that already showed purchases; their hit rate is not a market-wide estimate.

| Run | Recorded events in window | Purchase events | Candidates |
| --- | ---: | ---: | ---: |
| [Default 25 tickers](samples/2026-09-18/baseline/report.md) | 50 | 0 | 0 |
| [Seven example tickers](samples/2026-09-18/examples/report.md) | 36 | 34 | 14 |
| [Officer/director, plans excluded](samples/2026-09-18/leadership/report.md) | 36 | 34 | 9 |
| [All priced purchases](samples/2026-09-18/all-purchases/report.md) | 36 | 34 | 34 |

Each directory includes the original response snapshot, CSV and report. Snapshots retain retrieval times and the remaining-quota header, but no credentials or request headers. `discovery.json.gz` holds the three feed pages used to select the example tickers. [SEC XML sources and their URL manifest](samples/2026-09-18/filings) support the TENX, INBX, XBP and ALP examples.

## Check the code and saved results

```bash
python3 -m unittest discover -s tests -v
```

Tests replay every saved report and compare the output byte for byte, check filtering and date boundaries, and independently calculate the four example filings from SEC XML. CI runs them on Python 3.10 and 3.13.

Read the [full DEV walkthrough](https://dev.to/makeev/build-an-insider-buying-screener-with-python-and-sec-form-4-data-4eg1), published September 20, 2026 in the series *Market research scripts with AlphAI*. Related examples: [earnings week](https://github.com/makeev/alphai-earnings-week) and the [Polymarket walkthrough](https://dev.to/makeev/build-a-polymarket-research-brief-with-python-and-alphai-1hj6).

Code is [MIT licensed](LICENSE). Saved API responses and SEC filings are source evidence; the code license does not grant rights to third-party material.
