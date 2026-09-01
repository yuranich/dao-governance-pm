#!/usr/bin/env python3
"""
ENS DAO Process Mining — Script 4: Organizational Mining & Social Network Analysis

Analyses:
 - Handover-of-work / working-together / similar-activities SNA
 - Voter cohort analysis (whales, delegates, casual, power voters)
 - Co-voting coalitions and Gini coefficient
 - Voter loyalty / retention over time
"""

import pandas as pd
import numpy as np
import pm4py
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

from daogov.paths import event_log, FIGURES_DIR

FILE_PATH = event_log('ens_linked')
OUT_PREFIX = f"{FIGURES_DIR}/ens_out_04_"
WHALE_VP = 10_000
DELEGATE_MIN = 5

df = pd.read_csv(FILE_PATH)
df['time:timestamp'] = pd.to_datetime(df['time:timestamp'])
df = pm4py.format_dataframe(
    df,
    case_id='case:concept:name',
    activity_key='concept:name',
    timestamp_key='time:timestamp',
)

print("=" * 72)
print("SCRIPT 4 — ORGANIZATIONAL MINING & SOCIAL NETWORK ANALYSIS")
print("=" * 72)

df_votes = df[df['concept:name'].isin(['vote', 'VoteCast'])].dropna(subset=['org:resource']).copy()

# ── 1. SNA metrics via pm4py ─────────────────────────────────────────────
print("\n" + "-" * 72)
print("1. SOCIAL NETWORK METRICS (pm4py)")
print("-" * 72)

log = pm4py.convert_to_event_log(df)

for metric_name, metric_fn in [
    ('handover_of_work', pm4py.discover_handover_of_work_network),
    ('working_together', pm4py.discover_working_together_network),
    ('subcontracting', pm4py.discover_subcontracting_network),
]:
    try:
        sna = metric_fn(log)
        n_edges = sum(1 for row in sna for v in row if v > 0)
        print(f"\n  {metric_name}: matrix {len(sna)}×{len(sna[0]) if sna else 0}, "
              f"{n_edges} non-zero edges")
    except Exception as e:
        print(f"\n  {metric_name}: skipped ({e})")

# ── 2. Voter segmentation ────────────────────────────────────────────────
print("\n" + "-" * 72)
print("2. VOTER SEGMENTATION")
print("-" * 72)

voter_stats = df_votes.groupby('org:resource').agg(
    n_votes=('case:concept:name', 'count'),
    n_proposals=('case:concept:name', 'nunique'),
    total_vp=('voting_power', 'sum'),
    mean_vp=('voting_power', 'mean'),
    max_vp=('voting_power', 'max'),
    first_vote=('time:timestamp', 'min'),
    last_vote=('time:timestamp', 'max'),
).reset_index()

voter_stats['tenure_days'] = (voter_stats['last_vote'] - voter_stats['first_vote']).dt.total_seconds() / 86400

# Segment
voter_stats['segment'] = 'One-time'
voter_stats.loc[voter_stats['n_proposals'] >= 2, 'segment'] = 'Casual'
voter_stats.loc[voter_stats['n_proposals'] >= 5, 'segment'] = 'Regular'
voter_stats.loc[voter_stats['n_proposals'] >= 15, 'segment'] = 'Active'
voter_stats.loc[voter_stats['n_proposals'] >= 30, 'segment'] = 'Power voter'

# Whale flag
voter_stats['is_whale'] = voter_stats['max_vp'] >= WHALE_VP

total_voters = len(voter_stats)
total_vp_all = voter_stats['total_vp'].sum()

print(f"\nTotal unique voters: {total_voters:,}")
print(f"\nSegmentation:")
for seg in ['One-time', 'Casual', 'Regular', 'Active', 'Power voter']:
    sub = voter_stats[voter_stats['segment'] == seg]
    pct_voters = len(sub) / total_voters * 100
    pct_vp = sub['total_vp'].sum() / total_vp_all * 100
    print(f"  {seg:<14s}  {len(sub):>6,} voters ({pct_voters:>5.1f}%)  "
          f"VP share: {pct_vp:.1f}%  "
          f"Avg proposals: {sub['n_proposals'].mean():.1f}")

n_whales = voter_stats['is_whale'].sum()
whale_vp = voter_stats[voter_stats['is_whale']]['total_vp'].sum()
print(f"\nWhales (VP ≥ {WHALE_VP:,}): {n_whales} voters ({n_whales/total_voters*100:.1f}%)")
print(f"  VP share: {whale_vp/total_vp_all*100:.1f}%")

# ── 3. Gini coefficient & Lorenz curve data ──────────────────────────────
print("\n" + "-" * 72)
print("3. VOTING POWER INEQUALITY")
print("-" * 72)

