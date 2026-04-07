#!/usr/bin/env python3
"""v0.2.3 → v0.3.0 schema migration — on conflict + abort"""

import asyncio
import app.config  # noqa: F401
from sqlalchemy import text
from app.db import engine


SQL = """
ALTER TABLE results
  ADD COLUMN error_details_json TEXT NOT NULL DEFAULT '[]';

CREATE TABLE IF NOT EXISTS results_clean (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id            TEXT NOT NULL,
    filename           TEXT NOT NULL,
    timestamp          TEXT NOT NULL,
    config_json        TEXT NOT NULL,
    summary_json       TEXT NOT NULL,
    percentiles_json   TEXT NOT NULL,
    errors_json        TEXT NOT NULL DEFAULT '{}',
    error_details_json TEXT NOT NULL DEFAULT '[]',
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(test_id, filename)
);
"""

DEDUP = """
DELETE FROM results
WHERE rowid NOT IN (
    SELECT MIN(rowid) FROM results GROUP BY test_id, filename
);
"""

MOVE = """
INSERT OR REPLACE INTO results_clean
    (test_id, filename, timestamp, config_json, summary_json,
     percentiles_json, errors_json, error_details_json, created_at)
SELECT test_id, filename, timestamp, config_json, summary_json,
       percentiles_json, errors_json, error_details_json, created_at
FROM results;
"""

FINALIZE = """
DROP TABLE results;
ALTER TABLE results_clean RENAME TO results;
CREATE INDEX IF NOT EXISTS idx_results_test_id ON results(test_id);
CREATE INDEX IF NOT EXISTS idx_results_filename ON results(filename);
"""


async def main():
    print("migration start")

    async with engine.begin() as conn:
        # idempotency check — error_details_json already present → skip
        cur = await conn.execute(text("PRAGMA table_info(results)"))
        cols = {row[1] for row in cur.fetchall()}
        if "error_details_json" in cols:
            print("column error_details_json exists — skip migration")
            return

        await conn.execute(text(SQL))
        await conn.execute(text(DEDUP))
        await conn.execute(text(MOVE))
        await conn.execute(text(FINALIZE))

    print("migration done")


if __name__ == "__main__":
    asyncio.run(main())
