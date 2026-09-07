"""relevance-v2: gates, два пути ленты, gold precision."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from trendwatcher.relevance.classifier import classify, is_relevance_candidate
from trendwatcher.relevance.scorer import apply_gates
from trendwatcher.feed import _feed_eligible
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "tests" / "relevance" / "gold.jsonl"


class TestGates(unittest.TestCase):
    def test_security_gate(self):
        rel = apply_gates(
            ai_security=0.86,
            breakthrough=0.1,
            novelty=0.4,
            attack_surface=0.7,
            importance=0.6,
            evidence=0.8,
            reason="PI",
            attack_surfaces=["model.context"],
        )
        self.assertEqual(rel.relevance_class, "security")
        self.assertTrue(rel.in_feed())

    def test_breakthrough_needs_all_hard_gates(self):
        weak = apply_gates(
            ai_security=0.1,
            breakthrough=0.91,
            novelty=0.4,
            attack_surface=0.9,
            importance=0.9,
            evidence=0.5,
            reason="agentic framework",
            attack_surfaces=["agent.tools"],
        )
        self.assertFalse(weak.in_feed())
        strong = apply_gates(
            ai_security=0.1,
            breakthrough=0.88,
            novelty=0.86,
            attack_surface=0.9,
            importance=0.8,
            evidence=0.7,
            reason="MCP",
            attack_surfaces=["protocol.MCP"],
        )
        self.assertEqual(strong.relevance_class, "breakthrough")
        self.assertTrue(strong.in_feed())

    def test_interesting_llm_label_is_not_enough(self):
        rel = apply_gates(
            ai_security=0.2,
            breakthrough=0.79,
            novelty=0.9,
            attack_surface=0.9,
            importance=0.9,
            evidence=0.9,
            reason="interesting",
            attack_surfaces=["agent.tools"],
        )
        self.assertFalse(rel.in_feed())


class TestHeuristicPaths(unittest.TestCase):
    def test_model_launch_rejected(self):
        rel = classify("Introducing Claude Sonnet 5", "", use_llm=False)
        self.assertFalse(rel.in_feed())
        self.assertEqual(rel.relevance_class, "noise")

    def test_prompt_injection_security(self):
        rel = classify(
            "New MemGhost attack plants false memories via prompt injection in AI agents",
            use_llm=False,
        )
        self.assertTrue(rel.in_feed())
        self.assertEqual(rel.relevance_class, "security")

    def test_mcp_protocol_breakthrough(self):
        rel = classify(
            "Introducing the Model Context Protocol for connecting agents to arbitrary external tools",
            use_llm=False,
        )
        self.assertTrue(rel.in_feed())
        self.assertEqual(rel.relevance_class, "breakthrough")

    def test_another_agentic_framework_rejected(self):
        rel = classify("Another company launched an agentic framework", use_llm=False)
        self.assertFalse(rel.in_feed())

    def test_gemini_mcp_expansion_not_feed(self):
        rel = classify(
            "Expanding Managed Agents in Gemini API: background tasks, remote MCP and more",
            use_llm=False,
        )
        self.assertFalse(rel.in_feed())

    def test_benchmark_not_candidate(self):
        text = "OpenAI released model X with 15% better coding benchmark"
        self.assertFalse(is_relevance_candidate(text))


class TestTopStillFiltered(unittest.TestCase):
    def test_gpt5_launch(self):
        launch = SimpleNamespace(
            source_id="openai_news",
            doc_type="top",
            title="Introducing GPT-5",
            summary="A new flagship model",
            source_name="OpenAI News",
            tags=[],
        )
        self.assertFalse(_feed_eligible(launch))

    def test_hf_incident(self):
        incident = SimpleNamespace(
            source_id="openai_news",
            doc_type="top",
            title="The Hugging Face incident and the road ahead",
            summary="Models escaped containment during cybersecurity evaluation",
            source_name="OpenAI News",
            tags=["eval_containment_escape"],
        )
        self.assertTrue(_feed_eligible(incident))


class TestGoldSet(unittest.TestCase):
    def test_precision_on_noise_and_recall_on_labeled(self):
        rows = [
            json.loads(line)
            for line in GOLD.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        fp_noise = []
        miss_keep = []
        for row in rows:
            rel = classify(
                row["title"],
                row.get("summary") or "",
                source_name=row.get("source_name") or "",
                source_id=row.get("source_id") or "",
                use_llm=False,
            )
            expected = row["expected"]
            if expected == "noise" and rel.in_feed():
                fp_noise.append((row["title"][:70], rel.relevance_class, rel.reason))
            if expected in ("security", "breakthrough") and not rel.in_feed():
                miss_keep.append((row["title"][:70], rel.decision, rel.reason))
        self.assertEqual(fp_noise, [], msg=f"noise leaked into feed: {fp_noise}")
        # Precision first: можно пропустить 1–2 пограничных breakthrough.
        self.assertLessEqual(len(miss_keep), 3, msg=f"missed keepers: {miss_keep}")


if __name__ == "__main__":
    unittest.main()
