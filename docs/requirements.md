# Finance Alerts — Requirements & Scope

## 1. MVP Scope

### 1.1 Data Sources
- **Primary:** RSS/Atom feeds (10–20 sources at launch)
- **Fallback:** Lightweight HTML scraping for sources without RSS (trafilatura/newspaper3k)
- **Languages:** English-first; Turkish optional in v2
- **Update cadence:** Every 5 minutes (Celery beat schedule)

### 1.2 News Categories
| Category | Examples |
|----------|---------|
| Macro | Fed/ECB decisions, CPI, PPI, GDP, jobs report |
| Earnings | Earnings beat/miss, guidance, revenue surprise |
| Crypto | Major coin moves, regulatory news, exchange events |
| Energy | Oil/gas price spikes, OPEC decisions |
| Geopolitical | Sanctions, war escalation, trade policy |
| Banking | Bank run, capital requirements, M&A |

### 1.3 Filtering & Scoring
- Rule-based impact score (0–100)
- Only articles with `impact_score >= threshold` (default: 60) are forwarded
- Deduplication: SHA-256 hash of normalized title + canonical URL
- Optional fuzzy dedup via rapidfuzz (similarity > 0.85 → duplicate)

### 1.4 Notification Format (Telegram)
```
🚨 [IMPACT 82] Fed signals rate cut sooner than expected
• Reasons: rate cut, Fed, markets, 2026
• Source: Reuters | 2026-03-02 14:05 UTC
https://reuters.com/...
```
- Short title + score + 2–3 keyword reasons + source + link
- No full article body (copyright risk mitigation)

### 1.5 Delivery Targets
- Telegram channel (public or private) or group
- Bot must be admin in target channel/group
- One primary channel for MVP; multi-channel routing in v2

### 1.6 Speed Targets
- Ingest-to-Telegram latency: < 2 minutes from article publish
- 5-minute polling interval
- Daily alert volume: 10–30 high-impact notifications

---

## 2. Success Criteria

| Criterion | Target |
|-----------|--------|
| Sources online | 10–20 RSS feeds |
| Poll interval | 5 minutes |
| Daily alerts | 10–30 (tunable via threshold) |
| False-positive rate | < 20% (human-validated in first week) |
| Telegram delivery success | > 99% (retry on failure) |
| Dedup rate | > 95% (same story from multiple outlets = 1 alert) |
| Admin source toggle | Yes (enable/disable without redeploy) |
| Uptime | > 99.5% on VPS |

---

## 3. Customer Value & Pricing

### 3.1 Value Proposition
- **Time saved:** Traders/analysts spend 30–60 min/day scanning finance news manually. This bot does it in seconds.
- **Speed edge:** Alert arrives within 2 minutes of publish → actionable before most read it.
- **Signal-to-noise:** Only high-impact events, no noise.
- **Passive integration:** Works directly in Telegram (no extra app needed).

### 3.2 Pricing Plan (Draft)

| Plan | Price | Features |
|------|-------|---------|
| **Free / Trial** | $0 | 1 Telegram channel, top 5 sources, 1 alert/hour cap, 14-day trial |
| **Basic** | $19/mo | 1 channel, 10 sources, unlimited alerts, 5-min latency |
| **Pro** | $49/mo | 3 channels, 20 sources, 1-min latency, keyword filters, priority support |
| **Team** | $149/mo | 10 channels, all sources, custom keywords, webhook export, SLA |

### 3.3 Upsell Opportunities
- Custom keyword watchlists (e.g., "TSLA", "NVDA earnings")
- Webhook/API delivery (non-Telegram integrations)
- Historical signal archive
- ML-enhanced scoring (phase 2)

---

## 4. Risk Register

### 4.1 Legal / Copyright
| Risk | Severity | Mitigation |
|------|----------|-----------|
| Copying full article text | High | Only title + 1-line summary + link (fair use) |
| Ignoring `robots.txt` | Medium | Check `robots.txt` for each scraped source; skip if disallowed |
| ToS violation on news sites | Medium | Prefer RSS (publicly provided); scraping only where explicitly allowed |
| GDPR / user data | Low | No personal data in alerts; Stripe handles PII |

### 4.2 Technical
| Risk | Severity | Mitigation |
|------|----------|-----------|
| RSS feed URL changes | Medium | Health-check monitor; alert admin on 3 consecutive failures |
| Rate limiting by source | Medium | Per-source rate limits in config; exponential backoff |
| Telegram API rate limit | Low | Max 30 messages/sec; queue with delay if needed |
| Bot token compromise | High | Rotate via BotFather; store only in env secrets |
| DB downtime | Medium | Health endpoint; Docker restart policy; daily pg_dump |

### 4.3 Product Quality
| Risk | Severity | Mitigation |
|------|----------|-----------|
| High false-positive rate | High | Calibrate keyword weights in week 1; human review dashboard |
| Missing true-positive news | Medium | Monitor missed major events; add keyword/source if needed |
| Duplicate alerts (same story) | Medium | SHA-256 + fuzzy dedup; tune similarity threshold |
| Score gaming / clickbait | Low | Penalize sources with low signal/noise ratio over time |

### 4.4 Business
| Risk | Severity | Mitigation |
|------|----------|-----------|
| Low conversion (Free→Paid) | Medium | Feature-gate: multi-channel, custom keywords behind paywall |
| Stripe payment failure | Low | Webhook sync; pause service on `past_due` |
| Regulatory shutdown of Telegram channel | Low | Support multiple delivery adapters (email, webhook) in v2 |

---

## 5. Out of Scope (MVP)

- ML-based NLP scoring (phase 2)
- Sentiment analysis
- Multi-language support (Turkish, etc.)
- Mobile app or web dashboard (admin is CLI/API only for MVP)
- Real-time websocket feeds (RSS polling is sufficient for MVP)
- Historical backtesting of signals

---

## 6. Tech Stack (confirmed)

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 |
| API | FastAPI |
| Queue / Schedule | Celery + Redis |
| Database | PostgreSQL 16 |
| Containerization | Docker Compose |
| Telegram | python-telegram-bot or httpx direct API |
| RSS Parsing | feedparser |
| Scraping fallback | trafilatura |
| Dedup similarity | rapidfuzz |
| Migrations | Alembic |
| Testing | pytest |
| Secrets | .env / Docker secrets |
| Monitoring | Structured JSON logs; Sentry (optional) |

---

_Last updated: 2026-03-02 | Stage 1 complete_
