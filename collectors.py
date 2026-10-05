"""Collectors: fetch source pages politely and turn them into raw items.

A raw item is a dict: source_id, url, title, published (YYYY-MM-DD or None), body, fetched_at.
Network code is kept separate from the parsers so the parsers can be tested offline.
"""
import hashlib
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.utils import requote_uri

import config
from dates import find_date, parse_any
from sources import SOURCES, Source

_ROBOTS: dict = {}
_last_request = 0.0


# ------------------------------------------------------------------ parsers (no network)

def _clean(text: str) -> str:
    text = " ".join((text or "").split())
    return re.sub(r"\s+([.,;:!?])", r"\1", text)  # get_text(" ") leaves gaps before punctuation


def _child_text(children: dict, *names: str) -> str:
    for n in names:
        el = children.get(n)
        if el is not None:
            return (el.get("href") or el.text or "").strip() if n == "link" else (el.text or "").strip()
    return ""


def parse_feed(xml_text: str) -> list[dict]:
    """Parse an RSS 2.0 or Atom feed into [{title, url, published, body}]."""
    root = ET.fromstring(xml_text)
    out = []
    for node in root.iter():
        if node.tag.split("}")[-1] not in ("item", "entry"):
            continue
        children = {c.tag.split("}")[-1]: c for c in node}
        desc_html = _child_text(children, "description", "summary", "content")
        out.append(
            {
                "title": _clean(_child_text(children, "title")),
                "url": _child_text(children, "link"),
                "published": parse_any(_child_text(children, "pubDate", "published", "updated", "date")),
                "body": _clean(BeautifulSoup(desc_html, "lxml").get_text(" ")) if desc_html else "",
            }
        )
    return [i for i in out if i["title"] and i["url"]]


def parse_listing(html: str, base_url: str, link_pattern: str = "", min_title_len: int = 25) -> list[dict]:
    """Pull article links (title, url, date near the link) out of a listing page."""
    soup = BeautifulSoup(html, "lxml")
    seen, out = set(), []
    for a in soup.find_all("a", href=True):
        title = _clean(a.get_text(" "))
        if len(title) < min_title_len:
            continue
        url = requote_uri(urljoin(base_url, a["href"]).split("#")[0])  # encodes spaces in file names
        if link_pattern and not re.search(link_pattern, url):
            continue
        if url in seen:
            continue
        seen.add(url)
        published = None
        for parent in list(a.parents)[:4]:  # nearest small container holding a date
            text = parent.get_text(" ")
            if len(text) > 500:
                break
            published = find_date(text)
            if published:
                break
        out.append({"title": title, "url": url, "published": published, "body": ""})
    return out


def parse_article(html: str) -> dict:
    """Body text and publication date from an article page."""
    soup = BeautifulSoup(html, "lxml")
    published = None
    meta = soup.find("meta", attrs={"property": "article:published_time"})
    if meta and meta.get("content"):
        published = parse_any(meta["content"])
    if not published:
        t = soup.find("time")
        if t:
            published = parse_any(t.get("datetime") or t.get_text())
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    node = soup.find("main") or soup.find("article") or soup.body or soup
    text = _clean(node.get_text(" "))[:8000]
    if not published:
        published = find_date(text[:600])
    return {"body": text, "published": published}


def discover_feeds(html: str, base_url: str) -> list[str]:
    """RSS/Atom feeds a page advertises with <link rel="alternate" type="application/rss+xml">."""
    soup = BeautifulSoup(html, "lxml")
    feeds = []
    for link in soup.find_all("link", attrs={"rel": "alternate"}, href=True):
        if re.search(r"rss|atom", link.get("type", ""), re.I):
            feeds.append(requote_uri(urljoin(base_url, link["href"])))
    return feeds


def is_pdf(url: str) -> bool:
    return url.lower().split("?")[0].endswith(".pdf")


def analyse_listing(html: str, url: str, link_pattern: str = "") -> dict:
    """Facts about a listing page, used by diagnose_source.py to pick or fix a link_pattern."""
    soup = BeautifulSoup(html, "lxml")
    long_anchors = []
    for a in soup.find_all("a", href=True):
        title = _clean(a.get_text(" "))
        if len(title) >= 25:
            long_anchors.append((title, requote_uri(urljoin(url, a["href"]).split("#")[0])))

    prefixes: dict[str, list] = {}
    for title, href in long_anchors:
        path = urlparse(href).path
        segs = [s for s in path.split("/") if s]
        key = "/" + "/".join(segs[:-1]) + "/" if len(segs) > 1 else "/"
        prefixes.setdefault(key, []).append(title)
    ranked = sorted(prefixes.items(), key=lambda kv: len(kv[1]), reverse=True)[:6]

    for tag in soup(["script", "style"]):
        tag.decompose()
    return {
        "text_chars": len(_clean(soup.get_text(" "))),
        "scripts": len(BeautifulSoup(html, "lxml").find_all("script")),
        "long_anchors": len(long_anchors),
        "matching": parse_listing(html, url, link_pattern),
        "feeds": discover_feeds(html, url),
        "prefixes": [(k, len(v), v[0]) for k, v in ranked],
        "looks_js_rendered": len(long_anchors) < 5 and len(BeautifulSoup(html, "lxml").find_all("script")) >= 5,
    }


