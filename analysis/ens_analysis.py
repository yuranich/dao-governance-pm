#!/usr/bin/env python3
"""
ENS DAO Process Mining Analysis

Analyzes ENS DAO governance event logs to discover process patterns,
trace incompleteness, timing characteristics, and actor-driven variants.
"""

import pandas as pd
import numpy as np
import pm4py
from collections import defaultdict
from datetime import timedelta

# =============================================================================
# CONFIGURATION
# =============================================================================
from daogov.paths import event_log, figure

FILE_PATH = event_log('ens')
WHALE_THRESHOLD = 10000  # voting power threshold for "whale" classification
DELEGATE_PATTERN_THRESHOLD = 5  # min proposals participated to be considered delegate

# =============================================================================
# DATA LOADING
# =============================================================================
print("=" * 70)
print("ENS DAO PROCESS MINING ANALYSIS")
print("=" * 70)

df = pd.read_csv(FILE_PATH)
df['time:timestamp'] = pd.to_datetime(df['time:timestamp'])

# Format for pm4py
df = pm4py.format_dataframe(df, 
                            case_id='case:concept:name',
                            activity_key='concept:name', 
                            timestamp_key='time:timestamp')

print(f"\nDataset loaded: {len(df)} events, {df['case:concept:name'].nunique()} proposals")

# Convert to event log for some operations
log = pm4py.convert_to_event_log(df)

# =============================================================================
# 1. BASIC PROCESS DISCOVERY
# =============================================================================
print("\n" + "=" * 70)
print("1. PROCESS DISCOVERY")
print("=" * 70)

# Start and end activities
start_activities = pm4py.get_start_activities(log)
end_activities = pm4py.get_end_activities(log)

print("\nStart activities:", dict(start_activities))
print("End activities:", dict(end_activities))

# Discover DFG
dfg, start_act, end_act = pm4py.discover_dfg(log)
print(f"\nDFG edges (top 15 by frequency):")
sorted_dfg = sorted(dfg.items(), key=lambda x: x[1], reverse=True)[:15]
for (src, tgt), count in sorted_dfg:
    print(f"  {src} -> {tgt}: {count}")

# Get trace variants
variants = pm4py.get_variants(log)
print(f"\nTotal trace variants: {len(variants)}")
print("\nTop 10 trace variants:")
sorted_variants = sorted(variants.items(), key=lambda x: len(x[1]), reverse=True)[:10]
for i, (variant, traces) in enumerate(sorted_variants, 1):
    activities = list(variant) if isinstance(variant, tuple) else variant.split(',')
    print(f"  {i}. ({len(traces)} traces) {' -> '.join(activities[:5])}{'...' if len(activities) > 5 else ''}")

# =============================================================================
# 2. TRACE INCOMPLETENESS ANALYSIS
# =============================================================================
print("\n" + "=" * 70)
print("2. TRACE INCOMPLETENESS ANALYSIS")
print("=" * 70)
print("How many proposals never reach execution? Where do they stop?")

# Group by case to analyze trace endpoints
case_endpoints = df.groupby('case:concept:name').agg({
    'concept:name': list,
    'time:timestamp': ['min', 'max'],
    'case:proposal_title': 'first'
}).reset_index()
case_endpoints.columns = ['case_id', 'activities', 'start_time', 'end_time', 'title']

# Analyze final activities
case_endpoints['final_activity'] = case_endpoints['activities'].apply(lambda x: x[-1])
case_endpoints['has_proposal'] = case_endpoints['activities'].apply(lambda x: 'proposal' in x or 'ProposalQueued' in x)
case_endpoints['reached_execution'] = case_endpoints['activities'].apply(lambda x: 'ProposalExecuted' in x)
case_endpoints['has_votes'] = case_endpoints['activities'].apply(lambda x: 'vote' in x or 'VoteCast' in x)

print(f"\nTotal proposals: {len(case_endpoints)}")
print(f"Proposals reaching execution: {case_endpoints['reached_execution'].sum()} ({100*case_endpoints['reached_execution'].sum()/len(case_endpoints):.1f}%)")
print(f"Proposals NOT reaching execution: {(~case_endpoints['reached_execution']).sum()} ({100*(~case_endpoints['reached_execution']).sum()/len(case_endpoints):.1f}%)")

