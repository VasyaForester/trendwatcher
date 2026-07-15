"""Фильтрация и валидация тегов таксономии."""

from .taxonomy import AI_TECH_TAGS, SECURITY_TAGS, TAXONOMY

# Теги, которые участвуют в блоке «Сигналы» (только AI security, без общих AI-трендов).
SIGNAL_TAGS: frozenset[str] = frozenset(SECURITY_TAGS)

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
