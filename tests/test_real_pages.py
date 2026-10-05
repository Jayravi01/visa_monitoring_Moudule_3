"""Tests modelled on what the real listing pages looked like when checked (3 Oct 2026)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import classify  # noqa: E402
import collectors  # noqa: E402
from sources import BY_ID  # noqa: E402

MIA_HTML = """
<html><body><nav><a href="/about-us/our-organisation-and-people">About the organisation and people</a></nav>
<ul>
 <li><a href="/common/Uploaded files/Web/Public Resources/Media Releases/MIA-media-release-17Sept26-web.pdf">MIA broadly supportive of Government Migration Changes</a>
     <span>17 September 2026</span></li>
 <li><a href="/common/Uploaded files/Web/Public Resources/Media Releases/MIA-media-release-19-March-26.pdf">MIA Calls Out Migration Agent Attacks and Calls for Fee Freeze</a>
     <span>19 March 2026</span></li>
</ul></body></html>"""

STUDY_HTML = """
<html><body>
<a href="/en/study-in-australia/visas-and-costs-of-living">Visas and the cost of living in Australia</a>
<div class="card"><a href="/en/tools-and-resources/news/student-visa-application-charge-increase">Student Visa Application Charge increase</a><p>3 July 2026</p></div>
<div class="card"><a href="/en/tools-and-resources/news/pause-on-new-private-vet-and-elicos-providers-and-courses">Pause on new CRICOS registered private VET and ELICOS providers and courses</a><p>22 May 2026</p></div>
<a href="/en/tools-and-resources/news">All of the latest news and updates for students</a>
</body></html>"""


def test_mia_pdf_links_are_encoded_and_dated():
    items = collectors.parse_listing(MIA_HTML, "https://mia.org.au/Web/Web/Public-Resources/Media-Releases-Index.aspx",
                                     BY_ID["mia"].link_pattern)
    assert len(items) == 2
    assert items[0]["url"].startswith("https://mia.org.au/common/Uploaded%20files/")
    assert " " not in items[0]["url"]
    assert items[0]["published"] == "2026-09-17"
    assert collectors.is_pdf(items[0]["url"])


def test_study_australia_keeps_articles_only():
    items = collectors.parse_listing(STUDY_HTML, "https://www.studyaustralia.gov.au/en/tools-and-resources/news",
                                     BY_ID["study_australia"].link_pattern)
    assert [i["published"] for i in items] == ["2026-07-03", "2026-05-22"]
    assert all("/news/" in i["url"] for i in items)


def test_feed_autodiscovery():
    html = '<html><head><link rel="alternate" type="application/rss+xml" href="/rss.xml"></head></html>'
    assert collectors.discover_feeds(html, "https://example.org/news") == ["https://example.org/rss.xml"]


def test_analyse_listing_suggests_folder_and_flags_js_pages():
    info = collectors.analyse_listing(STUDY_HTML, "https://www.studyaustralia.gov.au/en/tools-and-resources/news")
    assert info["prefixes"][0][0] == "/en/tools-and-resources/news/"
    js_page = "<html><body>" + "<script>1</script>" * 6 + '<div id="app"></div></body></html>'
    assert collectors.analyse_listing(js_page, "https://example.org/")["looks_js_rendered"] is True


def _raw(title, body="", published=None):
    return {"source_id": "study_australia", "url": "https://example.org/x/" + title[:10], "title": title, "body": body,
            "published": published, "fetched_at": "2026-10-03T00:00:00+00:00"}


def test_real_titles_are_classified():
    pause = classify.classify(_raw("Pause on new CRICOS registered private VET and ELICOS providers and courses"),
                              BY_ID["study_australia"])
    assert "Closure / pause" in pause["change_types"]
    assert "Student (500)" in pause["visa_categories"]
    assert pause["impact"] == "High"

    charge = classify.classify(_raw("Student Visa Application Charge increase"), BY_ID["study_australia"])
    assert "Fee / charge" in charge["change_types"] and charge["impact"] == "Medium"

    grad = classify.classify(_raw("Massive temporary graduate visa fee increase hard to justify"), BY_ID["mia"])
    assert "Temporary Graduate (485)" in grad["visa_categories"]
    assert "Fee / charge" in grad["change_types"]


def test_missing_publication_date_falls_back_to_first_seen():
    rec = classify.classify(_raw("Student Visa Application Charge increase"), BY_ID["study_australia"])
    assert rec["published_date"] == "2026-10-03"
    assert "date first seen" in rec["impact_rationale"]
