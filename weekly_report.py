"""Weekly market intelligence report (Phase 4 deliverable).

    python weekly_report.py              # last 7 days of live data
    python weekly_report.py --sample     # demo data
    python weekly_report.py --days 14

The facts (counts, High-impact changes, upcoming effective dates) are generated.
The "emerging opportunities" section is left as prompts for the analyst: whether a
rule change helps or hurts demand is a judgement call, not something to automate.
"""
import argparse
from datetime import date, timedelta

import pandas as pd

import config
import storage


def _md_table(df: pd.DataFrame, cols: dict[str, str]) -> str:
    if df.empty:
        return "_None this period._\n"
    lines = ["| " + " | ".join(cols.values()) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if isinstance(v, list):
                v = ", ".join(v)
            elif isinstance(v, pd.Timestamp):
                v = v.date().isoformat()
            elif pd.isna(v):
                v = "not stated"
            cells.append(str(v).replace("|", "/"))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def build(df: pd.DataFrame, days: int, today: date, sample: bool) -> str:
    since = pd.Timestamp(today - timedelta(days=days))
    week = df[df["published_date"] >= since]
    upcoming = df[(df["effective_date"] >= pd.Timestamp(today)) &
                  (df["effective_date"] <= pd.Timestamp(today + timedelta(days=90)))].sort_values("effective_date")

    counts = week["impact"].value_counts()
    cats = week.explode("visa_categories")["visa_categories"].value_counts()
    prods = week.explode("products_affected")["products_affected"].value_counts()

    out = [f"# Visa & Regulatory Change Monitor: week to {today.isoformat()}\n"]
    if sample:
        out.append("> **Demo data.** Every item below is synthetic and is not a real announcement.\n")
    out.append(
        f"**{len(week)} changes** in the last {days} days: "
        f"{counts.get('High', 0)} High, {counts.get('Medium', 0)} Medium, {counts.get('Low', 0)} Low.\n"
    )

    out.append("## High-impact changes\n")
    out.append(_md_table(
        week[week["impact"] == "High"],
        {"published_date": "Published", "title": "Change", "effective_date": "Effective",
         "visa_categories": "Visa categories", "products_affected": "Products", "url": "Source"},
    ))

    out.append("## Coming into effect in the next 90 days\n")
    out.append(_md_table(
        upcoming,
        {"effective_date": "Effective", "title": "Change", "impact": "Impact",
         "visa_categories": "Visa categories", "url": "Source"},
    ))

    out.append("## Visa categories most affected this period\n")
    out.append("\n".join(f"- {k}: {v}" for k, v in cats.items()) + "\n" if len(cats) else "_None._\n")

    out.append("## Products to watch\n")
    out.append("\n".join(f"- {k}: {v} change(s)" for k, v in prods.items()) + "\n" if len(prods) else "_None._\n")

    out.append("## Emerging opportunities (analyst to complete)\n")
    out.append(
        "- Which changes are likely to raise demand for OSHC, OVHC or OWHC, and which to reduce it?\n"
        "- Which visa pathways are new or expanding, and who are the education or employer partners around them?\n"
        "- Which effective dates above create a window for pricing, promotion or partnership action?\n"
    )
    out.append("\n_Impact levels come from rule-based scoring (see `impact_rationale` in the data); "
               "review before circulating._\n")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()

    df = storage.load_df(storage.store_root(args.sample))
    if df.empty:
        raise SystemExit("No data yet. Run run_pipeline.py first (add --offline for demo data).")

    today = date.today()
    text = build(df, args.days, today, args.sample)
    config.REPORT_DIR.mkdir(exist_ok=True)
    path = config.REPORT_DIR / f"weekly_{today.isoformat()}{'_sample' if args.sample else ''}.md"
    path.write_text(text, encoding="utf-8")
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
