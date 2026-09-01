# Linking Onchain/Offchain Proposals via Tally API

## Overview

This guide describes how to link onchain Governor proposals to their offchain Snapshot temperature checks and Discourse discussions using the Tally API. The process was developed and validated on ENS DAO (62 onchain proposals, 27 full governance flows linked).

## Prerequisites

1. Event data extracted into `dao_events.duckdb` (table `{slug}_events` with both `onchain` and `snapshot` sources)
2. `TALLY` environment variable with API key from https://www.tally.xyz/user/settings

## Pipeline

### Step 1: Fetch Tally metadata

```bash
python extraction/fetch_tally.py --full-mapping data/mappings/{slug}_tally_mapping.csv
```

This queries the Tally GraphQL API (`https://api.tally.xyz/query`) and exports:
- Onchain proposal titles (not available from raw blockchain events)
- `snapshotURL` cross-references (sparse — only 2/62 for ENS)
- `discourseURL` forum discussion links (21/62 for ENS)

**Before running**, edit `fetch_tally.py` constants:

```python
ENS_GOVERNOR_ID = "eip155:{chain_id}:{governor_address}"
ENS_SLUG = "{tally_slug}"
```

### Step 2: Build linked DuckDB

```bash
python extraction/build_linked_db.py --dry-run    # verify matches
python extraction/build_linked_db.py              # write DB
```

**Before running**, edit `build_linked_db.py` constants:

```python
DAO_SLUG = "{slug}"
OUTPUT_DB = "{slug}_linked.duckdb"
TALLY_FILE = "{slug}_tally_mapping.csv"
```

Matching strategy:
1. **Tally direct links** — `snapshotURL` field maps onchain → snapshot proposal
2. **"Execute {PREFIX}{N}" pattern** — onchain titles referencing snapshot proposal numbers (ENS-specific, see below)
3. **Temporal + title similarity** — 90-day window, picks best title match (sim >= 0.4)
4. **Tight temporal bundle** — multiple snapshot social votes within 7 days before an onchain executable

### Step 3: Export for process mining

```bash
python extraction/export_pm4py.py {slug} --db data/db/{slug}_linked.duckdb -o data/processed/{slug}_linked_pm4py.csv
```

## DAO-specific configuration

| DAO | Tally slug | Governor ID | Proposals | Proposal prefix |
|---|---|---|---|---|
| ENS | `ens` | `eip155:1:0x323A76393544d5ecca80cd6ef2A560C6a395b7E3` | 62 | EP |
| Aave | `aave` | `eip155:1:0xEC568fffba86c094cf06b22134B23074DFE2252c` | 401 | AIP |
| Uniswap | `uniswap` | `eip155:1:0x408ED6354d4973f66138C91495F2f2FCbd8724C3` | 86 | — |
| Compound | `compound` | `eip155:1:0xc0Da01a04C3f3E0be433606045bB7017A7323E38` | — | — |
| Arbitrum | `arbitrum` | `eip155:42161:0x789fC99093B09aD01C34DC7251D0C89ce743e5a4` | — | AIP |
| Gitcoin | `gitcoin` | `eip155:1:0x9D4C63565D5618310271bF3F3c01b2571724C1F9` | — | — |

Tally slugs can be verified at `https://www.tally.xyz/gov/{slug}/proposals`.

## Adapting for non-ENS DAOs

The `is_execute_pattern()` function in `build_linked_db.py` matches ENS-specific titles like `"# Execute EP8, EP9 and EP10"`. Other DAOs use different patterns:

- **Aave**: AIP numbering, bundled executables are less common
- **Uniswap**: no consistent proposal prefix
- **Compound**: proposals reference CIP numbers occasionally

For a new DAO, either adjust the regex or rely on phases 1/3/4 (Tally links, title similarity, temporal bundling) which are DAO-agnostic.

## Suggested refactor

Both `fetch_tally.py` and `build_linked_db.py` currently use hardcoded constants. A future improvement would be to:

1. Accept `--dao {slug}` as a CLI argument (like `link_proposals.py` already does)
2. Look up governor address and chain from `dao_config.py`
3. Construct the Tally governor ID as `eip155:{chain_id}:{address}`
4. Derive file names automatically (`{slug}_tally_mapping.csv`, `{slug}_linked.duckdb`)

This would reduce the workflow to:

```bash
python extraction/fetch_tally.py aave --full-mapping
python extraction/build_linked_db.py aave
python extraction/export_pm4py.py aave --db data/db/aave_linked.duckdb -o data/processed/aave_linked_pm4py.csv
```

## ENS results reference

```
Tally proposals:   62
DB onchain:        56 (6 newer not in DB)
DB snapshot:       89

Linked cases:      27 full governance flows (snapshot → onchain)
Snapshot only:     54 (steward elections, social-only votes)
Onchain only:      29 (direct executables without temperature check)

Total events:      134,402
Total cases:       110
```
