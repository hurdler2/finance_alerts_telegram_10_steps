# Deployment Guide — Finance Alerts

## 1. Prerequisites

| Requirement | Minimum |
|-------------|---------|
| VPS | 2 vCPU, 2 GB RAM, 20 GB SSD |
| OS | Ubuntu 22.04 LTS |
| Docker | 25+ |
| Docker Compose | v2.24+ |
| Domain | DNS A record pointing to VPS IP |

---

## 2. First-Time Server Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose v2
sudo apt install -y docker-compose-plugin

# Create app directory
sudo mkdir -p /opt/finance-alerts
sudo chown $USER:$USER /opt/finance-alerts
cd /opt/finance-alerts
```

---

## 3. TLS Certificate (Let's Encrypt)

```bash
# Install certbot
sudo apt install -y certbot

# Issue certificate (standalone — stop nginx first if running)
sudo certbot certonly --standalone \
  -d yourdomain.com \
  --email admin@yourdomain.com \
  --agree-tos --no-eff-email

# Copy certs to nginx/certs/
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem nginx/certs/
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem   nginx/certs/
sudo chown $USER:$USER nginx/certs/*

# Auto-renew cron (runs twice daily)
echo "0 3,15 * * * root certbot renew --quiet --post-hook 'docker compose -f /opt/finance-alerts/docker-compose.prod.yml restart nginx'" \
  | sudo tee /etc/cron.d/certbot-renew
```

---

## 4. Deploy Application

```bash
# Clone repo
cd /opt/finance-alerts
git clone https://github.com/yourorg/finance-alerts.git .

# Configure environment
cp .env.example .env
nano .env
# Set: DATABASE_URL, REDIS_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID,
#      ADMIN_TOKEN, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, etc.

# Update nginx.conf with your domain
sed -i 's/yourdomain.com/actualdomain.com/g' nginx/nginx.conf

# Build and start
docker compose -f docker-compose.prod.yml up -d --build

# Run migrations
docker compose -f docker-compose.prod.yml exec api alembic upgrade head

# Seed sources
docker compose -f docker-compose.prod.yml exec api python scripts/seed_sources.py

# Verify
curl https://yourdomain.com/health
# → {"status":"ok","db":"ok"}
```

---

## 5. Telegram Bot Setup

```bash
# 1. Create bot: message @BotFather → /newbot
#    → Save token → TELEGRAM_BOT_TOKEN in .env

# 2. Create channel or group in Telegram app

# 3. Add bot as admin to channel/group:
#    Channel Settings → Administrators → Add Administrator → your bot
#    Required permissions: Post Messages

# 4. Get channel ID:
#    For public channel: use @channelname
#    For private channel or group:
#      - Add @userinfobot to group → it replies with chat ID (-100xxxxxxxxxx)
#    → Set TELEGRAM_CHANNEL_ID in .env

# 5. Test message:
curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -H "Content-Type: application/json" \
  -d '{"chat_id":"@yourchannel","text":"Finance Alerts bot online ✅"}'
```

---

## 6. Verify Services

```bash
# All containers healthy
docker compose -f docker-compose.prod.yml ps

# API health
curl https://yourdomain.com/health

# Admin stats
curl -H "Authorization: Bearer $ADMIN_TOKEN" https://yourdomain.com/admin/stats

# Celery worker alive
docker compose -f docker-compose.prod.yml exec worker \
  celery -A app.celery_app inspect ping

# Trigger one manual fetch cycle
docker compose -f docker-compose.prod.yml exec worker \
  celery -A app.celery_app call app.tasks.ingest.fetch_all_sources

# Watch worker logs
docker compose -f docker-compose.prod.yml logs -f worker
```

---

## 7. Updates & Re-deploy

```bash
cd /opt/finance-alerts
git pull
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d --no-deps api worker beat

# Run new migrations (if any)
docker compose -f docker-compose.prod.yml exec api alembic upgrade head
```

---

## 8. Scaling Workers

```bash
# Scale to 3 worker replicas
docker compose -f docker-compose.prod.yml up -d --scale worker=3

# Scale back down
docker compose -f docker-compose.prod.yml up -d --scale worker=1
```

---

## 9. Monitoring

### Structured Logs
```bash
# All services (JSON)
docker compose -f docker-compose.prod.yml logs -f --tail=100

# Filter high-impact signals sent
docker compose -f docker-compose.prod.yml logs worker | grep '"sent"'

# Filter errors
docker compose -f docker-compose.prod.yml logs | grep '"level":"error"'
```

### Key metrics to watch

| Metric | Where | Alert if |
|--------|-------|----------|
| `/health` DB status | API | `"db":"error"` |
| `consecutive_errors` per source | Admin `/admin/sources` | > 3 |
| `deliveries_failed` | Admin `/admin/stats` | Rising trend |
| Celery queue depth | Redis | `LLEN celery` > 500 |
| Disk usage | VPS | > 80% |
| Cert expiry | Let's Encrypt | < 14 days |

### Optional: Sentry error tracking
```bash
# Set in .env:
SENTRY_DSN=https://...@sentry.io/...
```

Add to `app/main.py` lifespan:
```python
import sentry_sdk
if settings.sentry_dsn:
    sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.1)
```

---

## 10. Security Checklist

- [ ] `ADMIN_TOKEN` is random 32-char hex (`python -c "import secrets; print(secrets.token_hex(32))"`)
- [ ] `POSTGRES_PASSWORD` is strong (min 20 chars)
- [ ] `REDIS_PASSWORD` set in production compose
- [ ] Ports 5432 and 6379 NOT exposed to internet (only internal Docker network)
- [ ] TLS certificate valid and auto-renewing
- [ ] `.env` file permissions: `chmod 600 .env`
- [ ] `STRIPE_WEBHOOK_SECRET` set and verified
- [ ] Telegram bot token stored only in `.env`, not in code
- [ ] Regular DB backups running (`docker compose logs backup`)
- [ ] `APP_ENV=production` in `.env`

---

## 11. Backup Verification

```bash
# List backups
ls -lh backups/

# Test restore to temp DB
docker run --rm -e PGPASSWORD=test \
  postgres:16-alpine \
  psql -h localhost -U test -d postgres \
  -c "\i /path/to/backup.sql"
```
