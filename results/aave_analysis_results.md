# AAVE DAO Process Mining Analysis Results

Dataset: `aave_linked_pm4py.csv` (updated with governance v3 contract events)  
3,198,485 events | 906 cases (proposals) | 83,422 unique voters  
Period: 2020-09-12 → 2026-03-09  
Scripts: `aave_01_discovery.py` through `aave_05_conformance_temporal.py`

---

## 1. Dataset Structure & Three-Era Governance Architecture

The updated dataset consolidates VoteEmitted events into their parent proposals (906 cases, down from the previously fragmented 10,291), revealing a coherent three-era governance architecture:

**Activity counts:**

| Activity | Count | Description |
|---|---|---|
| vote | 3,178,541 | Snapshot off-chain votes |
| VoteEmitted | 14,732 | On-chain votes (gov v1/v2) |
| proposal | 921 | Snapshot proposal creation |
| voting_started | 921 | Snapshot voting window open |
| voting_ended | 921 | Snapshot voting window close |
| ProposalCreated | 692 | On-chain proposal creation |
| ProposalExecuted | 648 | On-chain execution |
| ProposalQueued | 637 | On-chain queue for timelock |
| **VotingActivated** | **437** | **Governance v3 activation event** |
| ProposalCanceled | 33 | Cancelled proposals |
| ProposalFailed | 2 | Failed proposals (v3) |

**Proposal routing:**
- Linked (Snapshot + onchain): 421 (46.5%)
- Onchain-only: 386 (42.6%)
- Snapshot-only: 99 (10.9%)

**Key DFG edges reveal the v3 pattern:**
- `ProposalCreated → VotingActivated`: 433 occurrences
- `VotingActivated → ProposalExecuted`: 419 occurrences

This is a clean governance v3 fast-track: proposal creation triggers automated voting activation, which leads directly to execution — bypassing the manual Snapshot flow entirely.

---

## 2. Trace Variants & Process Patterns

196 distinct simplified trace patterns across 906 cases. Far more diverse than the previous fragmented dataset.

**Top patterns:**

| Rank | Pattern | Cases | Share |
|---|---|---|---|
| 1 | `ProposalQueued` (singleton) | 304 | 33.6% |
| 2 | `proposal → voting_started → vote → voting_ended` | 73 | 8.1% |
| 3 | `proposal → vote → voting_ended → ProposalCreated → VoteEmitted → ProposalQueued → ProposalExecuted → ProposalCreated → VotingActivated → ProposalExecuted` | 65 | 7.2% |
| 4 | `proposal → vote → voting_ended → VoteEmitted → ProposalCreated → VotingActivated → ProposalExecuted` | 40 | 4.4% |
| 5 | `ProposalCreated → VotingActivated → ProposalExecuted` (v3 pure) | 30 | 3.3% |

**Coverage:**
- 50% of cases covered by top 4 patterns
- 80% by top 29 patterns  
- 95% by top 151 patterns

**Three governance process archetypes emerge:**

1. **Snapshot-to-onchain pipeline** (patterns 2-4): `proposal → vote → voting_ended → [onchain lifecycle]` — the full deliberation-to-execution flow
2. **Pure v3 governance** (pattern 5): `ProposalCreated → VotingActivated → ProposalExecuted` — automated on-chain governance without Snapshot
3. **Queue-only stubs** (pattern 1): `ProposalQueued` singletons — on-chain queue events without associated lifecycle context

**Multi-step proposals**: Pattern 3 (65 cases) shows a full cross-version governance journey: Snapshot vote → v1/v2 on-chain execution → v3 re-execution. These represent proposals that span governance version upgrades — a process mining artifact of protocol evolution.

---

## 3. Governance Funnel & Trace Incompleteness

| Stage | Count | % |
|---|---|---|
| All proposals | 906 | 100% |
| With votes | 570 | 62.9% |
| ProposalCreated | 399 | 44.0% |
| VotingActivated (v3) | 383 | 42.3% |
| Reached queue | 588 | 64.9% |
| **Executed** | **383** | **42.3%** |
| Cancelled | 32 | 3.5% |
| Failed | 2 | 0.2% |

The execution rate jumped from the previous ~3% to **42.3%** with the v3 data. The `ProposalQueued → Executed` path is now well-populated.

**Drop-off points for non-executed proposals (n=523):**
- `ProposalQueued`: 404 (77.2%) — queued but never executed
- `voting_ended`: 101 (19.3%) — Snapshot vote completed, never moved on-chain
- `ProposalCanceled`: 13 (2.5%)
- `ProposalFailed`: 1 (0.2%)

**Execution rate by governance path:**
- Has onchain events: 383/807 (47.5%)
- Snapshot-only: 0/99 (0.0%)

**Insight**: The 404 proposals stuck at `ProposalQueued` are the primary governance bottleneck. These represent proposals that entered the execution pipeline but never completed — likely awaiting timelock expiry, manual execution triggers, or superseded by newer proposals. The 101 proposals ending at `voting_ended` are Snapshot proposals that passed community vote but were never submitted on-chain.

