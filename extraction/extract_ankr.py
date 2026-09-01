#!/usr/bin/env python3
"""
CLI for extracting on-chain governance events using public RPCs.

Supports incremental extraction with auto-resume from last saved block.
Safe to interrupt and restart — already-extracted events are skipped.

Usage:
    python extract_ankr.py --dao aave
    python extract_ankr.py --dao aave --start-block 11400000
    python extract_ankr.py --dao aave --rpc https://eth.llamarpc.com

    # Parallel extraction (split block ranges across terminals):
    python extract_ankr.py --dao aave --start-block 11400000 --end-block 16000000
    python extract_ankr.py --dao aave --start-block 16000000 --end-block 20000000 --rpc https://1rpc.io/eth
    python extract_ankr.py --dao aave --start-block 20000000 --rpc https://ethereum-rpc.publicnode.com
"""

import argparse
import os
import sys
from typing import Optional

import duckdb

from dao_config import DAOS, get_dao_config, get_all_dao_names
from db import DB_PATH, get_connection, insert_events, create_dao_table, get_event_count
from daogov.paths import shard_db, shard_glob
from ankr_onchain_extractor import (
    extract_all_onchain_events,
    get_supported_chains,
    DEFAULT_BLOCK_RANGE,
)

SAVE_EVERY = 500  # Save to DB every N events


def get_resume_block(dao_slug: str, db_path: str = DB_PATH) -> Optional[int]:
    """Get the highest block_number already extracted for this DAO."""
    try:
        conn = duckdb.connect(db_path, read_only=True)
        result = conn.execute(f"""
            SELECT MAX(block_number) FROM {dao_slug}_events
            WHERE source = 'onchain' AND block_number IS NOT NULL
        """).fetchone()
        conn.close()
        if result and result[0]:
            return int(result[0])
    except Exception:
        pass
    return None


def get_db_for_worker(dao_slug: str, start_block: Optional[int], end_block: Optional[int]) -> str:
    """
    Return DB path for this worker. Main (no explicit range) uses dao_events.duckdb.
    Parallel workers with explicit ranges use a shard file to avoid DuckDB locking.
    """
    if start_block is not None and end_block is not None:
        return str(shard_db(dao_slug, start_block, end_block))
    return DB_PATH


def merge_shards(dao_slug: str):
    """Merge any shard files into the main DB, then delete them."""
    import glob
    shards = glob.glob(shard_glob(dao_slug))
    if not shards:
        print(f"No shards match {shard_glob(dao_slug)} - nothing to merge")
        return

    conn = get_connection()
    create_dao_table(conn, dao_slug)
    table = f"{dao_slug}_events"

    for shard_path in sorted(shards):
        print(f"Merging {shard_path}...")
        try:
            conn.execute(f"ATTACH '{shard_path}' AS shard (READ_ONLY)")
            before = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            conn.execute(f"""
                INSERT OR IGNORE INTO {table}
                SELECT * FROM shard.{table}
            """)
            after = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            conn.execute("DETACH shard")
            added = after - before
            print(f"  +{added:,} new events from {shard_path}")
            os.remove(shard_path)
        except Exception as e:
            print(f"  Error merging {shard_path}: {e}")
            try:
                conn.execute("DETACH shard")
            except Exception:
                pass

    total = get_event_count(conn, dao_slug, source='onchain')
    print(f"Merge complete. Total on-chain events: {total:,}")
    conn.close()


