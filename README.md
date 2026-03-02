# Finance Alerts

Finance news impact scoring and Telegram alert SaaS.

## Quick Start

```bash
git clone https://github.com/hurdler2/finance_alerts_telegram_10_steps.git
cd finance_alerts_telegram_10_steps

cp .env.example .env
# .env dosyasını düzenle:
#   TELEGRAM_BOT_TOKEN=...
#   TELEGRAM_CHANNEL_ID=@kanalın
#   ADMIN_TOKEN=$(python -c "import secrets; print(secrets.token_hex(32))")

docker compose up --build
docker compose exec api alembic upgrade head
docker compose exec api python scripts/seed_sources.py

curl http://localhost:8000/health
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| api | 8000 | FastAPI admin + webhooks |
| worker | — | Celery task worker |
| beat | — | Celery scheduler (5-min RSS poll) |
| postgres | 5432 | PostgreSQL 16 |
| redis | 6379 | Broker + cache |

## Development

```bash
# Install dependencies locally
pip install -e ".[dev]"

# Run tests
pytest

# Run API only (no Docker)
uvicorn app.main:app --reload
```

## Database Setup

```bash
# 1. Start services
docker compose up -d postgres redis

# 2. Run migrations
docker compose exec api alembic upgrade head

# 3. Seed sources from YAML
docker compose exec api python scripts/seed_sources.py
```

## Project Status

| Stage | Description | Status |
|-------|-------------|--------|
| 1 | Requirements & scope | ✅ |
| 2 | Source list (RSS) | ✅ |
| 3 | Architecture & data flow | ✅ |
| 4 | Repo scaffold + Docker | ✅ |
| 5 | Data models + migrations | ✅ |
| 6 | Ingest (RSS fetcher) | ✅ |
| 7 | Normalize + score + dedupe | ✅ |
| 8 | Telegram notifier | ✅ |
| 9 | SaaS layer (Stripe + admin) | ✅ |
| 10 | Deploy + observability | ✅ |
