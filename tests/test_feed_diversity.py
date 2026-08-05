"""Тесты разнообразия ленты (квота CVE)."""

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from trendwatcher.feed import FEED_MAX_AGE_DAYS, MAX_CVE_SHARE, build_feed, diversify_feed


def _doc(i: int, *, cve: bool, source: str, days_ago: int = 0):
    return SimpleNamespace(
        id=i,
        source_id=source,
        source_name=source,
        source_type="vulnerability" if cve else "news",
        doc_type="vulnerability" if cve else "incident",
        title=f"CVE-2026-{1000+i}: agent bug" if cve else f"Incident at {source} #{i}",
        summary="",
        url=f"https://example.com/{i}",
        published_at=datetime(2026, 7, 20) - timedelta(days=days_ago),
        tags=["prompt_injection"] if not cve else ["vulnerability_cve"],
        to_dict=lambda self=None, **kw: {"id": i},
    )


class TestFeedDiversity(unittest.TestCase):
    def test_cve_share_capped(self):
        docs = [_doc(i, cve=True, source="nvd", days_ago=i) for i in range(40)]
        docs += [_doc(100 + i, cve=False, source=f"src{i%5}", days_ago=i) for i in range(40)]
        out = diversify_feed(docs, limit=40)
        cve_n = sum(1 for d in out if d.title.startswith("CVE-"))
        self.assertLessEqual(cve_n / len(out), MAX_CVE_SHARE + 0.05)
        self.assertGreater(cve_n, 0)

    def test_sources_interleaved(self):
        docs = []
        for s in ("thn", "openai", "google"):
            for i in range(10):
                docs.append(_doc(hash(s) % 1000 + i, cve=False, source=s, days_ago=i))
        out = diversify_feed(docs, limit=9)
        sources = [d.source_id for d in out[:6]]
        # первые слоты не из одного источника подряд целиком
        self.assertGreater(len(set(sources)), 1)

    def test_build_feed_drops_older_than_max_age(self):
        fresh = _doc(1, cve=False, source="google", days_ago=10)
        stale = _doc(2, cve=False, source="nist", days_ago=FEED_MAX_AGE_DAYS + 5)
        stale.title = "Draft NIST Guidelines Rethink Cybersecurity for the AI Era"
        stale.url = "https://nist.gov/old"
        # to_dict on SimpleNamespace — build_feed calls d.to_dict()
        fresh.to_dict = lambda: {"title": fresh.title, "published_at": fresh.published_at.isoformat()}
        stale.to_dict = lambda: {"title": stale.title, "published_at": stale.published_at.isoformat()}

        session = MagicMock()
        # build_feed filters by SQL cutoff; mock returns both, Python filter also applies
        session.scalars.return_value.all.return_value = [fresh, stale]

        with patch("trendwatcher.feed.utcnow", return_value=datetime(2026, 7, 22)):
            with patch("trendwatcher.feed._feed_eligible", return_value=True):
                with patch("trendwatcher.feed.is_arxiv_url", return_value=False):
                    out = build_feed(session, limit=10)

        titles = [d["title"] for d in out]
        self.assertIn(fresh.title, titles)
        self.assertNotIn(stale.title, titles)

    def test_build_feed_is_strictly_newest_first(self):
        docs = [
            _doc(1, cve=False, source="a", days_ago=3),
            _doc(2, cve=False, source="b", days_ago=1),
            _doc(3, cve=False, source="c", days_ago=2),
        ]
        for doc in docs:
            doc.to_dict = lambda d=doc: {
                "title": d.title,
                "published_at": d.published_at.isoformat(),
            }

        session = MagicMock()
        session.scalars.return_value.all.return_value = docs

        with patch("trendwatcher.feed.utcnow", return_value=datetime(2026, 7, 22)):
            with patch("trendwatcher.feed._feed_eligible", return_value=True):
                with patch("trendwatcher.feed.is_arxiv_url", return_value=False):
                    out = build_feed(session, limit=10)

        dates = [d["published_at"] for d in out]
        self.assertEqual(dates, sorted(dates, reverse=True))


if __name__ == "__main__":
    unittest.main()
