# ENS DAO Process Mining Analysis Results

## Dataset

| Property | Value |
|----------|-------|
| Events | 134,402 |
| Cases (proposals) | 110 |
| Unique voters | 91,585 |
| Date range | 2021-05-04 → 2025-12-26 |
| Sources | Snapshot (126,041 events), Onchain (8,361 events) |

Activity breakdown:

| Activity | Count |
|----------|-------|
| vote (Snapshot) | 125,774 |
| VoteCast (Onchain) | 8,259 |
| proposal | 89 |
| voting_started | 89 |
| voting_ended | 89 |
| ProposalQueued | 51 |
| ProposalExecuted | 51 |

## Analysis Suite

| Script | Technique | Outputs |
|--------|-----------|---------|
| `ens_01_discovery.py` | Process discovery (DFG, Petri net, BPMN, heuristic net) | 9 PNGs |
| `ens_02_trace_variants.py` | Trace variants, incompleteness, derived activities | 2 PNGs |
| `ens_03_performance.py` | Performance mining, timing, bottlenecks | 4 PNGs |
| `ens_04_social_network.py` | Organizational mining, voter cohorts, coalitions | text |
| `ens_05_conformance_temporal.py` | Conformance checking, concept drift, temporal evolution | 4 PNGs |

## Key Findings

### 1. Two Distinct Governance Sub-Processes with Zero Cross-Execution

Simplified trace analysis reveals the process naturally decomposes into two disjoint sub-processes:

- **Snapshot path**: `proposal → voting_started → vote → voting_ended` — soft signaling, **0% execution rate**
- **Onchain path**: `VoteCast → ProposalQueued → ProposalExecuted` — **91.1% execution rate**
- **Linked proposals** (27 of 110 cases) bridge both paths: `… → vote → voting_ended → VoteCast → ProposalQueued → ProposalExecuted`

54 of 110 proposals are snapshot-only and never reach execution. This is not a process failure — it reflects a designed two-tier governance architecture where Snapshot serves as a signaling/temperature-check layer.

Only 11 simplified trace patterns exist across 110 proposals, with the top 3 covering 73% of all cases:

| Pattern | Count |
|---------|-------|
| `proposal → voting_started → vote → voting_ended` | 36 |
| `VoteCast → ProposalQueued → ProposalExecuted` | 26 |
| `voting_started → proposal → vote → voting_ended` | 18 |

### 2. Extreme Voting Power Concentration (Gini = 0.967)

| Metric | Value |
|--------|-------|
| Gini coefficient (total VP cast) | 0.9674 |
| Gini coefficient (max VP) | 0.7117 |
| Top 1% VP share | 94.5% |
| Top 10% VP share | 95.9% |
| Whale voters (VP ≥ 10,000) | 180 (0.2% of voters) |
| Whale VP share | 93.0% |
| Median whale VP share per proposal | 98.9% |
| Proposals with whale share > 50% | 105 of 110 |

The process structurally resembles direct democracy (thousands of voters) but functionally behaves as oligarchic governance. 0.2% of participants control 93% of voting power.

### 3. Front-Loaded Voting with Long Tail

| Metric | Value |
|--------|-------|
| Votes in first quarter of window | 38.5% (mean) |
| Votes in last quarter of window | 26.6% (mean) |
| Votes in first half of window | 56.6% (mean) |
| Time to first vote after voting starts | 0.18h median (~11 min) |
| Window position at 50% of total VP | 59.1% (median) |

Votes arrive quickly but VP accumulates more slowly. Small voters are early movers; whales tend to vote later in the window.

### 4. Governance Maturation Over Time

| Year | Cases | Exec Rate | Avg Votes/Proposal | Avg Voters/Proposal |
|------|-------|-----------|--------------------|---------------------|
| 2021 | 8 | 12.5% | 11,615 | 11,615 |
| 2022 | 32 | 31.2% | 568 | 551 |
| 2023 | 22 | 40.9% | 652 | 545 |
| 2024 | 25 | 56.0% | 182 | 170 |
| 2025 | 23 | 73.9% | 175 | 168 |

Execution rate increased from 12.5% to 73.9% while participation per proposal dropped by ~98%. Governance consolidated: fewer participants, more proposals reaching execution. The 2021 peak was driven by the ENS airdrop and constitutional ratification.

### 5. No Concept Drift (Process Stability)

Cross-conformance testing — training a Petri net on early cases (pre-Nov 2023) and replaying late traces against it:

| Test | Fitness |
|------|---------|
| Early model → early traces | 1.0000 |
| Early model → late traces | 0.9998 |

