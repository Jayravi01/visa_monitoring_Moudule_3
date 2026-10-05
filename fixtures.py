"""Synthetic demo items so the pipeline and dashboard run without network access.

Every title starts with [SAMPLE] and every URL points at example.org, so none of this
can be mistaken for a real announcement. Dates are relative to today.
"""
from datetime import date, timedelta
from typing import Optional

from dates import MONTHS  # noqa: F401  (kept for parity with classify)


def _fmt(d: date) -> str:
    return f"{d.day} {d.strftime('%B %Y')}"


def sample_items(today: Optional[date] = None) -> list[dict]:
    today = today or date.today()
    ago = lambda n: today - timedelta(days=n)       # noqa: E731
    ahead = lambda n: today + timedelta(days=n)     # noqa: E731

    rows = [
        (2, "education_dept", "[SAMPLE] Student visa integrity reforms take effect today",
         "The student visa integrity reforms take effect today. The genuine student requirement is strengthened "
         "and the student visa application charge will increase for new applications. Providers must meet new "
         "compliance obligations."),
        (6, "study_australia", "[SAMPLE] Planning level for new international student commencements lowered",
         f"The national planning level for international student commencements will be lowered from {_fmt(ahead(120))}. "
         "Universities and colleges will receive revised allocations."),
        (12, "mia", "[SAMPLE] Briefing: Temporary Graduate visa English requirements change",
         f"From {_fmt(ahead(45))} the Temporary Graduate (subclass 485) visa will require a higher English language "
         "score. Graduates should check eligibility before applying."),
        (20, "ha_immi_news", "[SAMPLE] Skills in Demand (subclass 482) visa income threshold update",
         f"The income threshold for the Skills in Demand visa will increase from {_fmt(ahead(60))}. "
         "Employers should review sponsored workers' salaries."),
        (33, "ha_processing", "[SAMPLE] Global visa processing times: page content changed",
         "Processing times for student visa applications have been updated. Visitor visa processing times are unchanged."),
        (40, "fwo_media", "[SAMPLE] Fair Work Ombudsman commences legal action against a plumbing company",
         "The regulator alleges underpayment of apprentices at a small business."),
        (47, "fwo_media", "[SAMPLE] Wages recovered for international students at hospitality businesses",
         "The regulator recovered wages after finding international students on student visas were underpaid."),
        (61, "mia", "[SAMPLE] New working holiday program announced for an additional country",
         "A new working holiday program under subclass 417 will open to applicants from an additional country."),
        (78, "mia", "[SAMPLE] Universities warn international student cap could cut enrolments", ""),
        (95, "education_dept", "[SAMPLE] Visitor visa (subclass 600) application charge to rise",
         f"The visitor visa application charge will increase from {_fmt(ahead(30))}."),
        (120, "education_dept", "[SAMPLE] ESOS Act amendments introduce stricter provider rules",
         f"New compliance obligations apply to education providers enrolling international students from {_fmt(ahead(10))}."),
        (150, "mia", "[SAMPLE] Bridging visa conditions updated for temporary visa holders",
         "Visa conditions for some bridging visa holders have been updated."),
        (180, "education_dept", "[SAMPLE] Student visa processing priority direction replaced",
         "A new ministerial direction sets processing priorities for student visa applications."),
        (210, "study_australia", "[SAMPLE] Student visa financial capacity requirement increased",
         f"The financial capacity requirement for student visa applicants will increase from {_fmt(ago(180))}."),
        (250, "mia", "[SAMPLE] Migration strategy: temporary migrants to be reduced",
         "The migration program planning level for temporary migrants will be reduced."),
    ]
    items = []
    for i, (days_ago, source_id, title, body) in enumerate(rows, start=1):
        items.append(
            {
                "source_id": source_id,
                "url": f"https://example.org/sample/{i}",
                "title": title,
                "published": ago(days_ago).isoformat(),
                "body": body,
                "fetched_at": today.isoformat(),
            }
        )
    return items
