"""
Shared governance concentration metrics module.

Extracted from comparative_analysis.py for reuse by simulation scripts.
Computes C1/C3/C5, Shapley-Shubik, Gini, and taxonomy classification.
"""

import pandas as pd
import numpy as np
from pathlib import Path

VOTE_ACTIVITIES = {"vote", "Vote", "VoteCast", "VoteEmitted"}

SS_THRESHOLD = 0.75
MAJORITY_QUOTA = 0.50
BLOCK_THRESHOLD = 0.05
SS_SAMPLES = 10_000
TOP_K_VOTERS = 50

PAPER = {
    "c1_mean": 0.315,
    "c3_mean": 0.417,
    "c5_mean": 0.446,
    "c1_median": 0.2411,
    "c3_median": 0.3909,
    "c5_median": 0.4410,
    "controlled_pct": 0.44,
    "widely_held_block_pct": 0.47,
    "widely_held_no_block_pct": 0.09,
    "c3_median_common_law": 0.290,
    "c3_median_french_civil": 0.622,
    "c3_median_german_civil": 0.444,
    "c3_median_scandinavian": 0.361,
    "controlled_common_law": 0.32,
    "controlled_french_civil": 0.66,
}


def load_votes(csv_path: Path) -> pd.DataFrame:
    """Load event log and filter to vote events with valid voting power."""
    df = pd.read_csv(csv_path, low_memory=False)
    votes = df[df["concept:name"].isin(VOTE_ACTIVITIES)].copy()
    votes["voting_power"] = pd.to_numeric(votes["voting_power"], errors="coerce")
    votes = votes.dropna(subset=["voting_power", "org:resource"])
    votes = votes[votes["voting_power"] > 0]
    return votes


def gini(values: np.ndarray) -> float:
    """Gini coefficient. 0 = perfect equality, 1 = perfect inequality."""
    v = np.sort(np.asarray(values, dtype=float))
    v = v[v > 0]
    n = len(v)
    if n == 0:
        return 0.0
    idx = np.arange(1, n + 1)
    return float((2 * np.sum(idx * v) - (n + 1) * np.sum(v)) / (n * np.sum(v)))


def compute_concentration(votes: pd.DataFrame) -> pd.DataFrame:
    """Compute C1, C3, C5 per proposal (case).

    Each proposal is treated as a "firm"; each voter's VP share within
    the proposal is their equity holding.
    """
    agg = (
        votes.groupby(["case:concept:name", "org:resource"])["voting_power"]
        .sum()
        .reset_index()
    )
    total_vp = agg.groupby("case:concept:name")["voting_power"].transform("sum")
    agg["share"] = agg["voting_power"] / total_vp

    results = []
    for case_id, grp in agg.groupby("case:concept:name"):
        shares = grp["share"].sort_values(ascending=False).values
        n_voters = len(shares)
        total = shares.sum()
        c1 = shares[0] if n_voters >= 1 else 0
        c3 = shares[:3].sum() if n_voters >= 3 else total
        c5 = shares[:5].sum() if n_voters >= 5 else total

        max_block = shares[0]
        n_block = int((shares >= BLOCK_THRESHOLD).sum())

        results.append({
            "case_id": case_id,
            "n_voters": n_voters,
            "c1": c1,
            "c3": c3,
            "c5": c5,
            "max_block": max_block,
            "n_block_holders": n_block,
        })

    return pd.DataFrame(results)


def shapley_shubik_monte_carlo(weights: np.ndarray, n_samples: int = SS_SAMPLES) -> np.ndarray:
    """Approximate Shapley-Shubik power index via Monte Carlo random permutations."""
    n = len(weights)
    if n == 0:
        return np.array([])
    if n == 1:
        return np.array([1.0])

    pivots = np.zeros(n, dtype=np.int64)
    indices = np.arange(n)

    for _ in range(n_samples):
        np.random.shuffle(indices)
        cumsum = 0.0
        for idx in indices:
            cumsum += weights[idx]
            if cumsum >= MAJORITY_QUOTA:
                pivots[idx] += 1
                break

    return pivots / n_samples


def classify_proposals_ss(votes: pd.DataFrame, conc: pd.DataFrame) -> pd.DataFrame:
    """Compute Shapley-Shubik index for top voters per proposal and classify control."""
    agg = (
        votes.groupby(["case:concept:name", "org:resource"])["voting_power"]
        .sum()
        .reset_index()
    )
    total_vp = agg.groupby("case:concept:name")["voting_power"].transform("sum")
    agg["share"] = agg["voting_power"] / total_vp

    ss_results = []
    for case_id, grp in agg.groupby("case:concept:name"):
        shares_sorted = grp.sort_values("share", ascending=False)
        top_k = shares_sorted.head(TOP_K_VOTERS)
        top_shares = top_k["share"].values.copy()

        remainder = 1.0 - top_shares.sum()
        if remainder > 1e-9:
            top_shares = np.append(top_shares, remainder)

        ss_indices = shapley_shubik_monte_carlo(top_shares)
        actual_ss = ss_indices[:len(top_k)]
        max_ss = actual_ss.max() if len(actual_ss) > 0 else 0.0

        ss_results.append({
            "case_id": case_id,
            "ss_max": max_ss,
            "ss_controlled": max_ss >= SS_THRESHOLD,
            "ss_top1": actual_ss[0] if len(actual_ss) > 0 else 0,
            "n_voters_in_ss": len(top_k),
        })

    ss_df = pd.DataFrame(ss_results)
    return conc.merge(ss_df, on="case_id", how="left")


