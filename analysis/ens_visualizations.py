#!/usr/bin/env python3
"""
ENS DAO Process Mining - Visualization Export

Exports process models and generates visualization data.
"""

import pandas as pd
import pm4py
import warnings
warnings.filterwarnings('ignore')

# =============================================================================
# DATA LOADING
# =============================================================================
from daogov.paths import event_log, figure

FILE_PATH = event_log('ens')

df = pd.read_csv(FILE_PATH)
df['time:timestamp'] = pd.to_datetime(df['time:timestamp'])
df = pm4py.format_dataframe(df, 
                            case_id='case:concept:name',
                            activity_key='concept:name', 
                            timestamp_key='time:timestamp')

log = pm4py.convert_to_event_log(df)

print("=" * 70)
print("ENS DAO PROCESS MODEL EXPORT")
print("=" * 70)

# =============================================================================
# 1. DISCOVER AND SAVE DFG
# =============================================================================
print("\n1. Discovering Directly-Follows Graph...")

dfg, start_activities, end_activities = pm4py.discover_dfg(log)
pm4py.save_vis_dfg(dfg, start_activities, end_activities, figure("ens_dfg.png"))
print("   Saved: ens_dfg.png")

# =============================================================================
# 2. DISCOVER AND SAVE PETRI NET (Inductive Miner)
# =============================================================================
print("\n2. Discovering Petri Net (Inductive Miner)...")

net, initial_marking, final_marking = pm4py.discover_petri_net_inductive(log)
pm4py.save_vis_petri_net(net, initial_marking, final_marking, figure("ens_petri_net.png"))
print("   Saved: ens_petri_net.png")

# =============================================================================
# 3. DISCOVER BPMN
# =============================================================================
print("\n3. Discovering BPMN Model...")

bpmn = pm4py.discover_bpmn_inductive(log)
pm4py.save_vis_bpmn(bpmn, figure("ens_bpmn.png"))
print("   Saved: ens_bpmn.png")

# =============================================================================
# 4. PROCESS TREE
# =============================================================================
print("\n4. Discovering Process Tree...")

tree = pm4py.discover_process_tree_inductive(log)
pm4py.save_vis_process_tree(tree, figure("ens_process_tree.png"))
print("   Saved: ens_process_tree.png")

# =============================================================================
# 5. SEPARATE PROCESSES FOR SNAPSHOT AND ONCHAIN
# =============================================================================
print("\n5. Separate process models for Snapshot vs Onchain...")

# Snapshot process
df_snapshot = df[df['source'] == 'snapshot']
if len(df_snapshot) > 0:
    log_snapshot = pm4py.convert_to_event_log(df_snapshot)
    dfg_snap, start_snap, end_snap = pm4py.discover_dfg(log_snapshot)
    pm4py.save_vis_dfg(dfg_snap, start_snap, end_snap, figure("ens_dfg_snapshot.png"))
    print("   Saved: ens_dfg_snapshot.png")

# Onchain process  
df_onchain = df[df['source'] == 'onchain']
if len(df_onchain) > 0:
    log_onchain = pm4py.convert_to_event_log(df_onchain)
    dfg_onchain, start_onchain, end_onchain = pm4py.discover_dfg(log_onchain)
    pm4py.save_vis_dfg(dfg_onchain, start_onchain, end_onchain, figure("ens_dfg_onchain.png"))
    print("   Saved: ens_dfg_onchain.png")

# =============================================================================
# 6. PERFORMANCE DFG (with timing)
# =============================================================================
print("\n6. Discovering Performance DFG (with timing annotations)...")

dfg_perf, start_perf, end_perf = pm4py.discover_performance_dfg(log)
pm4py.save_vis_performance_dfg(dfg_perf, start_perf, end_perf, figure("ens_dfg_performance.png"))
print("   Saved: ens_dfg_performance.png")

# =============================================================================
# 7. HEURISTICS MINER
# =============================================================================
print("\n7. Discovering Heuristic Net...")

heu_net = pm4py.discover_heuristics_net(log)
pm4py.save_vis_heuristics_net(heu_net, figure("ens_heuristic_net.png"))
print("   Saved: ens_heuristic_net.png")

# =============================================================================
# 8. DOTTED CHART (event distribution over time)
# =============================================================================
print("\n8. Creating Dotted Chart...")

try:
    pm4py.save_vis_dotted_chart(df, figure("ens_dotted_chart.png"))
    print("   Saved: ens_dotted_chart.png")
except Exception as e:
    print(f"   Skipped (compatibility issue): {e}")

# =============================================================================
# 9. CASE DURATION DISTRIBUTION
# =============================================================================
print("\n9. Creating Case Duration Graph...")

try:
    pm4py.save_vis_case_duration_graph(df, figure("ens_case_duration.png"))
    print("   Saved: ens_case_duration.png")
except Exception as e:
    print(f"   Skipped (compatibility issue): {e}")

# =============================================================================
# 10. EVENTS OVER TIME
# =============================================================================
print("\n10. Creating Events Over Time Graph...")

try:
    pm4py.save_vis_events_distribution_graph(df, figure("ens_events_over_time.png"))
    print("   Saved: ens_events_over_time.png")
except Exception as e:
    print(f"   Skipped (compatibility issue): {e}")

print("\n" + "=" * 70)
print("All visualizations exported successfully!")
print("=" * 70)

# =============================================================================
# CONFORMANCE CHECKING
# =============================================================================
print("\n" + "=" * 70)
print("CONFORMANCE CHECKING")
print("=" * 70)

# Check conformance against discovered model
print("\nChecking conformance against Inductive Miner model...")

# Token-based replay fitness
fitness_token = pm4py.fitness_token_based_replay(log, net, initial_marking, final_marking)
print(f"\nToken-based Replay Fitness:")
print(f"  Average trace fitness: {fitness_token['average_trace_fitness']:.4f}")
print(f"  Log fitness: {fitness_token['log_fitness']:.4f}")

# Precision
precision = pm4py.precision_token_based_replay(log, net, initial_marking, final_marking)
print(f"\nPrecision (token-based): {precision:.4f}")

# Simplicity
simplicity = pm4py.algo.evaluation.simplicity.algorithm.apply(net)
print(f"Simplicity: {simplicity:.4f}")

print("\n" + "=" * 70)
print("COMPLETE")
print("=" * 70)

