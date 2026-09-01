#!/usr/bin/env python3
"""
AAVE DAO Process Mining — Script 3: Performance Mining

Analyses:
 - Inter-activity timing (create→first vote, vote→quorum, quorum→execution)
 - Vote arrival patterns (front-loaded vs last-minute)
 - Voting power accumulation curves
 - Bottleneck identification
"""

import pandas as pd
import numpy as np
import pm4py
import warnings
warnings.filterwarnings('ignore')

from daogov.paths import event_log, FIGURES_DIR

FILE_PATH = event_log('aave_linked')
OUT_PREFIX = f"{FIGURES_DIR}/aave_out_03_"

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
print("SCRIPT 3 — PERFORMANCE MINING (AAVE)")
print("=" * 72)

# ── 1. Performance DFG on skeleton log ────────────────────────────────────
print("\nBuilding skeleton log for performance DFG...")
vote_mask = df['concept:name'].isin(['vote', 'VoteEmitted'])
df_nonvote = df[~vote_mask]
df_vote_sampled = (
    df[vote_mask]
    .groupby('case:concept:name', group_keys=False)
    .apply(lambda g: g.sample(n=min(30, len(g)), random_state=42))
)
df_skeleton = pd.concat([df_nonvote, df_vote_sampled]).sort_values(
    ['case:concept:name', 'time:timestamp']
).reset_index(drop=True)
df_skeleton = pm4py.format_dataframe(
    df_skeleton,
    case_id='case:concept:name',
    activity_key='concept:name',
    timestamp_key='time:timestamp',
)
log = pm4py.convert_to_event_log(df_skeleton)

dfg_perf, sa, ea = pm4py.discover_performance_dfg(log)
pm4py.save_vis_performance_dfg(dfg_perf, sa, ea, f"{OUT_PREFIX}perf_dfg.png")
print(f"Saved {OUT_PREFIX}perf_dfg.png")

print("\nMean transition times (top 15 by duration):")

def _mean(v):
    if isinstance(v, dict):
        return v.get('mean', 0)
    return float(v)

sorted_perf = sorted(dfg_perf.items(), key=lambda x: _mean(x[1]), reverse=True)[:15]
for (s, t), val in sorted_perf:
    secs = _mean(val)
    hours = secs / 3600
    if hours > 24:
        label = f"{hours/24:.1f} days"
    else:
        label = f"{hours:.1f} hours"
    print(f"  {s} → {t}: {label}")

# ── 2. Case-level timing metrics (computed on full data) ─────────────────
print("\n" + "-" * 72)
print("CASE-LEVEL TIMING METRICS")
print("-" * 72)

metrics = []

