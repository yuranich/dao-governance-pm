# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code
in this repository.

## Project Overview

PhD thesis research: **Process Mining Analysis of DAO Governance**. Extracts governance
event data from on-chain/off-chain sources, links them, exports to pm4py format, runs
process mining analysis, and produces comparative governance metrics for thesis chapters
(written in Russian).

## Environment Setup

```bash
source venv/bin/activate
pip install -r requirements.txt
pip install -e .            # provides the daogov package
```

`pip install -e .` is not optional: every script imports `daogov.paths` for path
resolution. Without it they fail at import.

API keys live in `~/.zshrc` (`TALLY`, `GRAPH_API_KEY`) — never hardcode them.

## Running Scripts

Scripts resolve all paths from the repo root via `daogov.paths`, so the working
directory does not matter.

```bash
# Long-running extractions — wrap with caffeinate to prevent macOS sleep
caffeinate -i python extraction/extract_ankr.py --dao uniswap

# Incremental workflow: one DAO at a time, verify before adding more
python extraction/extract_snapshot.py --dao ens
python extraction/extract_ankr.py --dao ens
python extraction/link_proposals.py --dao ens
python extraction/build_linked_db.py --dao ens
python extraction/export_pm4py.py ens --db data/db/ens_linked.duckdb

# Analysis scripts are numbered by topic
python analysis/ens_01_discovery.py
python analysis/governance_metrics.py
python analysis/comparative_analysis.py
```

No formal test runner or linter is configured.

## Architecture

### Data Flow

```
APIs (Snapshot GraphQL, RPC, UK Parliament, Tally)
  → extraction/*.py
    → data/db/dao_events.duckdb ({dao_slug}_events tables)
      → link_proposals.py    (temporal + title similarity linking)
        → export_pm4py.py    (→ data/processed/*_linked_pm4py.csv)
          → analysis/*_01-05.py
            → governance_metrics.py + comparative_analysis.py
              → results/ + figures/  → thesis/chapters/*.md (Russian, gitignored)
```

### `daogov/` — path resolution

`paths.py` is the single source of truth. `REPO_ROOT` is derived from `__file__`,
never from the working directory. Use `event_log()`, `linked_db()`, `mapping()`,
`figure()`, `result()` instead of writing bare filenames.

`shard_db()` and `shard_glob()` must always change together — `extract_ankr.py`
writes shards with one and finds them with the other.

### `extraction/` — data acquisition

- **`db.py`** — DuckDB schema: `{dao_slug}_events` with columns `id, source, event_type,
  timestamp, proposal_id, proposal_title, proposal_author, proposal_state, voter,
  voting_power, choice, tx_hash, block_number, log_index, contract_address, raw_data`.
  Batch inserts of 10k rows; 3 indexes per table.
- **`dao_config.py`** — 10+ DAO configs (Uniswap, ENS, Compound, Aave, MakerDAO,
  Optimism, Gitcoin, Arbitrum, Nouns, Lido) with Governor contract addresses.
- **`ankr_onchain_extractor.py`** — on-chain extraction via public RPCs (LlamaRPC, PublicNode).
- **`snapshot_extractor.py`** — off-chain Snapshot GraphQL votes/proposals.
- **`fetch_tally.py`** — produces `data/mappings/{dao}_tally_mapping.csv`, consumed by
  `link_proposals.py` and `build_linked_db.py`.
- **`link_proposals.py`** — links Snapshot and Governor proposals using a 21-day temporal
  window plus SequenceMatcher title similarity.
- **`export_pm4py.py`** — exports pm4py CSV: `case:concept:name, concept:name,
  time:timestamp, org:resource, case:proposal_title, case:proposal_author`.

### `analysis/` — process mining

Scripts follow `{dao}_{nn}_{topic}.py`; see README for the topic table. Figure output
goes to `figures/` via `OUT_PREFIX`; textual results go to `results/` via `result()`.

**`governance_metrics.py`** — shared module: Gini coefficient, C1/C3/C5 concentration
indices, Shapley-Shubik power index (Monte Carlo, 10k samples).

### Canonical Data Files

| File | Events | Proposals | Voters |
|------|--------|-----------|--------|
| `data/processed/ens_linked_pm4py.csv` | 134,402 | 110 | 91,585 |
| `data/processed/aave_linked_pm4py.csv` | 3,198,485 | 906 | 83,422 |
| `data/processed/uk_parliament_pm4py.csv` | ~118,000 | 42 | 1,241 |

## Critical Domain Knowledge

- **Snapshot 0% execution rate is by design** — it is a signaling/temperature-check
  mechanism, not a broken pipeline. Do not treat this as a data error.
- **AAVE has three governance eras** (v1→v2→v3 migrations) that cause data artifacts.
  Execution rates look artificially low if only old contracts are used.
- **Use the paper's own methodology** for comparisons — C1/C3/C5 and Shapley-Shubik from
  Aminadav & Papaioannou (2016) benchmarks (26,843 firms, 85 countries). Do not fabricate
  or substitute metrics.
- **Process mining contribution must be explicit**: what can pm4py reveal about governance
  that pure statistics cannot?
- **Thesis is written in Russian** — all thesis chapter content, citations, and analysis
  narratives should be in Russian. Cite 1-2 papers per subsection.

## The `thesis/` directory

`thesis/` is gitignored in full: chapters, autoreferat, reviews, personal and
administrative documents, reference PDFs, and the tooling that builds them
(`thesis/tools/`, `thesis/skill/`). Nothing under it is ever committed. Keep it that way —
the dissertation must not be public before the defense.

## Key Documentation

- `docs/SCHEMA.md` — DuckDB table structure
- `docs/EXTRACTION_SPEC.md` — event type definitions
- `docs/LINKING_ONCHAIN_OFFCHAIN.md` — linking algorithm details
- `docs/COMPARISON_DATA_SOURCES.md` — data provenance
- `results/ANALYSIS_FINDINGS.md` — ENS key findings
