# Incident Runbook — Finance Alerts

## Quick Reference

| Symptom | Jump to |
|---------|---------|
| No alerts being sent | [§1 Pipeline Dead](#1-no-alerts-being-sent) |
| Telegram bot blocked / wrong channel | [§2 Telegram Issues](#2-telegram-issues) |
| Source errors / feed down | [§3 Source Failures](#3-source-failures) |
| DB connection errors | [§4 Database Issues](#4-database-issues) |
| High false-positive alerts | [§5 Score Tuning](#5-score-tuning) |
| Stripe webhook failing | [§6 Stripe Issues](#6-stripe-issues) |
| Bot token compromised | [§7 Token Rotation](#7-telegram-token-rotation) |
| Disk full / backup failure | [§8 Disk & Backup](#8-disk--backup) |
| Full restart procedure | [§9 Full Restart](#9-full-restart) |

---

## 1. No Alerts Being Sent

**Diagnosis:**
```bash
# Check all containers running
docker compose -f docker-compose.prod.yml ps

# Check pipeline stats
curl -sH "Authorization: Bearer $ADMIN_TOKEN" https://yourdomain.com/admin/stats | jq

# Check recent signals
curl -sH "Authorization: Bearer $ADMIN_TOKEN" \
  "https://yourdomain.com/admin/signals?limit=10" | jq '.[].status'

# Check failed deliveries
curl -sH "Authorization: Bearer $ADMIN_TOKEN" \
  "https://yourdomain.com/admin/deliveries?status=failed&limit=5" | jq '.[].error'

# Check Celery beat is firing
docker compose -f docker-compose.prod.yml logs beat --tail=20
```

**Possible causes & fixes:**

| Cause | Fix |
|-------|-----|
| Beat container stopped | `docker compose -f docker-compose.prod.yml restart beat` |
| Worker queue backed up | `docker compose -f docker-compose.prod.yml restart worker` |
| All signals suppressed (score < threshold) | Lower threshold: `PATCH /admin/config/threshold {"impact_threshold": 50}` |
| All articles are duplicates | Check dedup — may need to flush Redis cache (see §4) |
| Telegram delivery failing | See §2 |

---

## 2. Telegram Issues

### Bot not sending / chat not found
```bash
# Test bot token manually
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe"
# Should return {"ok":true,"result":{"username":"..."}}

# Test send to channel
curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -H "Content-Type: application/json" \
  -d "{\"chat_id\":\"${TELEGRAM_CHANNEL_ID}\",\"text\":\"test\"}"
```

**If "chat not found":**
- Verify `TELEGRAM_CHANNEL_ID` in `.env` (use `-100xxxxxxxxxx` for private, `@name` for public)
- Ensure bot is admin in the channel/group

**If "bot was blocked by the user":**
- User left the group or removed bot admin rights
- Re-add bot as admin in channel settings

### Rate limited (HTTP 429)
```bash
# Check delivery errors
curl -sH "Authorization: Bearer $ADMIN_TOKEN" \
  "https://yourdomain.com/admin/deliveries?status=failed" | jq '.[].error'
# Look for "RateLimited:retry_after=X"
```
Celery retries automatically with backoff — usually self-resolving within minutes.

---

## 3. Source Failures

### Find failing sources
```bash
curl -sH "Authorization: Bearer $ADMIN_TOKEN" \
  "https://yourdomain.com/admin/sources" | \
  jq '.[] | select(.consecutive_errors > 0) | {slug, consecutive_errors, last_error_msg}'
```

### Disable a broken source
```bash
# Find source ID first, then:
curl -sX PATCH \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}' \
  https://yourdomain.com/admin/sources/7
```

### RSS feed URL changed
1. Update `configs/sources.yaml` with new `rss_url`
2. Re-seed: `docker compose -f docker-compose.prod.yml exec api python scripts/seed_sources.py`
3. Re-enable source via admin API

---

## 4. Database Issues

### DB connection error
```bash
# Check postgres container
docker compose -f docker-compose.prod.yml logs postgres --tail=30

# Check health
docker compose -f docker-compose.prod.yml exec postgres \
  pg_isready -U finance_user -d finance_alerts

# Restart postgres (brief downtime)
docker compose -f docker-compose.prod.yml restart postgres
```

### Flush Redis dedup cache (use sparingly — will re-process recent articles)
```bash
docker compose -f docker-compose.prod.yml exec redis \
  redis-cli -a "${REDIS_PASSWORD}" FLUSHDB
```

### DB disk full
```bash
# Check sizes
docker compose -f docker-compose.prod.yml exec postgres \
  psql -U finance_user finance_alerts \
  -c "SELECT pg_size_pretty(pg_database_size('finance_alerts'));"

# Manually run cleanup (articles older than 30 days)
docker compose -f docker-compose.prod.yml exec worker \
  celery -A app.celery_app call app.tasks.process.cleanup_old_articles
```

---

## 5. Score Tuning

### Too many false positives (low-quality alerts being sent)
```bash
# Raise threshold (e.g. 70)
curl -sX PATCH \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"impact_threshold": 70}' \
  https://yourdomain.com/admin/config/threshold

# Persist in .env for next restart:
# IMPACT_THRESHOLD=70
```

### Missing important events (score too low)
- Check which keywords matched: `GET /admin/signals?min_score=0&status=suppressed`
- Add or increase keyword weights in `app/score/categories.py`
- Redeploy worker: `docker compose -f docker-compose.prod.yml up -d --no-deps worker`

---

## 6. Stripe Issues

### Webhook signature verification failing
```bash
# Check webhook secret
grep STRIPE_WEBHOOK_SECRET .env

# Re-roll webhook secret in Stripe Dashboard → Webhooks → endpoint → Reveal secret
# Update .env and restart api:
docker compose -f docker-compose.prod.yml up -d --no-deps api
```

### Subscription not syncing
```bash
# Check recent webhook deliveries in Stripe Dashboard → Developers → Webhooks
# Retry failed events from dashboard

# Check api logs for webhook errors
docker compose -f docker-compose.prod.yml logs api | grep stripe
```

---

## 7. Telegram Token Rotation

**Use immediately if token is compromised:**

```bash
# 1. Generate new token
#    Open Telegram → @BotFather → /mybots → your bot → API Token → Revoke

# 2. Update .env
nano .env
# Change TELEGRAM_BOT_TOKEN=<new_token>

# 3. Restart services that use the token
docker compose -f docker-compose.prod.yml up -d --no-deps api worker beat

# 4. Verify new token works
curl "https://api.telegram.org/bot${NEW_TOKEN}/getMe"
```

---

## 8. Disk & Backup

### Check disk usage
```bash
df -h /
du -sh /opt/finance-alerts/backups/
```

### Manual backup
```bash
docker compose -f docker-compose.prod.yml exec \
  -e PGPASSWORD=${POSTGRES_PASSWORD} postgres \
  pg_dump -U finance_user finance_alerts | \
  gzip > backups/manual_$(date +%Y%m%d_%H%M%S).sql.gz
```

### Restore from backup
```bash
# Stop worker and beat first (no new writes during restore)
docker compose -f docker-compose.prod.yml stop worker beat

gunzip -c backups/finance_alerts_20260302_030000.sql.gz | \
  docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U finance_user finance_alerts

docker compose -f docker-compose.prod.yml start worker beat
```

---

## 9. Full Restart

```bash
# Graceful restart (zero downtime for API)
docker compose -f docker-compose.prod.yml up -d --no-deps api worker beat nginx

# Full restart (brief downtime)
docker compose -f docker-compose.prod.yml restart

# Nuclear option — rebuild everything
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec api alembic upgrade head
```

---

## 10. Health Check Script

Save as `scripts/healthcheck.sh` and run from cron every 5 minutes:

```bash
#!/bin/bash
API_URL="https://yourdomain.com"
ADMIN_TOKEN="${ADMIN_TOKEN}"
ALERT_EMAIL="admin@yourdomain.com"

STATUS=$(curl -sf "${API_URL}/health" | jq -r '.status' 2>/dev/null)

if [ "$STATUS" != "ok" ]; then
  echo "Finance Alerts health check FAILED: status=${STATUS}" | \
    mail -s "ALERT: Finance Alerts Down" "$ALERT_EMAIL"
fi
```

---

_Last updated: 2026-03-02 | Stage 10 complete_