# ------------------------------------------------------------------ network

def robots_allowed(url: str) -> bool:
    parts = urlparse(url)
    base = f"{parts.scheme}://{parts.netloc}"
    rp = _ROBOTS.get(base)
    if rp is None:
        rp = robotparser.RobotFileParser()
        try:
            r = requests.get(base + "/robots.txt", headers={"User-Agent": config.USER_AGENT}, timeout=15)
            if r.status_code == 404:
                rp.parse([])  # no robots.txt: everything allowed
            elif r.ok:
                rp.parse(r.text.splitlines())
            else:
                rp = False if not config.ROBOTS_FAIL_OPEN else None
        except requests.RequestException:
            rp = False if not config.ROBOTS_FAIL_OPEN else None
        _ROBOTS[base] = rp
    if rp is None:   # fail open
        return True
    if rp is False:  # fail closed
        return False
    return rp.can_fetch(config.USER_AGENT, url)


def polite_get(url: str) -> str:
    global _last_request
    if not robots_allowed(url):
        parts = urlparse(url)
        if _ROBOTS.get(f"{parts.scheme}://{parts.netloc}") is False:
            raise PermissionError(f"robots.txt could not be read (network problem, or the site blocked the request): {url}")
        raise PermissionError(f"robots.txt disallows fetching this URL: {url}")
    wait = config.REQUEST_DELAY_SECONDS - (time.time() - _last_request)
    if wait > 0:
        time.sleep(wait)
    resp = requests.get(url, headers={"User-Agent": config.USER_AGENT}, timeout=30)
    _last_request = time.time()
    resp.raise_for_status()
    return resp.text


# ------------------------------------------------------------------ per-source collection

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _snapshot_item(src: Source) -> Optional[dict]:
    """Emit an item only when the page content changed since the last run."""
    html = polite_get(src.url)
    art = parse_article(html)
    digest = hashlib.sha256(art["body"].encode()).hexdigest()
    config.SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    f = config.SNAPSHOT_DIR / f"{src.id}.sha"
    previous = f.read_text().strip() if f.exists() else None
    f.write_text(digest)
    if previous is None or previous == digest:
        return None  # first run just records the baseline
    today = datetime.now(timezone.utc).date().isoformat()
    return {
        "source_id": src.id,
        "url": f"{src.url}#changed-{today}",
        "title": f"{src.name}: page content changed",
        "published": today,
        "body": art["body"][:2000],
        "fetched_at": _now(),
    }


def collect_source(src: Source, limit: int = 25, fetch_details: bool = True) -> list[dict]:
    if src.method == "manual":
        return []
    if src.method == "page_snapshot":
        item = _snapshot_item(src)
        return [item] if item else []

    text = polite_get(src.url)
    if src.method == "rss":
        items = parse_feed(text)
    else:
        items = parse_listing(text, src.url, src.link_pattern)
        if src.try_feed:  # a feed the page advertises is more reliable than scraping its layout
            for feed_url in discover_feeds(text, src.url)[:2]:
                try:
                    feed_items = parse_feed(polite_get(feed_url))
                except Exception:  # noqa: BLE001 - fall back to the scraped listing
                    continue
                if feed_items:
                    print(f"    using feed {feed_url}")
                    items = feed_items
                    break
    items = items[:limit]

    if src.method == "html_list" and src.fetch_detail and fetch_details:
        for it in items:
            if it.get("body") or is_pdf(it["url"]):
                continue  # feed already gave text, or a PDF (cannot be read as a web page)
            try:
                art = parse_article(polite_get(it["url"]))
            except (requests.RequestException, PermissionError):
                continue
            it["body"] = art["body"]
            it["published"] = it["published"] or art["published"]

    for it in items:
        it["source_id"] = src.id
        it["fetched_at"] = _now()
    return items


def collect_all(fetch_details: bool = True, only: Optional[list[str]] = None) -> tuple[list[dict], list[str]]:
    """Collect from every automatic source. One failing source never stops the run."""
    items, errors = [], []
    for src in SOURCES:
        if src.method == "manual" or (only and src.id not in only):
            continue
        try:
            got = collect_source(src, fetch_details=fetch_details)
            print(f"  {src.id}: {len(got)} items")
            items.extend(got)
        except Exception as e:  # noqa: BLE001 - report and carry on
            msg = f"{src.id}: {type(e).__name__}: {e}"
            print(f"  {msg}")
            errors.append(msg)
    return items, errors
