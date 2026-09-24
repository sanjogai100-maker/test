from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "dividends.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"

app = FastAPI(
    title="NEPSE Dividend Assistant API",
    version="0.1.0",
    description="Canonical dividend-event store for an AI assistant.",
)


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


@app.on_event("startup")
def startup() -> None:
    init_db()


class SourceEvidenceIn(BaseModel):
    source_name: str
    source_type: str = Field(pattern="^(PRIMARY|STRUCTURED_PROVIDER|AGGREGATOR|NEWS|OTHER)$")
    source_url: Optional[str] = None
    published_at: Optional[str] = None
    raw_excerpt: Optional[str] = None
    source_rank: int = Field(default=5, ge=1, le=10)


class DividendEventIn(BaseModel):
    symbol: str
    company_name: Optional[str] = None
    sector: Optional[str] = None
    fiscal_year: str
    bonus_percent: Optional[float] = Field(default=None, ge=0)
    cash_percent: Optional[float] = Field(default=None, ge=0)
    total_percent: Optional[float] = Field(default=None, ge=0)
    status: str = Field(
        pattern=(
            "^(RUMORED|PROPOSED|REGULATORY_APPROVED|AGM_ANNOUNCED|"
            "BOOK_CLOSE_ANNOUNCED|AGM_APPROVED|DISTRIBUTED|CANCELLED)$"
        )
    )
    announcement_date: Optional[str] = None
    agm_date: Optional[str] = None
    book_close_date: Optional[str] = None
    effective_date: Optional[str] = None
    notes: Optional[str] = None
    sources: list[SourceEvidenceIn] = []


def event_to_dict(row: sqlite3.Row, sources: list[dict]) -> dict:
    return {
        "id": row["id"],
        "symbol": row["symbol"],
        "company_name": row["company_name"],
        "sector": row["sector"],
        "fiscal_year": row["fiscal_year"],
        "bonus_percent": row["bonus_percent"],
        "cash_percent": row["cash_percent"],
        "total_percent": row["total_percent"],
        "status": row["status"],
        "announcement_date": row["announcement_date"],
        "agm_date": row["agm_date"],
        "book_close_date": row["book_close_date"],
        "effective_date": row["effective_date"],
        "notes": row["notes"],
        "sources": sources,
    }


def get_sources(conn: sqlite3.Connection, event_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT source_name, source_type, source_url, published_at,
               observed_at, raw_excerpt, source_rank
        FROM source_evidence
        WHERE dividend_event_id = ?
        ORDER BY source_rank ASC, observed_at DESC
        """,
        (event_id,),
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/dividends")
def upsert_dividend(payload: DividendEventIn) -> dict:
    symbol = payload.symbol.strip().upper()

    bonus = payload.bonus_percent
    cash = payload.cash_percent
    total = payload.total_percent
    if total is None and (bonus is not None or cash is not None):
        total = (bonus or 0) + (cash or 0)

    with connect() as conn:
        company = conn.execute(
            "SELECT id FROM companies WHERE symbol = ?",
            (symbol,),
        ).fetchone()

        if company is None:
            cur = conn.execute(
                "INSERT INTO companies(symbol, company_name, sector) VALUES (?, ?, ?)",
                (symbol, payload.company_name, payload.sector),
            )
            company_id = cur.lastrowid
        else:
            company_id = company["id"]
            conn.execute(
                """
                UPDATE companies
                SET company_name = COALESCE(?, company_name),
                    sector = COALESCE(?, sector)
                WHERE id = ?
                """,
                (payload.company_name, payload.sector, company_id),
            )

        conn.execute(
            """
            INSERT INTO dividend_events(
                company_id, fiscal_year, bonus_percent, cash_percent,
                total_percent, status, announcement_date, agm_date,
                book_close_date, effective_date, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company_id, fiscal_year) DO UPDATE SET
                bonus_percent = excluded.bonus_percent,
                cash_percent = excluded.cash_percent,
                total_percent = excluded.total_percent,
                status = excluded.status,
                announcement_date = COALESCE(excluded.announcement_date, dividend_events.announcement_date),
                agm_date = COALESCE(excluded.agm_date, dividend_events.agm_date),
                book_close_date = COALESCE(excluded.book_close_date, dividend_events.book_close_date),
                effective_date = COALESCE(excluded.effective_date, dividend_events.effective_date),
                notes = COALESCE(excluded.notes, dividend_events.notes),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                company_id,
                payload.fiscal_year,
                bonus,
                cash,
                total,
                payload.status,
                payload.announcement_date,
                payload.agm_date,
                payload.book_close_date,
                payload.effective_date,
                payload.notes,
            ),
        )

        event = conn.execute(
            """
            SELECT id FROM dividend_events
            WHERE company_id = ? AND fiscal_year = ?
            """,
            (company_id, payload.fiscal_year),
        ).fetchone()
        event_id = event["id"]

        for source in payload.sources:
            conn.execute(
                """
                INSERT INTO source_evidence(
                    dividend_event_id, source_name, source_type,
                    source_url, published_at, raw_excerpt, source_rank
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    source.source_name,
                    source.source_type,
                    source.source_url,
                    source.published_at,
                    source.raw_excerpt,
                    source.source_rank,
                ),
            )

        conn.commit()

    return {"ok": True, "symbol": symbol, "fiscal_year": payload.fiscal_year}


@app.get("/dividends/latest/{symbol}")
def latest_dividend(symbol: str) -> dict:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT de.*, c.symbol, c.company_name, c.sector
            FROM dividend_events de
            JOIN companies c ON c.id = de.company_id
            WHERE c.symbol = ?
            ORDER BY COALESCE(de.announcement_date, de.created_at) DESC
            LIMIT 1
            """,
            (symbol.upper(),),
        ).fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="No dividend event found")

        return event_to_dict(row, get_sources(conn, row["id"]))


@app.get("/dividends/history/{symbol}")
def dividend_history(symbol: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT de.*, c.symbol, c.company_name, c.sector
            FROM dividend_events de
            JOIN companies c ON c.id = de.company_id
            WHERE c.symbol = ?
            ORDER BY COALESCE(de.announcement_date, de.created_at) DESC
            """,
            (symbol.upper(),),
        ).fetchall()

        return [event_to_dict(r, get_sources(conn, r["id"])) for r in rows]


@app.get("/dividends/search")
def search_dividends(
    sector: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
) -> list[dict]:
    clauses = []
    params: list[str] = []

    if sector:
        clauses.append("c.sector = ?")
        params.append(sector)
    if status:
        clauses.append("de.status = ?")
        params.append(status)
    if start_date:
        clauses.append("de.announcement_date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("de.announcement_date <= ?")
        params.append(end_date)

    where = "WHERE " + " AND ".join(clauses) if clauses else ""

    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT de.*, c.symbol, c.company_name, c.sector
            FROM dividend_events de
            JOIN companies c ON c.id = de.company_id
            {where}
            ORDER BY COALESCE(de.announcement_date, de.created_at) DESC
            """,
            params,
        ).fetchall()

        return [event_to_dict(r, get_sources(conn, r["id"])) for r in rows]
