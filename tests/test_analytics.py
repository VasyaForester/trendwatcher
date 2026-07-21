"""Юнит-тесты расчёта динамики и фильтрации тегов."""

import unittest

from trendwatcher.analytics.velocity import (
    MAX_VELOCITY,
    cap_velocity,
    pct_change,
    velocity_from_counts,
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
        self.assertEqual(src, "share_90d")

    def test_velocity_from_shares_zero_prior(self):
        v, src = velocity_from_shares(0.03, 0.0)
        self.assertEqual(v, 0.0)
        self.assertIsNone(src)

    def test_velocity_label(self):
        self.assertIn("доли", velocity_label(0.5, "share_90d"))
        self.assertEqual(velocity_label(0.0, None), "н/д")

    def test_velocity_from_counts(self):
        v, src = velocity_from_counts(15, 10)
        self.assertAlmostEqual(v, 0.5)
        self.assertEqual(src, "counts_90d")
        v, src = velocity_from_counts(5, 0)
        self.assertEqual(v, 0.0)
        self.assertIsNone(src)


class TestLevelFromVelocity(unittest.TestCase):
    def test_positive_velocity_never_declining(self):
        from trendwatcher.analytics.signals import level_from_velocity

        level, _ = level_from_velocity(
            velocity=0.8,
            vel_source="share_90d",
            recent=20,
            prior=10,
            n_types=2,
            week_conc=0.3,
            genuinely_new=False,
            research_share_alltime=0.5,
            age_weeks=30,
            coverage_weeks=40,
        )
        self.assertNotEqual(level, "declining")
        self.assertIn(level, {"strong", "emerging"})

    def test_decline_only_when_negative(self):
        from trendwatcher.analytics.signals import level_from_velocity

        level, _ = level_from_velocity(
            velocity=-0.4,
            vel_source="share_90d",
            recent=10,
            prior=20,
            n_types=2,
            week_conc=0.2,
            genuinely_new=False,
            research_share_alltime=0.5,
            age_weeks=40,
            coverage_weeks=50,
        )
        self.assertEqual(level, "declining")

class TestTagFilter(unittest.TestCase):
    def test_signal_tags(self):
        self.assertTrue(is_signal_tag("prompt_injection"))
        self.assertTrue(is_signal_tag("agent_security"))
        self.assertTrue(is_signal_tag("self_evolving_agents"))
        self.assertTrue(is_signal_tag("computer_use_agents"))
        self.assertTrue(is_signal_tag("ai_codegen_security"))
        self.assertFalse(is_signal_tag("agentic_ai"))
        self.assertFalse(is_signal_tag("vulnerability_cve"))
        self.assertFalse(is_signal_tag("deepfake_fraud"))
        self.assertFalse(is_signal_tag("model_efficiency"))

    def test_normalize_tags_whitelist(self):
        self.assertEqual(normalize_tags(["prompt_injection", "fake_tag", "prompt_injection"]), ["prompt_injection"])

    def test_memghost_gets_agent_security(self):
        text = (
            "New MemGhost Attack Plants Persistent False Memories in AI Agents "
            "Through One Email"
        )
        tags = extract_tags(text)
        self.assertTrue("agent_security" in tags or "agent_memory_security" in tags)
        self.assertNotIn("long_context_memory", tags)

    def test_new_signal_tags_match(self):
        self.assertIn("computer_use_agents", extract_tags("OpenAI launches a computer-use agent for browsers"))
        self.assertIn("indirect_prompt_injection", extract_tags("Indirect prompt injection via malicious webpage"))
        self.assertIn("autonomous_cyber_offense", extract_tags("AI agents turned into attackers in autonomous intrusion"))


if __name__ == "__main__":
    unittest.main()
