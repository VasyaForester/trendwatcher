"""Тесты строгого фильтра ленты и дедупликации."""

import unittest

from trendwatcher.enrichment.tagger import (
    extract_tags,
    is_ai_related,
    is_ai_security_or_breakthrough,
)
from trendwatcher.ingestion.dedup import normalize_url, title_fingerprint


class TestStrictRelevance(unittest.TestCase):
    def test_simon_style_generic_ai_rejected(self):
        text = (
            "Weeknotes: miscellaneous web tooling, a few thoughts on AI productivity, "
            "and updating my blog theme"
        )
        self.assertTrue(is_ai_related(text))  # широкий фильтр ещё ловит
        self.assertFalse(is_ai_security_or_breakthrough(text))

    def test_prompt_injection_accepted(self):
        text = "New MemGhost attack plants false memories via prompt injection in AI agents"
        self.assertTrue(is_ai_security_or_breakthrough(text))
        self.assertIn("agent_security", extract_tags(text))

    def test_breakthrough_agentic_accepted(self):
        text = "OpenAI unveils a new agentic reasoning model for tool-using agents"
        self.assertTrue(is_ai_security_or_breakthrough(text))

    def test_bare_machine_learning_rejected(self):
        text = "Company improves machine learning pipeline for ad targeting"
        self.assertTrue(is_ai_related(text))
        self.assertFalse(is_ai_security_or_breakthrough(text))


class TestDedup(unittest.TestCase):
    def test_normalize_url_strips_tracking(self):
        a = normalize_url("https://www.Example.com/path/?utm_source=x&id=1#frag")
        b = normalize_url("https://example.com/path?id=1")
        self.assertEqual(a, b)

    def test_title_fingerprint_collapses_noise(self):
        a = title_fingerprint("OpenAI Launches New Agentic Model!!!")
        b = title_fingerprint("openai launches new agentic model")
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
