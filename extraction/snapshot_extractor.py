"""
Extract governance events from Snapshot GraphQL API.
Handles pagination for large datasets (millions of votes).
"""

import requests
import time
from typing import Iterator, Dict, Any, Optional
from datetime import datetime
from dao_config import DAOConfig


SNAPSHOT_API = "https://hub.snapshot.org/graphql"
REQUEST_DELAY = 1.0  # seconds between requests
MAX_PER_REQUEST = 1000
MAX_RETRIES = 3
RETRY_DELAY = 5.0  # seconds between retries


def query_snapshot(query: str, variables: Optional[Dict] = None, retries: int = MAX_RETRIES) -> Dict:
    """Execute a GraphQL query against Snapshot API with retry logic."""
    last_error = None
    
    for attempt in range(retries):
        try:
            response = requests.post(
                SNAPSHOT_API,
                json={'query': query, 'variables': variables or {}},
                headers={'Content-Type': 'application/json'},
                timeout=60  # 60 second timeout
            )
            response.raise_for_status()
            result = response.json()
            
            # Check for GraphQL errors
            if 'errors' in result:
                print(f"  GraphQL error: {result['errors']}")
                return {'data': {}}
            
            return result
            
        except requests.exceptions.HTTPError as e:
            last_error = e
            status_code = e.response.status_code if e.response else 0
            
            # Retry on 5xx server errors
            if 500 <= status_code < 600 and attempt < retries - 1:
                wait_time = RETRY_DELAY * (attempt + 1)
                print(f"  Server error {status_code}, retrying in {wait_time}s... (attempt {attempt + 1}/{retries})")
                time.sleep(wait_time)
                continue
            raise
            
        except requests.exceptions.Timeout as e:
            last_error = e
            if attempt < retries - 1:
                wait_time = RETRY_DELAY * (attempt + 1)
                print(f"  Timeout, retrying in {wait_time}s... (attempt {attempt + 1}/{retries})")
                time.sleep(wait_time)
                continue
            raise
    
    raise last_error


def get_proposals_paginated(space_id: str, created_gte: int = 0, first: int = MAX_PER_REQUEST) -> tuple[list, bool]:
    """
    Get proposals for a Snapshot space with timestamp-based pagination.
    Uses created_gte instead of skip (Snapshot limits skip to 5000).
    Returns (proposals_list, has_more).
    """
    query = """
    query Proposals($space: String!, $first: Int!, $created_gte: Int!) {
        proposals(
            first: $first,
            where: { space: $space, created_gte: $created_gte },
            orderBy: "created",
            orderDirection: asc
        ) {
            id
            title
            body
            choices
            start
            end
            state
            author
            created
            votes
            scores_total
            quorum
            link
        }
    }
    """
    
    result = query_snapshot(query, {
        'space': space_id,
        'first': first,
        'created_gte': created_gte
    })
    
    # Handle None or missing data
    proposals = result.get('data', {}).get('proposals') or []
    has_more = len(proposals) == first
    
    return proposals, has_more


def get_votes_paginated(proposal_id: str, created_gte: int = 0, first: int = MAX_PER_REQUEST) -> tuple[list, bool]:
    """
    Get votes for a proposal with timestamp-based pagination.
    Uses created_gte instead of skip (Snapshot limits skip to 5000).
    Returns (votes_list, has_more).
    """
    query = """
    query Votes($proposal: String!, $first: Int!, $created_gte: Int!) {
        votes(
            first: $first,
            where: { proposal: $proposal, created_gte: $created_gte },
            orderBy: "created",
            orderDirection: asc
        ) {
            id
            voter
            vp
            choice
            created
            reason
        }
    }
    """
    
    result = query_snapshot(query, {
        'proposal': proposal_id,
        'first': first,
        'created_gte': created_gte
    })
    
    # Handle None or missing data
    votes = result.get('data', {}).get('votes') or []
    has_more = len(votes) == first
    
    return votes, has_more


