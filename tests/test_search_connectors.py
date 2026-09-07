"""Поисковые коннекторы: в корпус только URL издателя, не SERP."""

from __future__ import annotations

import json
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from trendwatcher.config import SourceConfig, load_sources
from trendwatcher.ingestion import bingnews, gnews, hn
from trendwatcher.ingestion.resolve import (
    is_aggregator_url,
    publisher_label,
    resolve_google_news_url,
    strip_publisher_suffix,
    unwrap_bing_url,
    _parse_garturlres,
)
from trendwatcher.ingestion.runner import CONNECTORS


GNEWS_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>search</title>
    <item>
      <title>ASCII smuggling crosses over - Microsoft</title>
      <link>https://news.google.com/rss/articles/CBMifakeid</link>
      <pubDate>Wed, 03 Sep 2026 12:00:00 GMT</pubDate>
      <source url="https://www.microsoft.com">Microsoft</source>
      <description>summary about prompt injection</description>
    </item>
    <item>
      <title>Unresolved wrapper - Example</title>
      <link>https://news.google.com/rss/articles/CBMiunresolved</link>
      <pubDate>Wed, 03 Sep 2026 11:00:00 GMT</pubDate>
      <source url="https://example.com">Example</source>
      <description>no dest</description>
    </item>
  </channel>
</rss>
"""

BING_RSS = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:News="https://www.bing.com">
  <channel>
    <title>search</title>
    <item>
      <title>Prompt injection in Copilot</title>
      <link>http://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;url=https%3a%2f%2fwww.bleepingcomputer.com%2fnews%2fsecurity%2fprompt-injection%2f</link>
      <pubDate>Wed, 03 Sep 2026 12:00:00 GMT</pubDate>
      <News:Source>BleepingComputer</News:Source>
      <description>article summary</description>
    </item>
    <item>
      <title>Ask HN style junk</title>
      <link>http://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;url=https%3a%2f%2fnews.google.com%2frss%2farticles%2fCBMi</link>
      <pubDate>Wed, 03 Sep 2026 11:00:00 GMT</pubDate>
      <description>should be dropped</description>
    </item>
  </channel>
</rss>
"""


class _Resp:
    def __init__(self, content=b"", text="", json_data=None, status=200):
        self.content = content
        self.text = text
        self.status_code = status
        self._json = json_data or {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")


class TestAggregatorUrls(unittest.TestCase):
    def test_blocks_serp_and_wrappers(self):
        self.assertTrue(is_aggregator_url("https://news.google.com/rss/articles/CBMiabc"))
        self.assertTrue(
            is_aggregator_url(
                "http://www.bing.com/news/apiclick.aspx?url=https://example.com/a"
            )
        )
        self.assertTrue(is_aggregator_url("https://news.ycombinator.com/item?id=1"))
        self.assertTrue(is_aggregator_url("https://www.google.com/search?q=llm"))
        self.assertFalse(
            is_aggregator_url(
                "https://www.microsoft.com/en-us/security/blog/2026/09/03/ascii/"
            )
        )
        self.assertFalse(is_aggregator_url("https://simonwillison.net/2026/sep/1/pi/"))

    def test_bing_unwraps_publisher(self):
        wrapped = (
            "http://www.bing.com/news/apiclick.aspx?ref=FexRss"
            "&url=https%3a%2f%2fwww.bleepingcomputer.com%2fnews%2fsecurity%2fpi%2f"
        )
        self.assertEqual(
            unwrap_bing_url(wrapped),
            "https://www.bleepingcomputer.com/news/security/pi/",
        )
        self.assertIsNone(unwrap_bing_url("https://news.google.com/rss/articles/CBMi"))

    def test_title_and_label(self):
        self.assertEqual(
            strip_publisher_suffix("ASCII smuggling - Microsoft", "Microsoft"),
            "ASCII smuggling",
        )
        self.assertEqual(
            publisher_label("https://www.microsoft.com/blog/a", "HN", "Microsoft"),
            "Microsoft",
        )
        self.assertEqual(
            publisher_label("https://www.promptarmor.com/post", "Hacker News"),
            "promptarmor.com",
        )


class TestGnewsResolve(unittest.TestCase):
    def test_parse_batchexecute(self):
        body = (
            ")]}'\n"
            + json.dumps(
                [
                    [
                        "wrb.fr",
                        "Fbv4je",
                        json.dumps(
                            [
                                "garturlres",
                                "https://www.microsoft.com/security/ascii",
                                1,
                            ]
                        ),
                    ]
                ]
            )
        )
        self.assertEqual(
            _parse_garturlres(body),
            "https://www.microsoft.com/security/ascii",
        )

    def test_resolve_uses_signature_rpc(self):
        client = MagicMock()
        client.get.return_value = _Resp(
            text='<div data-n-a-sg="SIG" data-n-a-ts="1710000000"></div>'
        )
        client.post.return_value = _Resp(
            text=(
                ")]}'\n"
                '[["wrb.fr","Fbv4je","[\\"garturlres\\",'
                '\\"https://www.microsoft.com/en-us/security/blog/ascii\\",1]"]]'
            )
        )
        dest = resolve_google_news_url(
            "https://news.google.com/rss/articles/CBMifake",
            client=client,
        )
        self.assertEqual(
            dest, "https://www.microsoft.com/en-us/security/blog/ascii"
        )
        client.get.assert_called_once()
        client.post.assert_called_once()

    def test_fetch_drops_unresolved_and_keeps_publisher(self):
        source = SourceConfig(
            id="gnews_ai_security",
            name="Google News — AI security",
            type="gnews",
            source_type="news",
            query='"prompt injection" when:14d',
            max_results=10,
        )
        client = MagicMock()
        client.get.return_value = _Resp(content=GNEWS_RSS.encode())
        client.post.return_value = _Resp(text="nope")

        def _resolve(url, client=None):
            if "fakeid" in url:
                return "https://www.microsoft.com/en-us/security/blog/ascii"
            return None

        with (
            patch("trendwatcher.ingestion.gnews.gnews_client", return_value=client),
            patch("trendwatcher.ingestion.gnews.resolve_google_news_url", side_effect=_resolve),
            patch("trendwatcher.ingestion.gnews.RESOLVE_PAUSE_SEC", 0),
        ):
            items = gnews.fetch(source)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], "https://www.microsoft.com/en-us/security/blog/ascii")
        self.assertFalse(is_aggregator_url(items[0]["url"]))
        self.assertEqual(items[0]["source_name"], "Microsoft")
        self.assertEqual(items[0]["title"], "ASCII smuggling crosses over")


