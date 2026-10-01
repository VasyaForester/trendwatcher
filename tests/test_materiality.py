"""Concreteness gate: конкретное изменение проходит, обзор — нет."""

import unittest

from trendwatcher.relevance.classifier import classify
from trendwatcher.relevance.materiality import assess


POSITIVE = [
    (
        "real AI incident",
        "On 12 March 2026 OpenAI disclosed a security incident: models escaped containment during a cyber evaluation and accessed another tenant.",
    ),
    (
        "agent vulnerability",
        "Researchers disclosed a vulnerability in Cursor's coding agent: a malicious rule file executes commands. Affected versions 0.45-0.48. PoC published.",
    ),
    (
        "prompt injection poc",
        "Researchers demonstrated that a poisoned MCP tool description causes Agent X to exfiltrate API credentials despite guardrail Y.",
    ),
    (
        "mcp research",
        "New MCP security research shows a tool poisoning attack that bypasses the server allowlist. Proof of concept published.",
    ),
    (
        "dasf",
        "DASF 3.0 adds an Agentic AI component with 35 new agentic risks and 6 mitigation controls.",
    ),
    (
        "owasp",
        "OWASP GenAI Security Project released the Agent Control Standard, adding new controls for tool trust.",
    ),
    (
        "benchmark",
        "Frontier model X autonomously discovered 12 previously unknown vulnerabilities on the cyber benchmark, a jump versus the prior model.",
    ),
    (
        "eu ai act",
        "The European Commission adopted an implementing act under the EU AI Act setting security logging requirements.",
    ),
]

NEGATIVE = [
    "Prompt injection is still the biggest threat to AI agents.",
    "The top 10 AI security risks for 2026",
    "What is AI security?",
    "Why AI security matters for every enterprise",
    "The future of AI security",
    "5 ways to secure your AI",
    "Why businesses need AI security",
    "AI is changing cybersecurity",
    "Company raised $100m to build AI security",
    "Company partnered with X to advance AI security",
    "Company released a new LLM",
    "Conference recap: thoughts on agentic AI security",
    "AI agents are becoming more common",
    "MCP is becoming popular",
    "Company says agents are transforming enterprise security",
]


class TestMaterialityExamples(unittest.TestCase):
    def test_positive_examples_pass(self):
        failed = []
        for name, text in POSITIVE:
            verdict = assess(text, role="expert")
            if not verdict.accept:
                failed.append((name, verdict.topic_relevance, verdict.concreteness, verdict.reason))
        self.assertEqual(failed, [])

    def test_negative_examples_do_not_enter_feed(self):
        leaked = []
        for text in NEGATIVE:
            rel = classify(text, use_llm=False)
            if rel.in_feed() or assess(text, role="expert").accept:
                leaked.append(text)
        self.assertEqual(leaked, [])

    def test_discovery_is_stricter_than_primary(self):
        text = "DASF 3.0 adds an Agentic AI component"
        self.assertTrue(assess(text, role="primary").accept)
        self.assertFalse(assess(text, role="discovery").accept)


if __name__ == "__main__":
    unittest.main()
