"""
DuckDB database layer for DAO event storage.
Manages per-DAO tables and batch inserts.
"""

import json
import duckdb
from typing import Iterator, Dict, Any, Optional
from datetime import datetime
import os

from daogov.paths import EVENTS_DB

# str(), not Path: several call sites compare db_path against DB_PATH with != ,
# and a Path/str comparison is always True.
DB_PATH = str(EVENTS_DB)
BATCH_SIZE = 10000


def get_connection() -> duckdb.DuckDBPyConnection:
    """Get DuckDB connection."""
    conn = duckdb.connect(DB_PATH)
    return conn


def create_dao_table(conn: duckdb.DuckDBPyConnection, dao_slug: str) -> None:
    """Create table for a DAO if it doesn't exist."""
    table_name = f"{dao_slug}_events"
    
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id VARCHAR PRIMARY KEY,
            source VARCHAR NOT NULL,
            event_type VARCHAR NOT NULL,
            timestamp TIMESTAMP,
            -- Proposal fields
            proposal_id VARCHAR,
            proposal_title VARCHAR,
            proposal_author VARCHAR,
            proposal_state VARCHAR,
            -- Vote fields
            voter VARCHAR,
            voting_power DOUBLE,
            choice JSON,
            -- On-chain fields
            tx_hash VARCHAR,
            block_number BIGINT,
            log_index BIGINT,
            contract_address VARCHAR,
            raw_data JSON
        )
    """)
    
    # Create indexes for common queries
    conn.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_{dao_slug}_timestamp 
        ON {table_name}(timestamp)
    """)
    
    conn.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_{dao_slug}_source 
        ON {table_name}(source)
    """)
    
    conn.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_{dao_slug}_event_type 
        ON {table_name}(event_type)
    """)


def insert_events(conn: duckdb.DuckDBPyConnection, dao_slug: str, events: Iterator[Dict[str, Any]]) -> int:
    """
    Insert events in batches.
    Returns total number of events inserted.
    """
    table_name = f"{dao_slug}_events"
    create_dao_table(conn, dao_slug)
    
    batch = []
    total_inserted = 0
    
    for event in events:
        batch.append(event)
        
        if len(batch) >= BATCH_SIZE:
            _insert_batch(conn, table_name, batch)
            total_inserted += len(batch)
            batch = []
    
    # Insert remaining events
    if batch:
        _insert_batch(conn, table_name, batch)
        total_inserted += len(batch)
    
    return total_inserted


JSON_COLUMNS = {'choice', 'raw_data'}


def _sanitize_json(val: Any) -> Optional[str]:
    """Ensure a value is a valid JSON string for DuckDB JSON columns."""
    if val is None:
        return None
    if isinstance(val, str):
        try:
            json.loads(val)
            return val
        except (json.JSONDecodeError, ValueError):
            return json.dumps(val)
    return json.dumps(val)


def _insert_batch(conn: duckdb.DuckDBPyConnection, table_name: str, batch: list) -> None:
    """Insert a batch of events. Falls back to row-by-row on errors."""
    if not batch:
        return
    
    columns = list(batch[0].keys())
    placeholders = ', '.join(['?' for _ in columns])
    columns_str = ', '.join(columns)
    
    values = []
    for event in batch:
        row = []
        for col in columns:
            val = event.get(col)
            if val is None:
                row.append(None)
            elif col in JSON_COLUMNS:
                row.append(_sanitize_json(val))
            else:
                row.append(val)
        values.append(tuple(row))
    
    sql = f"INSERT OR IGNORE INTO {table_name} ({columns_str}) VALUES ({placeholders})"
    try:
        conn.executemany(sql, values)
    except Exception as e:
        skipped = 0
        for row in values:
            try:
                conn.execute(sql, row)
            except Exception:
                skipped += 1
        if skipped:
            print(f"  Skipped {skipped}/{len(values)} malformed records in batch")


def get_extraction_progress(conn: duckdb.DuckDBPyConnection, dao_slug: str, source: str) -> Optional[datetime]:
    """
    Get the latest timestamp for a DAO and source.
    Returns None if no events exist.
    """
    table_name = f"{dao_slug}_events"
    
    try:
        result = conn.execute(f"""
            SELECT MAX(timestamp) as max_timestamp
            FROM {table_name}
            WHERE source = ?
        """, [source]).fetchone()
        
        if result and result[0]:
            return result[0]
        return None
    except Exception:
        # Table doesn't exist yet
        return None


def get_event_count(conn: duckdb.DuckDBPyConnection, dao_slug: str, source: Optional[str] = None) -> int:
    """Get total event count for a DAO, optionally filtered by source."""
    table_name = f"{dao_slug}_events"
    
    try:
        if source:
            result = conn.execute(f"""
                SELECT COUNT(*) FROM {table_name}
                WHERE source = ?
            """, [source]).fetchone()
        else:
            result = conn.execute(f"""
                SELECT COUNT(*) FROM {table_name}
            """).fetchone()
        
        return result[0] if result else 0
    except Exception:
        return 0

