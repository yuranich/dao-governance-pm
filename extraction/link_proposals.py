"""
Link on-chain and off-chain DAO proposals using temporal and title similarity matching.

Strategy:
1. Load onchain proposal titles from Tally API export (ens_tally_mapping.csv)
2. Temporal proximity: onchain proposal starts within N days after snapshot ends
3. Title similarity: fuzzy match proposal titles (Tally enriched)
4. Generate unified case IDs for linked proposals

Usage:
    python link_proposals.py ens                    # Analyze and show matches
    python link_proposals.py ens --export          # Export linked CSV
    python link_proposals.py ens --threshold 0.6   # Lower similarity threshold
"""

import argparse
import csv
import os
import re
from difflib import SequenceMatcher
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field

import duckdb

from db import DB_PATH
from daogov.paths import mapping, event_log


@dataclass
class Proposal:
    """Unified proposal representation."""
    id: str
    source: str
    title: Optional[str]
    start_time: datetime
    end_time: Optional[datetime]
    event_count: int
    discourse_url: Optional[str] = None
    snapshot_url: Optional[str] = None


def normalize_title(title: str) -> str:
    """
    Normalize title for comparison.
    Removes EP numbers, brackets, extra whitespace.
    """
    if not title:
        return ""
    # Remove EP/proposal number patterns like [EP 6.5], [6.24.1], EP6.16
    normalized = re.sub(r'\[?EP?\s*\d+\.?\d*\.?\d*\]?\s*[-:]?\s*', '', title, flags=re.IGNORECASE)
    # Remove [Social], [Executable] tags
    normalized = re.sub(r'\[(Social|Executable|Draft)\]\s*', '', normalized, flags=re.IGNORECASE)
    # Normalize whitespace
    normalized = ' '.join(normalized.split())
    return normalized.lower().strip()


def title_similarity(title1: str, title2: str) -> float:
    """
    Calculate similarity ratio between two titles.
    Uses normalized versions for comparison.
    """
    if not title1 or not title2:
        return 0.0
    
    norm1 = normalize_title(title1)
    norm2 = normalize_title(title2)
    
    if not norm1 or not norm2:
        return 0.0
    
    return SequenceMatcher(None, norm1, norm2).ratio()


def get_snapshot_proposals(conn: duckdb.DuckDBPyConnection, dao_slug: str) -> list[Proposal]:
    """Get all snapshot proposals with their voting periods."""
    table_name = f"{dao_slug}_events"
    
    result = conn.execute(f"""
        SELECT 
            proposal_id,
            MAX(proposal_title) as title,
            MIN(CASE WHEN event_type = 'voting_started' THEN timestamp END) as start_time,
            MAX(CASE WHEN event_type = 'voting_ended' THEN timestamp END) as end_time,
            COUNT(*) as event_count
        FROM {table_name}
        WHERE source = 'snapshot'
        GROUP BY proposal_id
        ORDER BY start_time
    """).fetchall()
    
    return [
        Proposal(
            id=row[0],
            source='snapshot',
            title=row[1],
            start_time=row[2],
            end_time=row[3],
            event_count=row[4]
        )
        for row in result
        if row[2]  # Has start_time
    ]


def load_tally_data(dao_slug: str) -> dict[str, dict]:
    """
    Load Tally API export for onchain proposal enrichment.
    Returns dict keyed by onchain_id with title, discourse_url, snapshot_url, snapshot_id.
    """
    tally_file = str(mapping(dao_slug, "tally"))
    if not os.path.exists(tally_file):
        return {}

    tally = {}
    with open(tally_file) as f:
        for row in csv.DictReader(f):
            onchain_id = row.get('onchain_id', '').strip()
            if onchain_id:
                tally[onchain_id] = {
                    'title': row.get('title', '').strip() or None,
                    'discourse_url': row.get('discourse_url', '').strip() or None,
                    'snapshot_url': row.get('snapshot_url', '').strip() or None,
                    'snapshot_id': row.get('snapshot_id', '').strip() or None,
                }
    return tally


