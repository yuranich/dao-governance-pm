#!/usr/bin/env python3
"""
AAVE DAO Process Mining — Script 4: Organizational Mining & Social Network Analysis

Analyses:
 - Voter segmentation (whales, delegates, casual, power voters)
 - Voting power inequality (Gini, Lorenz, concentration)
 - Co-voting coalitions among top voters
 - Voter retention / cohort analysis
 - Participation trends over time
"""

import pandas as pd
import numpy as np
import pm4py
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

from daogov.paths import event_log, FIGURES_DIR

FILE_PATH = event_log('aave_linked')
OUT_PREFIX = f"{FIGURES_DIR}/aave_out_04_"
WHALE_VP = 100_000
DELEGATE_MIN = 10

print("Loading data...")
df = pd.read_csv(FILE_PATH, on_bad_lines='skip')
df['time:timestamp'] = pd.to_datetime(df['time:timestamp'], errors='coerce')
df = df.dropna(subset=['time:timestamp'])
df['voting_power'] = pd.to_numeric(df['voting_power'], errors='coerce')
df = pm4py.format_dataframe(
    df,
    case_id='case:concept:name',
    activity_key='concept:name',
    timestamp_key='time:timestamp',
)

print("=" * 72)
print("SCRIPT 4 — ORGANIZATIONAL MINING & SOCIAL NETWORK ANALYSIS (AAVE)")
print("=" * 72)

df_votes = df[df['concept:name'].isin(['vote', 'VoteEmitted'])].dropna(subset=['org:resource']).copy()

# ── 1. Voter segmentation ────────────────────────────────────────────────
print("\n" + "-" * 72)
print("1. VOTER SEGMENTATION")
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

voter_stats['segment'] = 'One-time'
voter_stats.loc[voter_stats['n_proposals'] >= 2, 'segment'] = 'Casual'
voter_stats.loc[voter_stats['n_proposals'] >= 5, 'segment'] = 'Regular'
voter_stats.loc[voter_stats['n_proposals'] >= 15, 'segment'] = 'Active'
voter_stats.loc[voter_stats['n_proposals'] >= 30, 'segment'] = 'Power voter'
voter_stats.loc[voter_stats['n_proposals'] >= 100, 'segment'] = 'Super voter'

voter_stats['is_whale'] = voter_stats['max_vp'] >= WHALE_VP

total_voters = len(voter_stats)
total_vp_all = voter_stats['total_vp'].sum()

print(f"\nTotal unique voters: {total_voters:,}")
print(f"\nSegmentation:")
for seg in ['One-time', 'Casual', 'Regular', 'Active', 'Power voter', 'Super voter']:
    sub = voter_stats[voter_stats['segment'] == seg]
    if sub.empty:
        continue
    pct_voters = len(sub) / total_voters * 100
    pct_vp = sub['total_vp'].sum() / total_vp_all * 100
    avg_tenure = sub['tenure_days'].mean()
    print(f"  {seg:<14s}  {len(sub):>6,} voters ({pct_voters:>5.1f}%)  "
          f"VP share: {pct_vp:>5.1f}%  "
          f"Avg proposals: {sub['n_proposals'].mean():>5.1f}  "
          f"Avg tenure: {avg_tenure:>6.0f}d")

n_whales = voter_stats['is_whale'].sum()
whale_vp = voter_stats[voter_stats['is_whale']]['total_vp'].sum()
print(f"\nWhales (VP ≥ {WHALE_VP:,}): {n_whales} voters ({n_whales/total_voters*100:.1f}%)")
print(f"  VP share: {whale_vp/total_vp_all*100:.1f}%")

# ── 2. Gini coefficient & power-law concentration ────────────────────────
print("\n" + "-" * 72)
print("2. VOTING POWER INEQUALITY")
print("-" * 72)

def gini(values):
    v = np.sort(np.array(values, dtype=float))
    v = v[v > 0]
    n = len(v)
    if n == 0:
        return 0
    idx = np.arange(1, n + 1)
    return (2 * np.sum(idx * v) - (n + 1) * np.sum(v)) / (n * np.sum(v))

