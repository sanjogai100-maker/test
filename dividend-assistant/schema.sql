PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL UNIQUE,
    company_name TEXT,
    sector TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dividend_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    fiscal_year TEXT NOT NULL,
    bonus_percent REAL,
    cash_percent REAL,
    total_percent REAL,
    status TEXT NOT NULL CHECK (status IN (
        'RUMORED',
        'PROPOSED',
        'REGULATORY_APPROVED',
        'AGM_ANNOUNCED',
        'BOOK_CLOSE_ANNOUNCED',
        'AGM_APPROVED',
        'DISTRIBUTED',
        'CANCELLED'
    )),
    announcement_date TEXT,
    agm_date TEXT,
    book_close_date TEXT,
    effective_date TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies(id),
    UNIQUE(company_id, fiscal_year)
);

CREATE TABLE IF NOT EXISTS source_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dividend_event_id INTEGER NOT NULL,
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN (
        'PRIMARY',
        'STRUCTURED_PROVIDER',
        'AGGREGATOR',
        'NEWS',
        'OTHER'
    )),
    source_url TEXT,
    published_at TEXT,
    observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_excerpt TEXT,
    source_rank INTEGER NOT NULL DEFAULT 5,
    FOREIGN KEY (dividend_event_id) REFERENCES dividend_events(id)
);

CREATE INDEX IF NOT EXISTS idx_dividend_company
ON dividend_events(company_id);

CREATE INDEX IF NOT EXISTS idx_dividend_announcement_date
ON dividend_events(announcement_date);

CREATE INDEX IF NOT EXISTS idx_source_event
ON source_evidence(dividend_event_id);
