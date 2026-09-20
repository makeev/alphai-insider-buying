#!/usr/bin/env python3
"""Screen recorded Form 4 purchases. Python 3.10+, standard library only."""

import argparse
import csv
import gzip
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


DEFAULT_TICKERS = (
    "NVDA AMD INTC ORCL CRM ADBE NKE LULU SBUX DIS PYPL SOFI "
    "HOOD JPM BAC C SCHW O CCI STAG AVGO AMZN GOOGL META TSLA"
).split()


def money(value):
    return None if value is None else Decimal(value)


def fetch(ticker, key):
    url = (
        "https://api.alphai.io/api/symbols/"
        + quote(ticker, safe="")
        + "/insider-trades/?page_size=1"
    )
    request = Request(url, headers={
        "Authorization": f"Bearer {key}",
        "User-Agent": "alphai-insider-buying-tutorial/0.1",
    })
    try:
        with urlopen(request, timeout=30) as response:
            return {
                "ticker": ticker,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "status": response.status,
                "remaining": response.headers.get("X-RateLimit-Remaining"),
                "body": json.load(response),
            }
    except HTTPError as error:
        retry = error.headers.get("Retry-After", "not supplied")
        raise SystemExit(f"{ticker}: HTTP {error.code}; Retry-After: {retry}") from None
    except (URLError, TimeoutError):
        raise SystemExit(f"{ticker}: request failed; no report generated") from None


def window_events(snapshot):
    start, end = snapshot["from_date"], snapshot["through_date"]
    unique = {}
    for response in snapshot["responses"]:
        # chart_events is independent of both page_size and the side filter.
        for event in response["body"]["chart_events"]:
            if not start <= event["transaction_date"] <= end:
                continue
            uid = event["news_uid"]
            if uid not in unique:
                unique[uid] = {**event, "tickers": []}
            unique[uid]["tickers"].append(response["ticker"])
    return list(unique.values())


def select(events, min_usd, exclude_plans=False, leadership_only=False):
    selected = []
    for event in events:
        if event["transaction_code"] != "P":
            continue
        amount = money(event["total_value_usd"])
        if amount is None or amount < min_usd:
            continue
        if exclude_plans and event["is_10b5_1"]:
            continue
        if leadership_only and not (event["is_officer"] or event["is_director"]):
            continue
        selected.append(event)
    return sorted(selected, key=lambda e: money(e["total_value_usd"]), reverse=True)


def role(event):
    labels = [name for flag, name in (
        ("is_officer", "officer"), ("is_director", "director"),
        ("is_ten_percent_owner", "10% owner"),
    ) if event[flag]]
    return ", ".join(labels) or "not reported"


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def write_report(snapshot, args):
    events = window_events(snapshot)
    buys = [e for e in events if e["transaction_code"] == "P"]
    selected = select(events, args.min_usd, args.exclude_plans, args.leadership_only)
    stats = {
        "window_events": len(events), "purchase_events": len(buys),
        "purchases_without_price": sum(e["total_value_usd"] is None for e in buys),
        "candidates": len(selected),
        "candidates_without_stake_pct": sum(e["stake_change_pct"] is None for e in selected),
    }
    columns = [
        "tickers", "insider_name", "role", "insider_title", "security_title",
        "ownership_form", "total_value_usd", "stake_change_pct", "is_10b5_1",
        "transaction_date", "filed_at", "tranche_count", "news_uid", "has_article",
    ]
    with (args.out / "candidates.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for event in selected:
            row = {field: event.get(field) for field in columns}
            row.update(tickers=",".join(event["tickers"]), role=role(event))
            writer.writerow(row)
    lines = [
        "# Insider purchase screen", "",
        f"Recorded at {snapshot['finished_at']}.", "",
        f"Transaction dates: {snapshot['from_date']} through {snapshot['through_date']} (inclusive).",
        f"Requested tickers: {', '.join(snapshot['tickers'])}.", "",
        f"Filters: code P; priced value >= ${args.min_usd:,.2f}; "
        f"exclude marked plans={args.exclude_plans}; officer/director only={args.leadership_only}.",
        "",
        *(f"- {name}: {value}" for name, value in stats.items()), "",
        "| Ticker | Reporting owner | Role | USD | Stake change | Plan marked | Trade date | Filed (UTC) | Tranches |",
        "| --- | --- | --- | ---: | ---: | --- | --- | --- | ---: |",
    ]
    for event in selected:
        pct = money(event["stake_change_pct"])
        values = [
            ",".join(event["tickers"]), event["insider_name"], role(event),
            f"${money(event['total_value_usd']):,.2f}",
            "unknown" if pct is None else f"{pct:+.1f}%",
            "yes" if event["is_10b5_1"] else "no",
            event["transaction_date"], event["filed_at"], event["tranche_count"],
        ]
        lines.append("| " + " | ".join(cell(v) for v in values) + " |")
    lines += [
        "", "Unknown percentages are retained. Unpriced purchases cannot pass the dollar filter.",
        "Values sum priced tranches and can be lower bounds. Read ownership details in the filing.",
        "This is a current snapshot of recorded events, not a point-in-time backtest.",
    ]
    (args.out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(stats))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tickers", nargs="*")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--min-usd", type=Decimal, default=Decimal("100000"))
    parser.add_argument("--exclude-plans", action="store_true")
    parser.add_argument("--leadership-only", action="store_true")
    parser.add_argument("--replay", type=Path, help="Re-screen a saved snapshot without API calls")
    parser.add_argument("--out", type=Path, required=True, help="New output directory")
    try:
        args = parser.parse_args()
    except InvalidOperation:
        parser.error("--min-usd must be a decimal number")
    if not 1 <= args.days <= 90:
        parser.error("--days must be between 1 and 90")
    if not args.min_usd.is_finite() or args.min_usd < 0:
        parser.error("--min-usd must be a finite non-negative amount")
    tickers = list(dict.fromkeys(t.upper() for t in (args.tickers or DEFAULT_TICKERS)))
    if any(not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,19}", t) for t in tickers):
        parser.error("invalid ticker")
    if args.replay and (args.tickers or args.days != 30):
        parser.error("replay uses the saved tickers and dates; omit tickers and --days")
    key = os.environ.get("ALPHAI_API_KEY")
    if not args.replay and not key:
        parser.error("set ALPHAI_API_KEY")
    args.out.mkdir(parents=True, exist_ok=False)
    if args.replay:
        opener = gzip.open if args.replay.suffix == ".gz" else open
        with opener(args.replay, "rt", encoding="utf-8") as stream:
            snapshot = json.load(stream)
        if not snapshot["complete"]:
            parser.error("snapshot is incomplete; no report generated")
    else:
        started = datetime.now(timezone.utc)
        snapshot = {
            "started_at": started.isoformat(), "complete": False,
            "from_date": (started.date() - timedelta(days=args.days - 1)).isoformat(),
            "through_date": started.date().isoformat(), "tickers": tickers, "responses": [],
        }
        for index, ticker in enumerate(tickers):
            if index:
                time.sleep(3.2)  # Pace every request, including the first pair.
            print(f"Fetching {ticker} ({index + 1}/{len(tickers)})", file=sys.stderr)
            snapshot["responses"].append(fetch(ticker, key))
            (args.out / "snapshot.json").write_text(json.dumps(snapshot, indent=2) + "\n")
        snapshot.update(complete=True, finished_at=datetime.now(timezone.utc).isoformat())
    (args.out / "snapshot.json").write_text(json.dumps(snapshot, indent=2) + "\n")
    write_report(snapshot, args)


if __name__ == "__main__":
    main()
