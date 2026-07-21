"""Тесты строгого фильтра ленты и дедупликации."""

import json
import unittest
from pathlib import Path

from trendwatcher.enrichment.tagger import (
    extract_tags,
    is_ai_related,
    is_feed_relevant,
)
from trendwatcher.ingestion.dedup import normalize_url, title_fingerprint

ROOT = Path(__file__).resolve().parents[1]


class TestStrictRelevance(unittest.TestCase):
    def test_simon_style_generic_ai_rejected(self):
        text = (
            "Weeknotes: miscellaneous web tooling, a few thoughts on AI productivity, "
            "and updating my blog theme"
        )
        self.assertTrue(is_ai_related(text))
        self.assertFalse(is_feed_relevant(text))

    def test_prompt_injection_accepted(self):
        text = "New MemGhost attack plants false memories via prompt injection in AI agents"
        self.assertTrue(is_feed_relevant(text))
        self.assertIn("agent_security", extract_tags(text))

    def test_product_agentic_launch_rejected(self):
        text = "Expanding Managed Agents in Gemini API: background tasks, remote MCP and more"
        self.assertFalse(is_feed_relevant(text))

    def test_model_launch_rejected(self):
        text = "Introducing Claude Sonnet 5"
        self.assertFalse(is_feed_relevant(text))

    def test_bare_machine_learning_rejected(self):
        text = "Company improves machine learning pipeline for ad targeting"
        self.assertTrue(is_ai_related(text))
        self.assertFalse(is_feed_relevant(text))

    def test_cve_mcp_accepted(self):
        text = (
            "CVE-2026-46341: The Apify MCP server enables AI agents to extract data "
            "from websites using ready-made scrapers"
        )
        self.assertTrue(is_feed_relevant(text))

    def test_hf_disclosure_with_source(self):
        text = "Security incident disclosure — July 2026"
        self.assertTrue(is_feed_relevant(text, source_name="Hugging Face Blog"))

    def test_batch1_agreement(self):
        path = ROOT / "data" / "feed_labels_batch1.json"
        if not path.exists():
            self.skipTest("batch1 labels missing")
        batch = json.loads(path.read_text(encoding="utf-8"))
        items = batch["items"] if isinstance(batch, dict) else batch
        ok = 0
        mismatches = []
        for item in items:
            label = item.get("label")
            if label not in ("relevant", "irrelevant"):
                continue
            pred = is_feed_relevant(
                item["title"], item.get("tags") or [], source_name=item.get("source") or ""
            )
            want = label == "relevant"
            if pred == want:
                ok += 1
            else:
                mismatches.append((item["i"], label, pred, item["title"][:70]))
        total = sum(1 for i in items if i.get("label") in ("relevant", "irrelevant"))
        self.assertGreaterEqual(ok, 18, f"only {ok}/{total} match: {mismatches}")

    def test_tuxbot_llm_assisted_iot_rejected(self):
        text = "TuxBot v3 Evolution Shows Signs of LLM-Assisted IoT Botnet Development"
        self.assertFalse(is_feed_relevant(text))

    def test_llm_for_classic_vuln_remediation_rejected(self):
        text = "Remediating Vulnerabilities With LLMs: Inside Ivanti's Automation Push"
        self.assertFalse(is_feed_relevant(text))

    def test_weekly_recap_rejected(self):
        text = (
            "Weekly Recap: WordPress RCE, SonicWall 0-Days, AI Service Attacks, "
            "SharePoint 0-Day and More"
        )
        self.assertFalse(is_feed_relevant(text))

    def test_servicenow_rce_as_ai_platform_accepted(self):
        text = "ServiceNow’s sandbox escape RCE hole now exploited in the wild"
        self.assertTrue(is_feed_relevant(text))

    def test_howto_steps_rejected(self):
        text = "5 steps to secure your infrastructure in the frontier model era"
        self.assertFalse(is_feed_relevant(text))

    def test_vendor_product_ad_rejected(self):
        text = "Hardware-Rooted AI Security That Won't Slow You Down"
        self.assertFalse(is_feed_relevant(text))

    def test_monthly_security_digest_rejected(self):
        text = "This month in security with Tony Anscombe – May 2026 edition"
        self.assertFalse(is_feed_relevant(text))

    def test_agent_data_injection_accepted(self):
        text = "New Agent Data Injection Attack Can Make AI Agents Misclick or Run Attacker Commands"
        self.assertTrue(is_feed_relevant(text))

    def test_batch2_agreement(self):
        path = ROOT / "data" / "feed_labels_batch2.json"
        if not path.exists():
            self.skipTest("batch2 labels missing")
        batch = json.loads(path.read_text(encoding="utf-8"))
        items = batch["items"]
        ok = 0
        mismatches = []
        for item in items:
            label = item.get("label")
            if label not in ("relevant", "irrelevant"):
                continue
            pred = is_feed_relevant(
                item["title"], item.get("tags") or [], source_name=item.get("source") or ""
            )
            want = label == "relevant"
            if pred == want:
                ok += 1
            else:
                mismatches.append((item["i"], label, pred, item["title"][:70]))
        total = sum(1 for i in items if i.get("label") in ("relevant", "irrelevant"))
        self.assertEqual(ok, total, f"only {ok}/{total} match: {mismatches}")


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
