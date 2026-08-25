"""Тип новости: суть заголовка, не триггер-слова incident/attack."""

import unittest

from trendwatcher.enrichment.doc_type import classify_doc_type
from trendwatcher.enrichment.tagger import classify_doc_type as tagger_classify


class TestDocTypeEssence(unittest.TestCase):
    def test_user_examples_are_not_incidents(self):
        cases = [
            "How Databricks Uses AI to Accelerate Incident Investigation",
            "‘We are hitting a different chapter’: OpenAI leader warns of threat of ‘persistent’ AI cyber-attacks",
            "OpenAI Adds Controls That Should've Been There Already",
            "Wazuh and AI For Enhanced SOC Workflows",
            "I worked at OpenAI. Here are the guardrails we need now | Miles Brundage",
        ]
        for title in cases:
            self.assertEqual(classify_doc_type(title, "news"), "news", msg=title)

    def test_specific_cases_remain_incidents(self):
        cases = [
            "OpenAI says its AI models hacked Hugging Face during testing",
            "Investigating three real-world incidents in our cybersecurity evaluations",
            "Anthropic’s AI Claude escaped testing environment and hacked organizations",
            "Hugging Face confirms breach affected internal datasets and credentials",
            "Security incident disclosure — July 2026",
            "How an OpenAI safety test became a real-world cyberattack on the Hugging Face platform",
            "AI Agent Drives Espionage Attack on Thai Ministry of Finance",
            "Taiwan says it was hit by ‘abnormal’ AI-assisted cyber-attack",
        ]
        for title in cases:
            self.assertEqual(classify_doc_type(title, "news"), "incident", msg=title)

    def test_flaw_is_not_regulation(self):
        self.assertNotEqual(
            classify_doc_type("Critical flaw patched in popular JavaScript sandbox used in AI projects", "news"),
            "regulation",
        )
        self.assertEqual(
            classify_doc_type("Britain says it is open to AI regulation if voluntary safeguards fall short", "news"),
            "regulation",
        )

    def test_hypothetical_technique_is_not_incident(self):
        self.assertEqual(
            classify_doc_type(
                "New Cryptographic Context Injection Attack Could Let Web Pages Steal Grok Chat Data",
                "news",
            ),
            "news",
        )

    def test_launch_still_tool_release(self):
        self.assertEqual(
            classify_doc_type("Microsoft launches its first cybersecurity model", "news"),
            "tool_release",
        )
        self.assertNotEqual(
            classify_doc_type("CISA warns of hackers exploiting critical MLflow vulnerability", "news"),
            "tool_release",
        )

    def test_cve_and_research_unchanged(self):
        self.assertEqual(
            classify_doc_type("CVE-2026-54457: TensorZero LLMOps platform", "vulnerability"),
            "vulnerability",
        )
        self.assertEqual(classify_doc_type("Any title", "research"), "research")

    def test_tagger_reexports_classifier(self):
        self.assertIs(tagger_classify, classify_doc_type)


if __name__ == "__main__":
    unittest.main()
