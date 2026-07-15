"""Фильтрация и валидация тегов таксономии."""

from .taxonomy import AI_TECH_TAGS, SECURITY_TAGS, TAXONOMY

# Ключевые AI-тренды для блока «Сигналы» (whitelist, не весь AI_TECH).
SIGNAL_AI_TAGS: frozenset[str] = frozenset(
    {"self_evolving_agents", "agentic_ai", "reasoning_models"}
)

# Теги, которые участвуют в блоке «Сигналы»: AI security + ключевые AI-тренды.
SIGNAL_TAGS: frozenset[str] = frozenset(SECURITY_TAGS) | SIGNAL_AI_TAGS

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