def classify_taxonomy(row: pd.Series) -> str:
    """Classify proposal using the paper's corporate control taxonomy."""
    if row.get("ss_controlled", False):
        return "controlled"
    if row["max_block"] >= BLOCK_THRESHOLD:
        return "widely_held_block"
    return "widely_held_no_block"


def classify_controller_type(row: pd.Series) -> str:
    """Map controller type analogy (corporate → DAO)."""
    if row["taxonomy"] == "widely_held_no_block":
        return "retail"
    if row["taxonomy"] == "controlled":
        if row["c1"] >= 0.50:
            return "whale_control"
        return "coalition_control"
    return "delegate_block"


def compute_all_metrics(votes: pd.DataFrame) -> pd.DataFrame:
    """Full pipeline: concentration → Shapley-Shubik → taxonomy."""
    conc = compute_concentration(votes)
    classified = classify_proposals_ss(votes, conc)
    classified["taxonomy"] = classified.apply(classify_taxonomy, axis=1)
    classified["controller_type"] = classified.apply(classify_controller_type, axis=1)
    return classified


def summarize_metrics(classified: pd.DataFrame) -> dict:
    """Compute summary statistics from per-proposal classified data."""
    return {
        "c1_mean": classified["c1"].mean(),
        "c1_median": classified["c1"].median(),
        "c3_mean": classified["c3"].mean(),
        "c3_median": classified["c3"].median(),
        "c5_mean": classified["c5"].mean(),
        "c5_median": classified["c5"].median(),
        "ss_max_mean": classified["ss_max"].mean(),
        "ss_max_median": classified["ss_max"].median(),
        "controlled_pct": classified["ss_controlled"].mean(),
        "widely_held_block_pct": (classified["taxonomy"] == "widely_held_block").mean(),
        "widely_held_no_block_pct": (classified["taxonomy"] == "widely_held_no_block").mean(),
        "whale_control_pct": (classified["controller_type"] == "whale_control").mean(),
        "coalition_control_pct": (classified["controller_type"] == "coalition_control").mean(),
        "delegate_block_pct": (classified["controller_type"] == "delegate_block").mean(),
        "retail_pct": (classified["controller_type"] == "retail").mean(),
        "n_voters_per_proposal_mean": classified["n_voters"].mean(),
        "n_voters_per_proposal_median": classified["n_voters"].median(),
        "n_block_holders_mean": classified["n_block_holders"].mean(),
    }


def compute_gini_overall(votes: pd.DataFrame) -> float:
    """Compute Gini of total VP cast per voter across all proposals."""
    per_voter = votes.groupby("org:resource")["voting_power"].sum().values
    return gini(per_voter)


def check_outcome_flips(original_votes: pd.DataFrame, transformed_votes: pd.DataFrame) -> pd.DataFrame:
    """Check per-proposal whether the majority outcome flips after VP transformation.

    Assumes both DataFrames have the same rows; only voting_power differs.
    Outcome = which choice gets more total VP (approximated as: top voter's side wins
    in baseline — we check whether the FOR/AGAINST balance changes).

    Since we don't have explicit for/against labels in the event log, we use a proxy:
    for each proposal, compute the share of the top-1 voter. If top-1's share drops
    below 50% of total VP *and* the top-1 voter had >50% in baseline, that's a flip.

    More robust approach: compute the total VP of each "side" (we don't have sides),
    so instead we check if the *ranking* of voters by VP changes enough to flip
    the majority coalition. Simplified: majority = top-50% VP holders. Check if
    the set of voters constituting >50% VP changes.
    """
    results = []
    for case_id in original_votes["case:concept:name"].unique():
        orig = original_votes[original_votes["case:concept:name"] == case_id]
        trans = transformed_votes[transformed_votes["case:concept:name"] == case_id]

        orig_agg = orig.groupby("org:resource")["voting_power"].sum().sort_values(ascending=False)
        trans_agg = trans.groupby("org:resource")["voting_power"].sum().sort_values(ascending=False)

        orig_total = orig_agg.sum()
        trans_total = trans_agg.sum()

        if orig_total == 0 or trans_total == 0:
            continue

        orig_cumshare = (orig_agg.cumsum() / orig_total).values
        trans_cumshare = (trans_agg.cumsum() / trans_total).values

        orig_majority_idx = int(np.searchsorted(orig_cumshare, 0.5))
        trans_majority_idx = int(np.searchsorted(trans_cumshare, 0.5))

        orig_majority_set = set(orig_agg.index[:orig_majority_idx + 1])
        trans_majority_set = set(trans_agg.index[:trans_majority_idx + 1])

        if len(orig_majority_set) == 0 or len(trans_majority_set) == 0:
            overlap = 0.0
        else:
            overlap = len(orig_majority_set & trans_majority_set) / len(orig_majority_set | trans_majority_set)

        orig_c1 = orig_agg.iloc[0] / orig_total if len(orig_agg) > 0 else 0
        trans_c1 = trans_agg.iloc[0] / trans_total if len(trans_agg) > 0 else 0

        flipped = overlap < 0.5

        results.append({
            "case_id": case_id,
            "orig_c1": orig_c1,
            "trans_c1": trans_c1,
            "majority_coalition_overlap": overlap,
            "majority_size_orig": orig_majority_idx + 1,
            "majority_size_trans": trans_majority_idx + 1,
            "outcome_flipped": flipped,
        })

    return pd.DataFrame(results)
