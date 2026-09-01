"""
Extract UK Parliament bill lifecycle and voting events into DuckDB.

Downloads data from the official Bills API and Commons Votes API,
normalizes it to the DAO event schema, and stores in DuckDB for
process mining comparison with DAO governance.

Usage:
    python extract_uk_parliament.py                        # All bills, stages only
    python extract_uk_parliament.py --votes                # Include individual MP votes
    python extract_uk_parliament.py --session 39           # Specific session only
    python extract_uk_parliament.py --votes --session 39   # Session + votes
"""

import argparse
import duckdb
from db import DB_PATH, create_dao_table, insert_events, get_event_count
from uk_parliament_extractor import extract_all


DAO_SLUG = "uk_parliament"


def main():
    parser = argparse.ArgumentParser(
        description="Extract UK Parliament bill events into DuckDB"
    )
    parser.add_argument(
        "--votes", action="store_true",
        help="Include individual MP vote events (slow: ~500 MPs per division)"
    )
    parser.add_argument(
        "--session", type=int, default=None,
        help="Parliament session ID to filter (e.g. 39 for 2024-25)"
    )
    parser.add_argument(
        "--db", default=None,
        help=f"DuckDB file path (default: {DB_PATH})"
    )
    args = parser.parse_args()

    db_path = args.db or DB_PATH
    conn = duckdb.connect(db_path)
    create_dao_table(conn, DAO_SLUG)

    existing = get_event_count(conn, DAO_SLUG)
    print(f"Existing events in {DAO_SLUG}_events: {existing}")

    events = extract_all(session_id=args.session, include_votes=args.votes)
    inserted = insert_events(conn, DAO_SLUG, events)

    total = get_event_count(conn, DAO_SLUG)
    sources = conn.execute(f"""
        SELECT source, event_type, COUNT(*) as cnt
        FROM {DAO_SLUG}_events
        GROUP BY source, event_type
        ORDER BY source, cnt DESC
    """).fetchall()

    print(f"\nInserted {inserted} new events (total: {total})")
    print("\nBreakdown:")
    for source, etype, cnt in sources:
        print(f"  {source} / {etype}: {cnt}")

    cases = conn.execute(f"""
        SELECT COUNT(DISTINCT proposal_id)
        FROM {DAO_SLUG}_events
    """).fetchone()[0]
    print(f"\nTotal cases (bills): {cases}")

    conn.close()


if __name__ == "__main__":
    main()
