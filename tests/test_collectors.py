import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import collectors  # noqa: E402

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>Student visa cap announced</title><link>https://example.org/a</link>
        <pubDate>Tue, 29 Sep 2026 03:00:00 GMT</pubDate>
        <description>&lt;p&gt;Details of the &lt;b&gt;cap&lt;/b&gt;.&lt;/p&gt;</description></item>
  <item><title></title><link>https://example.org/skip</link></item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><title>Atom entry about visas</title><link href="https://example.org/b"/>
         <updated>2026-09-30T10:00:00Z</updated><summary>Short summary</summary></entry>
</feed>"""

LISTING = """
<html><body><ul>
 <li><a href="/news/student-visa-changes-announced-today">Student visa changes announced today for providers</a>
     <span>2 October 2026</span></li>
 <li><a href="/news/short">Short</a></li>
 <li><a href="/about/team-and-contact-details-page">Team and contact details for the department</a></li>
 <li><a href="/news/student-visa-changes-announced-today#top">Student visa changes announced today for providers</a></li>
</ul></body></html>"""

ARTICLE = """
<html><head><meta property="article:published_time" content="2026-10-02T09:00:00+10:00"></head>
<body><nav>Menu</nav><main><h1>Title</h1><p>The new rules start from 1 January 2027.</p></main><footer>x</footer></body></html>"""


def test_parse_rss():
    items = collectors.parse_feed(RSS)
    assert len(items) == 1
    assert items[0]["published"] == "2026-09-29"
    assert items[0]["body"] == "Details of the cap."


def test_parse_atom():
    items = collectors.parse_feed(ATOM)
    assert items[0]["url"] == "https://example.org/b"
    assert items[0]["published"] == "2026-09-30"


def test_parse_listing_filters_and_dedupes():
    items = collectors.parse_listing(LISTING, "https://example.org/", link_pattern=r"/news/")
    assert [i["url"] for i in items] == ["https://example.org/news/student-visa-changes-announced-today"]
    assert items[0]["published"] == "2026-10-02"


def test_parse_article():
    art = collectors.parse_article(ARTICLE)
    assert art["published"] == "2026-10-02"
    assert "start from 1 January 2027" in art["body"]
    assert "Menu" not in art["body"]
