# Proje: Finans Haberleri → Etki Skoru → Telegram Kanal/Grup Bildirimi (SaaS)
Hedef: Yurtdışındaki önde gelen finans haber kaynaklarından (RSS/atom + gerektiğinde scraping) “piyasayı etkileyebilir” haberleri otomatik çekmek, normalize etmek, skorlayıp dedupe etmek ve **Telegram kanalında/grubunda otomatik paylaşmak**. Abonelik (aylık) ile satılabilir bir MVP + üretim sistemi.

> Claude Code için çalışma kuralı (memory bypass):
> - Her adım sonunda “Çıktılar / Dosyalar / Komutlar / Sonraki adımda ne yapılacak” diye özetle.
> - Kodları küçük parçalar halinde üret, her parçayı repo yapısına yerleştir.
> - Test/çalıştır komutlarını net ver.
> - “Önce minimal çalışan uçtan uca MVP, sonra kalite + ölçek” yaklaşımı.

---

## 1) Adım — Gereksinimler, Scope ve Başarı Kriterleri (Claude’a görev)
**Claude’a yapacağın iş:**
- MVP kapsamını netleştir: kaynaklar, filtreleme, paylaşım formatı, hız.
- “Müşteri değeri” ve “fiyatlandırma planı” taslağı.
- Risk listesi: telif/robots, rate limit, yanlış skor, yanlış pozitif/negatif.

**MVP başarı kriterleri:**
- 10–20 kaynak (RSS öncelikli) → 5 dk’da bir tarama
- Dedupe + etki skoruyla günde 10–30 bildirim
- Telegram’a sorunsuz gönderim (kanal veya grup)
- Admin panelden kaynak ekleme/kapama
- Basit abonelik (Stripe) + kullanıcı yönetimi

**Çıktı:** `docs/requirements.md`

---

## 2) Adım — Kaynak Stratejisi (RSS-first) + Kaynak Listesi
**Claude’a yapacağın iş:**
- “RSS/Atom var mı?” diye kaynakları sınıflandır.
- RSS yoksa scraping planı (etik ve kırılganlık notları).
- Her kaynak için: isim, URL, RSS URL, kategori (macro/earnings/fed/crypto), dil.

**MVP’de:** Paywall’suz ve RSS’li kaynakları seç.

**Çıktı dosyaları:**
- `configs/sources.yaml` (enable/disable, rss_url, priority)
- `docs/sources.md`

---

## 3) Adım — Mimari Tasarım (Modüler: ingest → normalize → score → notify)
**Claude’a yapacağın iş:**
- Üretime uygun ama basit mimari: servisler ve veri akışı.
- Modülleri ayrı katman yap:
  1) Ingest (RSS/scrape)
  2) Normalize (metin temizleme, dil tespiti, entity extraction opsiyonel)
  3) Score (etki skoru)
  4) Dedupe (hash + similarity)
  5) Router (hangi kanala gidecek)
  6) Notifier (Telegram adapter)
  7) Admin/API

**Önerilen teknoloji (MVP → prod uyumlu):**
- Python 3.12
- FastAPI (API + admin endpoints)
- PostgreSQL (kalıcı)
- Redis + Celery (job queue / schedule)
- Docker Compose (local+server)
- Observability: structured logs + Sentry opsiyonel

**Çıktı:** `docs/architecture.md` + `docs/dataflow.md`

---

## 4) Adım — Repo Yapısı + Docker Compose + Ortam Değişkenleri
**Claude’a yapacağın iş:**
- Repo scaffold oluştur.
- Docker Compose ile: `api`, `worker`, `beat/scheduler`, `postgres`, `redis`.
- `.env.example` üret.

**Hedef repo ağacı:**
```
finance-alerts/
  app/
    api/                # FastAPI
    core/               # config, logging
    ingest/             # rss/scrape fetchers
    normalize/
    score/
    dedupe/
    notify/             # telegram adapter
    models/             # SQLAlchemy
    tasks/              # Celery tasks
  configs/
    sources.yaml
  migrations/
  tests/
  docs/
  docker-compose.yml
  Dockerfile
  pyproject.toml
  .env.example
  README.md
```

**Çıktı:** `docker-compose up` ile boş API ayağa kalksın.

---

## 5) Adım — Veri Modeli (Haber, Kaynak, Teslimat, Abonelik)
**Claude’a yapacağın iş:**
SQLAlchemy modellerini ve migration’ları yaz.

**Minimum tablolar:**
- `sources`: id, name, rss_url, enabled, priority, last_checked_at
- `articles`: id, source_id, url, title, published_at, raw_text, cleaned_text, lang, hash, canonical_url
- `signals`: id, article_id, impact_score (0–100), reasons(JSON), tickers(JSON), categories(JSON)
- `deliveries`: id, signal_id, channel (telegram), status, sent_at, error
- `users` + `subscriptions` (Stripe customer_id, status, plan)

**Dedupe için:**
- `hash = sha256(normalized_title + canonical_url)` + opsiyonel similarity index

**Çıktı:** `app/models/*` + migration komutları + seed script.

---

