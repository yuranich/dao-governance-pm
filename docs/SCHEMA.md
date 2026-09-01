# Database Schema Documentation

## Overview

DAO events are stored in DuckDB database `dao_events.duckdb`. Each DAO has its own table following the naming pattern `{dao_slug}_events`.

## Table Structure

Each DAO table (`{dao_slug}_events`) uses the following schema:

```sql
CREATE TABLE {dao_slug}_events (
    id VARCHAR PRIMARY KEY,
    source VARCHAR NOT NULL,
    event_type VARCHAR NOT NULL,
    timestamp TIMESTAMP,
    -- Proposal fields
    proposal_id VARCHAR,
    proposal_title VARCHAR,
    proposal_author VARCHAR,
    proposal_state VARCHAR,
    -- Vote fields
    voter VARCHAR,
    voting_power DOUBLE,
    choice JSON,
    -- On-chain fields
    tx_hash VARCHAR,
    block_number BIGINT,
    log_index INT,
    contract_address VARCHAR,
    raw_data JSON
);
```

## Column Descriptions

### Core Fields

- **id** (VARCHAR, PRIMARY KEY): Unique event identifier
  - Snapshot: `snapshot_{proposal_id}_{event_type}` or `snapshot_{vote_id}`
  - On-chain: `onchain_{tx_hash}_{log_index}`

- **source** (VARCHAR, NOT NULL): Data source identifier
  - `snapshot`: Events from Snapshot GraphQL API
  - `onchain`: Events from on-chain logs via Dune Analytics

- **event_type** (VARCHAR, NOT NULL): Type of event
  - Snapshot: `proposal`, `vote`, `voting_started`, `voting_ended`
  - On-chain: `ProposalCreated`, `VoteCast`, `ProposalQueued`, `ProposalExecuted`, `ProposalCanceled`, `Unknown`

- **timestamp** (TIMESTAMP): Event timestamp
  - Snapshot: Unix timestamp converted to TIMESTAMP
  - On-chain: Block time from blockchain

### Proposal Fields

- **proposal_id** (VARCHAR): Unique proposal identifier
  - Snapshot: Proposal ID from Snapshot
  - On-chain: Extracted from event data (topic1 typically)

- **proposal_title** (VARCHAR): Proposal title (truncated to 500 chars)
  - Snapshot: From proposal data
  - On-chain: NULL

- **proposal_author** (VARCHAR): Address/identifier of proposal creator
  - Snapshot: Author address
  - On-chain: Extracted from event data

- **proposal_state** (VARCHAR): Current state of proposal
  - Snapshot: `active`, `closed`, `pending`, etc.
  - On-chain: NULL

### Vote Fields

- **voter** (VARCHAR): Address/identifier of voter
  - Snapshot: Voter address
  - On-chain: Extracted from event data

- **voting_power** (DOUBLE): Voting power used
  - Snapshot: VP (voting power) value
  - On-chain: Extracted from event data

- **choice** (JSON): Vote choice
  - Snapshot: Choice number or array for multiple choices
  - On-chain: Vote value (0=against, 1=for, 2=abstain typically)

### On-Chain Fields

- **tx_hash** (VARCHAR): Transaction hash
  - Snapshot: NULL
  - On-chain: Transaction hash containing the event

- **block_number** (BIGINT): Block number
  - Snapshot: NULL
  - On-chain: Block number where event occurred

- **log_index** (INT): Log index within transaction
  - Snapshot: NULL
  - On-chain: Index of log entry

- **contract_address** (VARCHAR): Contract address that emitted event
  - Snapshot: NULL
  - On-chain: Governor contract address

### Raw Data

- **raw_data** (JSON): Additional event data
  - Snapshot: Contains `body`, `choices`, `votes`, `scores_total`, `quorum`, `link`, `reason` (for votes)
  - On-chain: Contains `topic0`, `topic1`, `topic2`, `topic3`, `data` (raw log data)

## Indexes

Each table has three indexes for query performance:

1. **idx_{dao_slug}_timestamp**: Index on `timestamp` for time-range queries
2. **idx_{dao_slug}_source**: Index on `source` for filtering by data source
3. **idx_{dao_slug}_event_type**: Index on `event_type` for filtering by event type

## Table Naming Convention

Tables are named using the DAO slug (lowercase, underscores):
- `aave_events`
- `arbitrum_events`
- `optimism_events`
- `makerdao_events`
- `compound_events`
- `uniswap_events`
- `gitcoin_events`
- `ens_events`
- `lido_events`

## Example Queries

### Count events by source
```sql
SELECT source, COUNT(*) as count
FROM aave_events
GROUP BY source;
```

### Get all proposals
```sql
SELECT DISTINCT proposal_id, proposal_title, proposal_author, timestamp
FROM aave_events
WHERE event_type = 'proposal'
ORDER BY timestamp DESC;
```

### Get vote distribution
```sql
SELECT choice, COUNT(*) as votes, SUM(voting_power) as total_vp
FROM aave_events
WHERE event_type = 'vote'
GROUP BY choice;
```

### Get on-chain events by type
```sql
SELECT event_type, COUNT(*) as count
FROM aave_events
WHERE source = 'onchain'
GROUP BY event_type;
```

### Time-series of events
```sql
SELECT 
    DATE_TRUNC('day', timestamp) as day,
    event_type,
    COUNT(*) as count
FROM aave_events
WHERE timestamp >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY day, event_type
ORDER BY day DESC, event_type;
```

## Data Extraction Notes

- Snapshot events are extracted with full pagination support (handles millions of votes)
- On-chain events require manual creation of Dune queries (see `onchain_extractor.py`)
- Events are inserted in batches of 10,000 rows for performance
- Duplicate events are ignored (INSERT OR IGNORE based on primary key)