g_total = gini(voter_stats['total_vp'].values)
g_max = gini(voter_stats['max_vp'].values)
g_per_vote = gini(df_votes['voting_power'].dropna().values)

print(f"\n  Gini (total VP cast per voter):     {g_total:.4f}")
print(f"  Gini (max VP per voter):             {g_max:.4f}")
print(f"  Gini (individual vote VP):           {g_per_vote:.4f}")
print(f"  (1.0 = perfect inequality)")

sorted_vp = voter_stats['total_vp'].sort_values(ascending=False).values
cum = np.cumsum(sorted_vp)
total = cum[-1]
print(f"\nConcentration (total VP cast):")
for pct in [0.1, 1, 5, 10, 20, 50]:
    k = max(1, int(len(sorted_vp) * pct / 100))
    share = cum[k-1] / total * 100
    print(f"  Top {pct:>4}% of voters ({k:>5} addresses) hold {share:>5.1f}% of total VP cast")

# Participation concentration
sorted_props = voter_stats['n_proposals'].sort_values(ascending=False).values
cum_p = np.cumsum(sorted_props)
total_p = cum_p[-1]
print(f"\nConcentration (proposal participation):")
for pct in [1, 5, 10]:
    k = max(1, int(len(sorted_props) * pct / 100))
    share = cum_p[k-1] / total_p * 100
    print(f"  Top {pct}% of voters cast {share:.1f}% of total votes")

# ── 3. Co-voting coalitions ──────────────────────────────────────────────
print("\n" + "-" * 72)
print("3. CO-VOTING COALITIONS")
print("-" * 72)

TOP_N = 50
top_voters_set = set(voter_stats.nlargest(TOP_N, 'total_vp')['org:resource'])

proposal_voters = df_votes.groupby('case:concept:name')['org:resource'].apply(set).to_dict()
total_proposals = len(proposal_voters)

co_votes = defaultdict(int)
for cid, voters in proposal_voters.items():
    top_in = sorted(voters & top_voters_set)
    for i in range(len(top_in)):
        for j in range(i + 1, len(top_in)):
            co_votes[(top_in[i], top_in[j])] += 1

sorted_pairs = sorted(co_votes.items(), key=lambda x: -x[1])[:20]

print(f"\nTop 20 co-voting pairs (among top {TOP_N} voters by VP):")
for (v1, v2), cnt in sorted_pairs:
    overlap_pct = cnt / total_proposals * 100
    print(f"  {v1[:12]}… & {v2[:12]}…: {cnt} proposals ({overlap_pct:.1f}%)")

# Average co-voting rate among top voters
if co_votes:
    rates = [cnt / total_proposals for cnt in co_votes.values()]
    print(f"\nCo-voting statistics among top-{TOP_N}:")
    print(f"  Mean co-voting rate:   {np.mean(rates)*100:.1f}%")
    print(f"  Max co-voting rate:    {np.max(rates)*100:.1f}%")
    print(f"  Median co-voting rate: {np.median(rates)*100:.1f}%")

# ── 4. Voter retention / cohort analysis ─────────────────────────────────
print("\n" + "-" * 72)
print("4. VOTER RETENTION BY COHORT")
print("-" * 72)

df_votes_ts = df_votes.copy()
df_votes_ts['year_q'] = df_votes_ts['time:timestamp'].dt.to_period('Q')

voter_first_q = df_votes_ts.groupby('org:resource')['year_q'].min().rename('cohort')
df_votes_ts = df_votes_ts.merge(voter_first_q, left_on='org:resource', right_index=True)

cohorts = df_votes_ts.groupby(['cohort', 'year_q'])['org:resource'].nunique().unstack(fill_value=0)

print(f"\nCohort retention matrix (new voters per quarter → active in future quarters):")
quarters = sorted(cohorts.columns)
print(f"{'Cohort':<10s}", end='')
for q in quarters[:10]:
    print(f"  {str(q):>8s}", end='')
print("  …" if len(quarters) > 10 else "")