---

## 4. Performance Mining — Timing & Bottlenecks

### Inter-activity timing

| Transition | Mean | Median |
|---|---|---|
| Proposal creation → voting start | 20.5h | 24.0h |
| Voting start → first vote | 0.20h (12 min) | 0.05h (3 min) |
| Voting window duration | 88.9h | 72.0h |
| Voting end → queue | 500.7h (20.9 days) | 183.0h (7.6 days) |
| Queue → execution | 3,469.3h (144.6 days) | 24.2h (1.0 day) |
| ProposalCreated → ProposalExecuted | 649.1h (27.0 days) | 97.9h (4.1 days) |

**Queue → execution has bimodal distribution**: median 24.2h but mean 144.6 days. Most proposals execute within ~1 day of queuing, but a long tail of proposals sit in queue for months — likely representing cross-version migration artifacts or intentionally delayed execution.

**Voting end → queue (20.9 days mean, 7.6 days median)** remains the primary human-in-the-loop bottleneck, representing the gap between Snapshot approval and on-chain submission.

### Vote arrival patterns

- **55.2%** of proposals are front-loaded (>60% of votes in first half)
- **22.7%** back-loaded
- **22.1%** balanced
- First vote arrives within **3 minutes** (median) of voting start
- 50% of VP accumulated at **52.7h median** into the window

**Compared to previous analysis:** The front-loading percentage dropped from 65.4% to 55.2% — the v3 data includes more proposals with balanced vote distribution, suggesting the governance maturation included healthier deliberation patterns.

### VP accumulation dynamics

- 50% of VP reached at **68%** of voting window (median)
- Only **5.8%** of proposals decided in first 10% of window (down from 10.7%)

**This is a significant shift**: with the complete data, AAVE governance appears less "pre-determined" than the previous analysis suggested. VP accumulation is spread more evenly across the voting window.

---

## 5. Bottleneck Comparison: Executed vs. Non-Executed

| Metric | Executed | Not executed |
|---|---|---|
| Voting start → first vote (h) | -0.1 | 0.6 |
| Voting window (h) | 89.0 | 88.7 |
| First → last vote (h) | 862.7 | 284.0 |
| Number of votes | **6,769** | **1,149** |
| Total VP | 912,305 | **1,462,143** |

**Reversal from previous analysis**: Non-executed proposals now show *higher* total VP than executed ones (1.46M vs 0.91M). This is because the v3 data added many automated `ProposalCreated → VotingActivated → ProposalExecuted` flows that execute with lower VP (no community vote). The high-VP Snapshot proposals that fail to execute drag the non-executed VP average up.

Executed proposals still receive **5.9x more individual votes** — broad participation, not just VP magnitude, predicts execution.

---

## 6. Voting Power Inequality

| Metric | Value |
|---|---|
| Gini (total VP cast) | **0.9995** |
| Gini (max VP per voter) | 0.9987 |
| Gini (per-vote VP) | 0.9985 |

### Concentration

| Top % of voters | Addresses | Share of total VP |
|---|---|---|
| Top 0.1% | 83 | **96.2%** |
| Top 1% | 834 | 99.9% |
| Top 5% | 4,171 | ~100% |

**91 whale addresses (0.1% of 83,422 voters) hold 69.2% of VP.**

### Whale dominance — updated

| Category | Execution rate |
|---|---|
| Whale-dominant (>50% VP) | **60.6%** (269/444) |
| Non-whale-dominant | **66.7%** (84/126) |

**Previous paradox weakened but persists**: Non-whale-dominant proposals still execute at a moderately higher rate (66.7% vs 60.6%). The gap narrowed from 21.5 percentage points to 6.1 pp with the complete data. The v3 automated proposals (which execute regardless of whale share) diluted the effect, but the directional finding holds: proposals with more distributed voting are more likely to reach execution.

---

## 7. Voter Segmentation & Cohort Analysis

### Segmentation

| Segment | Voters | % | VP share | Avg proposals | Avg tenure |
|---|---|---|---|---|---|
| One-time | 15,618 | 18.7% | 2.6% | 1.0 | 0d |
| Casual (2-4) | 13,791 | 16.5% | 2.2% | 2.8 | 91d |
| Regular (5-14) | 22,274 | 26.7% | 4.6% | 9.3 | 157d |
| Active (15-29) | 8,818 | 10.6% | 6.6% | 20.7 | 244d |
| Power (30-99) | 9,517 | 11.4% | 11.4% | 53.4 | 343d |
| **Super (100+)** | **13,404** | **16.1%** | **72.5%** | **122.7** | **326d** |

**18.0% of voters are single-day participants, only 10.7% have tenure > 1 year.**

### Retention dynamics

Peak activity: Q1 2023 (17,595 new voters, 35,408 active). By Q1 2026: 38 new voters, 323 active.

**Returning voter % in 2024-2025 consistently above 83-95%**, indicating a consolidated core electorate. The DAO transitioned from growth mode (2021-2023) to steady state (2024+).