def gini(values):
    v = np.sort(np.array(values, dtype=float))
    n = len(v)
    idx = np.arange(1, n + 1)
    return (2 * np.sum(idx * v) - (n + 1) * np.sum(v)) / (n * np.sum(v))

g_total = gini(voter_stats['total_vp'].values)
g_max = gini(voter_stats['max_vp'].values)

print(f"\n  Gini (total VP cast):  {g_total:.4f}")
print(f"  Gini (max VP):         {g_max:.4f}")
print(f"  (1.0 = perfect inequality)")

# Power-law concentration
sorted_vp = voter_stats['total_vp'].sort_values(ascending=False).values
cum = np.cumsum(sorted_vp)
total = cum[-1]
for pct in [1, 5, 10, 20, 50]:
    k = max(1, int(len(sorted_vp) * pct / 100))
    share = cum[k-1] / total * 100
    print(f"  Top {pct:>2}% of voters hold {share:.1f}% of total VP cast")

# ── 4. Co-voting coalitions ──────────────────────────────────────────────
print("\n" + "-" * 72)
print("4. CO-VOTING COALITIONS")
print("-" * 72)

# Use top-N voters by VP for tractability
TOP_N = 100
top_voters = set(voter_stats.nlargest(TOP_N, 'total_vp')['org:resource'])

proposal_voters = df_votes.groupby('case:concept:name')['org:resource'].apply(set).to_dict()

co_votes = defaultdict(int)
total_proposals = len(proposal_voters)

for cid, voters in proposal_voters.items():
    top_in = sorted(voters & top_voters)
    for i in range(len(top_in)):
        for j in range(i + 1, len(top_in)):
            co_votes[(top_in[i], top_in[j])] += 1

sorted_pairs = sorted(co_votes.items(), key=lambda x: -x[1])[:15]

print(f"\nTop 15 co-voting pairs (among top {TOP_N} voters by VP):")
for (v1, v2), cnt in sorted_pairs:
    overlap_pct = cnt / total_proposals * 100
    print(f"  {v1[:16]}… & {v2[:16]}…: {cnt} proposals ({overlap_pct:.1f}%)")

# ── 5. Voter retention / cohort analysis ─────────────────────────────────
print("\n" + "-" * 72)
print("5. VOTER RETENTION BY COHORT")
print("-" * 72)

df_votes_ts = df_votes.copy()
df_votes_ts['year_q'] = df_votes_ts['time:timestamp'].dt.to_period('Q')

# First quarter each voter appeared
voter_first_q = df_votes_ts.groupby('org:resource')['year_q'].min().rename('cohort')
df_votes_ts = df_votes_ts.merge(voter_first_q, left_on='org:resource', right_index=True)

# For each cohort, count active voters in each subsequent quarter
cohorts = df_votes_ts.groupby(['cohort', 'year_q'])['org:resource'].nunique().unstack(fill_value=0)

print(f"\nCohort retention matrix (new voters per quarter → active in future quarters):")
print(f"{'Cohort':<10s}", end='')
quarters = sorted(cohorts.columns)
for q in quarters[:8]:
    print(f"  {str(q):>8s}", end='')
print("  …" if len(quarters) > 8 else "")

for cohort_q in sorted(cohorts.index)[:10]:
    row = cohorts.loc[cohort_q]
    print(f"{str(cohort_q):<10s}", end='')
    for q in quarters[:8]:
        print(f"  {row.get(q, 0):>8}", end='')
    print()

# New vs returning voters per quarter
new_voters_per_q = voter_first_q.value_counts().sort_index()
active_per_q = df_votes_ts.groupby('year_q')['org:resource'].nunique()

print(f"\nQuarterly voter dynamics:")
print(f"{'Quarter':<10s} {'New':>8s} {'Active':>8s} {'Return%':>8s}")
for q in sorted(active_per_q.index):
    new = new_voters_per_q.get(q, 0)
    act = active_per_q.get(q, 0)
    ret = (act - new) / act * 100 if act > 0 else 0
    print(f"{str(q):<10s} {new:>8} {act:>8} {ret:>7.1f}%")

# ── 6. Voter activity over time (participation trend) ────────────────────
print("\n" + "-" * 72)
print("6. PARTICIPATION TREND")
print("-" * 72)

monthly_votes = df_votes_ts.groupby(df_votes_ts['time:timestamp'].dt.to_period('M')).agg(
    votes=('org:resource', 'count'),
    unique_voters=('org:resource', 'nunique'),
    proposals=('case:concept:name', 'nunique'),
)

print(f"\n{'Month':<10s} {'Votes':>8s} {'Voters':>8s} {'Proposals':>10s}")
for period, row in monthly_votes.iterrows():
    print(f"{str(period):<10s} {row['votes']:>8} {row['unique_voters']:>8} {row['proposals']:>10}")

print("\n✓ Script 4 complete")
