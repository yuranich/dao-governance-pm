#!/usr/bin/env python3
"""
ENS DAO Process Mining — Script 5: Conformance Checking & Temporal Evolution

Analyses:
 - Conformance checking (fitness, simplicity) for snapshot/onchain subsets
 - Temporal splits: compare early vs late governance
 - Cross-conformance: late traces against early model (concept drift detection)
 - Yearly governance evolution
"""

import pandas as pd
import numpy as np
import pm4py
import warnings
warnings.filterwarnings('ignore')

from daogov.paths import event_log, FIGURES_DIR

FILE_PATH = event_log('ens_linked')
OUT_PREFIX = f"{FIGURES_DIR}/ens_out_05_"

df = pd.read_csv(FILE_PATH)
df['time:timestamp'] = pd.to_datetime(df['time:timestamp'])
df = pm4py.format_dataframe(
    df,
    case_id='case:concept:name',
    activity_key='concept:name',
    timestamp_key='time:timestamp',
)

print("=" * 72)
print("SCRIPT 5 — CONFORMANCE CHECKING & TEMPORAL EVOLUTION")
print("=" * 72)


def quick_conformance(label, dataframe):
    """Token-based replay fitness + simplicity on a subset (precision skipped for perf)."""
    log_sub = pm4py.convert_to_event_log(dataframe)
    net, im, fm = pm4py.discover_petri_net_inductive(log_sub)
    fit = pm4py.fitness_token_based_replay(log_sub, net, im, fm)
    simp = pm4py.algo.evaluation.simplicity.algorithm.apply(net)

    print(f"\n  {label}:")
    print(f"    Traces: {dataframe['case:concept:name'].nunique()}")
    print(f"    Token-based fitness: {fit['average_trace_fitness']:.4f}")
    print(f"    Log fitness:         {fit['log_fitness']:.4f}")
    print(f"    Simplicity:          {simp:.4f}")
    return net, im, fm, fit


# ── 1. Conformance per governance type ───────────────────────────────────
print("\n" + "-" * 72)
print("1. CONFORMANCE BY GOVERNANCE TYPE")
print("-" * 72)

for src in ['snapshot', 'onchain']:
    df_sub = df[df['source'] == src]
    if df_sub.empty:
        continue
    net_s, im_s, fm_s, _ = quick_conformance(src.upper(), df_sub)
    fname = f"{OUT_PREFIX}petri_{src}.png"
    pm4py.save_vis_petri_net(net_s, im_s, fm_s, fname)
    print(f"    Saved {fname}")

# ── 2. Temporal split: early vs late governance ──────────────────────────
print("\n" + "-" * 72)
print("2. TEMPORAL EVOLUTION — EARLY vs LATE GOVERNANCE")
print("-" * 72)

case_start = df.groupby('case:concept:name')['time:timestamp'].min()
median_date = case_start.median()
early_cases = set(case_start[case_start <= median_date].index)
late_cases = set(case_start[case_start > median_date].index)

print(f"\nSplit date: {median_date.date()}")
print(f"Early half: {len(early_cases)} cases  |  Late half: {len(late_cases)} cases")

for label, cases in [('EARLY', early_cases), ('LATE', late_cases)]:
    df_sub = df[df['case:concept:name'].isin(cases)]

    n_votes = df_sub[df_sub['concept:name'].isin(['vote', 'VoteCast'])].shape[0]
    n_voters = df_sub[df_sub['concept:name'].isin(['vote', 'VoteCast'])]['org:resource'].nunique()

    net_t, im_t, fm_t, _ = quick_conformance(label, df_sub)

    exec_cases = df_sub[df_sub['concept:name'] == 'ProposalExecuted']['case:concept:name'].nunique()
    print(f"    Events: {len(df_sub):,}  Votes: {n_votes:,}  Voters: {n_voters:,}")
    print(f"    Execution rate: {exec_cases}/{len(cases)} ({exec_cases/len(cases)*100:.1f}%)")

    # Save DFG per period
    log_sub = pm4py.convert_to_event_log(df_sub)
    dfg_t, sa_t, ea_t = pm4py.discover_dfg(log_sub)
    fname = f"{OUT_PREFIX}dfg_{label.lower()}.png"
    pm4py.save_vis_dfg(dfg_t, sa_t, ea_t, fname)
    print(f"    Saved {fname}")