def get_onchain_proposals(
    conn: duckdb.DuckDBPyConnection,
    dao_slug: str,
    tally_data: Optional[dict[str, dict]] = None,
) -> list[Proposal]:
    """Get all onchain proposals with their event windows, enriched with Tally titles."""
    table_name = f"{dao_slug}_events"
    tally_data = tally_data or {}

    result = conn.execute(f"""
        SELECT 
            proposal_id,
            MIN(timestamp) as start_time,
            MAX(timestamp) as end_time,
            COUNT(*) as event_count
        FROM {table_name}
        WHERE source = 'onchain'
        GROUP BY proposal_id
        ORDER BY start_time
    """).fetchall()

    proposals = []
    for row in result:
        if not row[1]:
            continue
        pid = row[0]
        tally = tally_data.get(pid, {})
        proposals.append(Proposal(
            id=pid,
            source='onchain',
            title=tally.get('title'),
            start_time=row[1],
            end_time=row[2],
            event_count=row[3],
            discourse_url=tally.get('discourse_url'),
            snapshot_url=tally.get('snapshot_url'),
        ))
    return proposals


def find_temporal_match(
    snapshot: Proposal,
    onchain_proposals: list[Proposal],
    max_days: int = 21
) -> Optional[Proposal]:
    """
    Find onchain proposal that starts within max_days after snapshot ends.
    Returns the closest match by time.
    """
    if not snapshot.end_time:
        return None
    
    snapshot_end = snapshot.end_time
    candidates = []
    
    for onchain in onchain_proposals:
        # Onchain should start after snapshot ends
        days_after = (onchain.start_time - snapshot_end).days
        
        # Allow some overlap (onchain might start slightly before snapshot ends)
        if -2 <= days_after <= max_days:
            candidates.append((onchain, abs(days_after)))
    
    if not candidates:
        return None
    
    # Return closest match
    return min(candidates, key=lambda x: x[1])[0]


def find_all_temporal_matches(
    snapshot: Proposal,
    onchain_proposals: list[Proposal],
    max_days: int = 21
) -> list[tuple[Proposal, int]]:
    """
    Find all onchain proposals that start within max_days after snapshot ends.
    Returns list of (proposal, days_gap) sorted by gap.
    """
    if not snapshot.end_time:
        return []
    
    snapshot_end = snapshot.end_time
    candidates = []
    
    for onchain in onchain_proposals:
        days_after = (onchain.start_time - snapshot_end).days
        
        # Allow some overlap (onchain might start slightly before snapshot ends)
        if -2 <= days_after <= max_days:
            candidates.append((onchain, days_after))
    
    return sorted(candidates, key=lambda x: abs(x[1]))


def find_best_match(
    snapshot: Proposal,
    onchain_proposals: list[Proposal],
    max_days: int = 21,
    min_similarity: float = 0.5
) -> tuple[Optional[Proposal], float, str]:
    """
    Find best matching onchain proposal using temporal + title similarity.
    When Tally titles are available, scores all temporal candidates by title
    similarity and picks the best one (not just the temporally closest).

    Returns:
        (matched_proposal, similarity_score, match_reason)
    """
    candidates = find_all_temporal_matches(snapshot, onchain_proposals, max_days)

    if not candidates:
        return None, 0.0, "no_temporal_match"

    # Check for Tally-provided direct snapshot link
    for onchain, days_gap in candidates:
        if onchain.snapshot_url and snapshot.id in (onchain.snapshot_url or ''):
            return onchain, 1.0, "tally_snapshot_link"

    # Score candidates by title similarity when titles are available
    if snapshot.title:
        scored = []
        for onchain, days_gap in candidates:
            if onchain.title:
                sim = title_similarity(snapshot.title, onchain.title)
                scored.append((onchain, sim, days_gap))
            else:
                scored.append((onchain, 0.0, days_gap))

        # Pick best by title similarity, break ties by temporal proximity
        scored.sort(key=lambda x: (-x[1], abs(x[2])))
        best, sim, gap = scored[0]

        if sim >= min_similarity:
            return best, sim, "temporal+title"
        elif sim > 0:
            return best, sim, "temporal+title_low"

    # Fall back to closest temporal match
    best_temporal = candidates[0][0]
    return best_temporal, 0.0, "temporal_only"


