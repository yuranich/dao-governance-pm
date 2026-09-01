"""
Build a DuckDB with unified case IDs linking onchain and offchain events.

Matching strategy (no temporal window restriction):
1. Tally direct snapshot links (snapshotURL)
2. Proposal prefix number matching (EP for ENS, AIP for Aave, etc.)
3. Global title similarity for remaining proposals

Usage:
    python build_linked_db.py aave                  # Build linked DB
    python build_linked_db.py aave --dry-run        # Show matches without writing
    python build_linked_db.py ens --dry-run         # ENS still works
"""

import argparse
import csv
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional

import duckdb

from dao_config import get_dao_by_slug, DAOS
from db import DB_PATH
from daogov.paths import mapping, linked_db, event_log

# DAO-specific proposal prefix patterns for "Execute {PREFIX}{N}" matching
DAO_PREFIXES = {
    'ens': 'EP',
    'aave': 'AIP',
    'arbitrum': 'AIP',
    'compound': 'CIP',
}


@dataclass
class ProposalInfo:
    proposal_id: str
    source: str
    title: Optional[str]
    ep_numbers: list[str]
    event_count: int


def extract_proposal_numbers(title: str, prefix: str = 'EP') -> list[str]:
    """Extract all proposal numbers from a title. Handles '{PREFIX}8, {PREFIX}9 and {PREFIX}10' patterns."""
    if not title:
        return []
    pattern = rf'{re.escape(prefix)}\s*(\d+(?:\.\d+)*)'
    matches = re.findall(pattern, title, re.IGNORECASE)
    return matches


def normalize_title(title: str, prefix: str = 'EP') -> str:
    if not title:
        return ""
    prefix_pattern = rf'\[?{re.escape(prefix)}\s*\d+\.?\d*\.?\d*\]?\s*[-:]?\s*'
    normalized = re.sub(prefix_pattern, '', title, flags=re.IGNORECASE)
    normalized = re.sub(r'\[(Social|Executable|Draft|Corrected|Temp Check|ARFC|Final)\]\s*', '', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'^#\s*', '', normalized)
    execute_pattern = rf'^Execute\s+{re.escape(prefix)}\d+.*'
    normalized = re.sub(execute_pattern, '', normalized, flags=re.IGNORECASE)
    normalized = ' '.join(normalized.split())
    return normalized.lower().strip()


def title_similarity(t1: str, t2: str, prefix: str = 'EP') -> float:
    n1, n2 = normalize_title(t1, prefix), normalize_title(t2, prefix)
    if not n1 or not n2:
        return 0.0
    return SequenceMatcher(None, n1, n2).ratio()


def load_tally(dao_slug: str) -> dict[str, dict]:
    tally_file = str(mapping(dao_slug, "tally"))
    if not os.path.exists(tally_file):
        print(f"Warning: {tally_file} not found. Run fetch_tally.py {dao_slug} first.")
        return {}
    tally = {}
    with open(tally_file) as f:
        for row in csv.DictReader(f):
            oid = row.get('onchain_id', '').strip()
            if oid:
                tally[oid] = {
                    'title': row.get('title', '').strip() or None,
                    'discourse_url': row.get('discourse_url', '').strip() or None,
                    'snapshot_url': row.get('snapshot_url', '').strip() or None,
                    'snapshot_id': row.get('snapshot_id', '').strip() or None,
                }
    return tally


