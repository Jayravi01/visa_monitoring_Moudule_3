"""Run the monitor end to end.

    python run_pipeline.py --offline           # synthetic demo data, no network, no AWS
    python run_pipeline.py                     # collect live sources, classify, store, alert
    python run_pipeline.py --aws               # ...then sync to S3 and refresh the Athena table
    python run_pipeline.py --sheets            # ...then rewrite the Google Sheet that Tableau reads
    python run_pipeline.py --only ha_minister fwo_media --no-detail

Schedule `python run_pipeline.py --aws` (daily is plenty) for the automated refresh.
"""
import argparse
import json

import alerts
import classify
import config
import fixtures
import storage
from sources import BY_ID, write_inventory


def load_manual() -> list[dict]:
    """Hand-entered items from data/manual_items.json (for sources that cannot be scraped, e.g. LinkedIn).

    A JSON list of objects: {"title": ..., "url": ..., "published": "YYYY-MM-DD", "body": "...", "source_id": "linkedin"}.
    `title` and `url` are required; `source_id` defaults to "linkedin" and must exist in sources.py.
    """
    f = config.DATA_DIR / "manual_items.json"
    if not f.exists():
        return []
    items = []
    for it in json.loads(f.read_text(encoding="utf-8")):
        it.setdefault("source_id", "linkedin")
        it.setdefault("body", "")
        it.setdefault("published", None)
        if not it.get("title") or not it.get("url") or it["source_id"] not in BY_ID:
            print(f"  skipped manual item (needs title, url and a known source_id): {it}")
            continue
        items.append(it)
    print(f"  manual items: {len(items)}")
    return items


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use synthetic sample items (stored separately)")
    ap.add_argument("--aws", action="store_true", help="sync live data to S3 and refresh Athena")
    ap.add_argument("--sheets", action="store_true", help="rewrite the Google Sheet (changes + by_category tabs)")
    ap.add_argument("--no-detail", action="store_true", help="skip opening each article (faster, less text)")
    ap.add_argument("--only", nargs="*", help="limit to these source ids")
    ap.add_argument("--no-notify", action="store_true", help="write alerts to file only")
    args = ap.parse_args()

    write_inventory()
    root = storage.store_root(sample=args.offline)

    if args.offline:
        print("== Offline: using synthetic sample items ==")
        raw, errors = fixtures.sample_items(), []
    else:
        print("== Collecting ==")
        from collectors import collect_all

        raw, errors = collect_all(fetch_details=not args.no_detail, only=args.only)
        raw += load_manual()

    records = []
    for item in raw:
        rec = classify.classify(item, BY_ID[item["source_id"]], is_sample=args.offline)
        if rec:
            records.append(rec)
    print(f"== Classified: {len(records)} relevant of {len(raw)} collected ==")

    new = storage.save_records(records, root)
    print(f"== Stored {len(new)} new records in {root} ==")

    raised = alerts.process(new, root, notify=not args.no_notify and not args.offline)
    high = sum(a["severity"] == "High" for a in raised)
    print(f"== Alerts: {high} High, {len(raised) - high} Medium ==")

    for p in storage.export_flat(root):
        print(f"   exported {p}")

    if args.aws:
        if args.offline:
            raise SystemExit("Refusing to upload sample data to AWS. Run without --offline.")
        import athena_setup
        import aws_s3

        print("== Syncing to S3 ==")
        aws_s3.sync_to_s3()
        print("== Refreshing Athena ==")
        athena_setup.setup()

    if args.sheets:
        if args.offline:
            raise SystemExit("Refusing to publish sample data to the Google Sheet. Run without --offline.")
        import sheets_sync

        print("== Updating Google Sheet ==")
        sheets_sync.sync_to_sheets()

    if errors:
        print("\nSources that failed (check URL, robots.txt, or layout):")
        for e in errors:
            print("  -", e)


if __name__ == "__main__":
    main()
