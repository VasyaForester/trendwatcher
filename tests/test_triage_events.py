"""Полнота раннего фильтра, группировка событий и редкие сигналы."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trendwatcher.analytics.signals import level_from_velocity
from trendwatcher.analytics.velocity import smoothing_for_window, velocity_from_smoothed_counts
from trendwatcher.ingestion.health import record_fetch
from trendwatcher.ingestion.watch import fetch as watch_fetch
from trendwatcher.relevance.editorial import cluster_event_key
from trendwatcher.relevance.triage import triage_document


class TestTriageKeepsBorderline(unittest.TestCase):
    def test_prompt_injection_without_security_word_is_kept(self):
        decision, _reason = triage_document(
            "Indirect prompt injection hides instructions in an email and the agent exfiltrates the inbox",
            role="expert",
            filter_ai=True,
        )
        self.assertIn(decision, {"include", "review"})

    def test_unknown_technique_from_primary_is_review_not_reject(self):
        decision, reason = triage_document(
            "GhostPrompt: we demonstrate a bypass that makes a coding agent run attacker commands",
            role="primary",
            source_id="openai_blog",
            filter_ai=True,
        )
        self.assertNotEqual(decision, "reject")
        self.assertNotEqual(reason, "off_topic")

    def test_model_launch_is_reject(self):
        decision, reason = triage_document(
            "Introducing GPT-5, a flagship model with a 20% benchmark gain",
            role="primary",
            filter_ai=True,
        )
        self.assertEqual(decision, "reject")
        self.assertEqual(reason, "obvious_noise")

    def test_vendor_incident_and_defense_tool_are_kept(self):
        incident, _ = triage_document(
            "Hugging Face security incident: a malicious model stole credentials from the inference cluster",
            role="primary",
            source_name="Hugging Face Blog",
            filter_ai=True,
        )
        tool, _ = triage_document(
            "DeepKeep AI Lens blocks tool calls from a coding agent before they leave the sandbox",
            role="expert",
            filter_ai=True,
        )
        self.assertNotEqual(incident, "reject")
        self.assertNotEqual(tool, "reject")

    def test_framework_update_is_kept(self):
        decision, _reason = triage_document(
            "OWASP GenAI published an updated taxonomy of agent attack techniques and test controls",
            role="primary",
            source_id="owasp_genai",
            filter_ai=True,
        )
        self.assertIn(decision, {"include", "review"})


class TestEventGrouping(unittest.TestCase):
    def test_same_cve_different_headlines_share_key(self):
        a = cluster_event_key(
            "CVE-2026-46341 lets the Apify MCP server extract website data",
            "",
            [],
        )
        b = cluster_event_key(
            "Apify MCP vulnerability CVE-2026-46341 is now public",
            "",
            [("CVE-2026-46341 lets the Apify MCP server extract website data", a)],
        )
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("cve:"))

    def test_similar_titles_different_products_stay_apart(self):
        first = cluster_event_key("Google patches prompt injection in Gemini enterprise", "", [])
        second = cluster_event_key(
            "Google patches prompt injection in Workspace enterprise",
            "",
            [("Google patches prompt injection in Gemini enterprise", first)],
        )
        self.assertNotEqual(first, second)

    def test_same_product_and_technique_link(self):
        first = cluster_event_key(
            "Researchers disclose prompt injection in GitHub Copilot that leaks secrets",
            "",
            [],
        )
        second = cluster_event_key(
            "GitHub Copilot prompt injection leaks secrets, researchers say",
            "",
            [(
                "Researchers disclose prompt injection in GitHub Copilot that leaks secrets",
                first,
            )],
        )
        self.assertEqual(first, second)


class TestRareSignal(unittest.TestCase):
    def test_two_to_six_unique_events_is_visible(self):
        smoothing = smoothing_for_window(6, 2, n_types=2, week_conc=0.4)
        velocity, _src = velocity_from_smoothed_counts(6, 2, smoothing=smoothing)
        level, _reason = level_from_velocity(
            velocity=velocity,
            vel_source="smoothed_counts_90d",
            recent=6,
            prior=2,
            n_types=2,
            week_conc=0.4,
            genuinely_new=False,
            research_share_alltime=0.0,
            age_weeks=30,
            coverage_weeks=40,
        )
        self.assertGreaterEqual(velocity, 0.25)
        self.assertEqual(level, "emerging")

    def test_reprint_spike_stays_damped(self):
        smoothing = smoothing_for_window(8, 1, n_types=1, week_conc=0.9)
        self.assertEqual(smoothing, 25)
        velocity, _src = velocity_from_smoothed_counts(8, 1, smoothing=smoothing)
        self.assertLess(velocity, 0.25)


class TestHealthAndWatch(unittest.TestCase):
    def test_empty_fetch_is_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("trendwatcher.ingestion.health.HEALTH_PATH", root / "health.json"), patch(
                "trendwatcher.ingestion.health.ARCHIVE_HEALTH_PATH", root / "archive.json"
            ):
                row = record_fetch("dead_source", fetched=0, accepted=0, rejected=0, status="empty")
        self.assertEqual(row["status"], "empty")
        self.assertNotIn("last_success", row)

    def test_error_is_separate_from_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("trendwatcher.ingestion.health.HEALTH_PATH", root / "health.json"), patch(
                "trendwatcher.ingestion.health.ARCHIVE_HEALTH_PATH", root / "archive.json"
            ):
                row = record_fetch(
                    "dead_source", fetched=0, accepted=0, rejected=0, error="timeout"
                )
        self.assertEqual(row["status"], "error")
        self.assertIn("timeout", row["last_error"])

    def test_unchanged_page_is_not_a_new_event(self):
        source = type("S", (), {"id": "nist_ai_rmf", "url": "https://example.test/rmf", "name": "NIST"})()
        page = "<html><title>AI RMF</title><body>same</body></html>"
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "page_watch.json"
            with patch("trendwatcher.ingestion.watch.STATE_PATH", state), patch(
                "trendwatcher.ingestion.watch.http_get",
                return_value=type("R", (), {"content": page.encode(), "text": page})(),
            ):
                first = watch_fetch(source)
                second = watch_fetch(source)
        self.assertEqual(first, [])
        self.assertEqual(second, [])


class TestQuoteCache(unittest.TestCase):
    def test_invented_quote_does_not_count(self):
        from trendwatcher.relevance.classifier import _quotes_match_source

        data = {"evidence_quotes": ["this sentence was not in the article at all"]}
        self.assertFalse(
            _quotes_match_source(data, "Prompt injection in Copilot", "The agent leaked a token")
        )


if __name__ == "__main__":
    unittest.main()
