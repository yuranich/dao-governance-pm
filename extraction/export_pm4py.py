"""
Export DAO events to pm4py-compatible CSV format for process mining.

Maps proposal_id as case identifier and event_type as activity name.
Output follows pm4py standard column naming conventions.

Usage:
    python export_pm4py.py ens                    # Export all events
    python export_pm4py.py ens -o custom.csv      # Custom output file
"""

import argparse
import duckdb
from db import DB_PATH
from daogov.paths import event_log


def export_pm4py_csv(dao_slug: str, output_file: str = None, db_path: str = None):
    """
    Export DAO events to pm4py-compatible CSV format.
    
    Column mappings:
    - proposal_id -> case:concept:name (case identifier)
    - event_type -> concept:name (activity)
    - timestamp -> time:timestamp
    - voter -> org:resource (resource/actor)
    - proposal_title -> case:proposal_title (case-level attribute)
    - proposal_author -> case:proposal_author (case-level attribute)
    """
    conn = duckdb.connect(db_path or DB_PATH)
    
    table_name = f"{dao_slug}_events"
    output_file = output_file or str(event_log(dao_slug))
    
    # Check if table exists
    tables = conn.execute("SHOW TABLES").fetchall()
    table_names = [t[0] for t in tables]
    
    if table_name not in table_names:
        print(f"Table {table_name} not found. Available tables:")
        for t in table_names:
            print(f"  - {t}")
        conn.close()
        return
    
    # Build query with pm4py column mappings
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
        ORDER BY timestamp
    """
    
    # Export to CSV
    conn.execute(f"COPY ({query}) TO '{output_file}' (HEADER, DELIMITER ',')")
    
    # Get row count and statistics
    count = conn.execute(f"SELECT COUNT(*) FROM ({query})").fetchone()[0]
    case_count = conn.execute(f"SELECT COUNT(DISTINCT proposal_id) FROM {table_name} WHERE proposal_id IS NOT NULL").fetchone()[0]
    
    print(f"Exported {count} events from {case_count} cases to {output_file}")
    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description='Export DAO events to pm4py-compatible CSV format'
    )
    parser.add_argument('dao', help='DAO slug (e.g., ens, arbitrum)')
    parser.add_argument('-o', '--output', help='Output file path (default: {dao}_pm4py.csv)')
    parser.add_argument('--db', help='DuckDB file path (default: dao_events.duckdb)')
    
    args = parser.parse_args()
    export_pm4py_csv(args.dao, args.output, db_path=args.db)


if __name__ == '__main__':
    main()

