# Architecture — Finance Alerts SaaS

## 1. Design Principles

- **Minimal surface area:** Each module does one thing. No shared mutable state between layers.
- **Async-safe:** All I/O (DB, HTTP, Redis) runs through async-compatible paths or Celery workers.
- **Config-driven:** Sources, thresholds, channel routing are YAML/env — no code change needed.
- **Fail-safe delivery:** Every notification attempt is logged; retries are automatic.
- **Horizontal scale path:** Worker pool scales independently of API; beat scheduler is single-node.

---

## 2. High-Level Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        EXTERNAL WORLD                           │
│   RSS Feeds  │  Scraped Sites  │  Telegram API  │  Stripe API   │
└──────┬───────┴────────┬────────┴───────┬─────────┴──────┬───────┘
       │                │                │                 │
       ▼                ▼                ▼                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                        DOCKER COMPOSE                            │
│                                                                  │
│  ┌──────────┐   ┌──────────────────────────────────────────┐    │
│  │  beat    │   │              worker (Celery)              │    │
│  │scheduler │──▶│  ingest │ normalize │ score │ dedupe │   │    │
│  └──────────┘   │                              notify       │    │
│                 └──────────────────────┬─────────────────────    │
│                                        │                         │
│  ┌─────────────┐        ┌─────────────▼──────────┐              │
│  │    api      │        │        postgres          │              │
│  │  (FastAPI)  │◀──────▶│  sources │ articles     │              │
│  └─────────────┘        │  signals │ deliveries   │              │
│                         │  users   │ subscriptions│              │
│  ┌─────────────┐        └──────────────────────────              │
│  │    redis    │◀───────────────────────────────────             │
│  │  (broker +  │        (Celery broker + result backend)         │
│  │   cache)    │                                                  │
│  └─────────────┘                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Service Definitions

### 3.1 `beat` — Scheduler
- **Image:** Same as `worker` (Celery beat mode)
- **Role:** Fires periodic tasks on schedule
- **Key tasks:**
  - `fetch_all_sources` → every 5 minutes
  - `retry_failed_deliveries` → every 10 minutes
  - `cleanup_old_articles` → daily at 03:00 UTC
- **Singleton:** Always exactly 1 instance (no horizontal scale)

### 3.2 `worker` — Celery Worker
- **Image:** Python 3.12 + app code
- **Role:** Executes all background jobs (ingest, score, notify)
- **Concurrency:** 4 threads per container (I/O-bound tasks)
- **Queues:**
  - `ingest` — RSS fetching (can be slow, 15s timeout per source)
  - `default` — normalize + score + dedupe
  - `notify` — Telegram delivery (rate-limited)
- **Scale:** `docker compose up --scale worker=N`

### 3.3 `api` — FastAPI Application
- **Role:** Admin endpoints + Stripe webhooks + health check
- **Port:** 8000 (internal), exposed via Nginx in production
- **Auth:** Bearer token (MVP admin token; JWT in v2)
- **Key routes:**
  - `GET /health` — liveness probe
  - `GET /admin/sources` — list sources
  - `PATCH /admin/sources/{id}` — enable/disable, change threshold
  - `GET /admin/signals` — last N signals with scores
  - `POST /stripe/webhook` — Stripe event handler
  - `GET /admin/deliveries` — delivery log

### 3.4 `postgres` — Database
- **Image:** `postgres:16-alpine`
- **Role:** Persistent storage for all entities
- **Connection pool:** SQLAlchemy async pool, max 10 connections per worker

### 3.5 `redis` — Message Broker + Cache
- **Image:** `redis:7-alpine`
- **Role:**
  - Celery task broker (task dispatch)
  - Celery result backend (task state)
  - Short-term dedup cache (URL hash → TTL 24h) for fast pre-DB check

---

## 4. Application Modules

