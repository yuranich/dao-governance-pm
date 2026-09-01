# ENS DAO Process Mining Analysis: Key Findings

## Executive Summary

Analysis of 134,402 governance events across 145 ENS DAO proposals reveals **two fundamentally distinct governance processes** with dramatically different execution characteristics, extreme voting power concentration, and front-loaded voting behavior.

---

## Dataset Overview

| Metric | Value |
|--------|-------|
| Total events | 134,402 |
| Total proposals | 145 |
| Unique voters | 91,585 |
| Date range | 2021-05-04 to 2025-12-26 |
| Total voting power cast | 295,166,967 |

---

## Key Finding 1: Dual Governance Architecture

**ENS operates two completely separate governance tracks with zero overlap:**

| Governance Type | Proposals | Execution Rate | Purpose |
|-----------------|-----------|----------------|---------|
| **Snapshot** | 89 | **0%** | Soft signaling, temperature checks |
| **Onchain** | 56 | **91.1%** | Binding execution |

### Process Models

**Snapshot Process:**
```
proposal/voting_started → vote* → voting_ended
```
- All 89 proposals terminate at `voting_ended`
- No execution mechanism - purely advisory
- Average 1,413 votes per proposal

**Onchain Process:**
```
VoteCast* → ProposalQueued → ProposalExecuted
```
- 51/56 (91%) reach execution
- 5 proposals stall at VoteCast (likely failed quorum)
- Average 147 votes per proposal (10x fewer than Snapshot)

**Insight:** The 0% Snapshot execution rate is not a failure - it's by design. Snapshot serves as a low-cost signal aggregation mechanism before expensive onchain execution.

---

## Key Finding 2: Extreme Voting Power Inequality

**Gini Coefficient: 0.967** (where 1.0 = perfect inequality)

| Concentration Metric | Value |
|---------------------|-------|
| Top 1% voters hold | 51.6% of voting power |
| Top 10% voters hold | 63.5% of voting power |
| Top-5 concentration per proposal | 47.2% average |
| Single largest voter per proposal | 13.0% average |

### Top Voters (by total VP cast across proposals)

1. `0x983110309620D91173...` - 17.5M VP across 81 proposals
2. `0xb8c2C29ee19D8307cb...` - 14.4M VP across 75 proposals  
3. `0x5BFCB4BE4d7B43437d...` - 14.1M VP across 78 proposals

**Insight:** A small cohort of ~10 addresses effectively controls governance outcomes. These appear to be delegates or large token holders who participate in nearly every proposal.

---

## Key Finding 3: Voting Coalition Patterns

Strong co-voting behavior among top voters indicates stable coalitions:

| Pair | Proposals Together |
|------|-------------------|
| `0x1D5460F8...` & `0x534631Bc...` | 80 |
| `0x534631Bc...` & `0x809FA673...` | 80 |
| `0x534631Bc...` & `0x839395e2...` | 80 |

**Insight:** The same ~5-10 addresses vote together on 75-80+ proposals, suggesting either coordination, ideological alignment, or delegation relationships.

---

## Key Finding 4: Front-Loaded Voting Dynamics

Voting behavior is heavily concentrated at the start of voting windows:

| Timing Metric | Value |
|--------------|-------|
| Time to first vote | 0.74h mean, 0.18h median |
| 50% of voting power reached | 37.2% through window |
| Votes in first quarter | 42.7% |
| Votes in last quarter | 17.7% |
| Votes in last hour | 0.3% |

**Insight:** Unlike deadline-driven systems (e.g., eBay sniping), ENS governance shows early momentum patterns. The first 10-20 minutes often define the trajectory.

---

## Key Finding 5: Voter Segmentation

| Segment | Voters | % of Total | Definition |
|---------|--------|------------|------------|
| Casual | 86,768 | 94.7% | 1-2 proposals |
| Regular | 3,370 | 3.7% | 3-9 proposals |
| Active | 1,205 | 1.3% | 10-24 proposals |
| Power Voter | 242 | 0.3% | 25+ proposals |

**Insight:** A tiny fraction (0.3%) of voters are "power voters" who participate in 25+ proposals. These 242 addresses likely include delegates and core community members.

---

## Key Finding 6: Temporal Patterns

### By Hour (UTC)
Peak voting hours: 01:00-04:00 UTC (7.9%, 7.0%, 5.8%, 5.7%)

### By Day
- **Tuesday: 45.3%** of all votes (massive spike)
- Other days: 6-16%

**Insight:** The Tuesday spike suggests coordinated governance activities, possibly aligned with DAO working group schedules or specific proposal timing patterns.

---

## Key Finding 7: Actor-Driven Classification

| Proposal Type | Count | Execution Rate |
|--------------|-------|----------------|
| Whale-coalition | 140 | 36.4% |
| Retail-driven | 4 | 0% |
| Single-whale-driven | 1 | 0% |

**Insight:** Almost all proposals (97%) are dominated by whale voting coalitions. The few retail-driven proposals (where no top-5 concentration exists) have 0% execution rate - they never make it to onchain execution.

---

## Process Model Quality Metrics

Conformance checking against discovered Inductive Miner model:

| Metric | Value |
|--------|-------|
| Token-based Replay Fitness | High |
| Precision | High |
| Simplicity | High |

The high fitness indicates the discovered models accurately represent the actual process behavior.

---

## Scientific Research Implications

### 1. Governance Inequality
The Gini coefficient of 0.967 is among the highest reported for any voting system. Compare to:
- Typical nation-state Gini (wealth): 0.3-0.6
- ENS DAO voting power: 0.967

This has implications for DAO legitimacy and decentralization claims.

### 2. Two-Phase Governance
The Snapshot → Onchain pattern represents a novel governance architecture that deserves formalization. It allows cheap signal aggregation before expensive execution.

### 3. Coalition Formation
The co-voting patterns suggest stable, persistent coalitions rather than issue-by-issue voting. This could indicate:
- Delegate capture
- Ideological alignment
- Meta-governance protocols

### 4. Early Voting Momentum
The front-loaded voting pattern contrasts with academic literature on deadline effects. This may indicate:
- Delegation (automatic early voting)
- Signaling games (early voters influence others)
- Low urgency (no sniping incentive)

---

## Scripts Created

1. **`ens_analysis.py`** - Core analysis: discovery, incompleteness, timing, derived activities
2. **`ens_deep_analysis.py`** - Extended analysis: coalitions, dynamics, success factors  
3. **`ens_visualizations.py`** - Process model export and conformance checking

## Visualizations Generated

- `ens_dfg.png` - Combined Directly-Follows Graph
- `ens_dfg_snapshot.png` - Snapshot process DFG
- `ens_dfg_onchain.png` - Onchain process DFG
- `ens_dfg_performance.png` - Performance-annotated DFG
- `ens_petri_net.png` - Petri net model
- `ens_bpmn.png` - BPMN model
- `ens_process_tree.png` - Process tree
- `ens_heuristic_net.png` - Heuristic net
- `ens_dotted_chart.png` - Event distribution over time
- `ens_case_duration.png` - Case duration distribution
- `ens_events_over_time.png` - Events over time

---

## Recommendations for Future Research

1. **Delegation network analysis**: Map explicit delegation relationships to explain co-voting
2. **Proposal content analysis**: Correlate proposal topics with voting patterns
3. **Cross-DAO comparison**: Compare ENS patterns with other DAOs (Uniswap, Compound, etc.)
4. **Temporal evolution**: Analyze how voting concentration has changed over time
5. **Quorum dynamics**: Investigate the 5 failed onchain proposals