## 6) Adım — Ingest: RSS Toplama + (Opsiyonel) Scraping Fallback
**Claude’a yapacağın iş:**
- RSS parser (feedparser) yaz.
- Her entry için: url, title, published_at, summary.
- İçerik çekme:
  - Önce RSS summary ile MVP
  - Sonra `trafilatura` veya `newspaper3k` ile makale gövdesi çek (site izinliyse)
- Canonical URL normalize et (utm param temizle).

**Çalışma şekli:**
- Celery task: `fetch_sources()` → her source için `fetch_rss(source)`
- Rate-limit + timeout + retry
- `articles` tablosuna upsert

**Çıktı:** `app/ingest/rss.py`, `app/tasks/ingest.py`, testler.

---

## 7) Adım — Normalize + Etki Skoru + Dedupe (Kurallı MVP, sonra ML)
**Claude’a yapacağın iş:**
**Normalize:**
- lower/strip, unicode normalize, stopword minimal
- dil tespiti (langdetect/fasttext opsiyonel)

**Rule-based etki skoru (MVP):**
- Anahtar kelime ağırlıkları:
  - “rate hike/cut”, “inflation”, “CPI”, “Fed”, “ECB”, “jobs report”, “earnings beat/miss”, “guidance”, “default”, “downgrade”, “sanctions”, “oil spike”, “bank run”…
- Kaynak önceliği + recency bonus
- Başlıkta geçen kritik kelimelere ekstra puan
- Çıkış: `impact_score` + `reasons[]`

**Dedupe:**
- Aynı canonical_url → direkt duplicate
- Title similarity (rapidfuzz) > eşik → duplicate
- Duplicate ise sadece “en yüksek skoru” sakla veya `articles.is_duplicate_of`

**Çıktı:** `app/normalize/*`, `app/score/rules.py`, `app/dedupe/*` + unit test.

---

## 8) Adım — Bildirim Router + Telegram Entegrasyonu (Stabil Yol)
**Claude’a yapacağın iş:**
“Notifier” interface’i tasarla:
- `send(message: str) -> DeliveryResult`

**Telegram gönderim yöntemi:**
- Telegram Bot token + `chat_id` (kanal/grup)
- Kanal için botu admin yap (gerekli izinler)
- Rate limit + retry + hata log

**Mesaj formatı (kısa ve net):**
- Başlık
- Skor + 2–3 gerekçe
- Kaynak + zaman
- Link

Örnek:
```
🚨 [IMPACT 82] Fed signals rate cut sooner
• Reasons: rate cut, Fed, markets
• Source: CNBC | 2026-03-02 14:05 UTC
https://...
```

**Router:**
- `impact_score >= threshold` ise gönder
- `threshold` config’ten yönetilsin
- Delivery log + retry

**Çıktı:** `app/notify/telegram.py`, `app/tasks/notify.py`, `configs/channels.yaml`

---

## 9) Adım — SaaS Katmanı: Kullanıcı/Plan/Stripe + Admin Panel
**Claude’a yapacağın iş:**
- Stripe abonelik akışı:
  - planlar: Basic / Pro (ör. kaynak sayısı, gecikme, kanal sayısı)
- Webhook endpoint:
  - subscription active/canceled/past_due sync
- Basit admin:
  - kaynak enable/disable
  - skor threshold ayarı
  - “son sinyaller” listesi
- Auth:
  - MVP: admin token
  - Sonra: JWT + RBAC

**Çıktı:** `app/api/*` (auth, admin, stripe_webhook), `docs/billing.md`

---

## 10) Adım — Deploy, İzleme, Güvenlik, Hukuk ve Operasyon
**Claude’a yapacağın iş:**
- Prod deploy:
  - VPS + Docker Compose
  - Nginx reverse proxy + HTTPS (Let’s Encrypt)
- Observability:
  - JSON log
  - Sentry opsiyonel
  - Healthchecks: `/health`
- Güvenlik:
  - env secrets
  - rate limit API
  - DB backup cron
- Hukuk/uyum:
  - Kaynak içeriklerini “kopyalama” yerine link + kısa özet (telif riskini azaltır)
  - robots.txt ve site terms kontrol notu
- Operasyon:
  - “Incident runbook” (ör. Telegram token sızarsa rotate)

**Çıktı:** `docs/deploy.md`, `docs/runbook.md`, production compose dosyası.

---

# Claude Code’a Tek Seferde Vereceğin “Master Prompt” (kopyala-yapıştır)
Aşağıdaki promptu Claude Code’a ver; her adımı bitirdikçe ilgili dosyaları repo’ya yazsın:

## PROMPT
You are implementing a production-ready MVP SaaS called “finance-alerts”.
Goal: ingest global finance news (RSS-first), normalize, score impact, deduplicate, and auto-post high-impact alerts to a Telegram channel/group via a Telegram bot.

Constraints:
- Python 3.12, FastAPI, Celery+Redis, Postgres, Docker Compose.
- Write small, testable modules. Add unit tests for scoring and dedupe.
- Provide .env.example and clear run commands.
- Keep summaries short and link to source; avoid copying full articles.
- After each step, output: changed files list, how to run, what’s next.

Implement in 10 steps exactly as described in docs/requirements.md; create that doc first.
Start now with Step 1: create docs/requirements.md and a minimal repo scaffold.
