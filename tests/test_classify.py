import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import classify  # noqa: E402
import fixtures  # noqa: E402
from sources import BY_ID  # noqa: E402


def test_effective_date_explicit_year():
    assert classify.extract_effective_date("applies from 1 July 2026", "2026-05-01") == "2026-07-01"


def test_effective_date_today_uses_published():
    assert classify.extract_effective_date("The changes take effect today.", "2026-10-02") == "2026-10-02"


def test_effective_date_rolls_into_next_year():
    assert classify.extract_effective_date("from 1 January the fee rises", "2026-11-10") == "2027-01-01"


def test_effective_date_absent():
    assert classify.extract_effective_date("Nothing dated here.", "2026-11-10") is None


def test_sample_items_expected_impact():
    today = date.today()
    recs = {}
    for item in fixtures.sample_items(today):
        rec = classify.classify(item, BY_ID[item["source_id"]], today=today, is_sample=True)
        if rec:
            recs[item["title"]] = rec

    by_part = lambda part: next(r for t, r in recs.items() if part in t)  # noqa: E731

    assert by_part("integrity reforms")["impact"] == "High"
    assert by_part("Planning level")["impact"] == "High"
    assert by_part("English requirements")["impact"] == "Medium"
    assert by_part("Wages recovered")["impact"] == "Low"
    assert "Student (500)" in by_part("integrity reforms")["visa_categories"]
    assert by_part("integrity reforms")["products_affected"] == ["OSHC"]
    # "take effect today" in an item published 2 days ago
    assert by_part("integrity reforms")["effective_date"] == (today - timedelta(days=2)).isoformat()


def test_irrelevant_items_are_dropped():
    today = date.today()
    item = next(i for i in fixtures.sample_items(today) if "plumbing" in i["title"])
    assert classify.classify(item, BY_ID[item["source_id"]], today=today) is None


def test_ids_are_stable():
    today = date.today()
    item = fixtures.sample_items(today)[0]
    a = classify.classify(item, BY_ID[item["source_id"]], today=today)
    b = classify.classify(item, BY_ID[item["source_id"]], today=today)
    assert a["id"] == b["id"]