def extract_ep_number(title: str) -> Optional[str]:
    """Extract EP number from title like '[EP5.1]' or 'EP 6.5'."""
    if not title:
        return None
    match = re.search(r'EP?\s*(\d+(?:\.\d+)*)', title, re.IGNORECASE)
    return match.group(1) if match else None


def create_unified_case_id(snapshot: Proposal) -> str:
    """
    Create a human-readable unified case ID from the proposal title.
    """
    if not snapshot.title:
        return f"case_{snapshot.id[:12]}"
    
    # Extract EP number if present
    ep_match = re.search(r'EP?\s*(\d+\.?\d*\.?\d*)', snapshot.title, re.IGNORECASE)
    ep_num = ep_match.group(1) if ep_match else None
    
    # Get main topic words
    normalized = normalize_title(snapshot.title)
    words = normalized.split()[:5]  # First 5 meaningful words
    topic = '-'.join(w for w in words if len(w) > 2)[:30]
    
    if ep_num:
        return f"EP{ep_num}-{topic}"
    return f"case-{topic}"


def analyze_proposals(
    dao_slug: str,
    max_days: int = 21,
    min_similarity: float = 0.5,
    verbose: bool = True
) -> list[dict]:
    """
    Analyze and link proposals for a DAO.

    Loads Tally API data to enrich onchain proposals with titles
    and discourse/snapshot URLs before matching.

    Handles many-to-one relationships where multiple snapshot proposals
    can link to the same onchain proposal (bundled executables).

    Returns list of match records.
    """
    conn = duckdb.connect(DB_PATH)

    tally_data = load_tally_data(dao_slug)
    if tally_data:
        tally_with_titles = sum(1 for v in tally_data.values() if v.get('title'))
        if verbose:
            print(f"Loaded Tally data: {len(tally_data)} proposals ({tally_with_titles} with titles)")
    elif verbose:
        print(f"No Tally data found ({mapping(dao_slug, 'tally')}). Run fetch_tally.py first for better results.")

    snapshot_proposals = get_snapshot_proposals(conn, dao_slug)
    onchain_proposals = get_onchain_proposals(conn, dao_slug, tally_data)

    if verbose:
        titled = sum(1 for p in onchain_proposals if p.title)
        print(f"Found {len(snapshot_proposals)} snapshot proposals")
        print(f"Found {len(onchain_proposals)} onchain proposals ({titled} with Tally titles)")
        print()

    matches = []
    matched_onchain_ids = set()
    ep_groups: dict[str, list] = {}

    for snapshot in snapshot_proposals:
        match, similarity, reason = find_best_match(
            snapshot, onchain_proposals, max_days, min_similarity
        )

        ep_num = extract_ep_number(snapshot.title)
        unified_id = create_unified_case_id(snapshot)

        if ep_num:
            if ep_num not in ep_groups:
                ep_groups[ep_num] = []
            ep_groups[ep_num].append(snapshot.id)

        record = {
            'unified_id': unified_id,
            'ep_number': ep_num,
            'snapshot_id': snapshot.id,
            'snapshot_title': snapshot.title,
            'snapshot_start': snapshot.start_time,
            'snapshot_end': snapshot.end_time,
            'snapshot_events': snapshot.event_count,
            'onchain_id': match.id if match else None,
            'onchain_title': match.title if match else None,
            'onchain_start': match.start_time if match else None,
            'onchain_end': match.end_time if match else None,
            'onchain_events': match.event_count if match else 0,
            'discourse_url': match.discourse_url if match else None,
            'similarity': similarity,
            'match_reason': reason,
        }

        if match:
            matched_onchain_ids.add(match.id)

        matches.append(record)

        if verbose:
            status = "MATCHED" if match else "UNMATCHED"
            title_short = (snapshot.title[:50] + "...") if snapshot.title and len(snapshot.title) > 50 else snapshot.title
            print(f"[{status}] {title_short}")
            if match:
                days_gap = (match.start_time - snapshot.end_time).days if snapshot.end_time else 0
                onchain_short = (match.title[:40] + "...") if match.title and len(match.title) > 40 else (match.title or match.id[:30] + "...")
                print(f"  -> {onchain_short} (gap: {days_gap}d, sim: {similarity:.2f}, {reason})")
            print()

    # Report many-to-one mappings
    onchain_to_snapshots: dict[str, list] = {}
    for m in matches:
        if m['onchain_id']:
            if m['onchain_id'] not in onchain_to_snapshots:
                onchain_to_snapshots[m['onchain_id']] = []
            onchain_to_snapshots[m['onchain_id']].append(m['snapshot_id'])

    bundled = [(k, v) for k, v in onchain_to_snapshots.items() if len(v) > 1]
    if verbose and bundled:
        print(f"\n=== {len(bundled)} onchain proposals with multiple snapshot links ===")
        for onchain_id, snap_ids in bundled[:5]:
            print(f"  {onchain_id[:25]}... <- {len(snap_ids)} snapshots")

    # Report unmatched onchain proposals (with Tally titles for context)
    unmatched_onchain = [p for p in onchain_proposals if p.id not in matched_onchain_ids]
    if verbose and unmatched_onchain:
        print(f"\n=== {len(unmatched_onchain)} unmatched onchain proposals ===")
        for p in unmatched_onchain[:15]:
            label = p.title or p.id[:30] + "..."
            print(f"  {label[:60]:60} ({p.start_time})")
        if len(unmatched_onchain) > 15:
            print(f"  ... and {len(unmatched_onchain) - 15} more")

    conn.close()
    return matches


