"""Categorisation logic (Phase 2): visa tagging, change type, effective date, impact.

Everything here is rule-based and transparent, so each score can be explained and
the rules tuned. The product mapping (which visa feeds which Medibank product) and
the impact weights are ASSUMPTIONS: confirm them with the Medibank product team.
"""
import hashlib
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from dates import MONTH_ALT, to_iso

# name, regex, products affected (OSHC / OVHC / OWHC)
VISA_CATEGORIES = [
    ("Student (500)", r"student visas?|subclass\s*500|international students?|overseas students?|genuine student|"
     r"confirmation of enrolment|\bCoE\b|national planning level|enrolment cap|\bESOS\b|\bCRICOS\b|\bELICOS\b|"
     r"international education settings", ["OSHC"]),
    ("Student Guardian (590)", r"student guardian|subclass\s*590", ["OSHC"]),
    ("Temporary Graduate (485)", r"temporary graduate|subclass\s*485|post-?study work|graduate visa", ["OVHC", "OWHC"]),
    ("Skills in Demand (482)", r"skills in demand|subclass\s*482|temporary skill shortage|\bTSS\b|specialist skills|"
     r"core skills|employer[- ]sponsor|sponsored workers?", ["OWHC"]),
    ("Training (407)", r"subclass\s*407|training visa", ["OWHC"]),
    ("Temporary Activity (408)", r"subclass\s*408|temporary activity visa", ["OVHC", "OWHC"]),
    ("Working Holiday (417/462)", r"working holiday|subclass\s*(?:417|462)|work and holiday", ["OVHC", "OWHC"]),
    ("Visitor (600)", r"visitor visas?|subclass\s*600|tourist visa|\bETA\b|subclass\s*(?:601|651)", ["OVHC"]),
    ("Skilled Migration (189/190/491)", r"subclass\s*(?:189|190|491)|skilled independent|skilled nominated|points test|"
     r"skilled migration", []),
    ("Employer Sponsored PR (186/494)", r"subclass\s*(?:186|494)|employer nomination", []),
    ("Partner & Family", r"partner visas?|subclass\s*(?:820|801|309|100)|family visas?|parent visas?", []),
    ("All temporary visas", r"temporary visas?|temporary migrants?|visa holders|migration program|migration strategy|"
     r"net overseas migration|temporary entrants?", ["OSHC", "OVHC", "OWHC"]),
]

# name, regex, weight
CHANGE_TYPES = [
    ("Cap / quota", r"\bcaps?\b|planning level|quota|ceiling|halve|reduc\w+ (?:the )?intake|limit(?:s|ed)? (?:on )?the number", 4),
    ("Closure / pause", r"\bclos(?:e|ed|es|ing|ure)\b|\bpaus(?:e|ed|es)\b|suspend|abolish|\bfreeze\b|stop accepting", 4),
    ("Eligibility", r"eligib|new requirements?|no longer (?:be )?(?:able|eligible)|age limit|points test|"
     r"english (?:language )?(?:requirement|test|score)|financial capacity|genuine student|genuine temporary|"
     r"salary threshold|income threshold|occupation list|skills list|\bCSOL\b|\bMLTSSL\b", 3),
    ("Fee / charge", r"application charge|\bVAC\b|fee increase|fees? (?:will )?(?:rise|increase|double)|"
     r"increase(?:s|d)? (?:in |to )?(?:the )?(?:visa )?(?:fee|charge)", 2),
    ("Compliance", r"complian|integrity|visa conditions?|work (?:hours|limits?)|sponsor obligations?|cancel|"
     r"crackdown|enforce|audit|fraud|migration agents?", 2),
    ("New pathway / program", r"new visa|new pathway|introduc\w+ (?:a )?(?:new )?visa|will replace|new program", 3),
    ("Processing", r"processing times?|ministerial direction|priority processing|backlog|service standards?", 1),
    ("Workplace compliance", r"underpa\w*|exploit\w*|wage theft|legal action|sham contracting|penalt\w+", 1),
]

# Used only to decide whether an item is relevant at all
RELEVANCE = re.compile(
    r"\bvisas?\b|migrat|immigra|international student|overseas student|student visa|sponsor|work rights|"
    r"skills assessment|temporary entrants?|health insurance|\bOSHC\b|\bOVHC\b|\bOWHC\b|"
    r"overseas student health cover|migrant workers?|visa holders?|international education|\bESOS\b|"
    r"\bCRICOS\b|\bELICOS\b|planning level",
    re.I,
)