# Where do incomplete traces stop?
incomplete = case_endpoints[~case_endpoints['reached_execution']]
print(f"\nDrop-off points for incomplete traces:")
drop_off = incomplete['final_activity'].value_counts()
for activity, count in drop_off.items():
    print(f"  {activity}: {count} proposals ({100*count/len(incomplete):.1f}%)")

# Analyze by source (snapshot vs onchain)
df_with_source = df.groupby('case:concept:name')['source'].apply(lambda x: 'onchain' if 'onchain' in x.values else 'snapshot').reset_index()
df_with_source.columns = ['case_id', 'primary_source']
case_endpoints = case_endpoints.merge(df_with_source, on='case_id')

print("\nExecution rate by source:")
for source in case_endpoints['primary_source'].unique():
    subset = case_endpoints[case_endpoints['primary_source'] == source]
    exec_rate = subset['reached_execution'].sum() / len(subset) * 100
    print(f"  {source}: {subset['reached_execution'].sum()}/{len(subset)} ({exec_rate:.1f}%)")

# =============================================================================
# 3. TIMING & WAITING STATES ANALYSIS
# =============================================================================
print("\n" + "=" * 70)
print("3. TIMING & WAITING STATES ANALYSIS")
print("=" * 70)

# Calculate various timing metrics per case
timing_metrics = []

for case_id, group in df.groupby('case:concept:name'):
    group = group.sort_values('time:timestamp')
    metrics = {'case_id': case_id}
    
    # Get timestamps for key events
    voting_started = group[group['concept:name'] == 'voting_started']['time:timestamp'].min()
    voting_ended = group[group['concept:name'] == 'voting_ended']['time:timestamp'].min()
    first_vote = group[group['concept:name'].isin(['vote', 'VoteCast'])]['time:timestamp'].min()
    last_vote = group[group['concept:name'].isin(['vote', 'VoteCast'])]['time:timestamp'].max()
    proposal_event = group[group['concept:name'] == 'proposal']['time:timestamp'].min()
    queued = group[group['concept:name'] == 'ProposalQueued']['time:timestamp'].min()
    executed = group[group['concept:name'] == 'ProposalExecuted']['time:timestamp'].min()
    
    # Calculate delays
    if pd.notna(voting_started) and pd.notna(first_vote):
        metrics['voting_start_to_first_vote'] = (first_vote - voting_started).total_seconds() / 3600
    
    if pd.notna(voting_started) and pd.notna(voting_ended):
        metrics['voting_window_hours'] = (voting_ended - voting_started).total_seconds() / 3600
    
    if pd.notna(voting_ended) and pd.notna(queued):
        metrics['voting_end_to_queue'] = (queued - voting_ended).total_seconds() / 3600
    
    if pd.notna(queued) and pd.notna(executed):
        metrics['queue_to_execution'] = (executed - queued).total_seconds() / 3600
    
    # Total votes
    metrics['total_votes'] = len(group[group['concept:name'].isin(['vote', 'VoteCast'])])
    
    # Calculate vote timing distribution (how spread out are votes?)
    votes = group[group['concept:name'].isin(['vote', 'VoteCast'])]
    if len(votes) > 1 and pd.notna(voting_started) and pd.notna(voting_ended):
        voting_window = (voting_ended - voting_started).total_seconds()
        if voting_window > 0:
            # Normalized vote times (0 = start, 1 = end)
            vote_positions = [(v - voting_started).total_seconds() / voting_window for v in votes['time:timestamp']]
            metrics['votes_in_first_quarter'] = sum(1 for v in vote_positions if v < 0.25) / len(vote_positions)
            metrics['votes_in_last_quarter'] = sum(1 for v in vote_positions if v > 0.75) / len(vote_positions)
    
    timing_metrics.append(metrics)

timing_df = pd.DataFrame(timing_metrics)

print("\nTime from voting start to first vote (hours):")
if 'voting_start_to_first_vote' in timing_df.columns:
    stats = timing_df['voting_start_to_first_vote'].describe()
    print(f"  Mean: {stats['mean']:.2f}h, Median: {stats['50%']:.2f}h, Max: {stats['max']:.2f}h")

print("\nVoting window duration (hours):")
if 'voting_window_hours' in timing_df.columns:
    stats = timing_df['voting_window_hours'].describe()
    print(f"  Mean: {stats['mean']:.2f}h, Median: {stats['50%']:.2f}h, Min: {stats['min']:.2f}h, Max: {stats['max']:.2f}h")