Fitness delta of 0.0002 indicates the process is structurally **stable** across the full observation period. What changed is participation volume and the ratio of snapshot-to-onchain proposals, not the process flow itself.

Both snapshot and onchain sub-processes individually achieve perfect fitness (1.0000) against their respective inductive models.

### 6. Massive Voter Attrition

| Segment | Voters | % of Total | VP Share | Avg Proposals |
|---------|--------|------------|----------|---------------|
| One-time | 82,388 | 90.0% | 5.3% | 1.0 |
| Casual (2–4) | 6,440 | 7.0% | 2.1% | 2.4 |
| Regular (5–14) | 2,111 | 2.3% | 6.5% | 8.0 |
| Active (15–29) | 507 | 0.6% | 11.8% | 19.5 |
| Power voter (30+) | 139 | 0.2% | 74.4% | 42.8 |

The 2021 Q4 cohort (83,123 voters from the airdrop) shows severe attrition: by 2022 Q1, only 919 remained active (98.9% drop). Returning voter rates stabilize around 60–80% in later quarters, but absolute numbers drop from tens of thousands to hundreds.

### 7. Co-Voting Coalitions Among Top Voters

Among the top 100 voters by VP, certain pairs co-vote in 65–66% of all proposals. The tightest co-voting pairs appear in 73 of 110 proposals (66.4% overlap). These patterns suggest coordinated delegates, multi-sig members, or formally aligned voting blocs.

### 8. Bottleneck: Voting End → Queue Transition

| Transition | Mean Duration |
|------------|---------------|
| voting_ended → VoteCast | 26.8 days |
| voting_ended → voting_started (re-proposal) | 10.1 days |
| ProposalQueued → ProposalExecuted | 3.0 days |
| VoteCast → ProposalQueued | 1.1 days |
| proposal → voting_started | 3.0 hours |

The 26.8-day gap between Snapshot signal completion and on-chain proposal submission is the single largest transition time in the DFG. This is a manual human-driven bottleneck with high variance (174h to 2,284h). Queue → Execution is a fixed ~3 day timelock.

## Performance Comparison: Executed vs Non-Executed Proposals

| Metric | Executed | Not Executed |
|--------|----------|--------------|
| Time to first vote (h) | 0.4 | 0.9 |
| Voting window (h) | 119.9 | 129.2 |
| First→last vote span (h) | 531.8 | 156.1 |
| Number of votes | 400 | 1,926 |
| Total voting power | 2,818,250 | 2,566,716 |

Non-executed proposals actually attract more votes on average (1,926 vs 400) because high-participation Snapshot signaling polls dominate the non-executed set. Executed proposals have a longer first-to-last vote span because they include both the Snapshot voting phase and the subsequent on-chain voting phase.

## Derived Activities

Enriching the log with derived activity labels:

| Derived Activity | Count |
|------------------|-------|
| VoteSnapshot | 125,774 |
| VoteByDelegate (≥5 proposals) | 35,552 |
| VoteOnchain | 8,259 |
| VoteByWhale (VP ≥ 10,000) | 3,972 |
| VoteInFirstHour | 922 |
| VoteInLastHour | 435 |
| FirstVote | 110 |

## Generated Visualizations

### Process Discovery (Script 1)
- `out_01_dfg_full.png` — DFG for the full event log
- `out_01_dfg_performance.png` — Performance-annotated DFG
- `out_01_petri_net.png` — Petri net (inductive miner)
- `out_01_bpmn.png` — BPMN model
- `out_01_process_tree.png` — Process tree
- `out_01_heuristic_net.png` — Heuristic net
- `out_01_dfg_snapshot.png` — DFG for Snapshot events only
- `out_01_dfg_onchain.png` — DFG for onchain events only
- `out_01_dfg_linked.png` — DFG for linked (both-source) proposals

### Trace Analysis (Script 2)
- `out_02_dfg_enriched.png` — DFG with derived activities included
- `out_02_dfg_derived_only.png` — DFG of derived activities only

### Performance Mining (Script 3)
- `out_03_perf_dfg.png` — Performance DFG
- `out_03_dotted_chart.png` — Dotted chart (events over time per case)
- `out_03_case_duration.png` — Case duration distribution
- `out_03_events_over_time.png` — Events distribution over time

### Conformance & Temporal (Script 5)
- `out_05_petri_snapshot.png` — Petri net for Snapshot sub-process
- `out_05_petri_onchain.png` — Petri net for onchain sub-process
- `out_05_dfg_early.png` — DFG for early period (pre-Nov 2023)
- `out_05_dfg_late.png` — DFG for late period (post-Nov 2023)
