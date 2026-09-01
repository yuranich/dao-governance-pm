"""
Export UK Parliament events to pm4py-compatible CSV for process mining.

Maps bill_id as case identifier and event_type as activity name.
Output follows pm4py standard column naming conventions, matching
the DAO export format in export_pm4py.py for direct comparison.

Usage:
    python export_uk_parliament_pm4py.py                         # All events
    python export_uk_parliament_pm4py.py --stages-only           # Stage transitions only
    python export_uk_parliament_pm4py.py -o custom.csv           # Custom output
"""

import argparse
import duckdb
from db import DB_PATH
from daogov.paths import event_log


DAO_SLUG = "uk_parliament"


def export_pm4py_csv(output_file: str = None,
                     stages_only: bool = False,
                     db_path: str = None):
    conn = duckdb.connect(db_path or DB_PATH)

    table_name = f"{DAO_SLUG}_events"
    output_file = output_file or str(event_log(DAO_SLUG))

    tables = [t[0] for t in conn.execute("SHOW TABLES").fetchall()]
    if table_name not in tables:
        print(f"Table {table_name} not found. Run extract_uk_parliament.py first.")
        conn.close()
        return

    source_filter = "AND source = 'uk_parliament_bills'" if stages_only else ""

    query = f"""
        SELECT
            proposal_id AS "case:concept:name",
            event_type AS "concept:name",
            timestamp AS "time:timestamp",
            source,
            voter AS "org:resource",
            voting_power,
            proposal_title AS "case:proposal_title",
            proposal_author AS "case:proposal_author"
        FROM {table_name}
        WHERE proposal_id IS NOT NULL
        {source_filter}
        ORDER BY timestamp
    """

    conn.execute(f"COPY ({query}) TO '{output_file}' (HEADER, DELIMITER ',')")

    count = conn.execute(f"SELECT COUNT(*) FROM ({query})").fetchone()[0]
    case_count = conn.execute(f"""
        SELECT COUNT(DISTINCT proposal_id)
        FROM {table_name}
        WHERE proposal_id IS NOT NULL {source_filter}
    """).fetchone()[0]

    print(f"Exported {count} events from {case_count} bills to {output_file}")

    # Stage distribution
    stage_dist = conn.execute(f"""
        SELECT event_type, COUNT(*) as cnt
        FROM {table_name}
        WHERE source = 'uk_parliament_bills'
        GROUP BY event_type
        ORDER BY cnt DESC
        LIMIT 15
    """).fetchall()

    if stage_dist:
        print("\nStage distribution (top 15):")
        for etype, cnt in stage_dist:
            print(f"  {etype}: {cnt}")

    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Export UK Parliament events to pm4py CSV"
    )
    parser.add_argument("-o", "--output", help="Output file path")
    parser.add_argument(
        "--stages-only", action="store_true",
        help="Export only stage transition events (no individual votes)"
    )
    parser.add_argument("--db", help=f"DuckDB file path (default: {DB_PATH})")

    args = parser.parse_args()
    export_pm4py_csv(args.output, args.stages_only, args.db)


if __name__ == "__main__":
    main()
