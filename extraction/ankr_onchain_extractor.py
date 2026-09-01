"""
Extract on-chain governance events using public RPC endpoints.
Tries multiple providers: LlamaNodes, PublicNode, 1RPC, Cloudflare, etc.

No API key required! Falls back to next endpoint on failure.
Block range limit varies by provider (typically 1000-10000 blocks).
"""

import os
import time
import json
import requests
from typing import Iterator, Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass

from dao_config import DAOConfig, DAOS, get_dao_config


# Public RPC endpoints - try multiple providers
# Order: most reliable first
PUBLIC_RPC_ENDPOINTS = {
    'ethereum': [
        'https://eth.llamarpc.com',                    # LlamaNodes - generous limits
        'https://ethereum-rpc.publicnode.com',         # PublicNode
        'https://1rpc.io/eth',                         # 1RPC
        'https://cloudflare-eth.com',                  # Cloudflare
        'https://rpc.ankr.com/eth',                    # Ankr (may need key now)
    ],
    'arbitrum': [
        'https://arb1.arbitrum.io/rpc',                # Official Arbitrum
        'https://arbitrum-one-rpc.publicnode.com',     # PublicNode
        'https://1rpc.io/arb',                         # 1RPC
        'https://rpc.ankr.com/arbitrum',               # Ankr
    ],
    'optimism': [
        'https://mainnet.optimism.io',                 # Official Optimism
        'https://optimism-rpc.publicnode.com',         # PublicNode
        'https://1rpc.io/op',                          # 1RPC
        'https://rpc.ankr.com/optimism',               # Ankr
    ],
}

# Ankr free tier: 1000 blocks per eth_getLogs request
DEFAULT_BLOCK_RANGE = 1000

# Rate limiting for public RPC (be respectful)
# ~2 requests per second for public endpoints
RATE_LIMIT_DELAY = 0.5

# Governance event signatures (keccak256 of event signature)
# OpenZeppelin Governor (ENS, Uniswap, Compound, Gitcoin, etc.)
GOVERNANCE_EVENTS = {
    '0x7d84a6263ae0d98d3329bd7b46bb4e8d6f9903af2a00a6287a9a684c1bc45d4e': 'ProposalCreated',
    '0xb8e138887d0aa13bab447e82de9d5c1777041ecd21ca36ba824ff1e6c07ddda4': 'VoteCast',
    '0xe2babfbac5889a709b63bb7f598b324e08bc5a4fb9ec647fb3cbc9ec07eb8712': 'VoteCastWithParams',
    '0x9a2e42fd6722813d69113e7d0079d3d940171428df7373df9c7f7617cfda2892': 'ProposalQueued',
    '0x712ae1383f79ac853f8d882153778e0260ef8f03b504e2866e0593e04d2b291f': 'ProposalExecuted',
    '0x789cf55be980739dad1d0699b93b58e806b51c9d96619bfa8fe0a28abfc7ef8c': 'ProposalCanceled',
    '0x877856338e13f63d0c36822ff0ef736b80934cd90574a3a5bc9262c39d217c46': 'VoteCast_Alpha',
    '0xccb45da8d5717e6c4544694297c4ba5cf151d455c9bb0ed4fc7a38411bc05461': 'ProposalThresholdSet',
    # Aave Governance V2 (custom contract, different event signatures)
    '0xd272d67d2c8c66de43c1d2515abb064978a5020c173e15903b6a2ab3bf7440ec': 'ProposalCreated',
    '0x0c611e7b6ae0de26f4772260e1bbdb5f58cbb7c275fe2de14671968d29add8d6': 'VoteEmitted',
    '0x11a0b38e70585e4b09b794bd1d9f9b1a51a802eb8ee2101eeee178d0349e73fe': 'ProposalQueued',
    '0x9c85b616f29fca57a17eafe71cf9ff82ffef41766e2cf01ea7f8f7878dd3ec24': 'ProposalExecuted',
    '0x789cf55be980739dad1d0699b93b58e806b51c9d96619bfa8fe0a28abaa7b30c': 'ProposalCanceled',
    # Aave Governance V3 (enum AccessControl encoded as uint8)
    '0xcc914becfa276bbc067049bf8db2d34ebbdc1bafa851e4d4936aaed376c08dbe': 'ProposalCreated',
    '0x45f1db29750f423920a6edede3a80ea19ceb9de3eabc072078eb539ca348dca0': 'VotingActivated',
    '0x2bed878481293fc7587c48352c8b09aeeca52bed666011d7f916706ec72d6d6d': 'ProposalFailed',
}


