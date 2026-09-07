"""Автотеги / новые тренды из заголовков."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from trendwatcher.enrichment.emerging import (
    clear_emerging_cache,
    discover_emerging_tags,
    load_emerging_tags,
    match_emerging_tags,
    save_emerging_tags,
)


def _doc(title: str, days_ago: int, now: datetime) -> SimpleNamespace:
    return SimpleNamespace(title=title, published_at=now - timedelta(days=days_ago))


class TestEmergingDiscovery(unittest.TestCase):
    def setUp(self):
        clear_emerging_cache()

    def tearDown(self):
        clear_emerging_cache()

    def test_discovers_repeated_new_phrase(self):
        now = datetime(2026, 9, 7)
        titles = [
            "New agent to agent protocol enables delegated credentials",
            "Vendors adopt agent to agent protocol for tool sharing",
            "Security review of the agent to agent protocol in production",
            "Introducing Claude Sonnet 5",
            "OpenAI released model X with 15% better coding benchmark",
        ]
        docs = [_doc(t, i, now) for i, t in enumerate(titles)]
        tags = discover_emerging_tags(docs, now=now, use_llm=False)
        slugs = {t["tag"] for t in tags}
        self.assertTrue(
            any("agent_to_agent" in s or "protocol" in s for s in slugs),
            msg=slugs,
        )
        self.assertNotIn("claude_sonnet", slugs)

    def test_skips_known_taxonomy_phrase(self):
        now = datetime(2026, 9, 7)
        docs = [
            _doc("Prompt injection against AI agents in production", i, now)
            for i in range(5)
        ]
        tags = discover_emerging_tags(docs, now=now, use_llm=False)
        self.assertNotIn("prompt_injection", {t["tag"] for t in tags})

    def test_overlay_roundtrip_and_extract(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "emerging_tags.json"
            save_emerging_tags(
                [
                    {
                        "tag": "agent_to_agent_protocol",
                        "label": "agent to agent protocol",
                        "patterns": [r"\bagent[- ]+to[- ]+agent[- ]+protocol\b"],
                        "category": "security",
                        "recent": 3,
                        "prior": 0,
                        "examples": [],
                        "source": "heuristic",
                    }
                ],
                path=path,
            )
            loaded = load_emerging_tags(path)
            self.assertEqual(loaded[0]["tag"], "agent_to_agent_protocol")
            clear_emerging_cache()
            # extract_tags uses default path; inject via save to default? use match with path
            found = match_emerging_tags(
                "Design of an agent to agent protocol for tools",
                path=path,
            )
            self.assertIn("agent_to_agent_protocol", found)

    def test_rejects_grammar_fragments_like_agents_can(self):
        now = datetime(2026, 9, 7)
        titles = [
            "From Overload to Insights: How AI Agents Can Support Scientists in Analyzing Complex Data",
            "AI agents can escape sandboxes without ever breaking them",
            "AgentForge proves AI agents can become persistent insider threats",
            "Why agents can take over your browser session",
            "Vendors adopt agent to agent protocol for tool sharing",
            "Security review of the agent to agent protocol in production",
            "New agent to agent protocol enables delegated credentials",
        ]
        docs = [_doc(t, i, now) for i, t in enumerate(titles)]
        tags = discover_emerging_tags(docs, now=now, use_llm=False)
        slugs = {t["tag"] for t in tags}
        self.assertNotIn("agents_can", slugs)
        self.assertFalse(any("_can" in s or s.endswith("can") for s in slugs), msg=slugs)
        self.assertTrue(
            any("agent_to_agent" in s or "protocol" in s for s in slugs),
            msg=slugs,
        )

    def test_load_drops_persisted_junk_slug(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "emerging_tags.json"
            path.write_text(
                '{"tags":[{"tag":"agents_can","label":"agents can","patterns":["\\\\bagents[- ]+can\\\\b"]},'
                '{"tag":"agent_to_agent_protocol","label":"agent to agent protocol",'
                '"patterns":["\\\\bagent[- ]+to[- ]+agent[- ]+protocol\\\\b"]}]}',
                encoding="utf-8",
            )
            loaded = load_emerging_tags(path)
            slugs = {t["tag"] for t in loaded}
            self.assertNotIn("agents_can", slugs)
            self.assertIn("agent_to_agent_protocol", slugs)


if __name__ == "__main__":
    unittest.main()