EFFECTIVE_RE = re.compile(
    rf"(?:from|effective(?:\s+from|\s+on)?|commenc\w+\s+(?:on|from)|takes?\s+effect(?:\s+on|\s+from)?|"
    rf"start(?:s|ing)?(?:\s+on|\s+from)?|begin(?:s|ning)?(?:\s+on|\s+from)?|as of|applies?\s+from|in force from)"
    rf"\s+(?:the\s+)?(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTH_ALT})(?:\s+(\d{{4}}))?",
    re.I,
)
IMMEDIATE_RE = re.compile(r"take[s]? effect today|effective immediately|\bfrom today\b|in effect today|now in effect", re.I)


def _flags(pattern_text: str, text: str) -> bool:
    return re.search(pattern_text, text, re.I) is not None


def extract_effective_date(text: str, published: Optional[str]) -> Optional[str]:
    """Effective date from phrases like 'from 1 July 2026' or 'takes effect today'."""
    pub = date.fromisoformat(published) if published else None
    if IMMEDIATE_RE.search(text) and pub:
        return pub.isoformat()
    m = EFFECTIVE_RE.search(text)
    if not m:
        return None
    day, month, year = int(m.group(1)), m.group(2), m.group(3)
    if year:
        return to_iso(day, month, int(year))
    if not pub:
        return None
    iso = to_iso(day, month, pub.year)
    if iso and date.fromisoformat(iso) < pub - timedelta(days=180):
        iso = to_iso(day, month, pub.year + 1)  # "from 1 January" announced in November
    return iso


def make_summary(title: str, body: str, max_len: int = 300) -> str:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", body or "") if len(s.strip()) > 30]
    sentences = [s for s in sentences if s.lower() != title.lower()]
    summary = " ".join(sentences[:2]) if sentences else title
    return summary if len(summary) <= max_len else summary[: max_len - 1].rstrip() + "…"


def impact_level(score: int) -> str:
    return "High" if score >= 6 else "Medium" if score >= 4 else "Low"


def classify(raw: dict, source, today: Optional[date] = None, is_sample: bool = False) -> Optional[dict]:
    """Turn a raw item into a dashboard record, or None if it is not relevant."""
    today = today or datetime.now(timezone.utc).date()
    title, body = raw.get("title", ""), raw.get("body", "")
    text = f"{title}. {body}"

    if not RELEVANCE.search(text):
        return None

    categories, products = [], []
    for name, pattern, prods in VISA_CATEGORIES:
        if _flags(pattern, text):
            categories.append(name)
            products += [p for p in prods if p not in products]

    change_types, weights = [], []
    for name, pattern, weight in CHANGE_TYPES:
        if _flags(pattern, text):
            change_types.append(name)
            weights.append(weight)

    # Workplace-compliance items only matter when they involve visa holders or students
    if change_types == ["Workplace compliance"] and not categories:
        return None
    if not categories and not change_types:
        return None

    published = raw.get("published")
    undated = not published
    if undated:  # keep the item visible in date filters and trends rather than losing it
        published = (raw.get("fetched_at") or datetime.now(timezone.utc).isoformat())[:10]
    effective = extract_effective_date(text, published)

    # ---- impact score (every contribution is recorded so it can be explained)
    score, why = 0, []
    if weights:
        base = min(sum(weights), 6)
        score += base
        why.append(f"{', '.join(change_types)} (+{base})")
    if "Student (500)" in categories or "Student Guardian (590)" in categories:
        score += 2
        why.append("student visa: core OSHC market (+2)")
    elif products:
        score += 1
        why.append(f"affects {'/'.join(products)} visa holders (+1)")
    if len(categories) >= 3:
        score += 1
        why.append("three or more visa categories (+1)")
    if effective:
        days = (date.fromisoformat(effective) - today).days
        if -30 <= days <= 90:
            score += 1
            why.append("effective within 90 days or just started (+1)")

    if undated:
        why.append("publication date not found, date first seen used")

    return {
        "id": hashlib.sha1(raw["url"].encode()).hexdigest()[:16],
        "source_id": raw["source_id"],
        "source_name": source.name,
        "org_type": source.org_type,
        "title": title,
        "summary": make_summary(title, body),
        "url": raw["url"],
        "published_date": published,
        "effective_date": effective,
        "change_types": change_types,
        "visa_categories": categories,
        "products_affected": products,
        "impact": impact_level(score),
        "impact_score": score,
        "impact_rationale": "; ".join(why) if why else "no scoring signals",
        "is_sample": is_sample,
        "first_seen": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
