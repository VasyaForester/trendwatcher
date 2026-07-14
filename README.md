# TrendWatcher

Агент мониторинга трендов **AI Security**: собирает публикации (инциденты, уязвимости, исследования, регуляторика, новости), находит паттерны и показывает дашборд — топ arXiv по TBSF, сигналы по темам, ленту новостей, графики.

**Сайт:** [aitrendwatcher.ru](http://aitrendwatcher.ru) — данные подтягиваются из `data.json` в этом репозитории (обновление раз в сутки через GitHub Actions).

План развития — в [PLAN.md](PLAN.md).

## Дашборд

| Блок | Что показывает |
|------|----------------|
| **Топ событий** | Только arXiv, сортировка по **TBSF** (убывание). Оценка по полному тексту статьи (HTML/PDF), не только abstract. |
| **Сигналы** | Динамика тегов за 4 нед. vs prior по **доле в корпусе** (замороженный архив). Можно скрыть нерелевантные (×, двойной клик) — только в вашем браузере. |
| **Динамика тем** | График топ-7 тегов за 13 недель. |
| **Лента** | Новости, CVE, инциденты, блоги — **без arXiv**, по дате (новые сверху). |

## Быстрый старт

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

# Собрать данные (arXiv, NVD, RSS) → data/trendwatcher.db
.venv\Scripts\python run.py ingest

# Локальный дашборд с живыми данными
.venv\Scripts\python run.py serve
# → http://127.0.0.1:8000
```

## Команды CLI

```powershell
.venv\Scripts\python run.py ingest       # сбор из источников (config/sources.yaml)
.venv\Scripts\python run.py retag        # переразметка тегов (без загрузки full-text arXiv)
.venv\Scripts\python run.py score-tbsf   # TBSF для research; full-text — инкрементально (~100/прогон)
.venv\Scripts\python run.py archive      # недельные снимки + documents.jsonl в data/archive/
.venv\Scripts\python run.py export       # dist/site/index.html + data.json + zip
.venv\Scripts\python run.py export-site  # только index.html для хостинга (данные с GitHub)
.venv\Scripts\python run.py analyze      # JSON: top_events + signals в stdout
.venv\Scripts\python run.py serve        # FastAPI + статика web/
```

## Деплой на хостинг

1. **Данные** — автоматически: workflow [`.github/workflows/update-data.yml`](.github/workflows/update-data.yml) каждый день делает `ingest` → `score-tbsf` → `export` → push `data.json`, `data/trendwatcher.db`, `data/archive/`.
2. **Вёрстка** — вручную, когда меняется `web/index.html`:

```powershell
.venv\Scripts\python run.py export-site
# загрузить dist/site/index.html в корень сайта на хостинге
```

В `web/index.html` задан `DATA_URL` на raw GitHub — после push данных сайт обновляется без перезаливки HTML.

## Структура проекта

```
config/
  sources.yaml          # RSS, arXiv, NVD — добавление источников без кода
  tbsf/                 # рубрика TBSF (синхрон с проектом TBSF)
data/
  trendwatcher.db       # SQLite-корпус
  archive/              # weekly_stats.json + documents.jsonl (immutable baseline для трендов)
  data.json             # снапшот для статического сайта
trendwatcher/
  ingestion/            # RSS, arXiv API, NVD 2.0, дедупликация
  enrichment/           # rule-based теги AI security / AI tech
  tbsf/                 # TBSF v1.1 для arXiv (🔴/🟡/⚪, full-text fetch)
  analytics/            # временные ряды, сигналы, архив, топ событий
  feed.py               # лента новостей (без research)
  api/                  # FastAPI
  export.py             # сборка data.json
web/
  index.html            # дашборд (Chart.js)
run.py                  # CLI
```

## Источники (MVP)

arXiv (security + general AI), NVD (CVE по AI), The Hacker News, BleepingComputer, Simon Willison, Schneier, Google Security Blog, OpenAI News, NIST News. CISA RSS — 403, в работе.

## TBSF

Research-статьи оцениваются **Threat-based Security Scoring Framework** (0–100%, уровни 🔴 Priority / 🟡 Reserve / ⚪ Low). Конфиг: `config/tbsf/`. Полный текст arXiv кэшируется в БД (`full_text`); за один прогон загружается до 100 новых статей.

## Архив и velocity

Чтобы избежать нереалистичных +1000% из-за догрузки старых статей в БД, каждую завершённую неделю фиксируем снимок в `data/archive/weekly_stats.json`. Сигналы сравнивают **долю тега в корпусе**, не сырые счётчики; в UI потолок ±300%.

## Статус

**Работает:** ingestion, rule-based теги, TBSF + full-text arXiv, топ/лента/сигналы, frozen archive, GitHub Actions, статический сайт.

**Дальше по [PLAN.md](PLAN.md):** LLM-обогащение и claims, PDF-квартальный отчёт, больше источников (AIID, GHSA, HN Algolia), кластеризация эмбеддингов, Postgres/pgvector.
