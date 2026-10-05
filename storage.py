"""Data storage structure (Phase 1 deliverable).

Layout (JSON Lines, one record per line, partitioned by the day a record was first seen):

    data/live/dt=2026-10-03/changes_101530.jsonl
    data/sample/dt=.../...        (synthetic demo data; never uploaded)

JSON Lines in date partitions maps straight onto an S3 prefix and an Athena table with
partition projection (see athena_setup.py).
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import config

LIST_COLS = ["change_types", "visa_categories", "products_affected"]


def store_root(sample: bool) -> Path:
    return config.SAMPLE_DIR if sample else config.LIVE_DIR


def _files(root: Path) -> list[Path]:
    return sorted(root.glob("dt=*/*.jsonl")) if root.exists() else []


def existing_ids(root: Path) -> set[str]:
    ids = set()
    for f in _files(root):
        with open(f, encoding="utf-8") as fh:
            ids.update(json.loads(line)["id"] for line in fh if line.strip())
    return ids


def save_records(records: list[dict], root: Path) -> list[dict]:
    """Append records that are not already stored. Returns the new ones."""
    seen = existing_ids(root)
    new = []
    for r in records:
        if r["id"] not in seen:
            seen.add(r["id"])
            new.append(r)
    if new:
        now = datetime.now(timezone.utc)
        folder = root / f"dt={now:%Y-%m-%d}"
        folder.mkdir(parents=True, exist_ok=True)
        with open(folder / f"changes_{now:%H%M%S}.jsonl", "w", encoding="utf-8") as fh:
            for r in new:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return new


def load_df(root: Path) -> pd.DataFrame:
    frames = [pd.read_json(f, lines=True, dtype=False) for f in _files(root)]
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True).drop_duplicates("id", keep="first")
    for col in LIST_COLS:
        df[col] = df[col].apply(lambda v: v if isinstance(v, list) else [])
    for col in ["published_date", "effective_date"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df.sort_values("published_date", ascending=False).reset_index(drop=True)


def export_flat(root: Path) -> list[Path]:
    """Flat CSVs for Tableau or Power BI: one row per change, and one row per change x visa category."""
    df = load_df(root)
    if df.empty:
        return []
    out_dir = root / "export"
    out_dir.mkdir(parents=True, exist_ok=True)

    flat = df.copy()
    for col in LIST_COLS:
        flat[col] = flat[col].apply("; ".join)
    p1 = out_dir / "changes_flat.csv"
    flat.to_csv(p1, index=False)

    long = df.explode("visa_categories").rename(columns={"visa_categories": "visa_category"})
    long["visa_category"] = long["visa_category"].fillna("Unclassified")
    for col in ["change_types", "products_affected"]:
        long[col] = long[col].apply("; ".join)
    p2 = out_dir / "changes_by_visa_category.csv"
    long.to_csv(p2, index=False)
    return [p1, p2]