@dataclass
class PublicRpcClient:
    """RPC client that tries multiple public endpoints."""
    chain: str
    debug: bool = False
    
    def __post_init__(self):
        if self.chain not in PUBLIC_RPC_ENDPOINTS:
            raise ValueError(f"Unsupported chain: {self.chain}. Supported: {list(PUBLIC_RPC_ENDPOINTS.keys())}")
        self.endpoints = PUBLIC_RPC_ENDPOINTS[self.chain]
        self.current_endpoint_idx = 0
        self._request_id = 0
        self._find_working_endpoint()
    
    def _find_working_endpoint(self):
        """Find first working endpoint."""
        for i, endpoint in enumerate(self.endpoints):
            try:
                self.current_endpoint_idx = i
                # Test with simple call
                self._call_single('eth_blockNumber', [], endpoint)
                print(f"  Using RPC: {endpoint}")
                return
            except Exception as e:
                if self.debug:
                    print(f"  Endpoint {endpoint} failed: {str(e)[:50]}")
                continue
        raise Exception(f"No working RPC endpoint found for {self.chain}")
    
    @property
    def endpoint(self) -> str:
        return self.endpoints[self.current_endpoint_idx]
    
    def _call_single(self, method: str, params: List[Any], endpoint: str) -> Any:
        """Make JSON-RPC call to specific endpoint. Retries on 429."""
        self._request_id += 1
        payload = {
            'jsonrpc': '2.0',
            'id': self._request_id,
            'method': method,
            'params': params,
        }

        for attempt in range(3):
            response = requests.post(
                endpoint,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=30,
            )

            if response.status_code == 429:
                wait = 2 ** (attempt + 1)
                time.sleep(wait)
                continue

            if not response.ok:
                try:
                    error_body = response.json()
                except Exception:
                    error_body = response.text[:200]
                raise Exception(f"HTTP {response.status_code}: {error_body}")

            result = response.json()
            if 'error' in result:
                raise Exception(f"RPC error: {result['error']}")

            return result.get('result')

        raise Exception(f"HTTP 429: rate limited after 3 retries")
    
    def _call(self, method: str, params: List[Any]) -> Any:
        """Make JSON-RPC call, trying next endpoint on failure."""
        if self.debug:
            print(f"  DEBUG request: {method} {json.dumps(params)[:200]}")
        
        last_error = None
        start_idx = self.current_endpoint_idx
        
        for attempt in range(len(self.endpoints)):
            idx = (start_idx + attempt) % len(self.endpoints)
            endpoint = self.endpoints[idx]
            
            try:
                result = self._call_single(method, params, endpoint)
                self.current_endpoint_idx = idx  # Remember working endpoint
                
                if self.debug:
                    if isinstance(result, list):
                        print(f"  DEBUG response: {len(result)} items")
                    else:
                        print(f"  DEBUG response: {str(result)[:100]}")
                
                return result
            except Exception as e:
                last_error = e
                if self.debug:
                    print(f"  Endpoint {endpoint} failed: {str(e)[:50]}")
                continue
        
        raise last_error or Exception("All endpoints failed")
    
    def get_block_number(self) -> int:
        """Get latest block number."""
        result = self._call('eth_blockNumber', [])
        return int(result, 16)
    
    def get_block_timestamp(self, block_number: int) -> Optional[int]:
        """Get timestamp for a specific block (returns Unix timestamp)."""
        try:
            result = self._call('eth_getBlockByNumber', [hex(block_number), False])
            if result and 'timestamp' in result:
                return int(result['timestamp'], 16)
        except Exception:
            pass
        return None
    
    def get_block_timestamps_batch(self, block_numbers: List[int]) -> Dict[int, int]:
        """
        Get timestamps for multiple blocks.
        Returns dict mapping block_number -> unix_timestamp.
        """
        timestamps = {}
        for block_num in block_numbers:
            ts = self.get_block_timestamp(block_num)
            if ts:
                timestamps[block_num] = ts
            time.sleep(0.1)  # Small delay to avoid rate limits
        return timestamps
    
    def get_logs(
        self,
        address: str,
        from_block: int,
        to_block: int,
        topics: Optional[List[str]] = None,
        retries: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Fetch logs via eth_getLogs with retry logic.
        
        Public RPCs can be inconsistent (load-balanced nodes with different states).
        We retry and take the result with the most logs.
        """
        params = {
            'address': address,
            'fromBlock': hex(from_block),
            'toBlock': hex(to_block),
        }
        if topics:
            params['topics'] = topics
        
        best_result = []
        for attempt in range(retries):
            try:
                result = self._call('eth_getLogs', [params])
                # Keep the result with the most logs (handle inconsistent RPCs)
                if len(result) > len(best_result):
                    best_result = result
                # If we found logs, we're done
                if best_result:
                    break
            except Exception as e:
                if attempt == retries - 1:
                    raise
                time.sleep(0.2)
        
        return best_result


# Alias for backwards compatibility
AnkrClient = PublicRpcClient


def decode_event_type(topic0: str) -> str:
    """Decode event type from topic0."""
    return GOVERNANCE_EVENTS.get(topic0.lower(), 'Unknown')


def decode_data_field(data: str, event_type: str) -> Dict[str, Any]:
    """
    Decode the data field of a log entry based on event type.
    
    Returns dict with decoded values: proposal_id, support, weight, etc.
    """
    result = {}
    
    if not data or data == '0x':
        return result
    
    # Remove 0x prefix
    if data.startswith('0x'):
        data = data[2:]
    
    # Each field is 32 bytes (64 hex chars)
    try:
        if event_type in ('VoteCast', 'VoteCastWithParams'):
            # VoteCast(address indexed voter, uint256 proposalId, uint8 support, uint256 weight, string reason)
            # Data: proposalId | support | weight | reason_offset | ...
            if len(data) >= 64:
                result['proposal_id'] = str(int(data[0:64], 16))
            if len(data) >= 128:
                result['support'] = int(data[64:128], 16)  # 0=Against, 1=For, 2=Abstain
            if len(data) >= 192:
                result['weight'] = int(data[128:192], 16)
                
        elif event_type == 'VoteCast_Alpha':
            # Compound Alpha: VoteCast(address voter, uint256 proposalId, bool support, uint256 votes)
            # voter is indexed, so data has: proposalId | support | votes
            if len(data) >= 64:
                result['proposal_id'] = str(int(data[0:64], 16))
            if len(data) >= 128:
                result['support'] = int(data[64:128], 16)
            if len(data) >= 192:
                result['weight'] = int(data[128:192], 16)

        elif event_type == 'VoteEmitted':
            # Aave V2: VoteEmitted(uint256 id, address indexed voter, bool support, uint256 votingPower)
            # Only voter is indexed (topic1). Data: id | support | votingPower
            if len(data) >= 64:
                result['proposal_id'] = str(int(data[0:64], 16))
            if len(data) >= 128:
                result['support'] = int(data[64:128], 16)
            if len(data) >= 192:
                result['weight'] = int(data[128:192], 16)
                
        elif event_type == 'ProposalCreated':
            # OZ Governor and Aave V2: proposalId is first field in data
            # Aave V3: all params indexed (in topics), data only has ipfsHash
            if len(data) >= 64:
                val = int(data[0:64], 16)
                if val < 10_000_000:
                    result['proposal_id'] = str(val)
                
        elif event_type in ('ProposalQueued', 'ProposalExecuted', 'ProposalCanceled'):
            if len(data) >= 64:
                result['proposal_id'] = str(int(data[0:64], 16))
                
    except (ValueError, TypeError):
        pass
    
    return result


def parse_log_to_event(log: Dict[str, Any], dao: DAOConfig) -> Dict[str, Any]:
    """Parse a raw log entry into unified event format."""
    topics = log.get('topics', [])
    topic0 = topics[0] if topics else ''
    event_type = decode_event_type(topic0)
    
    block_number = int(log.get('blockNumber', '0x0'), 16)
    log_index = int(log.get('logIndex', '0x0'), 16)
    tx_hash = log.get('transactionHash', '')
    data = log.get('data', '')
    
    proposal_id = None
    voter = None
    voting_power = None
    choice = None
    
    # First try to decode from data field
    decoded = decode_data_field(data, event_type)
    proposal_id = decoded.get('proposal_id')
    
    # Extract voter from indexed topic1 for VoteCast events (OZ Governor)
    if event_type in ('VoteCast', 'VoteCast_Alpha', 'VoteCastWithParams'):
        if len(topics) > 1:
            voter = '0x' + topics[1][-40:]
        if 'weight' in decoded:
            voting_power = decoded['weight'] / 1e18
        if 'support' in decoded:
            support_map = {0: 'Against', 1: 'For', 2: 'Abstain'}
            choice = json.dumps(support_map.get(decoded['support'], str(decoded['support'])))

    # Aave V2: VoteEmitted(uint256 id, address indexed voter, bool support, uint256 votingPower)
    # Only voter is indexed in topic1; proposalId comes from data field
    elif event_type == 'VoteEmitted':
        proposal_id = decoded.get('proposal_id')
        if len(topics) > 1:
            voter = '0x' + topics[1][-40:]
        if 'weight' in decoded:
            voting_power = decoded['weight'] / 1e18
        if 'support' in decoded:
            choice = json.dumps('For' if decoded['support'] else 'Against')

    # For other events, try topic1 if proposal_id not in data
    elif proposal_id is None and len(topics) > 1:
        try:
            proposal_id = str(int(topics[1], 16))
        except (ValueError, TypeError):
            pass
    
    return {
        'id': f"onchain_{tx_hash}_{log_index}",
        'source': 'onchain',
        'event_type': event_type,
        'timestamp': None,  # Will be populated by batch timestamp fetch
        'proposal_id': proposal_id,
        'proposal_title': None,
        'proposal_author': None,
        'proposal_state': None,
        'voter': voter,
        'voting_power': voting_power,
        'choice': choice,
        'tx_hash': tx_hash,
        'block_number': block_number,
        'log_index': log_index,
        'contract_address': log.get('address'),
        'raw_data': json.dumps({
            'topics': topics,
            'data': log.get('data'),
        }),
    }


def extract_logs_for_range(
    client: PublicRpcClient,
    dao: DAOConfig,
    from_block: int,
    to_block: int,
    governance_topics: Optional[List[str]] = None,
    fetch_timestamps: bool = True,
) -> Iterator[Dict[str, Any]]:
    """Extract logs for a specific block range with timestamps."""
    if not dao.governor_address:
        return
    
    logs = client.get_logs(
        address=dao.governor_address,
        from_block=from_block,
        to_block=to_block,
        topics=None,
    )
    
    governance_set = set(t.lower() for t in governance_topics) if governance_topics else None
    
    # Parse all events first
    events = []
    for log in logs:
        topics = log.get('topics', [])
        topic0 = topics[0].lower() if topics else ''
        
        if governance_set and topic0 not in governance_set:
            continue
        
        events.append(parse_log_to_event(log, dao))
    
    # Fetch timestamps for unique blocks if requested
    if fetch_timestamps and events:
        unique_blocks = list(set(e['block_number'] for e in events))
        timestamps = client.get_block_timestamps_batch(unique_blocks)
        
        # Populate timestamps
        for event in events:
            block_ts = timestamps.get(event['block_number'])
            if block_ts:
                event['timestamp'] = datetime.fromtimestamp(block_ts)
    
    for event in events:
        yield event


def extract_all_onchain_events(
    dao: DAOConfig,
    start_block: Optional[int] = None,
    end_block: Optional[int] = None,
    block_range: int = DEFAULT_BLOCK_RANGE,
    governance_only: bool = True,
    progress_callback=None,
    debug: bool = False,
    rpc_url: Optional[str] = None,
) -> Iterator[Dict[str, Any]]:
    """
    Extract all on-chain governance events for a DAO using public RPCs.
    Iterates over all governor addresses if multiple are configured.
    """
    addresses = dao.get_all_addresses() if hasattr(dao, 'get_all_addresses') else []
    if not addresses and dao.governor_address:
        addresses = [dao.governor_address]
    if not addresses:
        print(f"No governor address for {dao.name}, skipping on-chain extraction")
        return

    if dao.chain not in PUBLIC_RPC_ENDPOINTS:
        print(f"Unsupported chain {dao.chain} for {dao.name}, skipping")
        return

    for addr in addresses:
        dao_copy = DAOConfig(
            name=dao.name, slug=dao.slug, chain=dao.chain,
            governor_address=addr, snapshot_space=dao.snapshot_space,
        )
        for event in _extract_onchain_for_address(
            dao_copy, start_block, end_block, block_range,
            governance_only, progress_callback, debug, rpc_url,
        ):
            yield event


def _extract_onchain_for_address(
    dao: DAOConfig,
    start_block: Optional[int] = None,
    end_block: Optional[int] = None,
    block_range: int = DEFAULT_BLOCK_RANGE,
    governance_only: bool = True,
    progress_callback=None,
    debug: bool = False,
    rpc_url: Optional[str] = None,
) -> Iterator[Dict[str, Any]]:
    """Extract events for a single governor address."""
    if rpc_url:
        original = PUBLIC_RPC_ENDPOINTS.get(dao.chain, [])
        PUBLIC_RPC_ENDPOINTS[dao.chain] = [rpc_url] + [u for u in original if u != rpc_url]
    client = PublicRpcClient(chain=dao.chain, debug=debug)
    
    if end_block is None:
        end_block = client.get_block_number()
    
    if start_block is None:
        # Default start blocks per chain (approximate contract deployment)
        chain_start_blocks = {
            'ethereum': 13_000_000,  # ~2021
            'arbitrum': 1,
            'optimism': 1,
        }
        start_block = chain_start_blocks.get(dao.chain, 1)
    
    total_blocks = end_block - start_block
    num_requests = (total_blocks + block_range - 1) // block_range
    est_time_sec = num_requests * RATE_LIMIT_DELAY
    est_time_min = est_time_sec / 60
    
    print(f"Extracting on-chain events for {dao.name} ({dao.chain})")
    print(f"  Contract: {dao.governor_address}")
    print(f"  Block range: {start_block:,} to {end_block:,} ({total_blocks:,} blocks)")
    print(f"  Batch size: {block_range:,} blocks per request")
    print(f"  Estimated: {num_requests:,} API calls, ~{est_time_min:.1f} min")
    
    governance_topics = list(GOVERNANCE_EVENTS.keys()) if governance_only else None
    
    total_extracted = 0
    current_block = start_block
    requests_done = 0
    last_progress_block = start_block
    
    while current_block <= end_block:
        batch_end = min(current_block + block_range - 1, end_block)
        requests_done += 1
        
        # Progress every 500 requests (~4 min at 0.5s/req)
        if requests_done % 500 == 0 or current_block - last_progress_block >= 500_000:
            pct = 100 * (current_block - start_block) / total_blocks
            elapsed_blocks = current_block - start_block
            remaining = total_blocks - elapsed_blocks
            est_remaining_min = (remaining / block_range * RATE_LIMIT_DELAY) / 60
            print(f"  Progress: block {current_block:,} ({pct:.1f}%) | {total_extracted:,} events | ~{est_remaining_min:.0f} min remaining")
            last_progress_block = current_block
        
        try:
            events = list(extract_logs_for_range(
                client, dao, current_block, batch_end, governance_topics
            ))
            
            if events:
                print(f"  Blocks {current_block:,}-{batch_end:,}: {len(events):,} events (total: {total_extracted + len(events):,})")
                for event in events:
                    yield event
                    total_extracted += 1
            
        except Exception as e:
            error_msg = str(e)
            print(f"  Error at blocks {current_block:,}-{batch_end:,}: {error_msg[:100]}")
            
            # If response too large, try smaller range
            if 'too large' in error_msg.lower() or 'limit' in error_msg.lower():
                print(f"  Retrying with smaller block range ({block_range // 2})...")
                for event in extract_all_onchain_events(
                    dao, current_block, batch_end,
                    block_range=block_range // 2,
                    governance_only=governance_only,
                    debug=debug,
                ):
                    yield event
                    total_extracted += 1
        
        current_block = batch_end + 1
        
        if progress_callback:
            progress_callback(current_block - start_block, total_blocks)
        
        time.sleep(RATE_LIMIT_DELAY)
    
    print(f"Extracted {total_extracted:,} on-chain events total for {dao.name}")


def get_supported_chains() -> List[str]:
    """Get list of supported chains."""
    return list(PUBLIC_RPC_ENDPOINTS.keys())


if __name__ == '__main__':
    # Quick test
    dao = get_dao_config('ENS')
    if dao:
        print("Testing Ankr extraction for ENS (small range)...")
        events = list(extract_all_onchain_events(
            dao,
            start_block=13_700_000,
            end_block=13_705_000,  # 5000 blocks = 5 requests
        ))
        print(f"\nFound {len(events)} governance events")
        for event in events[:5]:
            print(f"  {event['event_type']}: block {event['block_number']}, tx {event['tx_hash'][:16]}...")