---

## 8. Temporal Evolution & Concept Drift

### Cross-conformance

| Model source | Fitness on EARLY | Fitness on LATE |
|---|---|---|
| EARLY model | 1.0000 | 0.9997 |
| **LATE model** | **0.9644** | **1.0000** |

**Asymmetric concept drift detected**: The late model cannot fully explain early traces (fitness 0.9644), but the early model handles late traces well (0.9997). This means the late governance process is a **strict superset** of the early process — new activities were added (VotingActivated, ProposalFailed) without removing existing ones. The governance evolved by *extension*, not *replacement*.

### Yearly governance evolution

| Year | Cases | Exec | Exec% | v3 events | Avg votes | Avg voters | Avg VP |
|---|---|---|---|---|---|---|---|
| 2020 | 3 | 2 | 66.7% | 2 | 103 | 103 | 9.3M |
| 2021 | 71 | 48 | 67.6% | 49 | 709 | 683 | 220K |
| 2022 | 123 | 73 | 59.3% | 74 | 3,307 | 2,915 | 484K |
| **2023** | **244** | **212** | **86.9%** | **209** | **10,443** | **8,659** | **1.05M** |
| 2024 | 218 | 7 | 3.2% | 7 | 713 | 279 | 752K |
| 2025 | 195 | 15 | 7.7% | 16 | 162 | 72 | 559K |
| 2026 | 52 | 26 | 50.0% | 26 | 16 | 16 | 123K |

**2023 was the governance apex**: 86.9% execution rate, 10K+ avg votes, highest VP. The 2024 crash to 3.2% execution with the v3 data filled in likely reflects the timelock/queue backlog, not governance failure.

**2024-2025 pattern shift**: `ProposalQueued` becomes the dominant terminal activity (68-69% of cases). These represent proposals that entered the queue but hadn't been executed at the time of data extraction — possibly awaiting timelock expiry or manual payloads.

### Trace variant stability

- **2021-2023**: Dominated by the Snapshot-to-onchain pipeline (`proposal → vote → voting_ended → ProposalCreated → VoteEmitted → ProposalQueued → ProposalExecuted → ProposalCreated → VotingActivated → ProposalExecuted`)
- **2024-2025**: `ProposalQueued` singleton dominates (68-69%), pure v3 `ProposalCreated → VotingActivated → ProposalExecuted` emerges
- **2026**: Balanced between `ProposalQueued` (40%), v3 pure (40%), and Snapshot pipeline (10%)

### Activity set evolution

Key milestone: `VotingActivated` appears in 2024 data (218 events), confirming governance v3 deployment. By 2025, `VotingActivated` (191) nearly equals `ProposalCreated` (201), showing v3 is the dominant execution path.

---

## 9. Co-Voting Coalitions

Top co-voting rate among top-50 VP voters: **41.9%** (down from 53.8% in previous data). Four addresses consistently co-vote at >38%:
- `0x070341aA5E…` & `0xB933AEe47C…`: 239/570 proposals (41.9%)
- `0x070341aA5E…` & `0x329c54289F…`: 234 (41.1%)
- `0x329c54289F…` & `0xea172676E4…`: 223 (39.1%)

Mean co-voting rate: 6.0%, median 2.5%. A small cluster of ~5 addresses forms a consistent voting bloc.

---

## Summary of Key Scientific Findings (Updated)

1. **Three governance eras with distinct process models**:
   - **2020-2022**: Snapshot + on-chain v1/v2 pipeline (VoteEmitted-based)
   - **2023**: Peak maturity — highest execution rate (86.9%), most voters, highest VP
   - **2024+**: Governance v3 (`ProposalCreated → VotingActivated → ProposalExecuted`) — automated, fewer voters, streamlined

2. **Governance evolved by extension, not replacement** (asymmetric concept drift): Late model fitness on early data = 0.9644; new activities were added without removing old ones. This is detectable via cross-conformance checking.

3. **Extreme voting power inequality persists** (Gini 0.9995): 83 addresses (0.1%) control 96.2% of VP. Consistent across the updated data.

4. **Whale dominance paradox weakened but directionally stable**: Non-whale-dominant proposals still execute at modestly higher rates (66.7% vs 60.6%). Gap narrowed from 21.5pp to 6.1pp with complete data.

5. **ProposalQueued is the new primary bottleneck**: 404 proposals (77.2% of non-executed) stall at `ProposalQueued` — the governance queue has replaced the voting_end → queue gap as the critical drop-off point.

6. **Vote front-loading moderated**: 55.2% front-loaded (down from 65.4%). VP accumulation at 68% of window (up from 40%). Governance appears less pre-determined with complete data.

7. **Dramatic participation decline**: From 28K+ active voters in peak 2023 to ~300 in 2026. Returning voter % > 88% — a tiny, stable core electorate runs governance.

8. **Snapshot-only proposals never execute (0%)**: Confirms Snapshot serves as signaling/temperature-check, not binding governance. All execution requires on-chain lifecycle events.
