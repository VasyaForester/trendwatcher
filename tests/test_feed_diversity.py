"""Тесты разнообразия ленты (квота CVE)."""

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from trendwatcher.feed import MAX_CVE_SHARE, diversify_feed


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
        tags=[],
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


if __name__ == "__main__":
    unittest.main()
