"""TBSF v3.2: stacking тем, консервативные штрафы, эвристики артефактов."""

import unittest
from datetime import date, timedelta

from trendwatcher.tbsf.scorer import DeterministicScorer, PaperInput, RepoInfo
from trendwatcher.tbsf.service import _repo_from_text, score_research_paper


class TestTopicStacking(unittest.TestCase):
    def setUp(self):
        self.scorer = DeterministicScorer()

    def test_hyphenated_coding_agent_matches(self):
        topic, vector, _, _, _ = self.scorer.score_topic(
            "IssueTrojanBench: Benchmarking AI Coding-Agents Against Malicious Issue Requests"
        )
        self.assertEqual(vector, "agent_security")
        self.assertGreaterEqual(topic, 21)

    def test_agent_and_prompt_stack(self):
        text = (
            "AI agent security: an agent hijacking attack via prompt injection "
            "and MCP tool attack leading to data exfiltration."
        )
        topic, vector, cyber, offensive, _ = self.scorer.score_topic(text)
        self.assertEqual(vector, "agent_security")
        self.assertTrue(offensive)
        self.assertGreaterEqual(topic, 33)
        self.assertLessEqual(topic, 35)

    def test_prompt_only_does_not_get_agent_base(self):
        topic, vector, _, _, _ = self.scorer.score_topic(
            "Indirect prompt injection against a chatbot, no agents involved."
        )
        self.assertEqual(vector, "prompt_mcp")
        self.assertLessEqual(topic, 15)

    def test_jailbreak_fallback_not_zero(self):
        topic, vector, _, _, _ = self.scorer.score_topic(
            "A new jailbreak and adversarial attacks benchmark for LLMs."
        )
        self.assertIsNotNone(vector)
        self.assertGreaterEqual(topic, 5)


class TestStrongPaperScore(unittest.TestCase):
    def test_priority_paper_reaches_80(self):
        from datetime import datetime

        published = datetime.combine(date.today() - timedelta(days=10), datetime.min.time())
        text = (
            "Stanford University. We study AI agent security: agent hijacking, "
            "agent sandbox escape and prompt injection against tool-using agents, "
            "including an MCP tool attack. The attack yields remote code execution "
            "and data exfiltration. Code is available at https://github.com/org/agent-poc "
            "under the MIT license, with requirements.txt and a reproduction guide. "
            "Our benchmark dataset has 2000 attack examples across injection, "
            "hijacking and exfiltration."
        )
        result = score_research_paper(
            "Agent Sandbox Escape via Prompt Injection",
            text,
            published_at=published,
        )
        self.assertGreaterEqual(result["tbsf_score"], 80)
        self.assertEqual(result["tbsf_level"], "🔴")
        self.assertEqual(result["tbsf_vector"], "agent_security")

    def test_arxiv_paper_is_not_unverifiable(self):
        scorer = DeterministicScorer()
        paper = PaperInput(
            title="Some LLM paper",
            text="A method for models.",
            venue_hint="arxiv",
        )
        self.assertEqual(scorer.score_author_heuristic(paper), 5)

    def test_dataset_without_repo(self):
        scorer = DeterministicScorer()
        score = scorer.score_dataset(
            None,
            "We release a benchmark of 1500 jailbreak attack examples.",
        )
        self.assertGreaterEqual(score, 7)

    def test_github_link_gives_code_points(self):
        repo = _repo_from_text(
            "Code is available at https://github.com/org/repo under the MIT license."
        )
        self.assertIsNotNone(repo)
        scorer = DeterministicScorer()
        self.assertGreaterEqual(scorer.score_code(repo), 10)
        self.assertGreaterEqual(scorer.score_license(repo, "MIT license"), 2)

    def test_no_license_penalty_on_inferred_repo(self):
        scorer = DeterministicScorer()
        repo = RepoInfo(has_py=True, has_readme=True, license=None)
        self.assertEqual(scorer.score_penalties(repo), 0)


if __name__ == "__main__":
    unittest.main()
