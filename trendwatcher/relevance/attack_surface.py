"""Таксономия поверхностей атаки и эвристика attack_surface_delta."""

from __future__ import annotations

import re

# tag → поверхность (PLAN / recommendation §15)
TAG_TO_SURFACE: dict[str, str] = {
    "prompt_injection": "model.context",
    "indirect_prompt_injection": "model.context",
    "jailbreak": "model.system_prompt",
    "guardrails_defense": "model.system_prompt",
    "inference_integrity": "model.inference",
    "model_theft": "model.weights",
    "model_drift": "model.fine_tuning",
    "data_poisoning": "data.training_data",
    "rag_security": "data.RAG",
    "agent_memory_security": "data.memory",
    "model_context_poisoning": "data.memory",
    "long_context_memory": "data.memory",
    "agent_security": "agent.autonomy",
    "agent_permissions": "agent.permissions",
    "agent_identity_trust": "agent.identity",
    "agent_swarm_security": "agent.delegation",
    "self_evolving_agents": "agent.autonomy",
    "agentic_skill_security": "agent.tools",
    "tool_calling_security": "agent.tools",
    "computer_use_agents": "execution.browser",
    "mcp_security": "protocol.MCP",
    "agent_harness": "protocol.tool_protocols",
    "multimodal_injection": "multimodal.image",
    "model_supply_chain": "supply_chain.models",
    "eval_containment_escape": "execution.sandbox",
    "autonomous_cyber_offense": "execution.shell",
    "ai_codegen_security": "execution.code_execution",
    "data_exfiltration": "agent.credentials",
}

# Что технология даёт атакующему — не «это AI?».
_SURFACE_DELTA: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"self[- ]replicat|spawn(s|ing)? (other )?agents|rewrite its own tools", re.I), 1.00, "agent.autonomy"),
    (re.compile(r"modify (its )?own (system )?prompt|rewrite.{0,20}system prompt", re.I), 0.95, "model.system_prompt"),
    (re.compile(r"model context protocol|\bmcp\b.{0,40}(protocol|standard|launch|introduc)", re.I), 0.95, "protocol.MCP"),
    (re.compile(r"agent[- ]to[- ]agent|\ba2a\b|multi[- ]agent (protocol|communication)", re.I), 0.85, "protocol.A2A"),
    (re.compile(r"autonomous(ly)? (acquire|steal) credentials|credential.{0,20}agent", re.I), 0.90, "agent.credentials"),
    (re.compile(r"agent.{0,40}(shell|arbitrary (code|command))|(shell|root) access.{0,40}agent", re.I), 0.80, "execution.shell"),
    (re.compile(r"computer[- ]use|browser agent|gui agent", re.I), 0.65, "execution.browser"),
    (re.compile(r"persistent (agent )?memory|agent memory architecture", re.I), 0.75, "data.memory"),
    (re.compile(r"delegate.{0,30}(other )?agents|spawn.{0,20}agents", re.I), 0.80, "agent.delegation"),
    (re.compile(r"arbitrary external tools|invoke arbitrary", re.I), 0.85, "agent.tools"),
    (re.compile(r"modify production infrastructure|write access to external", re.I), 0.85, "execution.cloud"),
    (re.compile(r"continuous learning.{0,30}agent|self[- ]modif", re.I), 0.80, "agent.autonomy"),
    (re.compile(r"sandbox escape|escaped? containment", re.I), 0.90, "execution.sandbox"),
    (re.compile(r"prompt injection|jailbreak|indirect prompt", re.I), 0.70, "model.context"),
]


def surfaces_from_tags(tags: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for tag in tags or []:
        surf = TAG_TO_SURFACE.get(tag)
        if surf and surf not in seen:
            seen.add(surf)
            out.append(surf)
    return out


def attack_surface_delta(text: str, tags: list[str] | None = None) -> tuple[float, list[str], str]:
    """Возвращает (delta 0–1, поверхности, короткая причина)."""
    surfaces = surfaces_from_tags(tags)
    best = 0.0
    reason = ""
    extra: list[str] = []
    for rx, delta, surf in _SURFACE_DELTA:
        if rx.search(text or ""):
            if delta > best:
                best = delta
                reason = surf
            if surf not in extra:
                extra.append(surf)
    for surf in extra:
        if surf not in surfaces:
            surfaces.append(surf)
    if best == 0.0 and surfaces:
        best = 0.45
        reason = surfaces[0]
    return round(min(best, 1.0), 2), surfaces, reason
