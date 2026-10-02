"""Разметка ленты 2026-10-02: да/нет по 20 последним материалам."""

import unittest
from datetime import datetime
from types import SimpleNamespace

from trendwatcher.feed import _one_copy_per_story
from trendwatcher.relevance.editorial import editorial_reject_reason


def _keep(title, summary="", source="", url=""):
    return editorial_reject_reason(title, summary, source_name=source, url=url) is None


class TestLabeledFeed(unittest.TestCase):
    def test_user_labels(self):
        cases = [
            (True, "ThreatsDay: AI-Powered Zero-Day Chain, 543K Live Secrets, Model Inspection RCE and 13 More Stories", "This week, the useful words are boring ones.", "The Hacker News", ""),
            (True, "DeepKeep’s AI Lens flags coding agent data leaks and routes destructive commands for approval", "DeepKeep has announced AI Lens for Developers.", "Help Net Security", ""),
            (False, "AI Has Changed Attack Speed, Not Security Fundamentals", "As AI accelerates vulnerability discovery.", "SecurityWeek", ""),
            (True, "AI agent used Zammad zero-days to breach Dutch vulnerability disclosure non-profit", "An agentic AI-powered attack that hit DIVD.", "Help Net Security", ""),
            (True, "AI Agent Chains Zammad Zero-Days To Take Over DIVD Systems in Seconds", "DIVD was breached through two Zammad zero-days.", "Security Affairs", ""),
            (True, "CVE-2026-51871: Devika v1.0 is vulnerable to Code Injection", "execution of LLM-generated content", "NVD", "https://nvd.nist.gov/"),
            (False, "Show HN: WattzGOAT – an intentionally vulnerable web app for security training", "48 deliberately planted flags, simulated (rule-based, not a real model) AI assistant", "github.com", ""),
            (False, "Google: AI Is Changing the Pace and Profile of Vulnerability Discovery", "Google’s analysis found that AI-discovered vulnerabilities are more likely to enable remote code execution.", "SecurityWeek", ""),
            (False, "OWASP Top 10 for LLM Applications: Guide for Security Teams", "Explore the OWASP Top 10 for LLM applications.", "Reco Blog", "https://www.reco.ai/blog"),
            (False, "EchoLeak Vulnerability: CVE-2025-32711 Explained", "Understand the EchoLeak vulnerability.", "Reco Blog", ""),
            (False, "Unsloth Studio Flaw Turns Routine Model Inspection Into Code Execution", "malicious AI models execute arbitrary Python code", "Dark Reading", ""),
            (True, "Automated AI agent used to breach cybersecurity nonprofit DIVD", "AI-driven cyberattack", "BleepingComputer", ""),
            (False, "How we found 24 Android vulnerabilities using our open source AI security agent", "critical Android bugs", "GitHub Security Blog", ""),
            (True, "Show HN: OpenAPPA – open-source deterministic guardrails that don't break agents", "Guardrails should prevent the agent from leaking sensitive data.", "openappa.com", ""),
            (False, "Webinar: How to Govern AI Agents, Reduce Excessive Access, and Control Shadow AI", "Okta webinar", "The Hacker News", ""),
            (False, "CVE-2026-100863: Heym versions 0.0.90 and earlier contain two SSRF egress gaps", "LLM image-edit input loader fetched caller-controlled HTTP URLs", "NVD", ""),
            (False, "Prompt Injection in the Wild", "", "cybershujin.github.io", ""),
            (False, "AI Sandbox Escapes: Why Forensic Readiness Matters More Than Containment", "the same access-control failures", "Dark Reading", ""),
            (True, "AI-Powered CARBONATO Botnet Steals Credentials to Fund Its Own LLM Gateway", "CARBONATO exploits exposed Docker daemons, installs an AI agent", "Security Affairs", ""),
            (False, "Salesforce Indirect Prompt Injection Vulnerability Enables 0-click Data Exfiltration", "Salesforce Indirect Prompt Injection", "cybersecuritynews.com", "https://cybersecuritynews.com/salesforce-prompt-injection"),
        ]
        bad = []
        for expect, title, summary, source, url in cases:
            got = _keep(title, summary, source, url)
            if got != expect:
                bad.append((expect, got, title[:70]))
        self.assertEqual(bad, [])

    def test_salesforce_original_stays(self):
        self.assertIsNone(
            editorial_reject_reason(
                "Salesforce Indirect Prompt Injection Vulnerability Enables 0-click Data Exfiltration",
                "A poisoned record causes the agent to exfiltrate CRM data.",
                url="https://github.com/advisories/salesforce",
            )
        )

    def test_divd_collapsed_to_one(self):
        docs = [
            SimpleNamespace(title="AI agent used Zammad zero-days to breach DIVD", summary="DIVD", source_type="news", published_at=datetime(2026, 10, 1)),
            SimpleNamespace(title="AI Agent Chains Zammad Zero-Days To Take Over DIVD", summary="DIVD", source_type="news", published_at=datetime(2026, 10, 1, 8)),
            SimpleNamespace(title="Automated AI agent used to breach cybersecurity nonprofit DIVD", summary="DIVD", source_type="news", published_at=datetime(2026, 9, 29)),
        ]
        kept = _one_copy_per_story(docs)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].published_at, datetime(2026, 9, 29))


if __name__ == "__main__":
    unittest.main()
