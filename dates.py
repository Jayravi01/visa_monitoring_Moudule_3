"""Small date-parsing helpers shared by the collectors and the classifier."""
import re
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from typing import Optional

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
MONTH_ALT = "|".join(sorted(MONTHS, key=len, reverse=True))

# e.g. "14 November 2026", "1st Jul 2026"
DMY_RE = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTH_ALT})\.?,?\s+(\d{{4}})\b", re.I)


def to_iso(day: int, month_name: str, year: int) -> Optional[str]:
    try:
        return date(year, MONTHS[month_name.lower()], day).isoformat()
    except (ValueError, KeyError):
        return None


def find_date(text: str) -> Optional[str]:
    """First 'D Month YYYY' date in the text, as YYYY-MM-DD."""
    m = DMY_RE.search(text or "")
    return to_iso(int(m.group(1)), m.group(2), int(m.group(3))) if m else None


def parse_any(value: Optional[str]) -> Optional[str]:
    """Parse ISO, RFC 822 (RSS) or 'D Month YYYY' strings into YYYY-MM-DD."""
    if not value:
        return None
    value = value.strip()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError):
        pass
    return find_date(value)