def load_proposals(conn: duckdb.DuckDBPyConnection, tally: dict, dao_slug: str, prefix: str) -> tuple[list[ProposalInfo], list[ProposalInfo]]:
    table = f"{dao_slug}_events"

    snap_rows = conn.execute(f"""
        SELECT proposal_id, MAX(proposal_title), COUNT(*)
        FROM {table} WHERE source = 'snapshot'
        GROUP BY proposal_id
    """).fetchall()

    onchain_rows = conn.execute(f"""
        SELECT proposal_id, COUNT(*)
        FROM {table} WHERE source = 'onchain'
        GROUP BY proposal_id
    """).fetchall()

    snapshots = []
    for pid, title, cnt in snap_rows:
        snapshots.append(ProposalInfo(
            proposal_id=pid,
            source='snapshot',
            title=title,
            ep_numbers=extract_proposal_numbers(title, prefix),
            event_count=cnt,
        ))

    onchains = []
    for pid, cnt in onchain_rows:
        t = tally.get(pid, {})
        title = t.get('title')
        onchains.append(ProposalInfo(
            proposal_id=pid,
            source='onchain',
            title=title,
            ep_numbers=extract_proposal_numbers(title, prefix),
            event_count=cnt,
        ))

    return snapshots, onchains


def create_unified_id(title: Optional[str], proposal_id: str, prefix: str = 'EP') -> str:
    if not title:
        return f"case_{proposal_id[:16]}"
    pattern = rf'{re.escape(prefix)}\s*(\d+\.?\d*\.?\d*)'
    num_match = re.search(pattern, title, re.IGNORECASE)
    num = num_match.group(1) if num_match else None
    normalized = normalize_title(title, prefix)
    words = normalized.split()[:5]
    topic = '-'.join(w for w in words if len(w) > 2)[:30]
    if num:
        return f"{prefix}{num}-{topic}" if topic else f"{prefix}{num}"
    return f"case-{topic}" if topic else f"case_{proposal_id[:16]}"


def get_proposal_timestamps(conn: duckdb.DuckDBPyConnection, dao_slug: str) -> dict[str, tuple]:
    """Get (min_timestamp, max_timestamp) per proposal_id."""
    rows = conn.execute(f"""
        SELECT proposal_id, MIN(timestamp), MAX(timestamp)
        FROM {dao_slug}_events
        GROUP BY proposal_id
    """).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows if r[0]}


def is_execute_pattern(title: str, prefix: str = 'EP') -> list[str]:
    """
    Detect 'Execute {PREFIX}{N}' patterns that explicitly reference snapshot proposals.
    Returns list of proposal numbers referenced.
    E.g. '# Execute EP8, EP9 and EP10' -> ['8', '9', '10']
    """
    if not title:
        return []
    pattern = rf'^#?\s*Execute\s+{re.escape(prefix)}'
    m = re.match(pattern, title, re.IGNORECASE)
    if m:
        num_pattern = rf'{re.escape(prefix)}(\d+)'
        return re.findall(num_pattern, title, re.IGNORECASE)
    return []


