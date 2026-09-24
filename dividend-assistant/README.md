# NEPSE Dividend Assistant — Prototype

This folder is the first working slice of a Nepal-market AI assistant.

It does **not train an AI model**. It creates a canonical dividend database that an AI assistant can query reliably.

## What exists now

```text
ShareHub dividends API
        |
        v
sharehub_sync.py
        |
        +--> raw/sharehub/*.json   (raw provenance snapshots)
        |
        v
SQLite canonical database
        |
        v
FastAPI
        |
        +--> /dividends/latest/{symbol}
        +--> /dividends/history/{symbol}
        +--> /dividends/search
        |
        v
AI assistant
```

The database separates the dividend event from the source evidence.

## Data model

### companies

Canonical company identity:

- symbol
- company name
- sector

### dividend_events

One dividend event per company + fiscal year:

- bonus %
- cash %
- total %
- lifecycle status
- announcement date
- AGM date
- book-close date
- effective date
- notes

Lifecycle status is deliberately conservative:

- UNKNOWN
- RUMORED
- PROPOSED
- REGULATORY_APPROVED
- AGM_ANNOUNCED
- BOOK_CLOSE_ANNOUNCED
- AGM_APPROVED
- DISTRIBUTED
- CANCELLED

### source_evidence

Every fact can retain multiple sources:

- source name
- source type
- URL
- publish date
- observation time
- raw excerpt
- source rank
- de-duplication fingerprint

## Run locally

Requires Python 3.11+.

```bash
cd dividend-assistant
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload
```

Open:

```text
http://127.0.0.1:8000/docs
```

FastAPI will provide an interactive API page.

## Add one event manually

Example **template only** — replace values with verified data:

```bash
curl -X POST http://127.0.0.1:8000/dividends \
  -H 'Content-Type: application/json' \
  -d '{
    "symbol": "DEMO",
    "company_name": "Demo Company",
    "fiscal_year": "081/82",
    "bonus_percent": 5,
    "cash_percent": 0.25,
    "total_percent": 5.25,
    "status": "PROPOSED",
    "announcement_date": "2026-01-01",
    "sources": [
      {
        "source_name": "Example primary notice",
        "source_type": "PRIMARY",
        "source_url": "https://example.com/notice",
        "source_rank": 1
      }
    ]
  }'
```

## Query it

Latest dividend:

```bash
curl http://127.0.0.1:8000/dividends/latest/DEMO
```

History:

```bash
curl http://127.0.0.1:8000/dividends/history/DEMO
```

Search:

```bash
curl 'http://127.0.0.1:8000/dividends/search?status=BOOK_CLOSE_ANNOUNCED'
```

## ShareHub connector

ShareHub documents a licensed JSON API for dividends and announcements.

Do **not** put credentials in source code or GitHub.

Set them in your shell:

```bash
export SHAREHUB_EMAIL='your-api-account@example.com'
export SHAREHUB_PASSWORD='your-password'
```

Then sync:

```bash
python sharehub_sync.py
```

Or only one company:

```bash
python sharehub_sync.py --symbol NABIL
```

The ShareHub account must have the required API service enabled and the machine/server IP must be allowed by the provider.

## Why raw snapshots are saved

Normalized data is convenient, but we also want provenance. Each ShareHub fetch is saved under:

```text
raw/sharehub/
```

This allows future verification of exactly what the provider returned at ingestion time.

Do not commit credentials. Decide separately whether raw provider payloads should be committed; production systems often archive them in private object storage instead.

## Next implementation steps

1. Run the ShareHub sync with a licensed API account and inspect the actual response field names.
2. Lock the ShareHub field mapping to the verified response schema.
3. Add an official/primary announcement adapter.
4. Add ShareSansar/MeroLagani/NepseAlpha as secondary evidence sources where access terms permit.
5. Add conflict/reconciliation logic.
6. Expose these read endpoints as AI tools.
7. Add scheduled detection of *new* dividend events and notifications.

See `AI_ASSISTANT_CONTRACT.md` for the rules the assistant should follow.
