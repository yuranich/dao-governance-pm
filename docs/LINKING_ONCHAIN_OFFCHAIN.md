# Linking Onchain and Offchain DAO Events

## Problem Statement

The extracted ENS DAO event data contains two disconnected event streams:

1. **Offchain events** (Snapshot): Use IPFS content hashes as case IDs
   - Example: `QmW5qrWwivELsMdLViGMTmH27QQYjyqGM2PMqVwpYxL2UN`
   
2. **Onchain events** (Governor): Use `keccak256` hashes of proposal parameters
   - Example: `90476529665364161211265365238121921179703522228680648046371476645353679539653`

These IDs have **no programmatic relationship**. In process mining terms, they appear as separate cases rather than stages of the same governance process.

## Root Cause

ENS (and most DAOs) use a **two-stage governance process**:

```
Stage 1: Temperature Check (Snapshot)
    ↓ (manual transition, no on-chain link)
Stage 2: Executable Proposal (Governor)
```

- Snapshot proposal IDs are IPFS CIDs generated from proposal content
- Governor proposal IDs are derived from `keccak256(targets, values, calldatas, descriptionHash)`
- No standard mechanism exists to store Snapshot references in onchain proposals
- The two proposals are created independently, often with slightly different titles

## Current Data Structure

From `ens_pm4py.csv`:

| Source | case:concept:name | Example Events |
|--------|-------------------|----------------|
| Snapshot | IPFS hash | `proposal`, `voting_started`, `vote`, `voting_ended` |
| Onchain | uint256 hash | `ProposalCreated`, `VoteCast`, `ProposalQueued`, `ProposalExecuted` |

## Proposed Solutions

### 1. Manual Mapping Table

Create `proposal_mapping.csv` linking related proposals based on research:

```csv
snapshot_id,onchain_id,topic,notes
QmW5qrWw...,90476529...,EP5.1 - Endowment Fund,Linked via ENS governance docs
```

**Pros**: Accurate, handles edge cases
**Cons**: Labor-intensive, doesn't scale, requires ongoing maintenance

### 2. Title/Content Similarity Matching

Use fuzzy matching algorithms on proposal titles:

```python
from difflib import SequenceMatcher
# or TF-IDF, Levenshtein distance

def find_matching_proposal(snapshot_title, onchain_proposals):
    best_match = max(onchain_proposals, 
                     key=lambda p: SequenceMatcher(None, snapshot_title, p.title).ratio())
    return best_match if ratio > 0.8 else None
```

**Pros**: Automated, scalable
**Cons**: Titles may differ significantly, false positives/negatives

### 3. Temporal Heuristics

Group proposals by time windows:

```python
# If onchain proposal created within N days after Snapshot ends → likely related
WINDOW_DAYS = 14

for snapshot_proposal in snapshot_proposals:
    snapshot_end = snapshot_proposal.end_timestamp
    candidates = [p for p in onchain_proposals 
                  if 0 < (p.created - snapshot_end).days < WINDOW_DAYS]
```

**Pros**: Simple, catches most cases
**Cons**: Multiple proposals may fall in same window, misses delayed proposals

### 4. External Data Sources (Recommended)

#### Tally API

Tally maintains cross-references between governance stages:

```graphql
query {
  proposals(input: { filters: { organizationId: "ENS_ORG_ID" } }) {
    nodes {
      ... on Proposal {
        onchainId
        metadata {
          title
          snapshotURL      # Direct link to Snapshot proposal
          discourseURL     # Link to forum discussion
        }
      }
    }
  }
}
```

**Key field**: `ProposalMetadata.snapshotURL` links onchain proposals to Snapshot

**Pros**: Authoritative, maintained by Tally, includes forum links
**Cons**: Requires API key (free), rate limited, may not cover all proposals

#### ENS Governance Docs

ENS maintains official governance documentation with proposal mappings.

### 5. Synthetic Case ID

Create unified case ID from normalized proposal topic:

```python
import hashlib
import re

def normalize_title(title):
    # Remove EP numbers, whitespace, lowercase
    return re.sub(r'ep\d+\.?\d*\s*[-:]?\s*', '', title.lower()).strip()

def synthetic_case_id(title):
    return hashlib.md5(normalize_title(title).encode()).hexdigest()[:12]
```

**Pros**: Deterministic, works across sources
**Cons**: Requires consistent naming, sensitive to title variations

## Recommended Approach

1. **Primary**: Use Tally API to fetch `snapshotURL` cross-references
2. **Fallback**: Title similarity matching for proposals not in Tally
3. **Validation**: Temporal proximity check to verify matches

## Implementation Plan

1. Obtain Tally API key (free): https://www.tally.xyz/user/settings
2. Query ENS organization to get `organizationId`
3. Fetch all proposals with metadata including `snapshotURL`
4. Extract Snapshot IDs from URLs and create mapping table
5. Update `export_pm4py.py` to use unified case IDs
6. Re-export with connected onchain/offchain events

## Expected Outcome

After linking, the event log will show complete governance lifecycle:

```
Case: EP5.1-Endowment-Fund
├── voting_started (Snapshot)
├── proposal (Snapshot) 
├── vote × N (Snapshot)
├── voting_ended (Snapshot)
├── ProposalCreated (Onchain)
├── VoteCast × M (Onchain)
├── ProposalQueued (Onchain)
└── ProposalExecuted (Onchain)
```

