#!/usr/bin/env python3
"""
ENS DAO Process Mining — Script 2: Trace Variants, Incompleteness & Derived Activities

Analyses:
 - Trace variant distribution (full log + per-source)
 - Drop-off / incompleteness: where do proposals stall?
 - Derived activities: FirstVote, VoteInLastHour, VoteByWhale, etc.
 - Rediscovery on the enriched log
"""

import pandas as pd
import numpy as np
import pm4py
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

from daogov.paths import event_log, FIGURES_DIR

FILE_PATH = event_log('ens_linked')
OUT_PREFIX = f"{FIGURES_DIR}/ens_out_02_"
WHALE_VP = 10_000
DELEGATE_MIN_PROPOSALS = 5

df = pd.read_csv(FILE_PATH)
df['time:timestamp'] = pd.to_datetime(df['time:timestamp'])
df = pm4py.format_dataframe(
    df,
    case_id='case:concept:name',
    activity_key='concept:name',
    timestamp_key='time:timestamp',
)
log = pm4py.convert_to_event_log(df)

print("=" * 72)
print("SCRIPT 2 — TRACE VARIANTS, INCOMPLETENESS & DERIVED ACTIVITIES")
print("=" * 72)

# ── 1. Trace variants ────────────────────────────────────────────────────
variants = pm4py.get_variants(log)
print(f"\nTotal distinct trace variants: {len(variants)}")

print("\nTop 15 variants (by trace count):")
sorted_v = sorted(variants.items(), key=lambda x: len(x[1]), reverse=True)
for i, (var, traces) in enumerate(sorted_v[:15], 1):
    acts = list(var) if isinstance(var, tuple) else str(var).split(',')
    trail = ' → '.join(acts[:8])
    if len(acts) > 8:
        trail += f' … (+{len(acts)-8})'
    print(f"  {i:>2}. [{len(traces):>4} traces] {trail}")

# Coverage of top-N variants
top_counts = [len(t) for _, t in sorted_v]
total_traces = sum(top_counts)
cumsum = np.cumsum(top_counts)
for pct in [50, 80, 90, 95]:
    idx = int(np.searchsorted(cumsum, total_traces * pct / 100))
    print(f"  {pct}% of traces covered by top {idx+1} variants")

# ── 2. Simplified trace patterns (collapse consecutive votes) ────────────
def simplify(activities):
    if not activities:
        return []
    out = [activities[0]]
    for a in activities[1:]:
        if a != out[-1]:
            out.append(a)
    return tuple(out)

case_simplified = df.sort_values('time:timestamp').groupby('case:concept:name')['concept:name'].apply(
    lambda s: simplify(s.tolist())
)
pattern_counts = case_simplified.value_counts()
print(f"\nSimplified patterns (consecutive dupes collapsed): {len(pattern_counts)}")
print("\nTop 10 simplified patterns:")
for i, (pat, cnt) in enumerate(pattern_counts.head(10).items(), 1):
    print(f"  {i:>2}. [{cnt:>3}] {' → '.join(pat)}")

# ── 3. Trace incompleteness / drop-off ───────────────────────────────────
print("\n" + "-" * 72)
print("TRACE INCOMPLETENESS — Where do proposals stall?")
print("-" * 72)

case_info = df.groupby('case:concept:name').agg(
    activities=('concept:name', list),
    start=('time:timestamp', 'min'),
    end=('time:timestamp', 'max'),
    title=('case:proposal_title', 'first'),
).reset_index()

case_info['final'] = case_info['activities'].apply(lambda a: a[-1])
case_info['has_vote'] = case_info['activities'].apply(
    lambda a: any(x in a for x in ['vote', 'VoteCast'])
)
case_info['executed'] = case_info['activities'].apply(lambda a: 'ProposalExecuted' in a)
case_info['queued'] = case_info['activities'].apply(lambda a: 'ProposalQueued' in a)

has_onchain = df.groupby('case:concept:name')['source'].apply(lambda s: 'onchain' in s.values)
case_info = case_info.merge(has_onchain.rename('is_onchain'), left_on='case:concept:name', right_index=True)

total = len(case_info)
executed = case_info['executed'].sum()
queued = case_info['queued'].sum()
print(f"\nTotal proposals:          {total}")
print(f"Reached execution:        {executed} ({executed/total*100:.1f}%)")
print(f"Reached queue:            {queued} ({queued/total*100:.1f}%)")
print(f"Never reached queue:      {total - queued} ({(total-queued)/total*100:.1f}%)")

# Drop-off points for non-executed
non_exec = case_info[~case_info['executed']]
print(f"\nDrop-off points (non-executed proposals, n={len(non_exec)}):")
for act, cnt in non_exec['final'].value_counts().items():
    print(f"  {act:<20s} {cnt:>4}  ({cnt/len(non_exec)*100:.1f}%)")

# Execution rate by governance type
print("\nExecution rate by governance path:")
for label, mask in [
    ('Onchain', case_info['is_onchain']),
    ('Snapshot-only', ~case_info['is_onchain']),
]:
    sub = case_info[mask]
    if sub.empty:
        continue
    rate = sub['executed'].sum() / len(sub) * 100
    print(f"  {label:<16s} {sub['executed'].sum():>3}/{len(sub):<3}  ({rate:.1f}%)")

# ── 4. Derived activities ────────────────────────────────────────────────
print("\n" + "-" * 72)
print("DERIVED ACTIVITIES — enriching the event log")
print("-" * 72)

df_votes = df[df['concept:name'].isin(['vote', 'VoteCast'])].copy()

# Voting windows per case
windows = {}
for cid, g in df.groupby('case:concept:name'):
    vs = g[g['concept:name'] == 'voting_started']['time:timestamp'].min()
    ve = g[g['concept:name'] == 'voting_ended']['time:timestamp'].min()
    windows[cid] = (vs, ve)