def export_linked_csv(dao_slug: str, matches: list[dict], output_file: str = None):
    """
    Export events with unified case IDs to CSV.
    
    Strategy for many-to-one relationships:
    - Each snapshot proposal keeps its own unified_id
    - Onchain proposals are assigned to ONE primary snapshot (the first temporal match)
    - This creates separate cases for each snapshot, with only one getting the onchain events
    
    Alternative: Use --bundled flag to merge all related proposals into one case.
    """
    conn = duckdb.connect(DB_PATH)
    table_name = f"{dao_slug}_events"
    output_file = output_file or str(event_log(f"{dao_slug}_linked"))
    
    # Build mapping from original ID to unified ID
    # For snapshot: direct mapping
    # For onchain: map to the FIRST snapshot that matches it (by time)
    id_mapping = {}
    onchain_assigned = {}  # Track which onchain IDs are assigned
    
    # Sort matches by snapshot start time
    sorted_matches = sorted(matches, key=lambda m: m['snapshot_start'] or datetime.min)
    
    for m in sorted_matches:
        id_mapping[m['snapshot_id']] = m['unified_id']
        
        # Assign onchain to first snapshot match (avoid duplicating onchain events)
        if m['onchain_id'] and m['onchain_id'] not in onchain_assigned:
            id_mapping[m['onchain_id']] = m['unified_id']
            onchain_assigned[m['onchain_id']] = m['unified_id']
    
    # Register the mapping as a table
    mapping_data = [(k, v) for k, v in id_mapping.items()]
    conn.execute("CREATE TEMP TABLE id_map (original_id VARCHAR, unified_id VARCHAR)")
    conn.executemany("INSERT INTO id_map VALUES (?, ?)", mapping_data)
    
    # Export with unified IDs
    query = f"""
        SELECT 
            COALESCE(m.unified_id, e.proposal_id) AS "case:concept:name",
            e.event_type AS "concept:name",
            e.timestamp AS "time:timestamp",
            e.source,
            e.voter AS "org:resource",
            e.voting_power,
            e.proposal_title AS "case:proposal_title",
            e.proposal_author AS "case:proposal_author",
            e.proposal_id AS "original_proposal_id"
        FROM {table_name} e
        LEFT JOIN id_map m ON e.proposal_id = m.original_id
        WHERE e.proposal_id IS NOT NULL
        ORDER BY e.timestamp
    """
    
    conn.execute(f"COPY ({query}) TO '{output_file}' (HEADER, DELIMITER ',')")
    
    # Stats
    count = conn.execute(f"SELECT COUNT(*) FROM ({query})").fetchone()[0]
    case_count = conn.execute(f"""
        SELECT COUNT(DISTINCT COALESCE(m.unified_id, e.proposal_id))
        FROM {table_name} e
        LEFT JOIN id_map m ON e.proposal_id = m.original_id
        WHERE e.proposal_id IS NOT NULL
    """).fetchone()[0]
    
    linked_cases = len(onchain_assigned)
    unlinked_snapshot = len([m for m in matches if not m['onchain_id']])
    
    print(f"\nExported {count:,} events to {output_file}")
    print(f"  Total cases: {case_count}")
    print(f"  Linked cases (snapshot+onchain): {linked_cases}")
    print(f"  Snapshot-only cases: {unlinked_snapshot}")
    print(f"  Note: Onchain proposals shared by multiple snapshots are assigned to the first match")
    
    conn.close()


