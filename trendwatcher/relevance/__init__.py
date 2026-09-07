"""Релевантность ленты: tagging ≠ «должно ли это быть в ленте?»."""

from .classifier import classify, classify_document, is_relevance_candidate
from .schema import Relevance

__all__ = [
    "Relevance",
    "classify",
    "classify_document",
    "is_relevance_candidate",
]