# Voter-level stats for whale/delegate classification
voter_stats = df_votes.groupby('org:resource').agg(
    max_vp=('voting_power', 'max'),
    proposals=('case:concept:name', 'nunique'),
).reset_index()
whales = set(voter_stats[voter_stats['max_vp'] >= WHALE_VP]['org:resource'])
delegates = set(voter_stats[voter_stats['proposals'] >= DELEGATE_MIN_PROPOSALS]['org:resource'])

# Build enriched rows
enriched_rows = []

for cid, g in df.groupby('case:concept:name'):
    g = g.sort_values('time:timestamp')
    votes = g[g['concept:name'].isin(['vote', 'VoteCast'])].copy()
    if votes.empty:
        continue

    vs, ve = windows.get(cid, (pd.NaT, pd.NaT))
    first_vote_ts = votes['time:timestamp'].iloc[0]

    for idx, (_, row) in enumerate(votes.iterrows()):
        ts = row['time:timestamp']
        voter = row['org:resource']
        vp = row['voting_power']

        derived = []

        # FirstVote: first vote in the case
        if idx == 0:
            derived.append('FirstVote')

        # Timing-based
        if pd.notna(ve):
            secs_to_end = (ve - ts).total_seconds()
            if 0 < secs_to_end < 3600:
                derived.append('VoteInLastHour')
        if pd.notna(vs):
            secs_from_start = (ts - vs).total_seconds()
            if 0 < secs_from_start < 3600:
                derived.append('VoteInFirstHour')

        # Actor-based
        if voter in whales:
            derived.append('VoteByWhale')
        if voter in delegates:
            derived.append('VoteByDelegate')

        # Source-based
        if row['source'] == 'onchain':
            derived.append('VoteOnchain')
        else:
            derived.append('VoteSnapshot')

        for d in derived:
            enriched_rows.append({
                'case:concept:name': cid,
                'concept:name': d,
                'time:timestamp': ts,
                'source': row['source'],
                'org:resource': voter,
                'voting_power': vp,
            })

df_derived = pd.DataFrame(enriched_rows)

# Counts
print("\nDerived activity counts:")
for act, cnt in df_derived['concept:name'].value_counts().items():
    print(f"  {act:<22s} {cnt:>7,}")

# Combine original + derived into enriched log
df_enriched = pd.concat([df, df_derived[df.columns.intersection(df_derived.columns)]], ignore_index=True)
df_enriched = df_enriched.sort_values(['case:concept:name', 'time:timestamp']).reset_index(drop=True)
df_enriched = pm4py.format_dataframe(
    df_enriched,
    case_id='case:concept:name',
    activity_key='concept:name',
    timestamp_key='time:timestamp',
)
log_enriched = pm4py.convert_to_event_log(df_enriched)

# DFG on enriched log
dfg_e, sa_e, ea_e = pm4py.discover_dfg(log_enriched)
fname = f"{OUT_PREFIX}dfg_enriched.png"
pm4py.save_vis_dfg(dfg_e, sa_e, ea_e, fname)
print(f"\n  Saved {fname}")

# DFG on derived-only activities
df_derived_fmt = pm4py.format_dataframe(
    df_derived,
    case_id='case:concept:name',
    activity_key='concept:name',
    timestamp_key='time:timestamp',
)
log_derived = pm4py.convert_to_event_log(df_derived_fmt)
dfg_d, sa_d, ea_d = pm4py.discover_dfg(log_derived)
fname = f"{OUT_PREFIX}dfg_derived_only.png"
pm4py.save_vis_dfg(dfg_d, sa_d, ea_d, fname)
print(f"  Saved {fname}")

# ── 5. Whale vs non-whale traces ─────────────────────────────────────────
print("\n" + "-" * 72)
print("WHALE vs NON-WHALE PARTICIPATION")
print("-" * 72)

vp_per_case = df_votes.groupby('case:concept:name').agg(
    total_vp=('voting_power', 'sum'),
    n_voters=('org:resource', 'nunique'),
)
whale_vp_per_case = df_votes[df_votes['org:resource'].isin(whales)].groupby('case:concept:name')['voting_power'].sum()
vp_per_case['whale_vp'] = whale_vp_per_case.reindex(vp_per_case.index, fill_value=0)
vp_per_case['whale_share'] = vp_per_case['whale_vp'] / vp_per_case['total_vp']

print(f"\nWhale VP share per proposal:")
print(f"  Mean:   {vp_per_case['whale_share'].mean()*100:.1f}%")
print(f"  Median: {vp_per_case['whale_share'].median()*100:.1f}%")
print(f"  Proposals with whale share > 50%: "
      f"{(vp_per_case['whale_share'] > 0.5).sum()}/{len(vp_per_case)}")

# Merge execution info
vp_per_case = vp_per_case.merge(
    case_info[['case:concept:name', 'executed']],
    left_index=True, right_on='case:concept:name', how='left',
)
whale_dominant = vp_per_case[vp_per_case['whale_share'] > 0.5]
whale_minor = vp_per_case[vp_per_case['whale_share'] <= 0.5]

print(f"\nExecution rates:")
if len(whale_dominant) > 0:
    print(f"  Whale-dominant (>50% VP):   {whale_dominant['executed'].sum()}/{len(whale_dominant)} "
          f"({whale_dominant['executed'].mean()*100:.1f}%)")
if len(whale_minor) > 0:
    print(f"  Non-whale-dominant:         {whale_minor['executed'].sum()}/{len(whale_minor)} "
          f"({whale_minor['executed'].mean()*100:.1f}%)")

print("\n✓ Script 2 complete")
