"""Source inventory (Phase 1 deliverable).

Run `python sources.py` to export it as source_inventory.csv.

`status` tells you how much to trust the entry:
  verified_listing - the listing page was opened and showed dated items (checked 3 Oct 2026)
  to_verify        - plausible URL, not confirmed; run `python diagnose_source.py <id>` before relying on it
  manual           - not collected automatically

None of the sites below advertises an RSS feed, so listings are scraped from HTML. The collector also looks
for a feed link on each page (`try_feed`) and uses it when one exists. Page layouts change: re-run
diagnose_source.py if a source suddenly returns nothing.

Removed after checking (do not re-add without re-checking):
  - Google News RSS: its robots.txt disallows fetching it.
  - minister.homeaffairs.gov.au landing page: not a listing, and last updated in 2022.
  - VisaConnect: promotional commentary, and every item links to an anchor on one page.
  - Study Australia /en/news and the Home Affairs /news-media/latest-news URLs: 404.
"""
import csv
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Source:
    id: str
    name: str
    org_type: str            # government | industry_body | news | social
    url: str
    method: str              # html_list | rss | page_snapshot | manual
    link_pattern: str = ""   # regex an article URL must match (html_list); use (?i) for case-insensitive
    fetch_detail: bool = True  # open each article to read the body text (skipped automatically for PDFs)
    try_feed: bool = True      # use an RSS/Atom feed advertised by the page, if there is one
    status: str = "to_verify"
    notes: str = ""


SOURCES = [
    Source(
        "study_australia", "Study Australia (Austrade) - news", "government",
        "https://www.studyaustralia.gov.au/en/tools-and-resources/news", "html_list",
        link_pattern=r"/en/tools-and-resources/news/[^/?#]+", status="verified_listing",
        notes="Dated items such as the student visa application charge, the CRICOS provider pause and "
              "international education settings. Article URLs look like .../news/<slug>.",
    ),
    Source(
        "mia", "Migration Institute of Australia - media releases", "industry_body",
        "https://mia.org.au/Web/Web/Public-Resources/Media-Releases-Index.aspx", "html_list",
        link_pattern=r"(?i)media(?:%20| )releases/.*\.pdf$", fetch_detail=False, status="verified_listing",
        notes="Releases are PDFs, so only the title and the listing date are used (no article text).",
    ),
    Source(
        "fwo_media", "Fair Work Ombudsman - media releases", "government",
        "https://www.fairwork.gov.au/newsroom/media-releases", "html_list",
        link_pattern=r"/newsroom/media-releases/", status="verified_listing",
        notes="Listing shows titles and dates. The link pattern is assumed: confirm it with diagnose_source.py. "
              "Most releases are unrelated and are dropped by the relevance filter.",
    ),
    Source(
        "education_dept", "Department of Education - ministers' media releases", "government",
        "https://ministers.education.gov.au/", "html_list",
        link_pattern=r"ministers\.education\.gov\.au/[a-z-]+/[a-z0-9-]+/?$", status="to_verify",
        notes="Real releases live at ministers.education.gov.au/<minister>/<slug> (for example the student visa "
              "integrity reforms). Find the best listing page with diagnose_source.py. The robots.txt check "
              "timed out when tested.",
    ),
    Source(
        "ha_immi_news", "Home Affairs (Immigration and citizenship) - news archive", "government",
        "https://immi.homeaffairs.gov.au/news-media/archive", "html_list",
        link_pattern=r"/news-media/", status="to_verify",
        notes="The page exists but came back as an empty template when fetched, so its list may be loaded by "
              "JavaScript. If diagnose_source.py finds no links, rely on the page-change sources below.",
    ),
    Source(
        "ha_student_changes", "Home Affairs - Changes to Student visa application rules (500 & 590)", "government",
        "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/changes-to-student-visa-application-rules-500-590",
        "page_snapshot", status="to_verify",
        notes="URL found in search results. Change detection by page hash; a change creates a record. "
              "The first run only records a baseline.",
    ),
    Source(
        "ha_processing", "Home Affairs - global visa processing times", "government",
        "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-processing-times/global-visa-processing-times",
        "page_snapshot", status="to_verify",
        notes="Change detection by page hash; a change creates a 'processing times updated' record.",
    ),
    Source(
        "ha_newsroom", "Home Affairs - news and media landing page", "government",
        "https://www.homeaffairs.gov.au/news-media", "manual", status="verified_listing",
        notes="Landing page only links to the ABF newsroom and speeches; no news listing or RSS.",
    ),
    Source(
        "linkedin", "LinkedIn company announcements", "social",
        "https://www.linkedin.com/", "manual", status="manual",
        notes="Scraping LinkedIn breaks its terms. Add items by hand in data/manual_items.json (see README).",
    ),
]

BY_ID = {s.id: s for s in SOURCES}


def write_inventory(path: Path = Path("source_inventory.csv")) -> Path:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(SOURCES[0])))
        w.writeheader()
        for s in SOURCES:
            w.writerow(asdict(s))
    return path


if __name__ == "__main__":
    print(f"Wrote {write_inventory()} ({len(SOURCES)} sources)")
