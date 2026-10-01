"""Квартальные Trend candidates: память + порог регулярности."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from trendwatcher.enrichment.candidates import refresh_candidates


def _doc(title: str, when: datetime, url: str) -> SimpleNamespace:
    return SimpleNamespace(
        title=title,
        summary="",
        url=url,
        published_at=when,
        source_name="arXiv",
        doc_type="research",
    )


class TestTrendCandidates(unittest.TestCase):
    def test_promotes_regular_growth_vs_prior_quarter(self):
        now = datetime(2026, 9, 10)
        docs = []
        # Q2: много шума, одна статья с фразой.
        for i in range(20):
            docs.append(
                _doc(
                    f"Unrelated reasoning models paper {i}",
                    datetime(2026, 5, 4) + timedelta(days=i),
                    f"https://example.com/q2-noise-{i}",
                )
            )
        docs.append(
            _doc(
                "Capability attestation protocol in multi-party agents",
                datetime(2026, 5, 20),
                "https://example.com/q2-hit",
            )
        )
        # Q3: та же фраза в 4 разных неделях, 8+ раз.
        for i in range(8):
            docs.append(
                _doc(
                    "Capability attestation protocol in multi-party agents",
                    datetime(2026, 7, 6) + timedelta(days=i * 7),
                    f"https://example.com/q3-hit-{i}",
                )
            )
        for i in range(8):
            docs.append(
                _doc(
                    f"Other Q3 filler {i}",
                    datetime(2026, 8, 2) + timedelta(days=i),
                    f"https://example.com/q3-fill-{i}",
                )
            )
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "trend_candidates.json"
            shown = refresh_candidates(docs, now=now, path=path)
        ids = {c["id"] for c in shown}
        self.assertTrue(any("attestation" in c["id"] for c in shown), msg={c["id"] for c in shown})
        hit = next(c for c in shown if "attestation" in c["id"])
        self.assertGreaterEqual(hit["count"], 8)
        self.assertGreaterEqual(hit["weeks"], 3)
        self.assertEqual(hit["quarter"], "2026-Q3")
        self.assertTrue(hit["docs"])
        self.assertTrue(all(d["url"].startswith("https://example.com/q3-hit") for d in hit["docs"]))

    def test_spike_stays_in_memory_not_on_site(self):
        now = datetime(2026, 9, 10)
        docs = [
            _doc(
                "Plugin hijack via untrusted tool descriptors",
                datetime(2026, 8, 3),
                f"https://example.com/spike-{i}",
            )
            for i in range(12)
        ]
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "trend_candidates.json"
            shown = refresh_candidates(docs, now=now, path=path)
            memory = path.read_text(encoding="utf-8")
        self.assertFalse(any(c["id"] == "plugin_hijack" for c in shown))
        self.assertIn("plugin_hijack", memory)

    def test_rejects_grammar_junk(self):
        now = datetime(2026, 9, 10)
        docs = [
            _doc(
                "AI agents can become persistent insider threats",
                datetime(2026, 7, 6) + timedelta(days=i * 7),
                f"https://example.com/junk-{i}",
            )
            for i in range(8)
        ]
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "trend_candidates.json"
            shown = refresh_candidates(docs, now=now, path=path)
        self.assertNotIn("agents_can", {c["id"] for c in shown})


if __name__ == "__main__":
    unittest.main()
