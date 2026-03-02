# Finance News Sources

## Classification Method

Each source is evaluated on:
1. **Has RSS?** — Direct RSS/Atom feed available (preferred)
2. **Scraping allowed?** — `robots.txt` and ToS permit automated access
3. **Paywall?** — Full body accessible or headlines/summary only
4. **Signal quality** — Relevance to high-impact finance events

**MVP policy:** Only RSS-first sources. Scraping fallback only where explicitly permitted.

---

## Source Table (MVP — 20 sources)

| # | ID | Name | Category | Priority | RSS | Scrape OK | Paywall | Enabled |
|---|----|------|----------|----------|-----|-----------|---------|---------|
| 1 | `reuters_business` | Reuters Business | macro | 1 | ✅ | ✅ | No | ✅ |
| 2 | `reuters_markets` | Reuters Markets | macro | 1 | ✅ | ✅ | No | ✅ |
| 3 | `ap_business` | AP News — Business | macro | 1 | ✅ | ✅ | No | ✅ |
| 4 | `fed_press_releases` | Federal Reserve Releases | macro | 1 | ✅ | ✅ | No | ✅ |
| 5 | `ecb_press` | ECB Press Releases | macro | 1 | ✅ | ✅ | No | ✅ |
| 6 | `cnbc_top_news` | CNBC Top News | general | 2 | ✅ | ❌ | Partial | ✅ |
| 7 | `cnbc_finance` | CNBC Finance | macro | 2 | ✅ | ❌ | Partial | ✅ |
| 8 | `ft_markets` | FT Markets | macro | 1 | ✅ | ❌ | Yes | ✅ |
| 9 | `wsj_markets` | WSJ Markets | macro | 1 | ✅ | ❌ | Yes | ✅ |
| 10 | `marketwatch_top` | MarketWatch Top | general | 2 | ✅ | ✅ | No | ✅ |
| 11 | `seeking_alpha_market_news` | Seeking Alpha Market News | earnings | 3 | ✅ | ❌ | Yes | ✅ |
| 12 | `businesswire_earnings` | Business Wire — Earnings | earnings | 2 | ✅ | ✅ | No | ✅ |
| 13 | `prnewswire_financial` | PR Newswire Financial | earnings | 3 | ✅ | ✅ | No | ✅ |
| 14 | `coindesk_news` | CoinDesk | crypto | 2 | ✅ | ✅ | No | ✅ |
| 15 | `cointelegraph` | CoinTelegraph | crypto | 2 | ✅ | ✅ | No | ✅ |
| 16 | `decrypt_news` | Decrypt | crypto | 3 | ✅ | ✅ | No | ❌ |
| 17 | `oilprice_news` | OilPrice.com | energy | 3 | ✅ | ✅ | No | ✅ |
| 18 | `eia_news` | EIA Press Releases | energy | 2 | ✅ | ✅ | No | ✅ |
| 19 | `bbc_business` | BBC Business | geopolitical | 2 | ✅ | ✅ | No | ✅ |
| 20 | `guardian_business` | The Guardian Business | geopolitical | 3 | ✅ | ✅ | No | ✅ |
| 21 | `ft_banking` | FT Banking | banking | 1 | ✅ | ❌ | Yes | ✅ |

**Enabled MVP:** 20 | **Disabled (v2):** 1 (`decrypt_news`)

---

## Category Breakdown

| Category | Count | Key Sources |
|----------|-------|-------------|
| macro | 7 | Reuters, AP, Fed, ECB, FT, WSJ, CNBC |
| earnings | 3 | BusinessWire, PRNewswire, Seeking Alpha |
| crypto | 3 | CoinDesk, CoinTelegraph, Decrypt |
| energy | 2 | OilPrice, EIA |
| geopolitical | 2 | BBC, The Guardian |
| banking | 1 | FT Banking |
| general | 2 | CNBC Top, MarketWatch |

---

## RSS vs Scraping Strategy

### Tier 1 — RSS with full body accessible (scrape_allowed: true)
Reuters, AP, BBC, Guardian, MarketWatch, BusinessWire, PRNewswire, CoinDesk, CoinTelegraph, OilPrice, EIA, Fed, ECB

**Implementation:** `feedparser` → extract `entry.summary` or `entry.content[0].value`. If body < 200 chars, run `trafilatura.fetch_url()` to pull full article.

### Tier 2 — RSS with headline/summary only (paywalled or scrape disallowed)
FT, WSJ, CNBC, Seeking Alpha

**Implementation:** `feedparser` → use `entry.title` + `entry.summary` only. Do NOT attempt to scrape full body. Score is based on title keywords.

### Tier 3 — Scraping required (no RSS)
None in MVP. If added in v2:
- Check `robots.txt` via `urllib.robotparser.RobotFileParser`
- Use `trafilatura` with `favor_recall=True`
- Respect `Crawl-delay` directive
- Identify with custom `User-Agent` per `defaults.user_agent`

---

## Robots.txt & Legal Notes

| Source | robots.txt status | ToS note |
|--------|------------------|----------|
| Reuters | Allows crawlers for non-commercial | Use RSS only; don't mass-scrape |
| AP News | Restricts automated access | RSS via RSSHub (public aggregator) |
| Fed / ECB | Public government data | No restrictions |
| FT / WSJ | Disallow most bots | RSS headline only — do not scrape |
| CNBC | Partial restrictions | RSS only |
| BBC | Allows with User-Agent | Standard fair use |
| BusinessWire / PRNewswire | Press release syndicators — open | OK to fetch |
| CoinDesk / CoinTelegraph | Allow crawlers | Standard fair use |
| MarketWatch | Partial restrictions | RSS only recommended |

**Rule:** If `scrape_allowed: false` in config, the ingestion layer must use RSS summary/title only and must not make additional HTTP requests to the article URL for body content.

---

## Adding a New Source (Operator Guide)

1. Verify RSS feed URL is live:
   ```bash
   curl -I "<rss_url>"
   ```
2. Check `robots.txt`:
   ```bash
   curl https://<domain>/robots.txt | grep -i "user-agent\|disallow\|crawl-delay"
   ```
3. Add entry to `configs/sources.yaml` with `enabled: false` first.
4. Run seed/test fetch:
   ```bash
   python -m app.ingest.rss --source-id <id> --dry-run
   ```
5. Review 10 sample articles for signal quality.
6. Set `enabled: true` if quality is acceptable.

---

_Last updated: 2026-03-02 | Stage 2 complete_