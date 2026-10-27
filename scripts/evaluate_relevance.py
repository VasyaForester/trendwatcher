"""Precision/recall на tests/relevance/gold.jsonl и решения раннего triage.

Метки gold не изменяются. Предсказания LLM не считаются истиной.
Классификатор вызывается с use_llm=False.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from trendwatcher.relevance.classifier import classify
from trendwatcher.relevance.triage import triage_document

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "tests" / "relevance" / "gold.jsonl"


def _load() -> list[dict]:
    rows = []
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _prf(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def evaluate() -> dict:
    rows = _load()
    by_class = defaultdict(lambda: {"hit": 0, "miss": 0})
    tp = fp = fn = tn = 0
    triage_drop = []
    for row in rows:
        expected = row.get("expected") or ""
        positive = expected in {"security", "breakthrough"}
        result = classify(
            row.get("title") or "",
            row.get("summary") or "",
            source_name=row.get("source_name") or "",
            source_id=row.get("source_id") or "",
            use_llm=False,
        )
        predicted = result.in_feed()
        if positive and predicted:
            tp += 1
            by_class[expected]["hit"] += 1
        elif positive and not predicted:
            fn += 1
            by_class[expected]["miss"] += 1
        elif not positive and predicted:
            fp += 1
            by_class[expected]["miss"] += 1
        else:
            tn += 1
            by_class[expected]["hit"] += 1
        decision, reason = triage_document(
            f"{row.get('title') or ''}\n{row.get('summary') or ''}",
            role=row.get("role") or "expert",
            source_name=row.get("source_name") or "",
            source_id=row.get("source_id") or "",
            filter_ai=True,
        )
        if positive and decision == "reject":
            triage_drop.append({"title": row.get("title"), "reason": reason, "expected": expected})
    per_class = {}
    for name, bucket in sorted(by_class.items()):
        total = bucket["hit"] + bucket["miss"]
        per_class[name] = {
            "n": total,
            "correct": bucket["hit"],
            "recall_or_specificity": round(bucket["hit"] / total, 3) if total else 0.0,
        }
    return {
        "n": len(rows),
        "classifier": _prf(tp, fp, fn),
        "tn": tn,
        "by_expected": per_class,
        "triage_false_rejects": triage_drop,
    }


def main() -> None:
    report = evaluate()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