```
app/
├── api/                    # FastAPI routers
│   ├── admin.py            # Source/signal/delivery management
│   ├── health.py           # /health endpoint
│   └── stripe_webhook.py   # Stripe event processing
│
├── core/                   # Cross-cutting concerns
│   ├── config.py           # Pydantic Settings (reads .env)
│   ├── logging.py          # Structured JSON logger
│   └── database.py         # SQLAlchemy async engine + session factory
│
├── ingest/                 # Layer 1: Data acquisition
│   ├── rss.py              # feedparser-based RSS fetcher
│   ├── scraper.py          # trafilatura fallback (only scrape_allowed sources)
│   └── canonical.py        # URL normalization (strip UTM params etc.)
│
├── normalize/              # Layer 2: Text cleaning
│   ├── cleaner.py          # lowercase, unicode norm, whitespace
│   └── langdetect.py       # Language detection (langdetect lib)
│
├── score/                  # Layer 3: Impact scoring
│   ├── rules.py            # Keyword weight table + scoring logic
│   └── categories.py       # Category → keyword mapping
│
├── dedupe/                 # Layer 4: Deduplication
│   ├── hash.py             # sha256(normalized_title + canonical_url)
│   └── similarity.py       # rapidfuzz title similarity check
│
├── notify/                 # Layer 5: Delivery
│   ├── base.py             # Abstract Notifier interface
│   ├── telegram.py         # Telegram Bot API adapter
│   └── formatter.py        # Message template rendering
│
├── models/                 # SQLAlchemy ORM models
│   ├── source.py
│   ├── article.py
│   ├── signal.py
│   ├── delivery.py
│   └── user.py
│
└── tasks/                  # Celery task definitions
    ├── ingest.py           # fetch_all_sources, fetch_source
    ├── process.py          # normalize_article, score_article, dedupe_article
    └── notify.py           # send_signal, retry_failed_deliveries
```

---

## 5. Module Interfaces

### 5.1 Ingest → Normalize
```python
@dataclass
class RawArticle:
    source_id: str
    url: str                  # canonical URL after normalization
    title: str
    summary: str              # RSS summary or scraped first paragraph
    published_at: datetime
    raw_html: str | None      # only if scrape_allowed
```

### 5.2 Normalize → Score
```python
@dataclass
class NormalizedArticle:
    source_id: str
    url: str
    title_clean: str
    body_clean: str
    lang: str                 # "en", "de", etc.
    hash: str                 # sha256 for dedup
    published_at: datetime
```

### 5.3 Score → Dedupe → Notify
```python
@dataclass
class Signal:
    article_id: int
    impact_score: int         # 0–100
    reasons: list[str]        # ["rate cut", "Fed", "markets"]
    tickers: list[str]        # ["SPY", "AAPL"] — extracted entities
    categories: list[str]     # ["macro", "earnings"]
    is_duplicate: bool
    duplicate_of: int | None  # article_id of original
```

---

## 6. Configuration Hierarchy

```
Priority (high → low):
  1. Environment variables (.env / Docker secrets)
  2. configs/sources.yaml     (source definitions)
  3. configs/channels.yaml    (Telegram channel routing)
  4. app/core/config.py       (Pydantic defaults)
```

**Key env variables:**
```
DATABASE_URL          postgres://user:pass@postgres:5432/finance_alerts
REDIS_URL             redis://redis:6379/0
TELEGRAM_BOT_TOKEN    <from BotFather>
TELEGRAM_CHANNEL_ID   @yourchannel or -100xxxxxxx
IMPACT_THRESHOLD      60
ADMIN_TOKEN           <random 32-char secret>
STRIPE_SECRET_KEY     sk_live_...
STRIPE_WEBHOOK_SECRET whsec_...
```

---

## 7. Error Handling Strategy

| Layer | On error | Action |
|-------|----------|--------|
| Ingest | HTTP timeout / 4xx / 5xx | Log + mark source `last_error_at`; retry after backoff |
| Ingest | RSS parse error | Log malformed entry; skip article |
| Score | Unexpected exception | Log + store article with `impact_score=0` |
| Telegram | Rate limit (429) | Exponential backoff (1s → 2s → 4s → 8s, max 3 retries) |
| Telegram | Bot blocked / chat not found | Log as permanent failure; alert admin via email (v2) |
| Stripe webhook | Signature mismatch | Return 400; log |
| DB | Connection error | Celery task auto-retry (max 3); circuit breaker pattern in v2 |

---

## 8. Security Considerations

- All secrets in environment variables — never in code or YAML
- Telegram bot token rotatable without code change (env-only)
- Stripe webhook signature validated with `stripe.Webhook.construct_event()`
- Admin API protected by `Authorization: Bearer <ADMIN_TOKEN>` header
- DB user has only `SELECT/INSERT/UPDATE/DELETE` on app schema (no DDL in prod)
- Rate limiting on `/admin/*` endpoints: 60 req/min per IP (v2: per user)

---

_Last updated: 2026-03-02 | Stage 3 complete_
