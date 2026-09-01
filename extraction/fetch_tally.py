"""
Fetch DAO proposals from Tally API and create cross-reference mapping
between onchain proposals, Snapshot votes, and Discourse discussions.

Requires TALLY environment variable with API key.
Get one at: https://www.tally.xyz/user/settings

Usage:
    python fetch_tally.py aave                              # Fetch and display
    python fetch_tally.py ens --full-mapping ens_tally_mapping.csv
    python fetch_tally.py aave --full-mapping aave_tally_mapping.csv
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

import duckdb
import requests

from dao_config import get_dao_by_slug, DAOS
from db import DB_PATH
from daogov.paths import mapping

TALLY_API = "https://api.tally.xyz/query"

CHAIN_IDS = {
    'ethereum': 1,
    'arbitrum': 42161,
    'optimism': 10,
}

PROPOSALS_QUERY = """
query DAOProposals($input: ProposalsInput!) {
  proposals(input: $input) {
    nodes {
      ... on Proposal {
        id
        onchainId
        status
        block {
          timestamp
        }
        start {
          ... on Block {
            timestamp
          }
        }
        end {
          ... on Block {
            timestamp
          }
        }
        metadata {
          title
          discourseURL
          snapshotURL
        }
        governor {
          id
          name
        }
      }
    }
    pageInfo {
      firstCursor
      lastCursor
      count
    }
  }
}
"""

ORG_QUERY = """
query DAOOrg($input: OrganizationInput!) {
  organization(input: $input) {
    id
    slug
    name
    governorIds
    proposalsCount
  }
}
"""


@dataclass
class TallyProposal:
    tally_id: str
    onchain_id: str
    title: str
    status: str
    snapshot_url: Optional[str] = None
    discourse_url: Optional[str] = None
    snapshot_id: Optional[str] = None
    start_timestamp: Optional[str] = None
    end_timestamp: Optional[str] = None
    governor_id: Optional[str] = None
    governor_name: Optional[str] = None


def get_api_key() -> str:
    key = os.environ.get("TALLY")
    if not key:
        print("Error: TALLY environment variable not set.", file=sys.stderr)
        print("Get an API key at: https://www.tally.xyz/user/settings", file=sys.stderr)
        sys.exit(1)
    return key


def tally_request(query: str, variables: dict, api_key: str) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Api-Key": api_key,
    }
    resp = requests.post(
        TALLY_API,
        json={"query": query, "variables": variables},
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data and data["errors"]:
        msg = data["errors"][0].get("message", "unknown error")
        raise RuntimeError(f"Tally API error: {msg}")
    return data["data"]


def fetch_organization(api_key: str, slug: str) -> dict:
    data = tally_request(ORG_QUERY, {"input": {"slug": slug}}, api_key)
    return data["organization"]


def extract_snapshot_id(url: Optional[str]) -> Optional[str]:
    """Extract Snapshot proposal ID from a Snapshot URL."""
    if not url:
        return None
    parsed = urlparse(url)
    # https://snapshot.org/#/ens.eth/proposal/0x...
    path = parsed.fragment or parsed.path
    match = re.search(r'proposal/(0x[a-fA-F0-9]+|Qm[a-zA-Z0-9]+)', path)
    if match:
        return match.group(1)
    # Fallback: last path segment
    parts = path.rstrip('/').split('/')
    if parts:
        return parts[-1]
    return None


def make_governor_id(chain: str, address: str) -> str:
    chain_id = CHAIN_IDS.get(chain)
    if not chain_id:
        raise ValueError(f"Unknown chain: {chain}. Supported: {list(CHAIN_IDS.keys())}")
    return f"eip155:{chain_id}:{address}"


def fetch_all_proposals(api_key: str, governor_id: str) -> list[TallyProposal]:
    """Fetch all proposals from Tally for a given governor, handling pagination."""
    proposals = []
    cursor = None
    page = 0

    while True:
        page += 1
        page_input = {"limit": 20}
        if cursor:
            page_input["afterCursor"] = cursor

        variables = {
            "input": {
                "filters": {"governorId": governor_id},
                "page": page_input,
                "sort": {"sortBy": "id", "isDescending": False},
            }
        }

        data = tally_request(PROPOSALS_QUERY, variables, api_key)
        nodes = data["proposals"]["nodes"]
        page_info = data["proposals"]["pageInfo"]

        if not nodes:
            break

        for node in nodes:
            metadata = node.get("metadata") or {}
            governor = node.get("governor") or {}
            snapshot_url = metadata.get("snapshotURL")

            start = node.get("start") or {}
            end = node.get("end") or {}

            p = TallyProposal(
                tally_id=str(node["id"]),
                onchain_id=node.get("onchainId") or "",
                title=metadata.get("title", ""),
                status=node.get("status", ""),
                snapshot_url=snapshot_url,
                discourse_url=metadata.get("discourseURL"),
                snapshot_id=extract_snapshot_id(snapshot_url),
                start_timestamp=start.get("timestamp"),
                end_timestamp=end.get("timestamp"),
                governor_id=governor.get("id"),
                governor_name=governor.get("name"),
            )
            proposals.append(p)

        print(f"  Page {page}: fetched {len(nodes)} proposals (total: {len(proposals)})")

        cursor = page_info.get("lastCursor")
        if not cursor or len(nodes) < 20:
            break

        time.sleep(0.5)

    return proposals


def get_db_onchain_ids(dao_slug: str = "ens") -> set[str]:
    """Get all onchain proposal IDs from the DuckDB database."""
    conn = duckdb.connect(DB_PATH, read_only=True)
    table_name = f"{dao_slug}_events"
    try:
        result = conn.execute(f"""
            SELECT DISTINCT proposal_id
            FROM {table_name}
            WHERE source = 'onchain'
              AND proposal_id IS NOT NULL
        """).fetchall()
        return {row[0] for row in result}
    finally:
        conn.close()


def get_db_snapshot_ids(dao_slug: str = "ens") -> set[str]:
    """Get all snapshot proposal IDs from the DuckDB database."""
    conn = duckdb.connect(DB_PATH, read_only=True)
    table_name = f"{dao_slug}_events"
    try:
        result = conn.execute(f"""
            SELECT DISTINCT proposal_id
            FROM {table_name}
            WHERE source = 'snapshot'
              AND proposal_id IS NOT NULL
        """).fetchall()
        return {row[0] for row in result}
    finally:
        conn.close()


def display_proposals(proposals: list[TallyProposal], db_onchain_ids: set[str], db_snapshot_ids: set[str]):
    """Display fetched proposals with match status."""
    matched_onchain = 0
    matched_snapshot = 0
    has_snapshot_url = 0
    has_discourse_url = 0

    for p in proposals:
        in_db = p.onchain_id in db_onchain_ids
        snap_match = p.snapshot_id in db_snapshot_ids if p.snapshot_id else False

        if in_db:
            matched_onchain += 1
        if snap_match:
            matched_snapshot += 1
        if p.snapshot_url:
            has_snapshot_url += 1
        if p.discourse_url:
            has_discourse_url += 1

        db_tag = "DB" if in_db else "  "
        snap_tag = "SNAP" if snap_match else "    "
        title_short = (p.title[:60] + "...") if len(p.title) > 60 else p.title

        print(f"[{db_tag}][{snap_tag}] {p.onchain_id[:25]:>25}  {p.status:<10} {title_short}")
        if p.snapshot_url:
            print(f"           snapshot: {p.snapshot_url}")
        if p.discourse_url:
            print(f"           discourse: {p.discourse_url}")

    print(f"\n=== Summary ===")
    print(f"Total Tally proposals:      {len(proposals)}")
    print(f"Matched in DB (onchain):    {matched_onchain} / {len(db_onchain_ids)} DB onchain proposals")
    print(f"Has Snapshot URL:           {has_snapshot_url}")
    print(f"Snapshot ID in DB:          {matched_snapshot}")
    print(f"Has Discourse URL:          {has_discourse_url}")


def export_mapping(proposals: list[TallyProposal], output_file: str):
    """Export Tally cross-reference mapping to CSV."""
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'onchain_id', 'tally_id', 'title', 'status',
            'snapshot_url', 'snapshot_id', 'discourse_url',
            'start_timestamp', 'end_timestamp',
        ])
        for p in proposals:
            writer.writerow([
                p.onchain_id, p.tally_id, p.title, p.status,
                p.snapshot_url or '', p.snapshot_id or '', p.discourse_url or '',
                p.start_timestamp or '', p.end_timestamp or '',
            ])
    print(f"Exported {len(proposals)} proposals to {output_file}")


def export_full_mapping(
    proposals: list[TallyProposal],
    db_onchain_ids: set[str],
    db_snapshot_ids: set[str],
    output_file: str,
):
    """
    Export mapping combining Tally data with existing DB proposal IDs.
    Produces one row per onchain proposal linking to its Snapshot counterpart.
    """
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'onchain_id', 'snapshot_id', 'title', 'status',
            'snapshot_url', 'discourse_url',
            'onchain_in_db', 'snapshot_in_db',
        ])
        for p in proposals:
            writer.writerow([
                p.onchain_id,
                p.snapshot_id or '',
                p.title,
                p.status,
                p.snapshot_url or '',
                p.discourse_url or '',
                p.onchain_id in db_onchain_ids,
                (p.snapshot_id in db_snapshot_ids) if p.snapshot_id else False,
            ])
    print(f"Exported full mapping ({len(proposals)} proposals) to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Fetch DAO proposals from Tally API'
    )
    parser.add_argument('dao', help='DAO slug (e.g., ens, aave, uniswap)')
    parser.add_argument('--export', type=str, metavar='FILE',
                        help='Export Tally proposals to CSV')
    parser.add_argument('--full-mapping', type=str, metavar='FILE',
                        help='Export full cross-reference mapping CSV')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='Suppress verbose output')
    args = parser.parse_args()

    dao = get_dao_by_slug(args.dao)
    if not dao:
        print(f"Unknown DAO slug: {args.dao}")
        print(f"Available: {', '.join(d.slug for d in DAOS)}")
        sys.exit(1)

    if not dao.governor_address:
        print(f"{dao.name} has no governor address configured")
        sys.exit(1)

    governor_id = make_governor_id(dao.chain, dao.governor_address)
    api_key = get_api_key()

    print(f"Fetching {dao.name} organization info...")
    org = fetch_organization(api_key, args.dao)
    print(f"  Organization: {org['name']} (id: {org['id']})")
    print(f"  Governor IDs: {org['governorIds']}")
    print(f"  Proposals count: {org['proposalsCount']}")
    print()

    print("Fetching all proposals...")
    proposals = fetch_all_proposals(api_key, governor_id)
    print(f"\nFetched {len(proposals)} proposals total.\n")

    db_onchain_ids = get_db_onchain_ids(args.dao)
    db_snapshot_ids = get_db_snapshot_ids(args.dao)

    if not args.quiet:
        display_proposals(proposals, db_onchain_ids, db_snapshot_ids)

    if args.export:
        export_mapping(proposals, args.export)

    full_mapping_file = args.full_mapping or str(mapping(args.dao, "tally"))
    if args.full_mapping is not None or (not args.export):
        export_full_mapping(proposals, db_onchain_ids, db_snapshot_ids, full_mapping_file)

    if not args.export and args.full_mapping is None:
        print(f"\nTip: Use --full-mapping FILE to save results.")


if __name__ == '__main__':
    main()
