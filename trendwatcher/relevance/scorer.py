"""Формула и hard gates: security vs breakthrough. Precision > recall."""

from __future__ import annotations

from .schema import Relevance

SECURITY_GATE = 0.65
BT_BREAKTHROUGH = 0.80
BT_NOVELTY = 0.75
BT_SURFACE = 0.70
BT_IMPORTANCE = 0.70


def security_combo(
    security: float,
    evidence: float,
    attack_surface: float,
    importance: float,
    novelty: float,
) -> float:
    return (
        0.45 * security
        + 0.20 * evidence
        + 0.15 * attack_surface
        + 0.10 * importance
        + 0.10 * novelty
    )


def breakthrough_combo(
    breakthrough: float,
    attack_surface: float,
    novelty: float,
    importance: float,
    evidence: float,
) -> float:
    return (
        0.30 * breakthrough
        + 0.25 * attack_surface
        + 0.20 * novelty
        + 0.15 * importance
        + 0.10 * evidence
    )


def apply_gates(
    *,
    ai_security: float,
    breakthrough: float,
    novelty: float,
    attack_surface: float,
    importance: float,
    evidence: float,
    reason: str,
    attack_surfaces: list[str],
    source: str = "heuristic",
) -> Relevance:
    sec_c = security_combo(ai_security, evidence, attack_surface, importance, novelty)
    bt_c = breakthrough_combo(breakthrough, attack_surface, novelty, importance, evidence)

    if ai_security >= SECURITY_GATE:
        decision = "signal" if ai_security >= 0.90 and attack_surface >= 0.70 else "feed"
        return Relevance(
            relevance_class="security",
            decision=decision,
            relevance_score=int(round(min(sec_c, 1.0) * 100)),
            ai_security=ai_security,
            breakthrough=breakthrough,
            novelty=novelty,
            attack_surface=attack_surface,
            importance=importance,
            evidence=evidence,
            reason=reason or "AI-specific security event",
            attack_surfaces=attack_surfaces,
            path="security",
            source=source,
        )

    if (
        breakthrough >= BT_BREAKTHROUGH
        and novelty >= BT_NOVELTY
        and attack_surface >= BT_SURFACE
        and importance >= BT_IMPORTANCE
    ):
        decision = "signal" if novelty >= 0.85 and attack_surface >= 0.85 else "feed"
        return Relevance(
            relevance_class="breakthrough",
            decision=decision,
            relevance_score=int(round(min(bt_c, 1.0) * 100)),
            ai_security=ai_security,
            breakthrough=breakthrough,
            novelty=novelty,
            attack_surface=attack_surface,
            importance=importance,
            evidence=evidence,
            reason=reason or "New capability changes a future AI attack surface",
            attack_surfaces=attack_surfaces,
            path="breakthrough",
            source=source,
        )

    if breakthrough >= 0.55 and attack_surface >= 0.55:
        return Relevance(
            relevance_class="breakthrough",
            decision="queue",
            relevance_score=int(round(min(bt_c, 1.0) * 100)),
            ai_security=ai_security,
            breakthrough=breakthrough,
            novelty=novelty,
            attack_surface=attack_surface,
            importance=importance,
            evidence=evidence,
            reason=reason or "Possible new surface, not enough novelty/evidence",
            attack_surfaces=attack_surfaces,
            path="breakthrough",
            source=source,
        )

    return Relevance(
        relevance_class="noise",
        decision="reject",
        relevance_score=int(round(min(max(sec_c, bt_c), 1.0) * 100)),
        ai_security=ai_security,
        breakthrough=breakthrough,
        novelty=novelty,
        attack_surface=attack_surface,
        importance=importance,
        evidence=evidence,
        reason=reason or "Ordinary AI news or incremental capability",
        attack_surfaces=attack_surfaces,
        path="none",
        source=source,
    )
