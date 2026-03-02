# Data Flow — Finance Alerts

## 1. End-to-End Pipeline Overview

```
[Celery Beat]
     │  every 5 min
     ▼
fetch_all_sources()
     │  fan-out: 1 task per enabled source
     ▼
fetch_source(source_id)          ← ingest layer
     │  feedparser → RawArticle[]
     │  canonical URL normalization
     │  upsert → articles table (status=raw)
     ▼
process_article(article_id)      ← normalize + score + dedupe
     │
     ├─ normalize: clean text, detect lang
     │       → update articles (cleaned_text, lang, hash)
     │
     ├─ dedupe: check redis cache + DB
     │       → if duplicate: mark articles.is_duplicate=true, STOP
     │
     ├─ score: keyword rules → impact_score, reasons[]
     │       → insert signals row
     │
     └─ route: impact_score >= IMPACT_THRESHOLD?
              YES → send_signal(signal_id)
              NO  → mark signal as suppressed, STOP
     ▼
send_signal(signal_id)           ← notify layer
     │  format message
     │  POST Telegram Bot API
     │  → insert deliveries row (status=sent / failed)
     │  on failure: retry queue (max 3)
```

---

## 2. Detailed Step-by-Step Flow

### Step 1 — Beat fires `fetch_all_sources`
```
beat scheduler
  └─ every 5 minutes: tasks.ingest.fetch_all_sources.delay()
       └─ queries DB: SELECT * FROM sources WHERE enabled=true
       └─ for each source:
            tasks.ingest.fetch_source.apply_async(
              args=[source.id],
              queue="ingest",
              countdown=index * 2   # stagger by 2s to avoid burst
            )
```

### Step 2 — `fetch_source(source_id)`
```
1. Load source config from DB (rss_url, scrape_allowed, poll_interval)
2. GET rss_url via httpx (timeout=15s, retries=3 with backoff)
3. feedparser.parse(response.content)
4. For each entry in feed.entries (max 50):
   a. canonical_url = ingest.canonical.normalize(entry.link)
   b. Check redis: HGET dedup_cache canonical_url
      → if exists: SKIP (already processed recently)
   c. Extract: title, summary, published_at
   d. If scrape_allowed AND summary < 200 chars:
        body = ingest.scraper.fetch_body(canonical_url)
   e. UPSERT articles(source_id, url, title, raw_text, published_at, status='raw')
        ON CONFLICT (hash) DO NOTHING
   f. If new article inserted:
        tasks.process.process_article.delay(article.id)
5. UPDATE sources SET last_checked_at=NOW() WHERE id=source_id
```

### Step 3 — `process_article(article_id)`
```
1. Load article from DB
2. NORMALIZE:
   a. title_clean  = normalize.cleaner.clean(article.title)
   b. body_clean   = normalize.cleaner.clean(article.raw_text)
   c. lang         = normalize.langdetect.detect(title_clean)
   d. UPDATE articles SET cleaned_text, lang, status='normalized'

3. DEDUPE:
   a. h = dedupe.hash.compute(title_clean, article.url)
   b. UPDATE articles SET hash=h
   c. Check DB: SELECT id FROM articles WHERE hash=h AND id != article.id
      → if found: UPDATE articles SET is_duplicate=true, duplicate_of=found.id
                  UPDATE articles SET status='duplicate'
                  RETURN (stop pipeline)
   d. Check rapidfuzz: SELECT title_clean FROM articles
        WHERE published_at > NOW()-1h AND id != article.id
        → if similarity(title_clean, candidate) > 0.85:
            mark duplicate, RETURN
   e. SET redis dedup_cache[h] = article.id  EX 86400

4. SCORE:
   a. score, reasons, tickers, categories = score.rules.evaluate(
        title=title_clean,
        body=body_clean,
        source_priority=source.priority,
        published_at=article.published_at
      )
   b. INSERT signals(article_id, impact_score, reasons, tickers, categories)
   c. UPDATE articles SET status='scored'

5. ROUTE:
   threshold = config.IMPACT_THRESHOLD  # default 60
   if signal.impact_score >= threshold:
       tasks.notify.send_signal.apply_async(
         args=[signal.id],
         queue="notify"
       )
   else:
       UPDATE signals SET status='suppressed'
```

### Step 4 — `send_signal(signal_id)`
```
1. Load signal + article + source from DB
2. Format message:
     text = notify.formatter.render(signal, article, source)
     # → "🚨 [IMPACT 82] Fed signals rate cut...\n• Reasons: ...\nhttps://..."
3. Determine target channel:
     channel_id = config.TELEGRAM_CHANNEL_ID
     # v2: router selects channel by signal.categories + user plan
4. POST https://api.telegram.org/bot{TOKEN}/sendMessage
     { chat_id: channel_id, text: text, parse_mode: "HTML" }
5. On success (HTTP 200):
     INSERT deliveries(signal_id, channel='telegram', status='sent', sent_at=NOW())
6. On failure:
     INSERT deliveries(signal_id, status='failed', error=response.text)
     if attempt < 3:
         tasks.notify.send_signal.apply_async(
           args=[signal_id],
           queue="notify",
           countdown=2**attempt * 10   # 10s, 20s, 40s
         )
     else:
         UPDATE deliveries SET status='permanent_failure'
         log.error("Permanent delivery failure", signal_id=signal_id)
```