for cohort_q in sorted(cohorts.index)[:12]:
    row = cohorts.loc[cohort_q]
    initial = row.get(cohort_q, 0)
    print(f"{str(cohort_q):<10s}", end='')
    for q in quarters[:10]:
        val = row.get(q, 0)
        if q < cohort_q:
            print(f"  {'':>8s}", end='')
        elif initial > 0 and q != cohort_q:
            print(f"  {val:>5} ({val/initial*100:>2.0f}%)" if val > 0 else f"  {val:>8}", end='')
        else:
            print(f"  {val:>8}", end='')
    print()

new_voters_per_q = voter_first_q.value_counts().sort_index()
active_per_q = df_votes_ts.groupby('year_q')['org:resource'].nunique()

print(f"\nQuarterly voter dynamics:")
print(f"{'Quarter':<10s} {'New':>8s} {'Active':>8s} {'Return%':>8s}")
for q in sorted(active_per_q.index):
    new = new_voters_per_q.get(q, 0)
    act = active_per_q.get(q, 0)
    ret = (act - new) / act * 100 if act > 0 else 0
    print(f"{str(q):<10s} {new:>8} {act:>8} {ret:>7.1f}%")

# ── 5. Participation trend ───────────────────────────────────────────────
print("\n" + "-" * 72)
print("5. PARTICIPATION TREND")
print("-" * 72)

monthly_votes = df_votes_ts.groupby(df_votes_ts['time:timestamp'].dt.to_period('M')).agg(
    votes=('org:resource', 'count'),
    unique_voters=('org:resource', 'nunique'),
    proposals=('case:concept:name', 'nunique'),
    total_vp=('voting_power', 'sum'),
)

print(f"\n{'Month':<10s} {'Votes':>8s} {'Voters':>8s} {'Props':>7s} {'Avg VP/voter':>14s}")
for period, row in monthly_votes.iterrows():
    avg_vp = row['total_vp'] / row['unique_voters'] if row['unique_voters'] > 0 else 0
    print(f"{str(period):<10s} {row['votes']:>8} {row['unique_voters']:>8} "
          f"{row['proposals']:>7} {avg_vp:>14,.0f}")

# ── 6. Voter lifespan analysis ───────────────────────────────────────────
print("\n" + "-" * 72)
print("6. VOTER LIFESPAN ANALYSIS")
print("-" * 72)

tenure = voter_stats['tenure_days']
print(f"\nVoter tenure (days between first and last vote):")
print(f"  Mean:   {tenure.mean():.0f} days")
print(f"  Median: {tenure.median():.0f} days")
print(f"  Zero-tenure (single-day voters): {(tenure == 0).sum()} ({(tenure == 0).sum()/len(tenure)*100:.1f}%)")
print(f"  >1 year tenure: {(tenure > 365).sum()} ({(tenure > 365).sum()/len(tenure)*100:.1f}%)")

# Voters per proposal histogram
votes_per_prop = df_votes.groupby('case:concept:name')['org:resource'].nunique()
print(f"\nVoters per proposal:")
print(f"  Mean:   {votes_per_prop.mean():.0f}")
print(f"  Median: {votes_per_prop.median():.0f}")
print(f"  Min:    {votes_per_prop.min()}")
print(f"  Max:    {votes_per_prop.max()}")
print(f"  Std:    {votes_per_prop.std():.0f}")

# Quintile analysis
for q_label, (lo, hi) in [
    ('Bottom 20%', (0, 0.2)),
    ('20-40%', (0.2, 0.4)),
    ('40-60%', (0.4, 0.6)),
    ('60-80%', (0.6, 0.8)),
    ('Top 20%', (0.8, 1.0)),
]:
    lo_v = votes_per_prop.quantile(lo)
    hi_v = votes_per_prop.quantile(hi)
    sub = votes_per_prop[(votes_per_prop >= lo_v) & (votes_per_prop <= hi_v)]
    print(f"  {q_label:<12s}: {lo_v:.0f} – {hi_v:.0f} voters")

print("\n✓ Script 4 complete")
