# DAO Event Extraction Specification

## Storage
- DuckDB database: `dao_events.duckdb`
- Schema-on-read: store raw events, classify later
- Export to Parquet for process mining tools

## Schema

```sql
CREATE TABLE raw_events (
    id VARCHAR PRIMARY KEY,
    dao_name VARCHAR NOT NULL,
    platform VARCHAR NOT NULL,
    contract_address VARCHAR,
    event_signature VARCHAR,
    block_number BIGINT,
    tx_hash VARCHAR,
    log_index INT,
    timestamp TIMESTAMP,
    raw_data JSON
);

CREATE INDEX idx_dao ON raw_events(dao_name);
CREATE INDEX idx_timestamp ON raw_events(timestamp);
CREATE INDEX idx_signature ON raw_events(event_signature);
```

## On-Chain (Dune Analytics)

### API
- Endpoint: Dune API via `dune-client`
- Auth: `DUNE_API_KEY` environment variable

### Query
```sql
SELECT
    block_time,
    block_number,
    tx_hash,
    index as log_index,
    contract_address,
    topic0,
    topic1,
    topic2,
    topic3,
    data
FROM {chain}.logs
WHERE contract_address = from_hex('{address}')
ORDER BY block_number, log_index
```

### Pagination
- Dune returns max 1M rows per query
- Use `OFFSET` and `LIMIT` for large datasets
- Rate limit: 10 requests/minute (free tier)

### Chains
- `ethereum.logs`
- `optimism.logs`
- `arbitrum.logs`

## Off-Chain (Snapshot)

### API
- Endpoint: `https://hub.snapshot.org/graphql`
- Auth: None required

### Queries

```graphql
# Proposals
query {
    proposals(
        first: 1000,
        skip: $offset,
        where: { space: $space },
        orderBy: "created"
    ) {
        id, title, body, choices, start, end,
        state, author, created, snapshot, scores
    }
}

# Votes
query {
    votes(
        first: 1000,
        skip: $offset,
        where: { proposal: $proposalId }
    ) {
        id, voter, vp, choice, created, reason
    }
}
```

### Pagination
- Max 1000 per request
- Use `skip` parameter
- No rate limit documented, use 1s delay

### Space IDs
- Uniswap: `uniswapgovernance.eth`
- ENS: `ens.eth`
- Arbitrum: `arbitrumfoundation.eth`
- Optimism: `opcollective.eth`
- Gitcoin: `gitcoindao.eth`
- Balancer: `balancer.eth`
- Lido: `lido-snapshot.eth`
- Convex: `cvx.eth`

## Off-Chain (Discourse Forums)

### API
- Endpoint: `https://{domain}/posts.json`
- Auth: None for public forums

### Forums
- `gov.uniswap.org`
- `governance.aave.com`
- `forum.makerdao.com`
- `forum.arbitrum.foundation`
- `gov.optimism.io`
- `gov.gitcoin.co`

### Pagination
- Use `before` parameter with post ID
- Rate limit: Respect `Retry-After` header

## Dependencies

```
duckdb>=0.9.0
requests>=2.28.0
pandas>=2.0.0
python-dotenv>=1.0.0
dune-client>=1.0.0
pyarrow>=14.0.0
```

## Extraction Order
1. Snapshot proposals (get proposal IDs)
2. Snapshot votes (per proposal, paginated)
3. On-chain events (per DAO contract)
4. Forum posts (optional, per DAO forum)

## Memory Management
- Insert in batches of 10,000 rows
- Use generators, not lists
- Close DuckDB connection after each DAO

## Event Classification (Post-Extraction)

```sql
CREATE VIEW governance_events AS
SELECT *,
    CASE 
        WHEN platform = 'snapshot' AND raw_data->>'type' = 'proposal' 
            THEN 'SnapshotProposalCreated'
        WHEN platform = 'snapshot' AND raw_data->>'type' = 'vote' 
            THEN 'SnapshotVoteCast'
        WHEN platform = 'ethereum' 
            THEN 'OnChain_' || SUBSTRING(event_signature, 1, 10)
    END as activity
FROM raw_events;
```

## Export for Process Mining

```python
import duckdb

conn = duckdb.connect('dao_events.duckdb')
conn.execute("""
    COPY (
        SELECT 
            tx_hash || '-' || log_index as case_id,
            activity,
            timestamp,
            dao_name as resource
        FROM governance_events
        WHERE dao_name = 'Arbitrum'
    ) TO 'arbitrum_events.parquet' (FORMAT PARQUET)
""")
```