def build_mapping(
    snapshots: list[ProposalInfo],
    onchains: list[ProposalInfo],
    tally: dict,
    conn: duckdb.DuckDBPyConnection,
    dao_slug: str,
    prefix: str = 'EP',
) -> dict[str, str]:
    """
    Build proposal_id -> unified_case_id mapping.

    Strategy:
    1. Tally direct snapshot links (snapshotURL field)
    2. "Execute {PREFIX}{N}" onchain titles → snapshot [{PREFIX}{N}] proposals
    3. Temporal proximity (90 days) + title similarity to pick best match
    """
    snap_by_id = {s.proposal_id: s for s in snapshots}
    onchain_by_id = {o.proposal_id: o for o in onchains}
    timestamps = get_proposal_timestamps(conn, dao_slug)

    linked: list[tuple[str, list[str], str]] = []  # (onchain_id, [snap_ids], reason)
    used_onchain: set[str] = set()
    used_snap: set[str] = set()

    # Phase 1: Tally direct snapshot links
    for onchain in onchains:
        t = tally.get(onchain.proposal_id, {})
        sid = t.get('snapshot_id')
        if sid and sid in snap_by_id:
            linked.append((onchain.proposal_id, [sid], 'tally_link'))
            used_onchain.add(onchain.proposal_id)
            used_snap.add(sid)

    # Phase 2: "Execute {PREFIX}{N}" pattern matching
    snap_by_num: dict[str, list[ProposalInfo]] = defaultdict(list)
    for s in snapshots:
        for num in s.ep_numbers:
            if '.' not in num:
                snap_by_num[num].append(s)

    for onchain in onchains:
        if onchain.proposal_id in used_onchain:
            continue
        exec_eps = is_execute_pattern(onchain.title, prefix)
        if not exec_eps:
            continue
        matched_snaps = []
        for ep in exec_eps:
            if ep in snap_by_num:
                for snap in snap_by_num[ep]:
                    if snap.proposal_id not in used_snap:
                        matched_snaps.append(snap.proposal_id)
                        used_snap.add(snap.proposal_id)
        if matched_snaps:
            linked.append((onchain.proposal_id, matched_snaps, 'execute_ep'))
            used_onchain.add(onchain.proposal_id)

    # Phase 3: Temporal + title similarity (90-day window)
    for onchain in onchains:
        if onchain.proposal_id in used_onchain:
            continue
        if not onchain.title:
            continue

        oc_ts = timestamps.get(onchain.proposal_id)
        if not oc_ts or not oc_ts[0]:
            continue
        oc_start = oc_ts[0]

        candidates = []
        for snap in snapshots:
            if snap.proposal_id in used_snap:
                continue
            s_ts = timestamps.get(snap.proposal_id)
            if not s_ts or not s_ts[1]:
                continue
            s_end = s_ts[1]
            gap_days = (oc_start - s_end).days
            if -5 <= gap_days <= 90:
                sim = title_similarity(onchain.title, snap.title, prefix) if snap.title else 0.0
                candidates.append((snap, sim, gap_days))

        if not candidates:
            continue

        # Pick best by title similarity, break ties by temporal proximity
        candidates.sort(key=lambda x: (-x[1], abs(x[2])))
        best_snap, best_sim, best_gap = candidates[0]

        # Accept if title similarity >= 0.4 OR if temporal gap <= 7 days
        if best_sim >= 0.4 or abs(best_gap) <= 7:
            linked.append((onchain.proposal_id, [best_snap.proposal_id], f'temporal+title({best_sim:.2f},{best_gap}d)'))
            used_onchain.add(onchain.proposal_id)
            used_snap.add(best_snap.proposal_id)

    # Phase 4: Tight temporal match (<=7 days) for bundled proposals
    # where multiple snapshot social votes precede a single onchain executable.
    # Gather ALL unmatched snapshots within 7 days before the onchain start.
    for onchain in onchains:
        if onchain.proposal_id in used_onchain:
            continue
        oc_ts = timestamps.get(onchain.proposal_id)
        if not oc_ts or not oc_ts[0]:
            continue
        oc_start = oc_ts[0]

        bundled_snaps = []
        for snap in snapshots:
            if snap.proposal_id in used_snap:
                continue
            s_ts = timestamps.get(snap.proposal_id)
            if not s_ts or not s_ts[1]:
                continue
            gap_days = (oc_start - s_ts[1]).days
            # Tight window: snapshot ended 0-7 days before onchain started
            if 0 <= gap_days <= 7:
                bundled_snaps.append((snap, gap_days))

        if bundled_snaps:
            bundled_snaps.sort(key=lambda x: x[1])
            snap_ids = [s.proposal_id for s, _ in bundled_snaps]
            linked.append((onchain.proposal_id, snap_ids, f'temporal_bundle({len(snap_ids)}x,<={bundled_snaps[-1][1]}d)'))
            used_onchain.add(onchain.proposal_id)
            for sid in snap_ids:
                used_snap.add(sid)

    # Build unified ID mapping
    id_map: dict[str, str] = {}

    for onchain_id, snap_ids, reason in linked:
        first_snap = snap_by_id.get(snap_ids[0]) if snap_ids else None
        uid = create_unified_id(first_snap.title if first_snap else None, snap_ids[0] if snap_ids else onchain_id, prefix)
        id_map[onchain_id] = uid
        for sid in snap_ids:
            id_map[sid] = uid

    # Unlinked proposals get their own case IDs
    for s in snapshots:
        if s.proposal_id not in id_map:
            id_map[s.proposal_id] = create_unified_id(s.title, s.proposal_id, prefix)
    for o in onchains:
        if o.proposal_id not in id_map:
            id_map[o.proposal_id] = create_unified_id(o.title, o.proposal_id, prefix)

    return id_map


