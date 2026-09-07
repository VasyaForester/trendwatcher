"""Автотеги / новые тренды из заголовков."""

from __future__ import annotations

import json
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

    def test_rejects_products_skill_parts_and_vague_roles(self):
        now = datetime(2026, 9, 7)
        titles = [
            "Optimizing production agents with Amazon Bedrock AgentCore Observability",
            "Detecting silent agent failures with Amazon Bedrock AgentCore",
            "How Mobileye transformed support using Amazon Bedrock AgentCore",
            "SkillSight: Seeing Through Shared Descriptions for Accurate Skill Retrieval",
            "Field Aware Agent Skill Retrieval",
            "Calibrating Generic Content Bias for Skill Retrieval",
            "Deterministic Executability Gating for LLM Skill Selection at Scale",
            "Co-Evolving Skill Selection and Utilization via RL",
            "Emotion2Skill: Adaptive Skill Selection and Evolution",
            "Progressive Multimodal Search Agents for Visual Question Answering",
            "When Search Agents Should Ask: DiscoBench",
            "Provenance-Guided Credit Assignment for Deep Search Agents",
            "MCP Server Architecture Patterns for LLM-Integrated Applications",
            "The Apify MCP server enables AI agents to extract data",
            "Presenton bundles an MCP server for Docker deployments",
            "A Framework for Coding Agent Failures",
            "Safety Steering for Multi-Turn Coding Agent",
            "Restricting a Coding Agent to execute_code",
            "Learning Adaptive Memory Management for Long-Horizon Coding Agents",
            "Learned Adaptive Memory Management for LLM Agents",
            "Generalizable Long-Term Memory Management via RL",
            "Credit assignment for less-entangled long-horizon agents",
            "Proactive memory agent for long-horizon agents",
            "Turn-level reward assignment for long-horizon agents",
            "A tool-use agent for browser workflows",
            "Evaluating tool use agent reliability in production",
            "When a tool use agent should refuse a function call",
            "Routing agents through a shared memory pool",
            "How agents through multi-hop tools leak context",
            "Coordinating agents through an untrusted broker",
            "Policy optimization for agents on long-horizon tasks",
            "Credit in agents on long-horizon benchmarks",
            "Memory for agents on long-horizon trajectories",
            "A survey of agentic optimization methods",
            "Gradient-free agentic optimization for tool loops",
            "Benchmarks of agentic optimization in the wild",
            "The rise of agentic commerce checkout flows",
            "Fraud risks in agentic commerce platforms",
            "Payments for agentic commerce agents",
            "Managing agentic context windows at scale",
            "Compression of agentic context for long tasks",
            "A taxonomy of agentic context types",
            "Query planning over an agentic graph",
            "Security of the agentic graph representation",
            "Traversal attacks on an agentic graph",
            "A benchmark for agentic tool use",
            "New benchmark for agentic coding agents",
            "Revisiting the benchmark for agentic planners",
            "Vendors adopt agent to agent protocol for tool sharing",
            "Security review of the agent to agent protocol in production",
            "New agent to agent protocol enables delegated credentials",
        ]
        docs = [_doc(t, i, now) for i, t in enumerate(titles)]
        slugs = {t["tag"] for t in discover_emerging_tags(docs, now=now, use_llm=False)}
        banned = {
            "bedrock_agentcore",
            "skill_retrieval",
            "skill_selection",
            "search_agents",
            "mcp_server",
            "coding_agent",
            "memory_management",
            "agents_through",
            "long_horizon_agents",
            "tool_use_agent",
            "agents_on_long_horizon",
            "agentic_optimization",
            "agentic_commerce",
            "agentic_context",
            "agentic_graph",
            "benchmark_for_agentic",
        }
        self.assertTrue(banned.isdisjoint(slugs), msg=slugs)
        self.assertTrue(
            any("agent_to_agent" in s or "protocol" in s for s in slugs),
            msg=slugs,
        )

    def test_load_drops_persisted_junk_slug(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "emerging_tags.json"
            junk = [
                ("agents_can", "agents can"),
                ("bedrock_agentcore", "bedrock agentcore"),
                ("skill_retrieval", "skill retrieval"),
                ("skill_selection", "skill selection"),
                ("search_agents", "search agents"),
                ("mcp_server", "mcp server"),
                ("coding_agent", "coding agent"),
                ("memory_management", "memory management"),
                ("agents_through", "agents through"),
                ("long_horizon_agents", "long-horizon agents"),
                ("tool_use_agent", "tool use agent"),
                ("agents_on_long_horizon", "agents on long-horizon"),
                ("agentic_optimization", "agentic optimization"),
                ("agentic_commerce", "agentic commerce"),
                ("agentic_context", "agentic context"),
                ("agentic_graph", "agentic graph"),
                ("benchmark_for_agentic", "benchmark for agentic"),
            ]
            tags = [
                {
                    "tag": slug,
                    "label": label,
                    "patterns": [rf"\\b{label.replace(' ', '[- ]+')}\\b"],
                }
                for slug, label in junk
            ]
            tags.append(
                {
                    "tag": "agent_to_agent_protocol",
                    "label": "agent to agent protocol",
                    "patterns": [r"\bagent[- ]+to[- ]+agent[- ]+protocol\b"],
                }
            )
            path.write_text(
                json.dumps({"tags": tags}),
                encoding="utf-8",
            )
            loaded = load_emerging_tags(path)
            slugs = {t["tag"] for t in loaded}
            self.assertEqual(slugs, {"agent_to_agent_protocol"})


if __name__ == "__main__":
    unittest.main()
