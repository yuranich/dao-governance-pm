#!/usr/bin/env python3
"""
AAVE DAO Process Mining — Script 2: Trace Variants, Incompleteness & Derived Activities

Analyses:
 - Trace variant distribution (full log + per-source)
 - Drop-off / incompleteness: where do proposals stall?
 - Derived activities: FirstVote, VoteInLastHour, VoteByWhale, etc.
 - Rediscovery on the enriched skeleton log
"""

import pandas as pd
import numpy as np
import pm4py
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

from daogov.paths import event_log, FIGURES_DIR

FILE_PATH = event_log('aave_linked')
OUT_PREFIX = f"{FIGURES_DIR}/aave_out_02_"
WHALE_VP = 100_000  # AAVE whale threshold (higher than ENS due to token economics)
DELEGATE_MIN_PROPOSALS = 10

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
print("SCRIPT 2 — TRACE VARIANTS, INCOMPLETENESS & DERIVED ACTIVITIES (AAVE)")
print("=" * 72)

# ── 1. Simplified trace patterns (collapse consecutive votes) ────────────
def simplify(activities):
    if not activities:
        return ()
    out = [activities[0]]
    for a in activities[1:]:
        if a != out[-1]:
            out.append(a)
    return tuple(out)

case_simplified = (
    df.sort_values('time:timestamp')
    .groupby('case:concept:name')['concept:name']
    .apply(lambda s: simplify(s.tolist()))
)
pattern_counts = case_simplified.value_counts()
total_cases = len(case_simplified)

print(f"\nTotal proposals (cases): {total_cases}")
print(f"Distinct simplified trace patterns: {len(pattern_counts)}")
print("\nTop 20 simplified patterns:")
for i, (pat, cnt) in enumerate(pattern_counts.head(20).items(), 1):
    trail = ' → '.join(pat[:10])
    if len(pat) > 10:
        trail += f' … (+{len(pat)-10})'
    print(f"  {i:>2}. [{cnt:>4} cases, {cnt/total_cases*100:>5.1f}%] {trail}")

# Coverage of top-N patterns
cumsum = np.cumsum(pattern_counts.values)
for pct in [50, 80, 90, 95]:
    idx = int(np.searchsorted(cumsum, total_cases * pct / 100))
    print(f"  {pct}% of cases covered by top {idx+1} patterns")

# ── 2. Raw trace variants (pm4py style, on skeleton log) ─────────────────
print("\n" + "-" * 72)
print("RAW TRACE VARIANTS (on skeleton log)")
print("-" * 72)

