"""Canonical filesystem locations for the dao-governance-pm repo.

Every script imports from here instead of assuming the current working
directory. The repo root is resolved from this file's own location, so
scripts behave identically no matter where they are invoked from.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = REPO_ROOT / "data"
DB_DIR = DATA_DIR / "db"
PROCESSED_DIR = DATA_DIR / "processed"
MAPPINGS_DIR = DATA_DIR / "mappings"
FIGURES_DIR = REPO_ROOT / "figures"
RESULTS_DIR = REPO_ROOT / "results"
DIAGRAMS_DIR = REPO_ROOT / "diagrams"
THESIS_DIR = REPO_ROOT / "thesis"
CHAPTERS_DIR = THESIS_DIR / "chapters"

EVENTS_DB = DB_DIR / "dao_events.duckdb"


def linked_db(dao_slug: str) -> Path:
    """Per-DAO linked database: 'ens' -> data/db/ens_linked.duckdb"""
    return DB_DIR / f"{dao_slug}_linked.duckdb"


def shard_db(dao_slug: str, start_block: int, end_block: int) -> Path:
    """Per-worker shard database. Must stay in sync with shard_glob()."""
    return DB_DIR / f"{dao_slug}_shard_{start_block}_{end_block}.duckdb"


def shard_glob(dao_slug: str) -> str:
    """Glob matching shard_db() output. Must stay in sync with shard_db()."""
    return str(DB_DIR / f"{dao_slug}_shard_*.duckdb")


def event_log(name: str) -> Path:
    """pm4py event log: event_log('ens_linked') -> data/processed/ens_linked_pm4py.csv"""
    return PROCESSED_DIR / f"{name}_pm4py.csv"


def mapping(dao_slug: str, kind: str = "tally") -> Path:
    """Proposal ID mapping: mapping('ens') -> data/mappings/ens_tally_mapping.csv"""
    return MAPPINGS_DIR / f"{dao_slug}_{kind}_mapping.csv"


def figure(name: str) -> Path:
    return FIGURES_DIR / name


def result(name: str) -> Path:
    return RESULTS_DIR / name


# Output directories are created on import: pm4py's save_vis_* and DuckDB both
# fail with opaque errors when the parent directory is missing. Input directories
# (mappings, thesis) are deliberately NOT created — a missing one is a real error.
for _d in (DB_DIR, PROCESSED_DIR, FIGURES_DIR, RESULTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
