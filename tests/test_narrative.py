"""Тесты гибридного обзора трендов (facts / template / LLM mock)."""

import unittest
from unittest.mock import MagicMock, patch

from trendwatcher.synthesis.facts import build_facts_pack
from trendwatcher.synthesis.narrative import (
    build_trend_brief,
    call_openai,
    facts_hash,
    render_template,
)


SAMPLE_SIGNALS = [
    {
        "tag": "self_evolving_agents",
        "recent": 62,
        "prior": 40,
        "velocity": 0.35,
        "velocity_source": "archive",
        "level": "research",
        "reason": "62 публ. за 3 мес., в основном research",
        "category": "ai_tech",
    },
    {
        "tag": "agentic_ai",
        "recent": 40,
        "prior": 30,
        "velocity": 0.2,
        "velocity_source": "archive",
        "level": "emerging",
        "reason": "рост доли",
        "category": "ai_tech",
    },
    {
        "tag": "prompt_injection",
        "recent": 80,
        "prior": 90,
        "velocity": -0.15,
        "velocity_source": "archive",
        "level": "declining",
        "reason": "доля упала",
        "category": "security",
    },
    {
        "tag": "agent_security",
        "recent": 45,
        "prior": 20,
        "velocity": 0.55,
        "velocity_source": "archive",
        "level": "strong",
        "reason": "45 публ., несколько типов источников",
        "category": "security",
    },
]

SAMPLE_EVENTS = [
    {
        "title": "Mako: A Self-Evolving Agentic OS",
        "url": "https://arxiv.org/abs/2607.11288",
        "source_name": "arXiv",
        "tags": ["self_evolving_agents", "agent_security"],
        "tbsf_score": 82,
    }
]

SAMPLE_FEED = [
    {
        "title": "OpenAI announces new safety evals",
        "url": "https://openai.com/index/safety",
        "source_type": "vendor",
        "source_name": "OpenAI News",
        "published_at": "2026-07-01T12:00:00",
        "tags": ["governance_regulation"],
    }
]


class TestFactsPack(unittest.TestCase):
    def test_facts_not_empty(self):
        facts = build_facts_pack(SAMPLE_SIGNALS, SAMPLE_EVENTS, SAMPLE_FEED)
        self.assertEqual(facts["window_weeks"], 13)
        self.assertTrue(facts["ai_tech_signals"])
        self.assertTrue(facts["security_signals"])
        self.assertTrue(facts["highlights"])
        self.assertTrue(facts["arxiv_papers"])
        self.assertTrue(facts["sources"])


class TestTemplate(unittest.TestCase):
    def test_template_paragraphs(self):
        facts = build_facts_pack(SAMPLE_SIGNALS, SAMPLE_EVENTS, SAMPLE_FEED)
        paragraphs = render_template(facts)
        self.assertGreaterEqual(len(paragraphs), 3)
        joined = " ".join(paragraphs)
        self.assertIn("3 месяца", joined)
        self.assertIn("self evolving agents", joined)
        self.assertIn("prompt injection", joined)


class TestBuildTrendBrief(unittest.TestCase):
    def test_template_without_key(self):
        brief = build_trend_brief(
            SAMPLE_SIGNALS,
            SAMPLE_EVENTS,
            SAMPLE_FEED,
            previous=None,
            api_key="",
            use_llm=True,
        )
        self.assertEqual(brief["mode"], "template")
        self.assertGreaterEqual(len(brief["paragraphs"]), 3)
        self.assertTrue(brief["facts_hash"])

    def test_cache_reuse(self):
        first = build_trend_brief(
            SAMPLE_SIGNALS,
            SAMPLE_EVENTS,
            SAMPLE_FEED,
            previous=None,
            api_key="",
        )
        cached = build_trend_brief(
            SAMPLE_SIGNALS,
            SAMPLE_EVENTS,
            SAMPLE_FEED,
            previous={
                **first,
                "paragraphs": ["cached a", "cached b", "cached c", "cached d"],
                "mode": "llm",
            },
            api_key="",
        )
        self.assertEqual(cached["paragraphs"][0], "cached a")
        self.assertEqual(cached["mode"], "llm")
        self.assertEqual(cached["facts_hash"], first["facts_hash"])

    @patch("trendwatcher.synthesis.narrative.httpx.Client")
    def test_llm_mode_with_mock(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": (
                            "Абзац один про AI тренды.\n\n"
                            "Абзац два про security.\n\n"
                            "Абзац три про новую тему.\n\n"
                            "Абзац четыре про зрелую угрозу."
                        )
                    }
                }
            ]
        }
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = False
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        brief = build_trend_brief(
            SAMPLE_SIGNALS,
            SAMPLE_EVENTS,
            SAMPLE_FEED,
            previous=None,
            api_key="sk-test",
            use_llm=True,
        )
        self.assertEqual(brief["mode"], "llm")
        self.assertEqual(len(brief["paragraphs"]), 4)
        self.assertIn("AI тренды", brief["paragraphs"][0])

    @patch("trendwatcher.synthesis.narrative.httpx.Client")
    def test_call_openai_direct(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "A.\n\nB.\n\nC.\n\nD."}}]
        }
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = False
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        facts = build_facts_pack(SAMPLE_SIGNALS, SAMPLE_EVENTS, SAMPLE_FEED)
        paras = call_openai(facts, "sk-test")
        self.assertEqual(paras, ["A.", "B.", "C.", "D."])
        self.assertEqual(len(facts_hash(facts)), 16)


if __name__ == "__main__":
    unittest.main()
