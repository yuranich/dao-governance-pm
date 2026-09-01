#!/usr/bin/env python3
"""
ENS DAO Process Mining — Script 1: Process Discovery & Overview

Discovers process models (DFG, Petri net, BPMN, heuristic net) for the
full log and for snapshot/onchain subsets independently.
"""

import pandas as pd
import pm4py
import warnings
warnings.filterwarnings('ignore')

from daogov.paths import event_log, FIGURES_DIR

FILE_PATH = event_log('ens_linked')
OUT_PREFIX = f"{FIGURES_DIR}/ens_out_01_"

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
print("SCRIPT 1 — PROCESS DISCOVERY & OVERVIEW")
print("=" * 72)

# ── Dataset overview ─────────────────────────────────────────────────────
n_events = len(df)
n_cases = df['case:concept:name'].nunique()
n_voters = df[df['concept:name'].isin(['vote', 'VoteCast'])]['org:resource'].nunique()
date_min, date_max = df['time:timestamp'].min(), df['time:timestamp'].max()

print(f"\nEvents: {n_events:,}  |  Cases: {n_cases}  |  Unique voters: {n_voters:,}")
print(f"Date range: {date_min.date()} → {date_max.date()}")
print(f"\nActivity counts:")
for act, cnt in df['concept:name'].value_counts().items():
    print(f"  {act:<20s} {cnt:>8,}")

print(f"\nSource breakdown:")
for src, cnt in df['source'].value_counts().items():
    print(f"  {src:<12s} {cnt:>8,}")

# ── Start / end activities ───────────────────────────────────────────────
start_act = pm4py.get_start_activities(log)
end_act = pm4py.get_end_activities(log)
print(f"\nStart activities: {dict(start_act)}")
print(f"End activities:   {dict(end_act)}")

# ── DFG (frequency) ─────────────────────────────────────────────────────
dfg, sa, ea = pm4py.discover_dfg(log)
print(f"\nDFG edges (top 15):")
for (s, t), c in sorted(dfg.items(), key=lambda x: -x[1])[:15]:
    print(f"  {s} → {t}: {c}")

pm4py.save_vis_dfg(dfg, sa, ea, f"{OUT_PREFIX}dfg_full.png")
print(f"  Saved {OUT_PREFIX}dfg_full.png")

# ── Performance DFG ──────────────────────────────────────────────────────
dfg_perf, sa_p, ea_p = pm4py.discover_performance_dfg(log)
pm4py.save_vis_performance_dfg(dfg_perf, sa_p, ea_p, f"{OUT_PREFIX}dfg_performance.png")
print(f"  Saved {OUT_PREFIX}dfg_performance.png")

# ── Petri net (inductive miner) ─────────────────────────────────────────
net, im, fm = pm4py.discover_petri_net_inductive(log)
pm4py.save_vis_petri_net(net, im, fm, f"{OUT_PREFIX}petri_net.png")
print(f"  Saved {OUT_PREFIX}petri_net.png")

# ── BPMN ─────────────────────────────────────────────────────────────────
bpmn = pm4py.discover_bpmn_inductive(log)
pm4py.save_vis_bpmn(bpmn, f"{OUT_PREFIX}bpmn.png")
print(f"  Saved {OUT_PREFIX}bpmn.png")

# ── Process tree ─────────────────────────────────────────────────────────
tree = pm4py.discover_process_tree_inductive(log)
pm4py.save_vis_process_tree(tree, f"{OUT_PREFIX}process_tree.png")
print(f"  Saved {OUT_PREFIX}process_tree.png")

# ── Heuristic net ────────────────────────────────────────────────────────
heu = pm4py.discover_heuristics_net(log)
pm4py.save_vis_heuristics_net(heu, f"{OUT_PREFIX}heuristic_net.png")
print(f"  Saved {OUT_PREFIX}heuristic_net.png")

# ── Separate DFGs for snapshot / onchain ─────────────────────────────────
for subset_name in ['snapshot', 'onchain']:
    df_sub = df[df['source'] == subset_name]
    if df_sub.empty:
        continue
    log_sub = pm4py.convert_to_event_log(df_sub)
    d, s, e = pm4py.discover_dfg(log_sub)
    fname = f"{OUT_PREFIX}dfg_{subset_name}.png"
    pm4py.save_vis_dfg(d, s, e, fname)
    print(f"  Saved {fname} ({len(df_sub):,} events, {df_sub['case:concept:name'].nunique()} cases)")

# ── Cases with both sources (linked proposals) ──────────────────────────
snap_cases = set(df[df['source'] == 'snapshot']['case:concept:name'].unique())
onch_cases = set(df[df['source'] == 'onchain']['case:concept:name'].unique())
linked = snap_cases & onch_cases
snap_only = snap_cases - onch_cases
onch_only = onch_cases - snap_cases

print(f"\nProposal routing:")
print(f"  Snapshot-only:  {len(snap_only)}")
print(f"  Onchain-only:   {len(onch_only)}")
print(f"  Both (linked):  {len(linked)}")

# ── DFG for linked proposals only ────────────────────────────────────────
if linked:
    df_linked = df[df['case:concept:name'].isin(linked)]
    log_linked = pm4py.convert_to_event_log(df_linked)
    d, s, e = pm4py.discover_dfg(log_linked)
    fname = f"{OUT_PREFIX}dfg_linked.png"
    pm4py.save_vis_dfg(d, s, e, fname)
    print(f"  Saved {fname} ({len(df_linked):,} events, {len(linked)} cases)")

print("\n✓ Script 1 complete")
