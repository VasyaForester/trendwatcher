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

# Переразметка + TBSF для всех research-документов
.venv\Scripts\python run.py retag

# Только TBSF-оценка arXiv (без ingest)
.venv\Scripts\python run.py score-tbsf

# Статический экспорт для хостинга без Python (GitHub Pages, S3, nginx):
# собирает dist/site (index.html + data.json) и zip-архив в dist/
.venv\Scripts\python run.py export
```

## Структура

- `config/sources.yaml` — декларативный конфиг источников (добавление без кода)
- `trendwatcher/ingestion/` — коннекторы (RSS, arXiv API, NVD API 2.0) + дедупликация
- `trendwatcher/tbsf/` — **TBSF v1.1** (Threat-based Security Scoring Framework): оценка arXiv-статей 0–100%, уровни 🔴/🟡/⚪ вместо звёзд
- `config/tbsf/` — рубрика, topic vectors, keywords (синхронизируется с проектом TBSF)
- `trendwatcher/analytics/` — временные ряды, velocity, сигналы (weak/emerging/strong),
  скоринг топ-событий с корроборацией между источниками
- `trendwatcher/api/` — FastAPI (`/api/stats`, `/api/top-events`, `/api/trends`,
  `/api/signals`, `/api/feed`)
- `web/` — дашборд (статический, Chart.js)

## Статус

MVP (этапы 0–3 плана): rule-based обогащение, SQLite. Дальше по плану: LLM-обогащение
с claims, кластеризация эмбеддингов, PDF-отчет за квартал, больше источников.