def print_mapping_report(
    id_map: dict[str, str],
    snapshots: list[ProposalInfo],
    onchains: list[ProposalInfo],
    tally: dict,
):
    snap_ids = {s.proposal_id for s in snapshots}
    onchain_ids = {o.proposal_id for o in onchains}

    # Find linked cases (case IDs shared by both sources)
    case_sources: dict[str, set] = defaultdict(set)
    for pid, uid in id_map.items():
        if pid in snap_ids:
            case_sources[uid].add('snapshot')
        if pid in onchain_ids:
            case_sources[uid].add('onchain')

    full_flow = sum(1 for s in case_sources.values() if 'snapshot' in s and 'onchain' in s)
    snap_only = sum(1 for s in case_sources.values() if s == {'snapshot'})
    onchain_only = sum(1 for s in case_sources.values() if s == {'onchain'})

    print(f"\n=== Linking Results ===")
    print(f"Total unique cases:              {len(case_sources)}")
    print(f"Full flow (snapshot + onchain):  {full_flow}")
    print(f"Snapshot only:                   {snap_only}")
    print(f"Onchain only:                    {onchain_only}")

    # Show full-flow cases
    print(f"\n=== Full Governance Flow Cases ({full_flow}) ===")
    snap_by_id = {s.proposal_id: s for s in snapshots}
    onchain_by_id = {o.proposal_id: o for o in onchains}

    case_proposals: dict[str, dict] = defaultdict(lambda: {'snap': [], 'onchain': []})
    for pid, uid in id_map.items():
        if pid in snap_ids:
            case_proposals[uid]['snap'].append(snap_by_id[pid])
        if pid in onchain_ids:
            case_proposals[uid]['onchain'].append(onchain_by_id[pid])

    for uid in sorted(case_proposals.keys()):
        cp = case_proposals[uid]
        if cp['snap'] and cp['onchain']:
            snap_titles = [s.title or s.proposal_id[:20] for s in cp['snap']]
            onchain_titles = [o.title or o.proposal_id[:20] for o in cp['onchain']]
            disc = None
            for o in cp['onchain']:
                t = tally.get(o.proposal_id, {})
                if t.get('discourse_url'):
                    disc = t['discourse_url']
                    break
            print(f"\n  {uid}")
            for st in snap_titles:
                print(f"    [snap]    {st[:70]}")
            for ot in onchain_titles:
                print(f"    [onchain] {ot[:70]}")
            if disc:
                print(f"    [forum]   {disc}")

    # Show unlinked onchain
    unlinked = [uid for uid, s in case_sources.items() if s == {'onchain'}]
    if unlinked:
        print(f"\n=== Onchain-Only Cases ({len(unlinked)}) ===")
        for uid in sorted(unlinked):
            cp = case_proposals[uid]
            for o in cp['onchain']:
                t = tally.get(o.proposal_id, {})
                disc = t.get('discourse_url', '')
                disc_tag = f" [forum]" if disc else ""
                print(f"  {uid:45} {disc_tag}")


