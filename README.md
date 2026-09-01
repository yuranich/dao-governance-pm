# DAO Governance Process Mining

Process mining analysis of decentralized autonomous organization (DAO) governance.
Extracts governance events from on-chain and off-chain sources, links them into
end-to-end proposal lifecycles, and compares ENS DAO and AAVE DAO against corporate
control benchmarks and UK Parliament voting patterns.

Part of a PhD thesis at ISUCT (ИГХТУ, Иваново).

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

The editable install provides the `daogov` package, which resolves every path from
the repository root. Scripts therefore run identically from any working directory.

API keys are read from the environment (`TALLY`, `GRAPH_API_KEY`); never hardcoded.

## Repository layout

| Path | Contents |
|------|----------|
| `extraction/` | Event acquisition: Snapshot GraphQL, on-chain RPC, Tally, UK Parliament |
| `analysis/` | Process mining, governance metrics, voting-mechanism simulations |
| `daogov/` | Path resolution shared by both layers |
| `data/mappings/` | On-chain ↔ off-chain proposal ID mappings (tracked) |
| `data/processed/`, `data/db/` | Event logs and DuckDB databases (not tracked) |
| `figures/` | Generated process maps and charts |
| `results/` | Analysis writeups and concentration tables |
| `docs/` | Schema, event-type spec, linking algorithm, data provenance |
| `diagrams/` | Graphviz sources for the methodology diagrams |

## Pipeline

```
Snapshot GraphQL ─┐
On-chain RPC     ─┼─→ DuckDB ─→ link_proposals ─→ build_linked_db ─→ export_pm4py ─→ *_pm4py.csv
Tally / UK API   ─┘                                                                      │
                                                                                         ▼
                                                        analysis/  →  figures/ + results/
```

Extract one DAO at a time and verify before adding more:

```bash
python extraction/extract_snapshot.py --dao ens
python extraction/extract_ankr.py --dao ens
python extraction/fetch_tally.py ens
python extraction/link_proposals.py --dao ens
python extraction/build_linked_db.py --dao ens
python extraction/export_pm4py.py ens --db data/db/ens_linked.duckdb
```

Long extractions should be wrapped with `caffeinate -i` to prevent macOS sleep.

## Analysis

Per-DAO scripts follow `{dao}_{nn}_{topic}.py`:

| Script | Topic |
|--------|-------|
| `*_01_discovery.py` | DFG, Petri nets, BPMN, process trees |
| `*_02_trace_variants.py` | Distinct governance process patterns |
| `*_03_performance.py` | Bottlenecks, dotted charts, duration distributions |
| `*_04_social_network.py` | Co-voting patterns, voter coalitions, delegation |
| `*_05_conformance_temporal.py` | Fitness, concept drift, temporal evolution |

Cross-cutting:

- `governance_metrics.py` — Gini, C1/C3/C5 concentration, Shapley-Shubik power index
- `comparative_analysis.py` — ENS / AAVE / UK Parliament vs. Aminadav & Papaioannou (2016)
- `simulation_01_quadratic.py` (VP = √VP), `simulation_02_capped.py`, `simulation_03_identity.py`

## Diagrams

```bash
make diagrams
```

Rebuilds `figures/pipeline_diagram.{svg,png}` and `figures/linking_algorithm.{svg,png}`
from the Graphviz sources in `diagrams/`. Requires `brew install graphviz`.

## Data availability

Event logs are not distributed with the repository: the AAVE log alone is ~380 MB.
They are reproducible from the extraction pipeline above using public APIs. The
small proposal-ID mappings needed for linking are tracked in `data/mappings/`.

## References

- Aminadav, G. & Papaioannou, E. (2016). Corporate Control around the World. NBER WP 23010.
- Buterin, V., Hitzig, Z. & Weyl, E. G. (2019). A Flexible Design for Funding Public Goods. *Management Science* 65(11).
- La Porta, R., Lopez-de-Silanes, F. & Shleifer, A. (1999). Corporate Ownership Around the World. *Journal of Finance* 54(2).

## License

MIT — see `LICENSE`.