# ── 3. Cross-conformance: concept drift detection ────────────────────────
print("\n" + "-" * 72)
print("3. CROSS-CONFORMANCE — CONCEPT DRIFT DETECTION")
print("-" * 72)

df_early = df[df['case:concept:name'].isin(early_cases)]
df_late = df[df['case:concept:name'].isin(late_cases)]
log_early = pm4py.convert_to_event_log(df_early)
log_late = pm4py.convert_to_event_log(df_late)

net_early, im_early, fm_early = pm4py.discover_petri_net_inductive(log_early)

fit_ee = pm4py.fitness_token_based_replay(log_early, net_early, im_early, fm_early)
fit_le = pm4py.fitness_token_based_replay(log_late, net_early, im_early, fm_early)

print(f"\nModel trained on EARLY cases:")
print(f"  Fitness on EARLY traces: {fit_ee['log_fitness']:.4f}")
print(f"  Fitness on LATE traces:  {fit_le['log_fitness']:.4f}")

delta = fit_ee['log_fitness'] - fit_le['log_fitness']
if abs(delta) > 0.05:
    print(f"  → Fitness drop of {delta:.4f} — indicates CONCEPT DRIFT")
else:
    print(f"  → Delta {delta:.4f} — process is relatively STABLE across periods")

# ── 4. Yearly governance metrics ─────────────────────────────────────────
print("\n" + "-" * 72)
print("4. YEARLY GOVERNANCE METRICS")
print("-" * 72)

case_year = df.groupby('case:concept:name').agg(
    year=('time:timestamp', lambda x: x.min().year),
    n_events=('concept:name', 'count'),
    executed=('concept:name', lambda x: 'ProposalExecuted' in x.values),
    n_votes=('concept:name', lambda x: sum(a in ['vote', 'VoteCast'] for a in x)),
    unique_voters=('org:resource', 'nunique'),
).reset_index()

print(f"\n{'Year':>6s} {'Cases':>6s} {'Exec':>6s} {'Exec%':>6s} "
      f"{'AvgVotes':>10s} {'AvgVoters':>10s}")
print("-" * 50)
for year, grp in case_year.groupby('year'):
    n = len(grp)
    ex = grp['executed'].sum()
    pct = ex / n * 100 if n else 0
    print(f"{year:>6} {n:>6} {ex:>6} {pct:>5.1f}% "
          f"{grp['n_votes'].mean():>10.0f} {grp['unique_voters'].mean():>10.0f}")

# ── 5. Trace variant stability ───────────────────────────────────────────
print("\n" + "-" * 72)
print("5. TRACE VARIANT STABILITY OVER TIME")
print("-" * 72)

def get_simplified_variant(g):
    acts = g.sort_values('time:timestamp')['concept:name'].tolist()
    simplified = [acts[0]]
    for a in acts[1:]:
        if a != simplified[-1]:
            simplified.append(a)
    return tuple(simplified)

case_variants = df.groupby('case:concept:name').apply(get_simplified_variant, include_groups=False)
case_years = df.groupby('case:concept:name')['time:timestamp'].min().dt.year

variant_by_year = pd.DataFrame({
    'variant': case_variants,
    'year': case_years,
})

for year, grp in variant_by_year.groupby('year'):
    vc = grp['variant'].value_counts()
    print(f"\n  {year}: {len(grp)} cases, {len(vc)} distinct variants")
    for v, c in vc.head(3).items():
        print(f"    [{c}] {' → '.join(v[:6])}{'…' if len(v) > 6 else ''}")

print("\n✓ Script 5 complete")