def extract_dao(
    dao_name: str,
    start_block: Optional[int] = None,
    end_block: Optional[int] = None,
    block_range: int = DEFAULT_BLOCK_RANGE,
    dry_run: bool = False,
    debug: bool = False,
    rpc_url: Optional[str] = None,
) -> int:
    """Extract on-chain events for a single DAO with incremental saving."""
    dao = get_dao_config(dao_name)
    if not dao:
        print(f"Unknown DAO: {dao_name}")
        print(f"Available DAOs: {', '.join(get_all_dao_names())}")
        return 0

    addresses = dao.get_all_addresses() if hasattr(dao, 'get_all_addresses') else []
    if not addresses and dao.governor_address:
        addresses = [dao.governor_address]
    if not addresses:
        print(f"No governor address for {dao.name}, skipping")
        return 0

    if dao.chain not in get_supported_chains():
        print(f"Unsupported chain {dao.chain} for {dao.name}")
        return 0

    # Auto-resume: find last extracted block if no explicit start
    if start_block is None:
        resume_block = get_resume_block(dao.slug)
        if resume_block:
            start_block = resume_block + 1
            print(f"Resuming from block {start_block:,} (last saved: {resume_block:,})")

    if dry_run:
        events_gen = extract_all_onchain_events(
            dao=dao, start_block=start_block, end_block=end_block,
            block_range=block_range, governance_only=True, debug=debug,
            rpc_url=rpc_url,
        )
        count = 0
        for event in events_gen:
            count += 1
            if count % 100 == 0:
                print(f"  Counted {count:,} events...")
        print(f"Dry run complete: {count:,} events would be extracted")
        return count

    db_path = get_db_for_worker(dao.slug, start_block, end_block)
    is_shard = db_path != DB_PATH
    if is_shard:
        print(f"  Writing to shard: {db_path} (run --merge after all workers finish)")

    conn = duckdb.connect(db_path)
    create_dao_table(conn, dao.slug)

    events_gen = extract_all_onchain_events(
        dao=dao, start_block=start_block, end_block=end_block,
        block_range=block_range, governance_only=True, debug=debug,
        rpc_url=rpc_url,
    )

    total_inserted = 0
    batch = []

    try:
        for event in events_gen:
            batch.append(event)
            if len(batch) >= SAVE_EVERY:
                inserted = insert_events(conn, dao.slug, iter(batch))
                total_inserted += inserted
                max_blk = max((e.get('block_number') or 0) for e in batch)
                print(f"  Saved {total_inserted:,} events (through block {max_blk:,})")
                batch = []

        if batch:
            inserted = insert_events(conn, dao.slug, iter(batch))
            total_inserted += inserted

    except KeyboardInterrupt:
        if batch:
            print(f"\n  Interrupted — saving {len(batch)} buffered events...")
            insert_events(conn, dao.slug, iter(batch))
            total_inserted += len(batch)
        print(f"  Saved {total_inserted:,} events total. Re-run to resume.")
    finally:
        total = get_event_count(conn, dao.slug, source='onchain')
        print(f"Total on-chain events for {dao.name}: {total:,}")
        conn.close()

    return total_inserted


def main():
    parser = argparse.ArgumentParser(
        description='Extract on-chain governance events using public RPCs.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Features:
    - Auto-resume from last saved block (safe to interrupt with Ctrl+C)
    - Incremental saving every %(save)d events
    - Custom RPC endpoint for parallel extraction

Examples:
    # Extract (auto-resumes if interrupted)
    python extract_ankr.py --dao aave

    # Parallel extraction across 3 terminals (each writes its own shard file):
    python extract_ankr.py --dao aave --start-block 11400000 --end-block 16000000
    python extract_ankr.py --dao aave --start-block 16000000 --end-block 20000000 --rpc https://1rpc.io/eth
    python extract_ankr.py --dao aave --start-block 20000000 --end-block 24600000 --rpc https://ethereum-rpc.publicnode.com

    # After all workers finish, merge shards into main DB:
    python extract_ankr.py --dao aave --merge
        """ % {'save': SAVE_EVERY},
    )

    parser.add_argument('--dao', type=str, help='DAO name (or "all")')
    parser.add_argument('--start-block', type=int, default=None, help='Starting block (default: auto-resume or chain default)')
    parser.add_argument('--end-block', type=int, default=None, help='Ending block (default: latest)')
    parser.add_argument('--block-range', type=int, default=DEFAULT_BLOCK_RANGE,
                        help=f'Blocks per request (default: {DEFAULT_BLOCK_RANGE})')
    parser.add_argument('--rpc', type=str, default=None,
                        help='Custom RPC endpoint URL (prepended to default list)')
    parser.add_argument('--dry-run', action='store_true', help='Count without saving')
    parser.add_argument('--merge', action='store_true',
                        help='Merge shard files from parallel workers into main DB')
    parser.add_argument('--debug', action='store_true', help='Print debug info')
    parser.add_argument('--list-daos', action='store_true', help='List DAOs and exit')

    args = parser.parse_args()

    if args.list_daos:
        print("Available DAOs:")
        print("-" * 60)
        for dao in DAOS:
            chain_ok = "+" if dao.chain in get_supported_chains() else "-"
            n_addr = len(dao.get_all_addresses()) if hasattr(dao, 'get_all_addresses') else (1 if dao.governor_address else 0)
            print(f"  {dao.name:<15} chain={dao.chain:<10} [{chain_ok}] contracts={n_addr}")
        return 0

    if not args.dao:
        parser.print_help()
        return 1

    if args.merge:
        dao = get_dao_config(args.dao)
        if dao:
            merge_shards(dao.slug)
        return 0

    if args.dao.lower() == 'all':
        for dao in DAOS:
            if dao.chain in get_supported_chains() and dao.governor_address:
                print()
                print("=" * 60)
                extract_dao(
                    dao.name,
                    start_block=args.start_block, end_block=args.end_block,
                    block_range=args.block_range, dry_run=args.dry_run,
                    debug=args.debug, rpc_url=args.rpc,
                )
    else:
        extract_dao(
            args.dao,
            start_block=args.start_block, end_block=args.end_block,
            block_range=args.block_range, dry_run=args.dry_run,
            debug=args.debug, rpc_url=args.rpc,
        )

    return 0


if __name__ == '__main__':
    sys.exit(main())