def write_linked_db(conn_src: duckdb.DuckDBPyConnection, id_map: dict[str, str], dao_slug: str, output_db: str):
    if os.path.exists(output_db):
        os.remove(output_db)

    conn_dst = duckdb.connect(output_db)
    table = f"{dao_slug}_events"

    conn_dst.execute(f"""
        CREATE TABLE {table} (
            id VARCHAR PRIMARY KEY,
            source VARCHAR NOT NULL,
            event_type VARCHAR NOT NULL,
            timestamp TIMESTAMP,
            proposal_id VARCHAR,
            proposal_title VARCHAR,
            proposal_author VARCHAR,
            proposal_state VARCHAR,
            voter VARCHAR,
            voting_power DOUBLE,
            choice JSON,
            tx_hash VARCHAR,
            block_number BIGINT,
            log_index BIGINT,
            contract_address VARCHAR,
            raw_data JSON
        )
    """)

    # Load mapping into source connection
    mapping_data = list(id_map.items())
    conn_src.execute("CREATE OR REPLACE TEMP TABLE id_map (original_id VARCHAR, unified_id VARCHAR)")
    conn_src.executemany("INSERT INTO id_map VALUES (?, ?)", mapping_data)

    # Read mapped events from source
    rows = conn_src.execute(f"""
        SELECT
            e.id,
            e.source,
            e.event_type,
            e.timestamp,
            COALESCE(m.unified_id, e.proposal_id) as proposal_id,
            e.proposal_title,
            e.proposal_author,
            e.proposal_state,
            e.voter,
            e.voting_power,
            e.choice,
            e.tx_hash,
            e.block_number,
            e.log_index,
            e.contract_address,
            e.raw_data
        FROM {table} e
        LEFT JOIN id_map m ON e.proposal_id = m.original_id
        WHERE e.proposal_id IS NOT NULL
        ORDER BY e.timestamp
    """).fetchall()

    conn_dst.executemany(
        f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows
    )

    # Create indexes
    conn_dst.execute(f"CREATE INDEX idx_timestamp ON {table}(timestamp)")
    conn_dst.execute(f"CREATE INDEX idx_source ON {table}(source)")
    conn_dst.execute(f"CREATE INDEX idx_proposal ON {table}(proposal_id)")

    count = conn_dst.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    cases = conn_dst.execute(f"SELECT COUNT(DISTINCT proposal_id) FROM {table}").fetchone()[0]

    print(f"\nWrote {count:,} events ({cases} cases) to {output_db}")

    # Verify full-flow cases
    full = conn_dst.execute(f"""
        SELECT proposal_id, COUNT(DISTINCT source) as src_count
        FROM {table}
        GROUP BY proposal_id
        HAVING src_count = 2
    """).fetchall()
    print(f"Cases with both onchain + snapshot events: {len(full)}")

    conn_dst.close()


def main():
    parser = argparse.ArgumentParser(description='Build linked DuckDB for process mining')
    parser.add_argument('dao', help='DAO slug (e.g., ens, aave, uniswap)')
    parser.add_argument('--dry-run', action='store_true', help='Show matches without writing DB')
    args = parser.parse_args()

    dao = get_dao_by_slug(args.dao)
    if not dao:
        print(f"Unknown DAO slug: {args.dao}")
        print(f"Available: {', '.join(d.slug for d in DAOS)}")
        sys.exit(1)

    dao_slug = args.dao
    output_db = str(linked_db(dao_slug))
    prefix = DAO_PREFIXES.get(dao_slug, 'EP')

    print(f"Loading Tally data for {dao.name}...")
    tally = load_tally(dao_slug)
    print(f"  {len(tally)} onchain proposals with Tally metadata")

    conn = duckdb.connect(DB_PATH, read_only=True)
    snapshots, onchains = load_proposals(conn, tally, dao_slug, prefix)
    print(f"  {len(snapshots)} snapshot proposals, {len(onchains)} onchain proposals")

    print(f"\nBuilding proposal mapping (prefix={prefix})...")
    id_map = build_mapping(snapshots, onchains, tally, conn, dao_slug, prefix)

    print_mapping_report(id_map, snapshots, onchains, tally)

    conn.close()

    if not args.dry_run:
        print("\nWriting linked database...")
        conn_rw = duckdb.connect(DB_PATH)
        write_linked_db(conn_rw, id_map, dao_slug, output_db)
        conn_rw.close()
        print(f"\nDone. Export with:")
        print(f"  python extraction/export_pm4py.py {dao_slug} --db {output_db} -o {event_log(f'{dao_slug}_linked')}")


if __name__ == '__main__':
    main()
