from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app import DividendEventIn, SourceEvidenceIn, init_db, upsert_dividend

BASE_URL = "https://sharehubnepal.com"
LOGIN_URL = BASE_URL + "/account/api/v1/auth/login/email"
DIVIDENDS_URL = BASE_URL + "/data/api/v1/nepse-data/dividends"
RAW_DIR = Path(__file__).resolve().parent / "raw" / "sharehub"


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: Optional[dict[str, Any]] = None,
    token: Optional[str] = None,
) -> dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "nepse-dividend-assistant/0.1",
    }
    body = None

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ShareHub HTTP {exc.code}: {detail}") from exc


def login() -> str:
    email = os.environ.get("SHAREHUB_EMAIL")
    password = os.environ.get("SHAREHUB_PASSWORD")

    if not email or not password:
        raise RuntimeError(
            "Set SHAREHUB_EMAIL and SHAREHUB_PASSWORD in your environment. "
            "Do not commit credentials to GitHub."
        )

    response = request_json(
        LOGIN_URL,
        method="POST",
        payload={
            "email": email,
            "password": password,
            "useOnCookies": False,
        },
    )

    token = ((response.get("data") or {}).get("accessToken"))
    if not token:
        raise RuntimeError(f"ShareHub login did not return accessToken: {response}")

    return token


def canonical_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def pick(row: dict[str, Any], *names: str) -> Any:
    indexed = {canonical_key(str(k)): v for k, v in row.items()}
    for name in names:
        key = canonical_key(name)
        if key in indexed:
            return indexed[key]
    return None


def as_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace(",", "").replace("%", "")
    try:
        return float(text)
    except ValueError:
        return None


def infer_status(row: dict[str, Any]) -> str:
    # We deliberately avoid guessing approval/distribution status.
    # Only explicit lifecycle dates are used to advance the status.
    if pick(row, "bookClosureDate", "bookCloseDate", "bookClosure"):
        return "BOOK_CLOSE_ANNOUNCED"
    if pick(row, "agmDate", "annualGeneralMeetingDate"):
        return "AGM_ANNOUNCED"
    return "UNKNOWN"


def normalize(row: dict[str, Any], source_url: str) -> DividendEventIn:
    symbol = pick(row, "symbol", "stockSymbol", "securitySymbol")
    fiscal_year = pick(row, "fiscalYear", "fiscal_year", "year")

    if not symbol or not fiscal_year:
        raise ValueError(
            "Dividend row is missing symbol or fiscal year; "
            f"available keys={sorted(row.keys())}"
        )

    bonus = as_float(
        pick(
            row,
            "bonus",
            "bonusPercent",
            "bonusPercentage",
            "bonusDividend",
            "bonusShare",
        )
    )
    cash = as_float(
        pick(
            row,
            "cash",
            "cashPercent",
            "cashPercentage",
            "cashDividend",
        )
    )
    total = as_float(
        pick(
            row,
            "total",
            "totalPercent",
            "totalPercentage",
            "totalDividend",
        )
    )

    if total is None and (bonus is not None or cash is not None):
        total = (bonus or 0.0) + (cash or 0.0)

    raw_excerpt = json.dumps(row, ensure_ascii=False, sort_keys=True)
    if len(raw_excerpt) > 4000:
        raw_excerpt = raw_excerpt[:3997] + "..."

    return DividendEventIn(
        symbol=str(symbol).strip().upper(),
        company_name=pick(row, "companyName", "company", "name"),
        sector=pick(row, "sectorName", "sector"),
        fiscal_year=str(fiscal_year),
        bonus_percent=bonus,
        cash_percent=cash,
        total_percent=total,
        status=infer_status(row),
        announcement_date=pick(
            row,
            "announcementDate",
            "announcedDate",
            "declaredDate",
        ),
        agm_date=pick(row, "agmDate", "annualGeneralMeetingDate"),
        book_close_date=pick(
            row,
            "bookClosureDate",
            "bookCloseDate",
            "bookClosure",
        ),
        notes="Imported from ShareHub dividends API. Lifecycle status is conservative.",
        sources=[
            SourceEvidenceIn(
                source_name="ShareHub Nepal",
                source_type="STRUCTURED_PROVIDER",
                source_url=source_url,
                published_at=pick(
                    row,
                    "announcementDate",
                    "announcedDate",
                    "declaredDate",
                ),
                raw_excerpt=raw_excerpt,
                source_rank=2,
            )
        ],
    )


def save_raw(payload: dict[str, Any], page: int) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RAW_DIR / f"{stamp}_page_{page}.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def fetch_page(
    token: str,
    *,
    page: int,
    size: int,
    symbol: Optional[str],
    fiscal_year: Optional[str],
) -> tuple[dict[str, Any], str]:
    params: dict[str, Any] = {
        "Page": page,
        "Size": size,
        "ListedStocksOnly": "true",
    }
    if symbol:
        params["Symbol"] = symbol.upper()
    if fiscal_year:
        params["FiscalYear"] = fiscal_year

    url = DIVIDENDS_URL + "?" + urllib.parse.urlencode(params)
    return request_json(url, token=token), url


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync ShareHub dividend records into the local canonical database."
    )
    parser.add_argument("--symbol", help="Optional NEPSE symbol, e.g. NABIL")
    parser.add_argument("--fiscal-year", help="Optional ShareHub fiscal year, e.g. 081/82")
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=50)
    args = parser.parse_args()

    init_db()
    token = login()

    imported = 0
    skipped = 0

    for page in range(1, args.max_pages + 1):
        response, source_url = fetch_page(
            token,
            page=page,
            size=args.page_size,
            symbol=args.symbol,
            fiscal_year=args.fiscal_year,
        )
        raw_path = save_raw(response, page)

        data = response.get("data") or {}
        rows = data.get("content")
        if rows is None and isinstance(data, list):
            rows = data
        if rows is None:
            rows = []

        print(f"page={page} rows={len(rows)} raw={raw_path}")

        for row in rows:
            try:
                event = normalize(row, source_url)
                upsert_dividend(event)
                imported += 1
            except Exception as exc:
                skipped += 1
                print(f"SKIP row={row!r} error={exc}", file=sys.stderr)

        total_pages = data.get("totalPages") if isinstance(data, dict) else None
        if not rows:
            break
        if total_pages is not None and page >= int(total_pages):
            break
        if len(rows) < args.page_size:
            break

    print(f"done imported={imported} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
