# TrendWatcher

Агент мониторинга трендов AI Security: собирает публикации (инциденты, уязвимости,
исследования, фреймворки, регуляторика, новости), находит паттерны и показывает
дашборды — топ событий, динамику тем, сигналы. План развития — в [PLAN.md](PLAN.md).

## Быстрый старт

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

# 1. Собрать данные из источников (arXiv, NVD, RSS-ленты) в data/trendwatcher.db
.venv\Scripts\python run.py ingest

# 2. Запустить веб-дашборд на http://127.0.0.1:8000
.venv\Scripts\python run.py serve

# Опционально: аналитический срез в JSON (топ событий + сигналы)
.venv\Scripts\python run.py analyze

# Статический экспорт для хостинга без Python (GitHub Pages, S3, nginx):
# собирает dist/site (index.html + data.json) и zip-архив в dist/
.venv\Scripts\python run.py export
```

## Структура

- `config/sources.yaml` — декларативный конфиг источников (добавление без кода)
- `trendwatcher/ingestion/` — коннекторы (RSS, arXiv API, NVD API 2.0) + дедупликация
- `trendwatcher/enrichment/` — таксономия AI security (OWASP LLM Top 10 / MITRE ATLAS),
  разметка тегов, типов, сущностей и severity
- `trendwatcher/analytics/` — временные ряды, velocity, сигналы (weak/emerging/strong),
  скоринг топ-событий с корроборацией между источниками
- `trendwatcher/api/` — FastAPI (`/api/stats`, `/api/top-events`, `/api/trends`,
  `/api/signals`, `/api/feed`)
- `web/` — дашборд (статический, Chart.js)

## Статус

MVP (этапы 0–3 плана): rule-based обогащение, SQLite. Дальше по плану: LLM-обогащение
с claims, кластеризация эмбеддингов, PDF-отчет за квартал, больше источников.