def export_mapping_csv(matches: list[dict], output_file: str):
    """Export the proposal mapping table."""

    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'unified_id', 'snapshot_id', 'onchain_id',
            'snapshot_title', 'onchain_title', 'discourse_url',
            'snapshot_end', 'onchain_start',
            'gap_days', 'similarity', 'match_reason'
        ])
        writer.writeheader()

        for m in matches:
            gap_days = None
            if m['snapshot_end'] and m['onchain_start']:
                gap_days = (m['onchain_start'] - m['snapshot_end']).days

            writer.writerow({
                'unified_id': m['unified_id'],
                'snapshot_id': m['snapshot_id'],
                'onchain_id': m['onchain_id'],
                'snapshot_title': m['snapshot_title'],
                'onchain_title': m.get('onchain_title'),
                'discourse_url': m.get('discourse_url'),
                'snapshot_end': m['snapshot_end'],
                'onchain_start': m['onchain_start'],
                'gap_days': gap_days,
                'similarity': m['similarity'],
                'match_reason': m['match_reason'],
            })

    print(f"Exported mapping to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Link on-chain and off-chain DAO proposals'
    )
    parser.add_argument('dao', help='DAO slug (e.g., ens)')
    parser.add_argument('--export', action='store_true', 
                        help='Export linked CSV')
    parser.add_argument('--mapping', type=str,
                        help='Export mapping table to CSV')
    parser.add_argument('-o', '--output', type=str,
                        help='Output file path')
    parser.add_argument('--max-days', type=int, default=21,
                        help='Max days between snapshot end and onchain start (default: 21)')
    parser.add_argument('--threshold', type=float, default=0.5,
                        help='Min title similarity threshold (default: 0.5)')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='Suppress verbose output')
    
    args = parser.parse_args()
    
    print(f"Analyzing {args.dao.upper()} proposals...")
    print(f"  Max days gap: {args.max_days}")
    print(f"  Similarity threshold: {args.threshold}")
    print()
    
    matches = analyze_proposals(
        args.dao,
        max_days=args.max_days,
        min_similarity=args.threshold,
        verbose=not args.quiet
    )
    
    # Summary
    matched = len([m for m in matches if m['onchain_id']])
    print(f"\n=== Summary ===")
    print(f"Total snapshot proposals: {len(matches)}")
    print(f"Linked to onchain: {matched} ({100*matched/len(matches):.1f}%)")
    print(f"Snapshot only: {len(matches) - matched}")
    
    if args.mapping:
        export_mapping_csv(matches, args.mapping)
    
    if args.export:
        export_linked_csv(args.dao, matches, args.output)


if __name__ == '__main__':
    main()
