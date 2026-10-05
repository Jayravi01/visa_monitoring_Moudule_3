import config
import sheets_sync


def test_tables_have_expected_shape():
    changes, by_cat = sheets_sync.build_tables(config.SAMPLE_DIR)
    assert len(changes) > 0 and len(by_cat) >= len(changes)
    assert "visa_category" in by_cat.columns and "visa_categories" in changes.columns
    assert "dt" not in changes.columns
    assert changes["published_date"].str.match(r"\d{4}-\d{2}-\d{2}$").all()  # ISO dates so Sheets reads them as dates
    assert (by_cat["visa_category"] != "").all()


def test_values_are_plain_cells():
    changes, _ = sheets_sync.build_tables(config.SAMPLE_DIR)
    rows = sheets_sync._values(changes)
    assert rows[0] == list(changes.columns)
    assert all(isinstance(c, (str, int, float, bool)) for r in rows[1:] for c in r)
