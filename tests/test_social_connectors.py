"""Telegram preview parser и отказ X без backend не бросают исключение."""

import unittest
from types import SimpleNamespace

from trendwatcher.ingestion.html_article import article_links, parse_article
from trendwatcher.ingestion.telegram import parse_channel_html
from trendwatcher.ingestion.x import fetch as fetch_x


FIXTURE = """
<div class="tgme_widget_message" data-post="llmsecurity/42">
<div class="tgme_widget_message_text js-message_text" dir="auto">
Researchers demonstrated a poisoned MCP tool.
<a href="https://arxiv.org/abs/2601.00001">paper</a>
</div>
<a href="https://t.me/llmsecurity/42"><time datetime="2026-08-01T12:00:00+00:00"></time></a>
</div>
"""


class TestTelegramParse(unittest.TestCase):
    def test_prefers_external_primary_url(self):
        items = parse_channel_html(FIXTURE, "llmsecurity")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], "https://arxiv.org/abs/2601.00001")
        self.assertIn("t.me/llmsecurity/42", items[0]["summary"])
        self.assertEqual(items[0]["published_at"].year, 2026)


class TestHtmlArticle(unittest.TestCase):
    def test_index_links_and_jsonld(self):
        index = '<a href="/blog/dasf-3">DASF</a><a href="https://other.example/x">no</a>'
        links = article_links(index, "https://vendor.example/blog")
        self.assertEqual(links, ["https://vendor.example/blog/dasf-3"])
        page = """
        <script type="application/ld+json">
        {"@type":"NewsArticle","headline":"DASF 3.0 adds an Agentic AI component","datePublished":"2026-06-01T00:00:00Z","description":"35 new risks"}
        </script>
        """
        item = parse_article(page, "https://vendor.example/blog/dasf-3")
        self.assertIsNotNone(item)
        self.assertIn("DASF 3.0", item["title"])
        self.assertEqual(item["published_at"].year, 2026)


class TestXDegrades(unittest.TestCase):
    def test_missing_backend_returns_empty(self):
        source = SimpleNamespace(id="x_test", username="simonw", max_results=5)
        # load_x_backends читает yaml; пустые списки и отсутствие токена → [].
        import os

        old = os.environ.pop("X_BEARER_TOKEN", None)
        try:
            self.assertEqual(fetch_x(source), [])
        finally:
            if old is not None:
                os.environ["X_BEARER_TOKEN"] = old


if __name__ == "__main__":
    unittest.main()
