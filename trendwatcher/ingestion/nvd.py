"""Коннектор NVD API 2.0 — CVE по ключевым словам AI-продуктов."""

import time
from datetime import timedelta

from dateutil import parser as dateparser

from ..config import SourceConfig
from ..db import utcnow
from .common import http_get, to_naive_utc

API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"


def _cvss_score(cve: dict) -> float | None:
    metrics = cve.get("metrics", {})
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        entries = metrics.get(key)
        if entries:
            return entries[0].get("cvssData", {}).get("baseScore")
    return None


def fetch(source: SourceConfig) -> list[dict]:
    end = utcnow()
    start = end - timedelta(days=min(source.days_back, 120))
    fmt = "%Y-%m-%dT%H:%M:%S.000"
    items: dict[str, dict] = {}

    for i, keyword in enumerate(source.keywords):
        if i > 0:
            time.sleep(7)  # лимит NVD без API-ключа: 5 запросов / 30 секунд
        resp = http_get(
            API_URL,
            params={
                "keywordSearch": keyword,
                "pubStartDate": start.strftime(fmt),
                "pubEndDate": end.strftime(fmt),
                "resultsPerPage": 500,
            },
            timeout=60.0,
        )
        for vuln in resp.json().get("vulnerabilities", []):
            cve = vuln.get("cve", {})
            cve_id = cve.get("id")
            if not cve_id or cve_id in items:
                continue
            descriptions = cve.get("descriptions", [])
            desc = next(
                (d["value"] for d in descriptions if d.get("lang") == "en"),
                descriptions[0]["value"] if descriptions else "",
            )
            published = to_naive_utc(dateparser.parse(cve.get("published")))
            score = _cvss_score(cve)
            title = f"{cve_id}: {desc[:120]}"
            items[cve_id] = {
                "url": f"https://nvd.nist.gov/vuln/detail/{cve_id}",
                "title": title,
                "summary": desc[:4000],
                "published_at": published,
                "cvss": score,
            }
    return list(items.values())