print("\nTime from voting end to queue (hours):")
if 'voting_end_to_queue' in timing_df.columns:
    stats = timing_df['voting_end_to_queue'].dropna().describe()
    print(f"  Mean: {stats['mean']:.2f}h, Median: {stats['50%']:.2f}h, Max: {stats['max']:.2f}h")

print("\nTime from queue to execution (hours):")
if 'queue_to_execution' in timing_df.columns:
    stats = timing_df['queue_to_execution'].dropna().describe()
    print(f"  Mean: {stats['mean']:.2f}h, Median: {stats['50%']:.2f}h")

print("\nVote timing distribution:")
if 'votes_in_first_quarter' in timing_df.columns:
    first_q = timing_df['votes_in_first_quarter'].mean()
    last_q = timing_df['votes_in_last_quarter'].mean()
    print(f"  Avg % votes in first quarter of voting window: {first_q*100:.1f}%")
    print(f"  Avg % votes in last quarter of voting window: {last_q*100:.1f}%")

# =============================================================================
# 4. DERIVED ACTIVITIES ANALYSIS
# =============================================================================
print("\n" + "=" * 70)
print("4. DERIVED ACTIVITIES ANALYSIS")
print("=" * 70)

# Create derived activity classifications
df_votes = df[df['concept:name'].isin(['vote', 'VoteCast'])].copy()

# Get voting windows per case
voting_windows = df.groupby('case:concept:name').apply(
    lambda x: (
        x[x['concept:name'] == 'voting_started']['time:timestamp'].min(),
        x[x['concept:name'] == 'voting_ended']['time:timestamp'].min()
    )
).to_dict()

# Classify votes
derived_activities = defaultdict(int)

for case_id, group in df_votes.groupby('case:concept:name'):
    group = group.sort_values('time:timestamp')
    
    if len(group) == 0:
        continue
    
    # FirstVote - first vote in each case
    derived_activities['FirstVote'] += 1
    
    window = voting_windows.get(case_id)
    if window and pd.notna(window[0]) and pd.notna(window[1]):
        voting_start, voting_end = window
        voting_duration = (voting_end - voting_start).total_seconds()
        
        for _, vote in group.iterrows():
            vote_time = vote['time:timestamp']
            time_from_end = (voting_end - vote_time).total_seconds()
            time_from_start = (vote_time - voting_start).total_seconds()
            
            # VoteInLastHour
            if time_from_end < 3600 and time_from_end > 0:
                derived_activities['VoteInLastHour'] += 1
            
            # VoteInFirstHour
            if time_from_start < 3600 and time_from_start > 0:
                derived_activities['VoteInFirstHour'] += 1

# Classify by voter type
voter_stats = df_votes.groupby('org:resource').agg({
    'voting_power': 'max',
    'case:concept:name': 'nunique'
}).reset_index()
voter_stats.columns = ['voter', 'max_voting_power', 'proposals_participated']

# Whale votes
whales = set(voter_stats[voter_stats['max_voting_power'] >= WHALE_THRESHOLD]['voter'])
derived_activities['VoteByWhale'] = len(df_votes[df_votes['org:resource'].isin(whales)])
derived_activities['VoteByNonWhale'] = len(df_votes) - derived_activities['VoteByWhale']

# Frequent voters (likely delegates)
delegates = set(voter_stats[voter_stats['proposals_participated'] >= DELEGATE_PATTERN_THRESHOLD]['voter'])
derived_activities['VoteByFrequentVoter'] = len(df_votes[df_votes['org:resource'].isin(delegates)])

# EOA vs Contract (simple heuristic: contracts often have lower voting power per proposal diversity)
# More sophisticated: check address patterns or on-chain data
derived_activities['VoteFromSnapshot'] = len(df_votes[df_votes['source'] == 'snapshot'])
derived_activities['VoteFromOnchain'] = len(df_votes[df_votes['source'] == 'onchain'])

print("\nDerived activity counts:")
for activity, count in sorted(derived_activities.items(), key=lambda x: -x[1]):
    pct = 100 * count / len(df_votes) if len(df_votes) > 0 else 0
    print(f"  {activity}: {count} ({pct:.1f}% of all votes)")

# =============================================================================
# 5. ACTOR-DRIVEN VARIANTS
# =============================================================================
print("\n" + "=" * 70)
print("5. ACTOR-DRIVEN VARIANTS ANALYSIS")
print("=" * 70)
print("Same process, different execution style based on who drives the voting")