This enables process mining analysis across the full governance lifecycle.

---

## Implementation Results

### Temporal + Title Similarity Matching (Implemented)

Script: `link_proposals.py`

#### Approach
1. **Primary**: Temporal proximity matching (onchain starts within 21 days after snapshot ends)
2. **Secondary**: Title similarity scoring using `SequenceMatcher` (for validation when titles available)
3. **Unified IDs**: Generated from proposal titles (e.g., `EP11-end-the-$ens-and-airdrops`)

#### ENS DAO Results

```
Total events: 134,402
Unique cases: 126

Linking Results:
  Snapshot proposals analyzed: 89
  Linked to onchain: 55 (61.8%)
  Snapshot-only: 34

Case Breakdown:
  Full governance flow (snapshot→onchain): 19
  Snapshot only (social votes): 70
  Onchain only (not linked): 37
```

#### Example Linked Flow

```
Case: EP11-end-the-$ens-and-airdrops
Title: [EP11] [Executable] End the $ENS and EP2 airdrops

Event sequence:
  2022-04-20 23:23:41 | snapshot | voting_started
  2022-04-20 23:23:47 | snapshot | proposal
  2022-04-20 23:25:59 | snapshot | vote (×827)
  2022-04-25 23:23:41 | snapshot | voting_ended
  2022-04-25 23:57:59 | onchain  | VoteCast (×346)
  2022-05-03 05:52:43 | onchain  | ProposalQueued
  2022-05-05 06:09:23 | onchain  | ProposalExecuted
```

#### Usage

```bash
# Analyze and show matches
python extraction/link_proposals.py ens

# Export linked CSV for process mining
python extraction/link_proposals.py ens --export

# Export mapping table
python extraction/link_proposals.py ens --mapping data/mappings/ens_proposal_mapping.csv

# Adjust parameters
python extraction/link_proposals.py ens --max-days 30 --threshold 0.6
```

#### Output Files

- `ens_linked_pm4py.csv` - Events with unified case IDs
- `ens_proposal_mapping.csv` - Mapping table with match details

#### Limitations

1. **No onchain titles**: Onchain proposals don't have titles in the database, limiting title similarity matching
2. **Many-to-one relationships**: Multiple snapshot proposals may map to one bundled onchain executable
3. **37 unlinked onchain proposals**: May be direct onchain proposals without Snapshot temperature checks

### Tally API Enrichment (Implemented)

Script: `fetch_tally.py`

#### Approach

1. Query Tally GraphQL API (`https://api.tally.xyz/query`) for all ENS proposals
2. Extract `metadata.title`, `metadata.snapshotURL`, `metadata.discourseURL` per proposal
3. Enrich onchain proposals with Tally titles → enables title-similarity matching
4. Re-run `link_proposals.py` with enriched data

Requires `TALLY` environment variable with API key from https://www.tally.xyz/user/settings

#### Tally API Results

```
Tally ENS organization: id=2206072050458560426, slug=ens
Governor: eip155:1:0x323A76393544d5ecca80cd6ef2A560C6a395b7E3

Total Tally proposals:   62
Matched in DB (onchain): 56 / 56 (100%)
Has Snapshot URL:         2 (Tally rarely stores these cross-references)
Has Discourse URL:       21
```

#### Combined Matching Results (Temporal + Tally Titles)

```
Total events: 134,402

Matching (max_days=30):
  Snapshot proposals: 89
  Linked to onchain:  60 (67.4%)
  Snapshot-only:      29

  High-confidence title matches (sim >= 0.5): 10
  Direct Tally snapshot links:                 1
  Temporal-only matches (bundled executables): 50

Case Breakdown:
  Full governance flow (snapshot→onchain): 27
  Snapshot only (social votes):            29
  Onchain only (direct executables):       29
```

Improvement over pure temporal matching: +5 unique onchain links (19 → 27) due to
title similarity disambiguating among temporal candidates.

#### Usage

```bash
# Step 1: Fetch Tally data (requires TALLY env var)
python extraction/fetch_tally.py --full-mapping data/mappings/ens_tally_mapping.csv

# Step 2: Re-run linking (automatically loads ens_tally_mapping.csv)
python extraction/link_proposals.py ens --max-days 30 --export --mapping data/mappings/ens_proposal_mapping.csv
```

#### Output Files

- `ens_tally_mapping.csv` - Raw Tally API export (onchain_id, title, snapshot_url, discourse_url)
- `ens_proposal_mapping.csv` - Combined mapping with Tally titles, discourse URLs, similarity scores
- `ens_linked_pm4py.csv` - Events with unified case IDs for process mining

#### Why 29 Onchain Proposals Remain Unlinked

These are direct executables without Snapshot temperature checks:
endowment funding, ETH-to-USDC conversions, controller upgrades, karpatkey permissions, etc.
They go directly to onchain governance per ENS rules. Discourse URLs from Tally provide
forum discussion links for many of these.

#### Future Improvements

1. Decode `ProposalCreated` event data to extract descriptions from blockchain
2. Use ENS governance documentation for manual validation of edge cases
3. Periodically refresh Tally data to capture new proposals