def extract_proposal_events(proposal: Dict[str, Any], space_id: str) -> Iterator[Dict[str, Any]]:
    """Transform a proposal into event records."""
    proposal_id = proposal['id']
    created_ts = datetime.fromtimestamp(proposal['created'])
    start_ts = datetime.fromtimestamp(proposal['start']) if proposal.get('start') else None
    end_ts = datetime.fromtimestamp(proposal['end']) if proposal.get('end') else None
    
    # ProposalCreated event
    yield {
        'id': f"snapshot_{proposal_id}_created",
        'source': 'snapshot',
        'event_type': 'proposal',
        'timestamp': created_ts,
        'proposal_id': proposal_id,
        'proposal_title': proposal.get('title', '')[:500] if proposal.get('title') else None,
        'proposal_author': proposal.get('author'),
        'proposal_state': proposal.get('state'),
        'voter': None,
        'voting_power': None,
        'choice': None,
        'tx_hash': None,
        'block_number': None,
        'log_index': None,
        'contract_address': None,
        'raw_data': {
            'space': space_id,
            'body': proposal.get('body'),
            'choices': proposal.get('choices'),
            'votes': proposal.get('votes'),
            'scores_total': proposal.get('scores_total'),
            'quorum': proposal.get('quorum'),
            'link': proposal.get('link'),
        }
    }
    
    # VotingStarted event
    if start_ts:
        yield {
            'id': f"snapshot_{proposal_id}_started",
            'source': 'snapshot',
            'event_type': 'voting_started',
            'timestamp': start_ts,
            'proposal_id': proposal_id,
            'proposal_title': proposal.get('title', '')[:500] if proposal.get('title') else None,
            'proposal_author': None,
            'proposal_state': proposal.get('state'),
            'voter': None,
            'voting_power': None,
            'choice': None,
            'tx_hash': None,
            'block_number': None,
            'log_index': None,
            'contract_address': None,
            'raw_data': None,
        }
    
    # VotingEnded event
    if end_ts:
        yield {
            'id': f"snapshot_{proposal_id}_ended",
            'source': 'snapshot',
            'event_type': 'voting_ended',
            'timestamp': end_ts,
            'proposal_id': proposal_id,
            'proposal_title': proposal.get('title', '')[:500] if proposal.get('title') else None,
            'proposal_author': None,
            'proposal_state': proposal.get('state'),
            'voter': None,
            'voting_power': None,
            'choice': None,
            'tx_hash': None,
            'block_number': None,
            'log_index': None,
            'contract_address': None,
            'raw_data': None,
        }


def extract_vote_events(vote: Dict[str, Any], proposal_id: str) -> Dict[str, Any]:
    """Transform a vote into an event record."""
    vote_id = vote['id']
    created_ts = datetime.fromtimestamp(vote['created'])
    
    return {
        'id': f"snapshot_{vote_id}",
        'source': 'snapshot',
        'event_type': 'vote',
        'timestamp': created_ts,
        'proposal_id': proposal_id,
        'proposal_title': None,
        'proposal_author': None,
        'proposal_state': None,
        'voter': vote.get('voter'),
        'voting_power': vote.get('vp'),
        'choice': vote.get('choice'),
        'tx_hash': None,
        'block_number': None,
        'log_index': None,
        'contract_address': None,
        'raw_data': {
            'reason': vote.get('reason'),
        }
    }


def extract_all_snapshot_events(dao: DAOConfig, progress_callback=None, skip_votes: bool = False) -> Iterator[Dict[str, Any]]:
    """
    Extract all Snapshot events for a DAO.
    Yields events as dictionaries ready for database insertion.
    
    Args:
        skip_votes: If True, only extract proposals (much faster for large DAOs)
    """
    if not dao.snapshot_space:
        return
    
    space_id = dao.snapshot_space
    print(f"Extracting Snapshot events for {dao.name} (space: {space_id})")
    if skip_votes:
        print("  (skipping votes - proposals only)")
    
    # Extract proposals using timestamp-based pagination
    created_gte = 0
    proposal_count = 0
    last_proposal_created = 0
    
    while True:
        proposals, has_more = get_proposals_paginated(space_id, created_gte=created_gte)
        
        if not proposals:
            break
        
        for proposal in proposals:
            proposal_id = proposal['id']
            proposal_count += 1
            
            # Yield proposal events
            for event in extract_proposal_events(proposal, space_id):
                yield event
            
            # Extract votes for this proposal (skip if skip_votes=True)
            if not skip_votes:
                # Extract votes using timestamp-based pagination
                # (Snapshot limits skip to 5000, so we use created_gte instead)
                try:
                    vote_created_gte = 0  # Start from beginning
                    vote_errors = 0
                    last_created = 0
                    while True:
                        try:
                            votes, votes_has_more = get_votes_paginated(proposal_id, created_gte=vote_created_gte)
                        except Exception as e:
                            vote_errors += 1
                            print(f"  Error fetching votes for proposal {proposal_id[:20]}... at created_gte={vote_created_gte}: {e}")
                            if vote_errors >= 3:
                                print(f"  Skipping remaining votes for this proposal after {vote_errors} errors")
                                break
                            time.sleep(RETRY_DELAY)
                            continue
                        
                        if not votes:
                            break
                        
                        for vote in votes:
                            yield extract_vote_events(vote, proposal_id)
                            last_created = vote.get('created', 0)
                        
                        if not votes_has_more:
                            break
                        
                        # Use last vote's created timestamp + 1 for next page
                        # Add 1 to avoid getting the same vote again
                        vote_created_gte = last_created + 1
                        time.sleep(REQUEST_DELAY)
                except Exception as e:
                    print(f"  Error processing votes for proposal {proposal_id[:20]}...: {e}")
            
            if progress_callback:
                progress_callback(proposal_count)
            
            # Track last proposal's created timestamp for pagination
            last_proposal_created = proposal.get('created', 0)
        
        if not has_more:
            break
        
        # Use last proposal's created timestamp + 1 for next page
        created_gte = last_proposal_created + 1
        time.sleep(REQUEST_DELAY)
    
    print(f"Extracted {proposal_count} proposals from Snapshot")