# Calculate voting power concentration per proposal
voting_power_analysis = []

for case_id, group in df_votes.groupby('case:concept:name'):
    group = group.dropna(subset=['voting_power'])
    if len(group) == 0:
        continue
    
    total_vp = group['voting_power'].sum()
    if total_vp == 0:
        continue
    
    # Get top voters by voting power
    top_voters = group.nlargest(5, 'voting_power')
    top5_vp = top_voters['voting_power'].sum()
    top1_vp = group['voting_power'].max()
    
    # Check if whales participated
    whale_votes = group[group['org:resource'].isin(whales)]
    whale_vp = whale_votes['voting_power'].sum() if len(whale_votes) > 0 else 0
    
    # Check if frequent voters participated
    frequent_votes = group[group['org:resource'].isin(delegates)]
    frequent_vp = frequent_votes['voting_power'].sum() if len(frequent_votes) > 0 else 0
    
    voting_power_analysis.append({
        'case_id': case_id,
        'total_voting_power': total_vp,
        'num_voters': len(group),
        'top1_concentration': top1_vp / total_vp,
        'top5_concentration': top5_vp / total_vp,
        'whale_vp_share': whale_vp / total_vp,
        'frequent_voter_share': frequent_vp / total_vp,
        'avg_vp_per_voter': total_vp / len(group)
    })

vp_df = pd.DataFrame(voting_power_analysis)
vp_df = vp_df.merge(case_endpoints[['case_id', 'reached_execution', 'title', 'primary_source']], on='case_id')

# Classify proposals by dominant actor type
vp_df['actor_type'] = 'Retail-driven'
vp_df.loc[vp_df['top1_concentration'] > 0.5, 'actor_type'] = 'Single-whale-driven'
vp_df.loc[(vp_df['top5_concentration'] > 0.7) & (vp_df['top1_concentration'] <= 0.5), 'actor_type'] = 'Oligarch-driven'
vp_df.loc[vp_df['whale_vp_share'] > 0.5, 'actor_type'] = 'Whale-coalition'

print("\nProposal classification by actor type:")
for actor_type, group in vp_df.groupby('actor_type'):
    exec_rate = group['reached_execution'].sum() / len(group) * 100 if len(group) > 0 else 0
    print(f"\n  {actor_type}: {len(group)} proposals")
    print(f"    Execution rate: {exec_rate:.1f}%")
    print(f"    Avg voters: {group['num_voters'].mean():.0f}")
    print(f"    Avg total voting power: {group['total_voting_power'].mean():,.0f}")

print("\nTop-1 voter concentration statistics:")
print(f"  Mean: {vp_df['top1_concentration'].mean()*100:.1f}%")
print(f"  Median: {vp_df['top1_concentration'].median()*100:.1f}%")
print(f"  Max: {vp_df['top1_concentration'].max()*100:.1f}%")

print("\nTop-5 voters concentration statistics:")
print(f"  Mean: {vp_df['top5_concentration'].mean()*100:.1f}%")
print(f"  Median: {vp_df['top5_concentration'].median()*100:.1f}%")

# =============================================================================
# 6. VOTER BEHAVIOR PATTERNS
# =============================================================================
print("\n" + "=" * 70)
print("6. VOTER BEHAVIOR PATTERNS")
print("=" * 70)

# Analyze voter participation patterns
voter_behavior = df_votes.groupby('org:resource').agg({
    'case:concept:name': ['count', 'nunique'],
    'voting_power': ['mean', 'max', 'min'],
    'source': lambda x: 'both' if len(x.unique()) > 1 else x.iloc[0]
}).reset_index()
voter_behavior.columns = ['voter', 'total_votes', 'proposals', 'avg_vp', 'max_vp', 'min_vp', 'voting_source']

print(f"\nTotal unique voters: {len(voter_behavior)}")

# Voter segmentation
voter_behavior['segment'] = 'Casual'
voter_behavior.loc[voter_behavior['proposals'] >= 3, 'segment'] = 'Regular'
voter_behavior.loc[voter_behavior['proposals'] >= 10, 'segment'] = 'Active'
voter_behavior.loc[voter_behavior['proposals'] >= 25, 'segment'] = 'Power Voter'

