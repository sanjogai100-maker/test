# AI Assistant Contract

The AI assistant is a **reader and explainer**, not the source of dividend facts.

## Canonical tools

The assistant should use these API operations:

- `GET /dividends/latest/{symbol}` — latest known dividend event for a company.
- `GET /dividends/history/{symbol}` — dividend history for a company.
- `GET /dividends/search` — filter by sector, lifecycle status, and announcement date.
- `POST /dividends` — ingestion/admin operation, not a normal user-facing read tool.

## Answering rules

1. Never invent a dividend percentage, fiscal year, book-close date, AGM date, or lifecycle status.
2. Treat `UNKNOWN` literally. Do not upgrade it to proposed/approved/distributed without evidence.
3. Distinguish:
   - bonus dividend,
   - cash dividend,
   - total dividend,
   - proposal/announcement,
   - book-close announcement,
   - AGM approval,
   - actual distribution/listing.
4. Prefer primary evidence when it is available.
5. If multiple sources disagree, state the disagreement instead of silently choosing a value.
6. Include the fiscal year because the same company has many dividend events.
7. When answering "latest", use the event date stored in the database, not model memory.
8. The source list is provenance. Surface it when the user asks "where did this come from?" or when facts conflict.

## Example questions

- Has NABIL announced a dividend?
- What is NABIL's latest known dividend?
- Show NABIL dividend history.
- Which companies have a book-close announced?
- Which commercial banks have a dividend event in a date range?
- Which records are still UNKNOWN and need verification?

## Example answer shape

```text
NABIL — FY <fiscal year>

Bonus: <x>%
Cash: <y>%
Total: <z>%
Status: <status>
Announcement date: <date or not recorded>
Book close: <date or not recorded>
AGM: <date or not recorded>

Evidence:
- <source 1>
- <source 2>

Note: <only if there is uncertainty/conflict>
```

The assistant may explain the record in natural language, but it must not replace the canonical values with its own inference.
