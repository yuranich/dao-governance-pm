"""
Extract off-chain governance events from Snapshot.
Snapshot is used by many DAOs for temperature checks and signaling votes.

API: https://hub.snapshot.org/graphql
No API key required for read-only queries.
"""

import requests
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional
from daogov.paths import result

SNAPSHOT_API = "https://hub.snapshot.org/graphql"

# DAO space IDs on Snapshot
# Find more at: https://snapshot.org/#/
SNAPSHOT_SPACES = {
    'Uniswap': 'uniswapgovernance.eth',  # Uniswap governance space
    'ENS': 'ens.eth',
    'Compound': 'comp-vote.eth',
    'Aave': 'aave.eth',  # Aave uses on-chain primarily
    'Gitcoin': 'gitcoindao.eth',
    'Arbitrum': 'arbitrumfoundation.eth',
    'Optimism': 'opcollective.eth',
    'Nouns': 'nouns.eth',
    'Lido': 'lido-snapshot.eth',
    'MakerDAO': 'makerdao.eth',  # MakerDAO uses own polling system
    'Balancer': 'balancer.eth',
    'Curve': 'curve.eth',
    'Synthetix': 'snxgov.eth',  # Synthetix governance
    'Convex': 'cvx.eth',
    'Decentraland': 'decentraland.eth',
    'Aura Finance': 'aura.eth',
    'Safe': 'safe.eth',
    '1inch': '1inch.eth',
    'Hop Protocol': 'hop.eth',
}


def query_snapshot(query: str, variables: Optional[Dict] = None) -> Dict:
    """Execute a GraphQL query against Snapshot API."""
    response = requests.post(
        SNAPSHOT_API,
        json={'query': query, 'variables': variables or {}},
        headers={'Content-Type': 'application/json'}
    )
    response.raise_for_status()
    return response.json()


def get_proposals(space_id: str, limit: int = 100) -> List[Dict]:
    """Get proposals for a Snapshot space."""
    query = """
    query Proposals($space: String!, $first: Int!) {
        proposals(
            first: $first,
            skip: 0,
            where: { space: $space },
            orderBy: "created",
            orderDirection: desc
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
    
    result = query_snapshot(query, {'space': space_id, 'first': limit})
    return result.get('data', {}).get('proposals', [])


def get_votes(proposal_id: str, limit: int = 1000) -> List[Dict]:
    """Get votes for a specific proposal."""
    query = """
    query Votes($proposal: String!, $first: Int!) {
        votes(
            first: $first,
            where: { proposal: $proposal }
        ) {
            id
            voter
            vp
            choice
            created
        }
    }
    """
    
    result = query_snapshot(query, {'proposal': proposal_id, 'first': limit})
    return result.get('data', {}).get('votes', [])


def get_space_info(space_id: str) -> Dict:
    """Get information about a Snapshot space."""
    query = """
    query Space($id: String!) {
        space(id: $id) {
            id
            name
            about
            members
            proposalsCount
            votesCount
            followersCount
        }
    }
    """
    
    result = query_snapshot(query, {'id': space_id})
    return result.get('data', {}).get('space', {})


def count_snapshot_events(space_id: str) -> Dict[str, int]:
    """Count all events for a Snapshot space."""
    space_info = get_space_info(space_id)
    
    if not space_info:
        return {
            'proposals_count': 0,
            'votes_count': 0,
            'followers_count': 0,
        }
    
    return {
        'proposals_count': space_info.get('proposalsCount', 0) or 0,
        'votes_count': space_info.get('votesCount', 0) or 0,
        'followers_count': space_info.get('followersCount', 0) or 0,
    }


def extract_proposal_events(space_id: str, limit: int = 100) -> pd.DataFrame:
    """
    Extract proposal events for process mining.
    Returns events in a format suitable for process mining tools.
    """
    proposals = get_proposals(space_id, limit)
    
    events = []
    for proposal in proposals:
        proposal_id = proposal['id']
        
        # ProposalCreated event
        events.append({
            'case_id': proposal_id,
            'activity': 'SnapshotProposalCreated',
            'timestamp': datetime.fromtimestamp(proposal['created']),
            'resource': proposal['author'],
            'title': proposal['title'][:100] if proposal.get('title') else '',
            'state': proposal['state'],
            'votes_count': proposal['votes'],
            'platform': 'snapshot',
        })
        
        # Voting period start
        events.append({
            'case_id': proposal_id,
            'activity': 'SnapshotVotingStarted',
            'timestamp': datetime.fromtimestamp(proposal['start']),
            'resource': 'system',
            'title': '',
            'state': proposal['state'],
            'votes_count': proposal['votes'],
            'platform': 'snapshot',
        })
        
        # Voting period end
        events.append({
            'case_id': proposal_id,
            'activity': 'SnapshotVotingEnded',
            'timestamp': datetime.fromtimestamp(proposal['end']),
            'resource': 'system',
            'title': '',
            'state': proposal['state'],
            'votes_count': proposal['votes'],
            'platform': 'snapshot',
        })
    
    return pd.DataFrame(events)


def main():
    """Count Snapshot events across all configured DAOs."""
    results = []
    
    print("Counting Snapshot events for DAOs...\n")
    
    for dao_name, space_id in SNAPSHOT_SPACES.items():
        print(f"Querying {dao_name} ({space_id})...")
        
        try:
            counts = count_snapshot_events(space_id)
            total = counts['proposals_count'] + counts['votes_count']
            
            results.append({
                'dao_name': dao_name,
                'snapshot_space': space_id,
                'proposals_count': counts['proposals_count'],
                'votes_count': counts['votes_count'],
                'followers_count': counts['followers_count'],
                'total_events': total,
            })
            
            print(f"  Proposals: {counts['proposals_count']}, Votes: {counts['votes_count']}")
            
        except Exception as e:
            print(f"  Error: {e}")
            results.append({
                'dao_name': dao_name,
                'snapshot_space': space_id,
                'proposals_count': 0,
                'votes_count': 0,
                'followers_count': 0,
                'total_events': 0,
            })
    
    # Create DataFrame and sort
    df = pd.DataFrame(results)
    df = df.sort_values('total_events', ascending=False)
    
    # Save to CSV
    output_file = str(result("snapshot_event_counts.csv"))
    df.to_csv(output_file, index=False)
    
    print(f"\nResults saved to {output_file}")
    print("\nTop DAOs by Snapshot events:")
    print(df.to_string(index=False))
    
    return df


if __name__ == '__main__':
    main()

