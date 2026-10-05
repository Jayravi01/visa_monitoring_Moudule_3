"""Check one source against the live site and suggest what to fix.

    python diagnose_source.py study_australia
    python diagnose_source.py https://example.gov.au/news --pattern "/news/[^/?#]+"

Run it on your own computer (it needs internet access). It respects robots.txt like the real collector.
It reports: HTTP/robots status, how many links were found, which links your link_pattern keeps, a sample of
parsed items, any RSS/Atom feed the page advertises, the most common URL folders among long link texts
(use one as your link_pattern), and whether the page looks like it builds its list with JavaScript.
"""
import argparse
import re
import sys

import requests

import collectors
from sources import BY_ID


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="a source id from sources.py, or a full URL")
    ap.add_argument("--pattern", default=None, help="link_pattern regex to test (defaults to the source's own)")
    args = ap.parse_args()

    if args.target in BY_ID:
        src = BY_ID[args.target]
        url, pattern = src.url, args.pattern if args.pattern is not None else src.link_pattern
        print(f"Source: {src.id} ({src.method}, status {src.status})")
    else:
        url, pattern = args.target, args.pattern or ""
    print(f"URL: {url}\nlink_pattern: {pattern or '(none)'}\n")

    try:
        html = collectors.polite_get(url)
    except PermissionError as e:
        if "could not be read" in str(e):
            print(f"NOT CHECKED: {e}\n-> Check your internet connection and try again. If it keeps failing, the site "
                  "may block scripts: add items by hand instead.")
        else:
            print(f"BLOCKED: {e}\n-> The site asks scrapers to stay away. Do not scrape it; use another source "
                  "or add items by hand.")
        return 1
    except requests.HTTPError as e:
        print(f"HTTP error: {e}\n-> The URL is wrong or has moved. Open it in a browser and copy the real address.")
        return 1
    except requests.RequestException as e:
        print(f"Network error: {e}")
        return 1

    info = collectors.analyse_listing(html, url, pattern)
    print(f"Page text: {info['text_chars']:,} characters, {info['scripts']} script tags, "
          f"{info['long_anchors']} links with 25+ characters of text")

    if info["looks_js_rendered"]:
        print("\nWARNING: very few links and many scripts. This page probably builds its list with JavaScript, "
              "so a plain download will not see it. Look for a feed or an individual article page to use "
              "with page_snapshot instead.")

    if info["feeds"]:
        print("\nFeeds advertised (the collector uses these automatically when try_feed is on):")
        for f in info["feeds"]:
            print("  ", f)
    else:
        print("\nNo RSS/Atom feed advertised.")

    print("\nMost common URL folders among long link texts (pick one for link_pattern):")
    for prefix, count, example in info["prefixes"]:
        print(f"  {count:3d}  {prefix}   e.g. {example[:60]!r}")
        if pattern and re.search(pattern, prefix):
            print("       ^ already matched by your pattern")

    items = info["matching"]
    print(f"\nLinks kept by link_pattern: {len(items)}")
    for it in items[:8]:
        print(f"  {it['published'] or 'no date':10s}  {it['title'][:70]}\n              {it['url']}")
    if not items:
        print("  None. Try one of the folders above, for example --pattern \"/news/\".")
    elif sum(1 for it in items if not it["published"]) > len(items) / 2:
        print("\nNote: most items have no date next to the link. They will be dated by the day they are first seen "
              "unless the article page carries a date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