---

## 3. State Machine — Article Lifecycle

```
         ┌─────────┐
         │  raw    │  ← inserted by ingest
         └────┬────┘
              │ process_article()
              ▼
       ┌─────────────┐
       │ normalized  │
       └──────┬──────┘
              │
       ┌──────▼──────┐      ┌───────────┐
       │   dedupe?   │─YES─▶│ duplicate │ (pipeline stops)
       └──────┬──────┘      └───────────┘
              │ NO
              ▼
        ┌──────────┐
        │  scored  │
        └─────┬────┘
              │
       ┌──────▼──────────┐      ┌────────────┐
       │ score >= thresh? │─NO──▶│ suppressed │
       └──────┬───────────┘      └────────────┘
              │ YES
              ▼
        ┌──────────┐
        │  queued  │
        └─────┬────┘
              │ send_signal()
              ▼
        ┌──────────┐      ┌─────────┐
        │  sent    │  OR  │ failed  │──retry──▶ sent / permanent_failure
        └──────────┘      └─────────┘
```

---

## 4. Deduplication Logic Detail

```
Input: title_clean, canonical_url

1. Hash check (exact):
   h = sha256(title_clean.lower() + "|" + canonical_url)
   → O(1) lookup in redis + DB unique index

2. URL check:
   SELECT 1 FROM articles WHERE url = canonical_url AND id != current
   → catches same URL from different RSS feeds

3. Fuzzy title check (within 1-hour window):
   candidates = SELECT title_clean FROM articles
                WHERE published_at > NOW() - INTERVAL '1 hour'
                AND id != current_id
                AND is_duplicate = false
   for candidate in candidates:
       if rapidfuzz.fuzz.token_sort_ratio(title_clean, candidate) >= 85:
           mark duplicate

   → catches "Reuters: Fed cuts rates" vs "AP: Fed cuts interest rates"
```

---

## 5. Impact Scoring Detail

```
Base score = 0

# Keyword weights (additive)
for keyword, weight in KEYWORD_WEIGHTS.items():
    if keyword in title_clean:
        score += weight * TITLE_MULTIPLIER (1.5x)
    elif keyword in body_clean:
        score += weight

# Source priority bonus
score += (6 - source.priority) * 3   # priority 1 = +15, priority 5 = +3

# Recency bonus (article age in minutes)
age_min = (now - published_at).seconds / 60
if age_min < 10:  score += 10
elif age_min < 30: score += 5

# Cap at 100
score = min(score, 100)

# Top keywords by weight (sample):
KEYWORD_WEIGHTS = {
    "rate hike":      25,  "rate cut":       25,
    "emergency":      30,  "bank run":       35,
    "default":        30,  "bankruptcy":     30,
    "inflation":      15,  "CPI":            15,
    "Fed":            10,  "ECB":            10,
    "jobs report":    15,  "nonfarm":        15,
    "earnings beat":  20,  "earnings miss":  20,
    "guidance":       12,  "downgrade":      18,
    "sanctions":      20,  "oil spike":      18,
    "recession":      20,  "GDP":            12,
    "FOMC":           15,  "rate decision":  20,
    "crypto":          8,  "SEC":            15,
    "acquisition":    10,  "merger":         10,
}
```

---

## 6. Telegram Message Format

```python
def render(signal, article, source) -> str:
    emoji = "🚨" if signal.impact_score >= 80 else "📢"
    reasons = " • ".join(signal.reasons[:3])
    time_str = article.published_at.strftime("%Y-%m-%d %H:%M UTC")

    return (
        f"{emoji} <b>[IMPACT {signal.impact_score}]</b> {article.title}\n"
        f"• {reasons}\n"
        f"• <i>{source.name}</i> | {time_str}\n"
        f"{article.url}"
    )
```

**Output example:**
```
🚨 [IMPACT 82] Fed signals rate cut sooner than expected
• rate cut • Fed • FOMC
• Reuters | 2026-03-02 14:05 UTC
https://reuters.com/...
```

---

## 7. Retry & Failure Budget

| Task | Max retries | Backoff | On exhaustion |
|------|-------------|---------|---------------|
| fetch_source | 3 | 30s, 60s, 120s | Mark source `error`; alert admin |
| process_article | 2 | 10s, 30s | Mark article `failed`; log |
| send_signal | 3 | 10s, 20s, 40s | Mark delivery `permanent_failure` |
| retry_failed_deliveries | N/A (beat task) | 10min interval | — |

---

_Last updated: 2026-03-02 | Stage 3 complete_