vote_mask = df['concept:name'].isin(['vote', 'VoteEmitted'])
df_nonvote = df[~vote_mask]
df_vote_sampled = (
    df[vote_mask]
    .groupby('case:concept:name', group_keys=False)
    .apply(lambda g: g.sample(n=min(20, len(g)), random_state=42))
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

variants = pm4py.get_variants(log)
print(f"\nTotal raw trace variants (skeleton): {len(variants)}")
sorted_v = sorted(variants.items(), key=lambda x: len(x[1]), reverse=True)
print("\nTop 10 raw variants:")
for i, (var, traces) in enumerate(sorted_v[:10], 1):
    acts = list(var) if isinstance(var, tuple) else str(var).split(',')
    trail = ' → '.join(acts[:8])
    if len(acts) > 8:
        trail += f' … (+{len(acts)-8})'
    print(f"  {i:>2}. [{len(traces):>4} traces] {trail}")

# ── 3. Trace incompleteness / drop-off ───────────────────────────────────
print("\n" + "-" * 72)
print("TRACE INCOMPLETENESS — Where do proposals stall?")
print("-" * 72)

case_info = df.groupby('case:concept:name').agg(
    activities=('concept:name', list),
    start=('time:timestamp', 'min'),
    end=('time:timestamp', 'max'),
    title=('case:proposal_title', 'first'),
    n_events=('concept:name', 'count'),
).reset_index()

case_info['final'] = case_info['activities'].apply(lambda a: a[-1] if a else 'UNKNOWN')
case_info['unique_acts'] = case_info['activities'].apply(lambda a: set(a))
case_info['has_vote'] = case_info['unique_acts'].apply(
    lambda s: bool(s & {'vote', 'VoteEmitted'})
)
case_info['executed'] = case_info['unique_acts'].apply(lambda s: 'ProposalExecuted' in s)
case_info['queued'] = case_info['unique_acts'].apply(lambda s: 'ProposalQueued' in s)
case_info['cancelled'] = case_info['unique_acts'].apply(lambda s: 'ProposalCanceled' in s)
case_info['failed'] = case_info['unique_acts'].apply(lambda s: 'ProposalFailed' in s)
case_info['voting_activated'] = case_info['unique_acts'].apply(lambda s: 'VotingActivated' in s)
case_info['created_onchain'] = case_info['unique_acts'].apply(lambda s: 'ProposalCreated' in s)

has_onchain = df.groupby('case:concept:name')['source'].apply(lambda s: 'onchain' in s.values)
case_info = case_info.merge(has_onchain.rename('is_onchain'), left_on='case:concept:name', right_index=True)

total = len(case_info)
executed = case_info['executed'].sum()
queued = case_info['queued'].sum()
cancelled = case_info['cancelled'].sum()
failed = case_info['failed'].sum()
voting_activated = case_info['voting_activated'].sum()
created_onchain = case_info['created_onchain'].sum()
with_votes = case_info['has_vote'].sum()

print(f"\nTotal proposals:          {total}")
print(f"With votes:               {with_votes} ({with_votes/total*100:.1f}%)")
print(f"ProposalCreated:          {created_onchain} ({created_onchain/total*100:.1f}%)")
print(f"VotingActivated (v3):     {voting_activated} ({voting_activated/total*100:.1f}%)")
print(f"Reached queue:            {queued} ({queued/total*100:.1f}%)")
print(f"Reached execution:        {executed} ({executed/total*100:.1f}%)")
print(f"Cancelled:                {cancelled} ({cancelled/total*100:.1f}%)")
print(f"Failed:                   {failed} ({failed/total*100:.1f}%)")
print(f"Never reached queue:      {total - queued} ({(total-queued)/total*100:.1f}%)")

# Drop-off points for non-executed
non_exec = case_info[~case_info['executed']]
print(f"\nDrop-off points (non-executed proposals, n={len(non_exec)}):")
final_counts = non_exec['final'].value_counts()
for act, cnt in final_counts.items():
    print(f"  {act:<22s} {cnt:>4}  ({cnt/len(non_exec)*100:.1f}%)")

# Execution funnel
print(f"\nGovernance funnel:")
stages = [
    ('All proposals', total),
    ('With votes', with_votes),
    ('ProposalCreated', created_onchain),
    ('VotingActivated', voting_activated),
    ('Reached queue', queued),
    ('Executed', executed),
]
for label, cnt in stages:
    bar = '█' * int(cnt / total * 40)
    print(f"  {label:<20s} {cnt:>4} ({cnt/total*100:>5.1f}%) {bar}")

# Execution rate by governance type
print(f"\nExecution rate by governance path:")
for label, mask in [
    ('Has onchain events', case_info['is_onchain']),
    ('Snapshot-only', ~case_info['is_onchain']),
]:
    sub = case_info[mask]
    if sub.empty:
        continue
    rate = sub['executed'].sum() / len(sub) * 100
    print(f"  {label:<22s} {sub['executed'].sum():>3}/{len(sub):<3}  ({rate:.1f}%)")

# ── 4. Derived activities ────────────────────────────────────────────────
print("\n" + "-" * 72)
print("DERIVED ACTIVITIES — enriching the event log")
print("-" * 72)

df_votes = df[df['concept:name'].isin(['vote', 'VoteEmitted'])].copy()

windows = {}
for cid, g in df.groupby('case:concept:name'):
    vs = g[g['concept:name'] == 'voting_started']['time:timestamp'].min()
    ve = g[g['concept:name'] == 'voting_ended']['time:timestamp'].min()
    windows[cid] = (vs, ve)

voter_stats = df_votes.dropna(subset=['org:resource']).groupby('org:resource').agg(
    max_vp=('voting_power', 'max'),
    proposals=('case:concept:name', 'nunique'),
).reset_index()
whales = set(voter_stats[voter_stats['max_vp'] >= WHALE_VP]['org:resource'])
delegates = set(voter_stats[voter_stats['proposals'] >= DELEGATE_MIN_PROPOSALS]['org:resource'])

print(f"\nWhale threshold: {WHALE_VP:,} VP → {len(whales)} whale addresses")
print(f"Delegate threshold: {DELEGATE_MIN_PROPOSALS}+ proposals → {len(delegates)} delegates")

# Build enriched rows — process per-case to avoid giant loops
enriched_rows = []
for cid, g in df.groupby('case:concept:name'):
    g = g.sort_values('time:timestamp')
    votes = g[g['concept:name'].isin(['vote', 'VoteEmitted'])].copy()
    if votes.empty:
        continue

    vs, ve = windows.get(cid, (pd.NaT, pd.NaT))

    for idx, (_, row) in enumerate(votes.iterrows()):
        ts = row['time:timestamp']
        voter = row['org:resource']
        vp = row.get('voting_power', np.nan)
        derived = []

        if idx == 0:
            derived.append('FirstVote')

        if pd.notna(ve):
            secs_to_end = (ve - ts).total_seconds()
            if 0 < secs_to_end < 3600:
                derived.append('VoteInLastHour')
        if pd.notna(vs):
            secs_from_start = (ts - vs).total_seconds()
            if 0 < secs_from_start < 3600:
                derived.append('VoteInFirstHour')

        if voter in whales:
            derived.append('VoteByWhale')
        if voter in delegates:
            derived.append('VoteByDelegate')

        if row.get('source') == 'onchain':
            derived.append('VoteOnchain')
        else:
            derived.append('VoteSnapshot')

        for d in derived:
            enriched_rows.append({
                'case:concept:name': cid,
                'concept:name': d,
                'time:timestamp': ts,
                'source': row.get('source', ''),
                'org:resource': voter,
                'voting_power': vp,
            })

df_derived = pd.DataFrame(enriched_rows)

print(f"\nDerived activity counts:")
for act, cnt in df_derived['concept:name'].value_counts().items():
    print(f"  {act:<22s} {cnt:>10,}")

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

vp_per_case = df_votes.dropna(subset=['org:resource']).groupby('case:concept:name').agg(
    total_vp=('voting_power', 'sum'),
    n_voters=('org:resource', 'nunique'),
)
whale_vp_per_case = (
    df_votes[df_votes['org:resource'].isin(whales)]
    .groupby('case:concept:name')['voting_power'].sum()
)
vp_per_case['whale_vp'] = whale_vp_per_case.reindex(vp_per_case.index, fill_value=0)
vp_per_case['whale_share'] = vp_per_case['whale_vp'] / vp_per_case['total_vp']
vp_per_case['whale_share'] = vp_per_case['whale_share'].fillna(0)

print(f"\nWhale VP share per proposal:")
print(f"  Mean:   {vp_per_case['whale_share'].mean()*100:.1f}%")
print(f"  Median: {vp_per_case['whale_share'].median()*100:.1f}%")
print(f"  Proposals with whale share > 50%: "
      f"{(vp_per_case['whale_share'] > 0.5).sum()}/{len(vp_per_case)}")
print(f"  Proposals with whale share > 80%: "
      f"{(vp_per_case['whale_share'] > 0.8).sum()}/{len(vp_per_case)}")

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
