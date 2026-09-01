"""
Simulation 01: Quadratic Voting

VP_new = sqrt(VP_old) — reduces whale influence by applying a sublinear
transformation. Recomputes all concentration metrics and checks for
majority coalition changes.

Reference: Buterin, Hitzig & Weyl (2019) "Liberal Radicalism"
"""

import pandas as pd
import numpy as np
import random
import time
from pathlib import Path

from daogov.paths import event_log, result
from governance_metrics import (
    PAPER, load_votes, compute_all_metrics, summarize_metrics,
    compute_gini_overall, check_outcome_flips, gini,
)

MECHANISM_NAME = "Quadratic Voting"
MECHANISM_SHORT = "QV"
OUTPUT_FILE = result("simulation_results_quadratic.md")


def transform_vp(votes: pd.DataFrame) -> pd.DataFrame:
    """Apply quadratic voting: VP_new = sqrt(VP_old)."""
    transformed = votes.copy()
    transformed["voting_power"] = np.sqrt(transformed["voting_power"])
    return transformed


def run_simulation(name: str, csv_path: Path) -> dict:
    print(f"\n{'='*60}")
    print(f"  {MECHANISM_SHORT} Simulation: {name}")
    print(f"{'='*60}")

    t0 = time.time()
    original_votes = load_votes(csv_path)
    n_proposals = original_votes["case:concept:name"].nunique()
    n_voters = original_votes["org:resource"].nunique()
    print(f"  Loaded {len(original_votes):,} votes, {n_proposals} proposals, {n_voters:,} voters")

    print("  Computing baseline metrics...")
    baseline_classified = compute_all_metrics(original_votes)
    baseline_summary = summarize_metrics(baseline_classified)
    baseline_gini = compute_gini_overall(original_votes)

    print(f"  Applying {MECHANISM_NAME} transformation...")
    transformed_votes = transform_vp(original_votes)

    print("  Computing transformed metrics...")
    trans_classified = compute_all_metrics(transformed_votes)
    trans_summary = summarize_metrics(trans_classified)
    trans_gini = compute_gini_overall(transformed_votes)

    print("  Checking outcome flips...")
    flips = check_outcome_flips(original_votes, transformed_votes)

    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.1f}s")

    return {
        "name": name,
        "n_proposals": n_proposals,
        "n_voters": n_voters,
        "baseline_summary": baseline_summary,
        "baseline_gini": baseline_gini,
        "trans_summary": trans_summary,
        "trans_gini": trans_gini,
        "baseline_classified": baseline_classified,
        "trans_classified": trans_classified,
        "flips": flips,
    }


def pct(v):
    return f"{v*100:.1f}%"


def fmt(v, decimals=4):
    return f"{v:.{decimals}f}"


def delta(baseline, transformed):
    diff = transformed - baseline
    if baseline != 0:
        rel = diff / abs(baseline) * 100
        sign = "+" if diff > 0 else ""
        return f"{sign}{rel:.1f}%"
    return "N/A"