print("\nVoter segmentation by participation:")
for segment in ['Casual', 'Regular', 'Active', 'Power Voter']:
    subset = voter_behavior[voter_behavior['segment'] == segment]
    total_vp = subset['avg_vp'].sum()
    print(f"  {segment}: {len(subset)} voters ({len(subset)/len(voter_behavior)*100:.1f}%)")

# Power law analysis
print("\nVoting power distribution (power law check):")
sorted_vp = voter_behavior['max_vp'].sort_values(ascending=False)
top_1pct = int(len(sorted_vp) * 0.01) or 1
top_10pct = int(len(sorted_vp) * 0.10) or 1
print(f"  Top 1% of voters hold: {sorted_vp.head(top_1pct).sum() / sorted_vp.sum() * 100:.1f}% of max voting power")
print(f"  Top 10% of voters hold: {sorted_vp.head(top_10pct).sum() / sorted_vp.sum() * 100:.1f}% of max voting power")

# =============================================================================
# 7. TEMPORAL PATTERNS
# =============================================================================
print("\n" + "=" * 70)
print("7. TEMPORAL PATTERNS")
print("=" * 70)

df_votes['date'] = df_votes['time:timestamp'].dt.date
df_votes['hour'] = df_votes['time:timestamp'].dt.hour
df_votes['day_of_week'] = df_votes['time:timestamp'].dt.day_name()

print("\nVotes by hour of day (top 5):")
hour_dist = df_votes['hour'].value_counts().sort_index()
for hour, count in hour_dist.nlargest(5).items():
    print(f"  {hour:02d}:00 - {count} votes ({count/len(df_votes)*100:.1f}%)")

print("\nVotes by day of week:")
day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
day_dist = df_votes['day_of_week'].value_counts()
for day in day_order:
    if day in day_dist:
        print(f"  {day}: {day_dist[day]} votes ({day_dist[day]/len(df_votes)*100:.1f}%)")

# Trend over time
df_votes['year_month'] = df_votes['time:timestamp'].dt.to_period('M')
monthly = df_votes.groupby('year_month').size()
print(f"\nMonthly activity range: {monthly.min()} to {monthly.max()} votes/month")
print(f"Most active month: {monthly.idxmax()} with {monthly.max()} votes")

# =============================================================================
# 8. KEY INSIGHTS SUMMARY
# =============================================================================
print("\n" + "=" * 70)
print("KEY INSIGHTS SUMMARY")
print("=" * 70)

insights = []

# Insight 1: Execution rate
exec_rate = case_endpoints['reached_execution'].sum() / len(case_endpoints) * 100
insights.append(f"1. LOW EXECUTION RATE: Only {exec_rate:.1f}% of proposals reach execution. "
                f"{(~case_endpoints['reached_execution']).sum()}/{len(case_endpoints)} proposals fail to complete.")

# Insight 2: Snapshot vs onchain
snapshot_exec = case_endpoints[case_endpoints['primary_source'] == 'snapshot']['reached_execution'].mean() * 100
onchain_exec = case_endpoints[case_endpoints['primary_source'] == 'onchain']['reached_execution'].mean() * 100
if abs(snapshot_exec - onchain_exec) > 10:
    insights.append(f"2. SOURCE MATTERS: Snapshot proposals have {snapshot_exec:.1f}% execution rate vs "
                    f"{onchain_exec:.1f}% for onchain proposals.")

# Insight 3: Power concentration
if vp_df['top5_concentration'].mean() > 0.5:
    insights.append(f"3. VOTING POWER CONCENTRATION: On average, top 5 voters control "
                    f"{vp_df['top5_concentration'].mean()*100:.1f}% of voting power in each proposal.")

# Insight 4: Vote timing
if 'votes_in_last_quarter' in timing_df.columns:
    last_q = timing_df['votes_in_last_quarter'].mean()
    if last_q > 0.3:
        insights.append(f"4. LAST-MINUTE VOTING: {last_q*100:.1f}% of votes occur in the last quarter of voting period.")

# Insight 5: Whale influence
whale_driven = len(vp_df[vp_df['actor_type'].isin(['Single-whale-driven', 'Whale-coalition'])])
insights.append(f"5. WHALE INFLUENCE: {whale_driven}/{len(vp_df)} proposals ({whale_driven/len(vp_df)*100:.1f}%) "
                f"are whale-driven (single whale or coalition).")

for insight in insights:
    print(f"\n{insight}")

print("\n" + "=" * 70)
print("ANALYSIS COMPLETE")
print("=" * 70)