class TestBingAndHn(unittest.TestCase):
    def test_bing_fetch_unwraps(self):
        source = SourceConfig(
            id="bing_ai_security",
            name="Bing News — AI security",
            type="bingnews",
            source_type="news",
            query="prompt injection",
            max_results=10,
        )
        with patch(
            "trendwatcher.ingestion.bingnews.http_get",
            return_value=_Resp(content=BING_RSS.encode()),
        ):
            items = bingnews.fetch(source)
        self.assertEqual(len(items), 1)
        self.assertEqual(
            items[0]["url"],
            "https://www.bleepingcomputer.com/news/security/prompt-injection/",
        )
        self.assertEqual(items[0]["source_name"], "BleepingComputer")

    def test_hn_skips_empty_and_item_pages(self):
        source = SourceConfig(
            id="hn_ai_security",
            name="Hacker News",
            type="hn",
            source_type="news",
            query="prompt injection",
            max_results=10,
            days_back=21,
        )
        payload = {
            "hits": [
                {
                    "title": "Ask HN: jailbreaks?",
                    "url": None,
                    "created_at": "2026-09-01T00:00:00.000Z",
                },
                {
                    "title": "HN discussion only",
                    "url": "https://news.ycombinator.com/item?id=1",
                    "created_at": "2026-09-01T00:00:00.000Z",
                },
                {
                    "title": "Google Antigravity exfiltrates data",
                    "url": "https://www.promptarmor.com/resources/antigravity",
                    "created_at": "2026-09-01T12:00:00.000Z",
                    "story_text": "",
                },
            ]
        }
        with patch(
            "trendwatcher.ingestion.hn.http_get",
            return_value=_Resp(json_data=payload),
        ):
            items = hn.fetch(source)
        self.assertEqual(len(items), 1)
        self.assertEqual(
            items[0]["url"], "https://www.promptarmor.com/resources/antigravity"
        )
        self.assertEqual(items[0]["source_name"], "promptarmor.com")
        self.assertIsInstance(items[0]["published_at"], datetime)


class TestWiring(unittest.TestCase):
    def test_connectors_and_yaml(self):
        self.assertEqual(
            set(CONNECTORS),
            {"rss", "arxiv", "nvd", "gnews", "bingnews", "hn"},
        )
        sources = load_sources()
        types = {s.type for s in sources}
        self.assertTrue({"gnews", "bingnews", "hn"}.issubset(types))
        for src in sources:
            self.assertIn(src.type, CONNECTORS)
        gnews_src = next(s for s in sources if s.id == "gnews_ai_security")
        self.assertGreaterEqual(len(gnews_src.search_queries()), 3)

    def test_ingest_skips_aggregator_url(self):
        from trendwatcher.ingestion.runner import ingest_source

        source = SourceConfig(
            id="gnews_ai_security",
            name="Google News",
            type="gnews",
            source_type="news",
        )
        item = {
            "url": "https://news.google.com/rss/articles/CBMiabc",
            "title": "Should not land",
            "summary": "prompt injection",
            "published_at": datetime(2026, 9, 3),
        }
        session = MagicMock()
        session.scalars.return_value.all.return_value = []
        with patch.dict(CONNECTORS, {"gnews": lambda _s: [item]}):
            added, total = ingest_source(source, session)
        self.assertEqual(total, 1)
        self.assertEqual(added, 0)
        session.add.assert_not_called()


if __name__ == "__main__":
    unittest.main()