for cid, g in df.groupby('case:concept:name'):
    g = g.sort_values('time:timestamp')
    m = {'case_id': cid}

    ts_voting_start = g.loc[g['concept:name'] == 'voting_started', 'time:timestamp'].min()
    ts_voting_end = g.loc[g['concept:name'] == 'voting_ended', 'time:timestamp'].min()
    ts_proposal = g.loc[g['concept:name'] == 'proposal', 'time:timestamp'].min()
    ts_created = g.loc[g['concept:name'] == 'ProposalCreated', 'time:timestamp'].min()
    ts_voting_activated = g.loc[g['concept:name'] == 'VotingActivated', 'time:timestamp'].min()
    ts_queued = g.loc[g['concept:name'] == 'ProposalQueued', 'time:timestamp'].min()
    ts_executed = g.loc[g['concept:name'] == 'ProposalExecuted', 'time:timestamp'].min()

    votes = g[g['concept:name'].isin(['vote', 'VoteEmitted'])].sort_values('time:timestamp')
    ts_first_vote = votes['time:timestamp'].min() if len(votes) else pd.NaT
    ts_last_vote = votes['time:timestamp'].max() if len(votes) else pd.NaT
    m['n_votes'] = len(votes)

    def delta_h(a, b):
        if pd.notna(a) and pd.notna(b):
            return (b - a).total_seconds() / 3600
        return np.nan

    m['proposal_to_voting_start_h'] = delta_h(ts_proposal, ts_voting_start)
    m['voting_start_to_first_vote_h'] = delta_h(ts_voting_start, ts_first_vote)
    m['voting_window_h'] = delta_h(ts_voting_start, ts_voting_end)
    m['first_to_last_vote_h'] = delta_h(ts_first_vote, ts_last_vote)
    m['created_to_voting_activated_h'] = delta_h(ts_created, ts_voting_activated)
    m['voting_activated_to_first_vote_h'] = delta_h(ts_voting_activated, ts_first_vote)
    m['voting_end_to_queue_h'] = delta_h(ts_voting_end, ts_queued)
    m['queue_to_execution_h'] = delta_h(ts_queued, ts_executed)
    m['created_to_executed_h'] = delta_h(ts_created, ts_executed)
    m['total_case_duration_h'] = delta_h(g['time:timestamp'].min(), g['time:timestamp'].max())

    if len(votes) > 1 and pd.notna(ts_voting_start) and pd.notna(ts_voting_end):
        window_s = (ts_voting_end - ts_voting_start).total_seconds()
        if window_s > 0:
            positions = [(v - ts_voting_start).total_seconds() / window_s
                         for v in votes['time:timestamp']]
            m['pct_votes_first_quarter'] = sum(1 for p in positions if p < 0.25) / len(positions)
            m['pct_votes_last_quarter'] = sum(1 for p in positions if p > 0.75) / len(positions)
            m['pct_votes_first_half'] = sum(1 for p in positions if p < 0.50) / len(positions)

    if len(votes) > 0:
        vp_sorted = votes.dropna(subset=['voting_power']).sort_values('time:timestamp')
        if len(vp_sorted) > 0:
            cum = vp_sorted['voting_power'].cumsum()
            total_vp = cum.iloc[-1]
            m['total_vp'] = total_vp
            if total_vp > 0 and pd.notna(ts_voting_start):
                idx50 = (cum >= total_vp * 0.5).idxmax()
                t50 = (vp_sorted.loc[idx50, 'time:timestamp'] - ts_voting_start).total_seconds() / 3600
                m['hours_to_50pct_vp'] = t50
                if pd.notna(ts_voting_end) and m.get('voting_window_h', 0) > 0:
                    m['pct_window_to_50pct_vp'] = t50 / m['voting_window_h']

    m['source'] = 'onchain' if 'onchain' in g['source'].values else 'snapshot'
    m['executed'] = 'ProposalExecuted' in g['concept:name'].values
    m['has_onchain'] = 'onchain' in g['source'].values
    metrics.append(m)

mdf = pd.DataFrame(metrics)

def print_stat(label, col):
    s = mdf[col].dropna()
    if s.empty:
        return
    print(f"\n{label} (n={len(s)}):")
    print(f"  Mean: {s.mean():.2f}h  Median: {s.median():.2f}h  "
          f"Min: {s.min():.2f}h  Max: {s.max():.2f}h  Std: {s.std():.2f}h")

print_stat("Proposal creation → voting start", 'proposal_to_voting_start_h')
print_stat("Voting start → first vote", 'voting_start_to_first_vote_h')
print_stat("Voting window duration", 'voting_window_h')
print_stat("First vote → last vote", 'first_to_last_vote_h')
print_stat("ProposalCreated → VotingActivated (v3)", 'created_to_voting_activated_h')
print_stat("VotingActivated → first vote (v3)", 'voting_activated_to_first_vote_h')
print_stat("Voting end → queue", 'voting_end_to_queue_h')
print_stat("Queue → execution", 'queue_to_execution_h')
print_stat("ProposalCreated → ProposalExecuted", 'created_to_executed_h')
print_stat("Total case duration", 'total_case_duration_h')

# ── 3. Vote arrival patterns ─────────────────────────────────────────────
print("\n" + "-" * 72)
print("VOTE ARRIVAL PATTERNS")
print("-" * 72)

for col, label in [
    ('pct_votes_first_quarter', '% votes in first quarter of window'),
    ('pct_votes_last_quarter', '% votes in last quarter of window'),
    ('pct_votes_first_half', '% votes in first half of window'),
]:
    s = mdf[col].dropna()
    if s.empty:
        continue
    print(f"\n{label} (n={len(s)}):")
    print(f"  Mean: {s.mean()*100:.1f}%  Median: {s.median()*100:.1f}%  "
          f"Min: {s.min()*100:.1f}%  Max: {s.max()*100:.1f}%")

