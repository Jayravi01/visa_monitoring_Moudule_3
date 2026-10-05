"""Publish the live records to a Google Sheet so Tableau (Cloud or Desktop) can read them with a Google sign-in.

Two tabs are rewritten on every run from the local live store (data/live):
    changes      one row per change
    by_category  one row per change x visa category (for the category chart)

Rewriting the tabs (instead of appending) means running twice never creates duplicates.
Setup is in README.md ("Google Sheets for Tableau"). Needs GOOGLE_SHEET_ID and a service-account key.
"""
import json
from pathlib import Path

import pandas as pd

import config
import storage

CHANGES_TAB = "changes"
CATEGORY_TAB = "by_category"
DROP = ["dt"]


def build_tables(root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(changes, by_category) as plain-text tables, same columns as the CSV exports."""
    df = storage.load_df(root)
    if df.empty:
        return df, df
    changes = df.copy()
    for col in storage.LIST_COLS:
        changes[col] = changes[col].apply("; ".join)
    long = df.explode("visa_categories").rename(columns={"visa_categories": "visa_category"})
    long["visa_category"] = long["visa_category"].fillna("Unclassified").replace("", "Unclassified")
    for col in ["change_types", "products_affected"]:
        long[col] = long[col].apply("; ".join)
    return _plain(changes), _plain(long)


def _plain(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["published_date", "effective_date"]:
        out[col] = out[col].dt.strftime("%Y-%m-%d").fillna("")
    out = out.drop(columns=[c for c in DROP if c in out.columns])
    return out.fillna("").astype(object).map(lambda v: v if isinstance(v, (int, float, bool)) else str(v))


def _values(df: pd.DataFrame) -> list[list]:
    return [list(df.columns)] + df.values.tolist()


def _client():
    import gspread

    if config.GOOGLE_SERVICE_ACCOUNT_JSON:
        return gspread.service_account_from_dict(json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON))
    if config.GOOGLE_SERVICE_ACCOUNT_FILE and Path(config.GOOGLE_SERVICE_ACCOUNT_FILE).exists():
        return gspread.service_account(filename=config.GOOGLE_SERVICE_ACCOUNT_FILE)
    raise SystemExit("Google key not found. Set GOOGLE_SERVICE_ACCOUNT_FILE (path to the JSON key) in .env.")


def _write_tab(book, title: str, df: pd.DataFrame) -> None:
    values = _values(df)
    try:
        ws = book.worksheet(title)
    except Exception:  # noqa: BLE001 - gspread raises WorksheetNotFound
        ws = book.add_worksheet(title=title, rows=len(values) + 20, cols=len(values[0]))
    ws.clear()
    ws.resize(rows=max(len(values) + 20, 100), cols=len(values[0]))
    ws.update(range_name="A1", values=values, value_input_option="USER_ENTERED")  # lets Sheets read dates as dates
    print(f"  {title}: {len(df)} rows")


def sync_to_sheets(root: Path = None) -> None:
    if not config.GOOGLE_SHEET_ID:
        raise SystemExit("GOOGLE_SHEET_ID is not set in .env (the long id in the sheet's web address).")
    root = root or config.LIVE_DIR
    changes, by_cat = build_tables(root)
    if changes.empty:
        raise SystemExit(f"No records in {root}; refusing to overwrite the sheet with an empty table.")
    book = _client().open_by_key(config.GOOGLE_SHEET_ID)
    _write_tab(book, CHANGES_TAB, changes)
    _write_tab(book, CATEGORY_TAB, by_cat)


if __name__ == "__main__":
    sync_to_sheets()