def generate_report(results: list[dict]):
    lines = []
    lines.append(f"# Simulation Results: {MECHANISM_NAME}")
    lines.append("")
    lines.append(f"**Mechanism**: VP_new = sqrt(VP_old)")
    lines.append("")
    lines.append("Quadratic voting reduces the marginal influence of each additional token,")
    lines.append("equalizing power between large and small holders. A voter with 10,000 tokens")
    lines.append("gets VP=100, while a voter with 1 token gets VP=1 — a 100x ratio instead of 10,000x.")
    lines.append("")
    lines.append("---")
    lines.append("")

    for r in results:
        b = r["baseline_summary"]
        t = r["trans_summary"]
        name = r["name"]

        lines.append(f"## {name}")
        lines.append("")
        lines.append(f"**Data**: {r['n_proposals']} proposals, {r['n_voters']:,} voters")
        lines.append("")

        lines.append("### Concentration Indices")
        lines.append("")
        lines.append("| Metric | Baseline | Quadratic | Change |")
        lines.append("|---|---|---|---|")

        metrics = [
            ("C1 mean", "c1_mean"), ("C1 median", "c1_median"),
            ("C3 mean", "c3_mean"), ("C3 median", "c3_median"),
            ("C5 mean", "c5_mean"), ("C5 median", "c5_median"),
        ]
        for label, key in metrics:
            lines.append(f"| {label} | {pct(b[key])} | {pct(t[key])} | {delta(b[key], t[key])} |")

        lines.append(f"| Gini (overall) | {fmt(r['baseline_gini'])} | {fmt(r['trans_gini'])} | {delta(r['baseline_gini'], r['trans_gini'])} |")
        lines.append("")

        lines.append("### Shapley-Shubik & Taxonomy")
        lines.append("")
        lines.append("| Metric | Baseline | Quadratic | Change |")
        lines.append("|---|---|---|---|")
        lines.append(f"| SS max (mean) | {fmt(b['ss_max_mean'])} | {fmt(t['ss_max_mean'])} | {delta(b['ss_max_mean'], t['ss_max_mean'])} |")
        lines.append(f"| SS max (median) | {fmt(b['ss_max_median'])} | {fmt(t['ss_max_median'])} | {delta(b['ss_max_median'], t['ss_max_median'])} |")
        lines.append(f"| % controlled | {pct(b['controlled_pct'])} | {pct(t['controlled_pct'])} | {delta(b['controlled_pct'], t['controlled_pct'])} |")
        lines.append(f"| % widely-held block | {pct(b['widely_held_block_pct'])} | {pct(t['widely_held_block_pct'])} | {delta(b['widely_held_block_pct'], t['widely_held_block_pct'])} |")
        lines.append(f"| % widely-held no block | {pct(b['widely_held_no_block_pct'])} | {pct(t['widely_held_no_block_pct'])} | {delta(b['widely_held_no_block_pct'], t['widely_held_no_block_pct'])} |")
        lines.append(f"| % whale control | {pct(b['whale_control_pct'])} | {pct(t['whale_control_pct'])} | {delta(b['whale_control_pct'], t['whale_control_pct'])} |")
        lines.append("")

        flips = r["flips"]
        n_flipped = flips["outcome_flipped"].sum() if len(flips) > 0 else 0
        n_total = len(flips)
        flip_pct = n_flipped / n_total * 100 if n_total > 0 else 0

        lines.append("### Outcome Impact")
        lines.append("")
        lines.append(f"- Proposals with majority coalition change: **{n_flipped}** / {n_total} ({flip_pct:.1f}%)")
        if len(flips) > 0:
            avg_overlap = flips["majority_coalition_overlap"].mean()
            avg_size_orig = flips["majority_size_orig"].mean()
            avg_size_trans = flips["majority_size_trans"].mean()
            lines.append(f"- Average majority coalition overlap: {avg_overlap:.3f}")
            lines.append(f"- Average majority coalition size: {avg_size_orig:.1f} (baseline) → {avg_size_trans:.1f} (QV)")
        lines.append("")

        lines.append("### C3 Comparison with Corporate Benchmarks")
        lines.append("")
        lines.append("| Reference | C3 Median |")
        lines.append("|---|---|")
        lines.append(f"| Common law (corporate) | {pct(PAPER['c3_median_common_law'])} |")
        lines.append(f"| French civil law (corporate) | {pct(PAPER['c3_median_french_civil'])} |")
        lines.append(f"| {name} baseline | {pct(b['c3_median'])} |")
        lines.append(f"| **{name} + {MECHANISM_SHORT}** | **{pct(t['c3_median'])}** |")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append(f"Quadratic voting (VP = √VP) reduces concentration across all metrics.")
    lines.append("The transformation compresses the VP distribution, making large holders")
    lines.append("less dominant while preserving the ordering of voter influence.")
    lines.append("")
    lines.append(f"*Generated by `simulation_01_quadratic.py`*")

    OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written to {OUTPUT_FILE}")


def main():
    random.seed(42)
    np.random.seed(42)

    configs = [
        ("ENS", event_log("ens_linked")),
        ("AAVE", event_log("aave_linked")),
    ]

    results = []
    for name, path in configs:
        if not path.exists():
            print(f"ERROR: {path} not found")
            continue
        results.append(run_simulation(name, path))

    if results:
        generate_report(results)


if __name__ == "__main__":
    main()
