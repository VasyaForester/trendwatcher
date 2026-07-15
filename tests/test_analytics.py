"""Юнит-тесты расчёта динамики и фильтрации тегов."""

import unittest

from trendwatcher.analytics.velocity import (
    MAX_VELOCITY,
    cap_velocity,
    pct_change,
    velocity_from_shares,
    velocity_label,
)
from trendwatcher.enrichment.tagger import extract_tags
from trendwatcher.enrichment.tag_filter import is_signal_tag, normalize_tags


class TestPctChange(unittest.TestCase):
    def test_positive_change(self):
        self.assertAlmostEqual(pct_change(15, 10), 0.5)

    def test_negative_change(self):
        self.assertAlmostEqual(pct_change(12, 15), -0.2)

    def test_zero_prior_returns_none(self):
        self.assertIsNone(pct_change(50, 0))

    def test_cap_velocity(self):
        self.assertEqual(cap_velocity(5.0), MAX_VELOCITY)
        self.assertEqual(cap_velocity(None), 0.0)

    def test_velocity_from_shares(self):
        v, src = velocity_from_shares(0.03, 0.02)
        self.assertAlmostEqual(v, 0.5)
        self.assertEqual(src, "archive")

    def test_velocity_from_shares_zero_prior(self):
        v, src = velocity_from_shares(0.03, 0.0)
        self.assertEqual(v, 0.0)
        self.assertIsNone(src)

    def test_velocity_label(self):
        self.assertIn("+50%", velocity_label(0.5, "archive"))


class TestTagFilter(unittest.TestCase):
    def test_signal_tags_are_security_only(self):
        self.assertTrue(is_signal_tag("prompt_injection"))
        self.assertTrue(is_signal_tag("agent_security"))
        self.assertFalse(is_signal_tag("model_efficiency"))
        self.assertFalse(is_signal_tag("agentic_ai"))

    def test_normalize_tags_whitelist(self):
        self.assertEqual(normalize_tags(["prompt_injection", "fake_tag", "prompt_injection"]), ["prompt_injection"])

    def test_memghost_gets_agent_security(self):
        text = (
            "New MemGhost Attack Plants Persistent False Memories in AI Agents "
            "Through One Email"
        )
        tags = extract_tags(text)
        self.assertIn("agent_security", tags)
        self.assertNotIn("long_context_memory", tags)


if __name__ == "__main__":
    unittest.main()
