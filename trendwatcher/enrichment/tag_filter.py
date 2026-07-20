"""Фильтрация и валидация тегов таксономии."""

from .taxonomy import AI_TECH_TAGS, SECURITY_TAGS, TAXONOMY

# AI-тренды, которые показываем в блоке «Сигналы» (по разметке пользователя).
SIGNAL_AI_TAGS: frozenset[str] = frozenset(
    {
        "self_evolving_agents",
        "computer_use_agents",
        "long_context_memory",
    }
)

# Явный whitelist сигналов: AI security + выбранные breakthrough-темы.
# Остальные теги таксономии остаются для обогащения/ленты, но не в панели сигналов.
SIGNAL_TAGS: frozenset[str] = frozenset(
    {
        # security (keep)
        "prompt_injection",
        "jailbreak",
        "agent_security",
        "mcp_security",
        "rag_security",
        "model_supply_chain",
        "data_poisoning",
        "red_teaming",
        "guardrails_defense",
        "governance_regulation",
        "data_exfiltration",
        "model_theft",
        "model_drift",
        "agent_identity_trust",
        "agent_permissions",
        "agent_swarm_security",
        "inference_integrity",
        # security (new)
        "indirect_prompt_injection",
        "model_context_poisoning",
        "multimodal_injection",
        "agent_memory_security",
        "tool_calling_security",
        "ai_codegen_security",
        "autonomous_cyber_offense",
    }
) | SIGNAL_AI_TAGS

# График 1 — общие темы (разметка о/с).
TREND_CHART_GENERAL: frozenset[str] = frozenset(
    {
        "jailbreak",
        "prompt_injection",
        "agent_security",
        "mcp_security",
        "guardrails_defense",
        "indirect_prompt_injection",
        "data_poisoning",
        "red_teaming",
        "governance_regulation",
        "data_exfiltration",
    }
)

# График 2 — специальные / новые (разметка о/с).
TREND_CHART_SPECIAL: frozenset[str] = frozenset(
    {
        "self_evolving_agents",
        "agent_swarm_security",
        "computer_use_agents",
        "rag_security",
        "model_theft",
        "model_supply_chain",
        "model_drift",
        "agent_identity_trust",
        "agent_permissions",
        "inference_integrity",
        "long_context_memory",
        "agent_memory_security",
        "tool_calling_security",
        "ai_codegen_security",
        "autonomous_cyber_offense",
        "model_context_poisoning",
        "multimodal_injection",
    }
)

# Явный whitelist — только ключи из TAXONOMY (защита от мусора в будущем).
ALL_TAXONOMY_TAGS: frozenset[str] = frozenset(TAXONOMY)


def normalize_tags(tags: list[str]) -> list[str]:
    """Оставляет только известные теги таксономии, без дубликатов, стабильный порядок."""
    seen: set[str] = set()
    out: list[str] = []
    for tag in tags:
        if tag in ALL_TAXONOMY_TAGS and tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def is_signal_tag(tag: str) -> bool:
    return tag in SIGNAL_TAGS


def is_security_tag(tag: str) -> bool:
    return tag in SECURITY_TAGS


def is_ai_tech_tag(tag: str) -> bool:
    return tag in AI_TECH_TAGS