# Classify vote distribution patterns
if 'pct_votes_first_half' in mdf.columns:
    s = mdf['pct_votes_first_half'].dropna()
    front_loaded = (s > 0.6).sum()
    back_loaded = (s < 0.4).sum()
    balanced = len(s) - front_loaded - back_loaded
    print(f"\nVote distribution classification:")
    print(f"  Front-loaded (>60% in 1st half): {front_loaded} ({front_loaded/len(s)*100:.1f}%)")
    print(f"  Back-loaded (<40% in 1st half):  {back_loaded} ({back_loaded/len(s)*100:.1f}%)")
    print(f"  Balanced:                        {balanced} ({balanced/len(s)*100:.1f}%)")

# ── 4. VP accumulation dynamics ──────────────────────────────────────────
print("\n" + "-" * 72)
print("VOTING POWER ACCUMULATION DYNAMICS")
print("-" * 72)

s = mdf['pct_window_to_50pct_vp'].dropna()
if len(s) > 0:
    print(f"\n50% of total VP reached at (fraction of voting window, n={len(s)}):")
    print(f"  Mean: {s.mean()*100:.1f}%  Median: {s.median()*100:.1f}%")
    early_decisive = (s < 0.1).sum()
    print(f"  Proposals decided in first 10% of window: {early_decisive} ({early_decisive/len(s)*100:.1f}%)")

s = mdf['hours_to_50pct_vp'].dropna()
if len(s) > 0:
    print(f"\nHours to reach 50% of total VP (n={len(s)}):")
    print(f"  Mean: {s.mean():.1f}h  Median: {s.median():.1f}h")

# ── 5. Bottleneck comparison: executed vs non-executed ────────────────────
print("\n" + "-" * 72)
print("BOTTLENECK COMPARISON: EXECUTED vs NON-EXECUTED")
print("-" * 72)

timing_cols = [
    'voting_start_to_first_vote_h', 'voting_window_h',
    'first_to_last_vote_h', 'n_votes', 'total_vp',
]

exec_df = mdf[mdf['executed']]
noex_df = mdf[~mdf['executed']]

print(f"\n{'Metric':<35s} {'Executed':>12s} {'Not executed':>14s}")
print("-" * 63)
for col in timing_cols:
    ev = exec_df[col].dropna().mean()
    nv = noex_df[col].dropna().mean()
    fmt = '.0f' if col in ('n_votes',) else '.1f'
    ev_s = f"{ev:{fmt}}" if not np.isnan(ev) else 'N/A'
    nv_s = f"{nv:{fmt}}" if not np.isnan(nv) else 'N/A'
    print(f"  {col:<33s} {ev_s:>12s} {nv_s:>14s}")

# ── 6. Snapshot vs onchain timing ────────────────────────────────────────
print("\n" + "-" * 72)
print("SNAPSHOT vs ONCHAIN TIMING")
print("-" * 72)

for src_label, mask in [
    ('SNAPSHOT-ONLY', ~mdf['has_onchain']),
    ('WITH ONCHAIN', mdf['has_onchain']),
]:
    sub = mdf[mask]
    if sub.empty:
        continue
    print(f"\n  {src_label} (n={len(sub)}):")
    for col in ['voting_window_h', 'voting_start_to_first_vote_h', 'n_votes', 'total_case_duration_h']:
        s = sub[col].dropna()
        if s.empty:
            continue
        fmt = '.0f' if col == 'n_votes' else '.1f'
        print(f"    {col:<35s} mean={s.mean():{fmt}}  median={s.median():{fmt}}")

# ── 7. Dotted chart ──────────────────────────────────────────────────────
print("\nGenerating visualizations on skeleton log...")
try:
    pm4py.save_vis_dotted_chart(df_skeleton, f"{OUT_PREFIX}dotted_chart.png")
    print(f"  Saved {OUT_PREFIX}dotted_chart.png")
except Exception as e:
    print(f"  Dotted chart skipped: {e}")

try:
    pm4py.save_vis_case_duration_graph(df_skeleton, f"{OUT_PREFIX}case_duration.png")
    print(f"  Saved {OUT_PREFIX}case_duration.png")
except Exception as e:
    print(f"  Case duration graph skipped: {e}")

try:
    pm4py.save_vis_events_distribution_graph(df_skeleton, f"{OUT_PREFIX}events_over_time.png")
    print(f"  Saved {OUT_PREFIX}events_over_time.png")
except Exception as e:
    print(f"  Events-over-time graph skipped: {e}")

print("\n✓ Script 3 complete")
