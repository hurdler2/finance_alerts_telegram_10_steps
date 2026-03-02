"""
Category → keyword mapping used by the scoring engine.
Each keyword maps to a base weight (0–35).
Higher weight = stronger signal of market impact.
"""
from __future__ import annotations

# (keyword_or_phrase, base_weight)
# All matching is case-insensitive against cleaned text.
KEYWORD_WEIGHTS: list[tuple[str, int]] = [
    # ── Central bank / monetary policy (highest impact) ────────────────────
    ("emergency rate", 35),
    ("bank run", 35),
    ("bank failure", 35),
    ("default", 30),
    ("bankruptcy", 30),
    ("financial crisis", 30),
    ("systemic risk", 28),
    ("rate hike", 25),
    ("rate cut", 25),
    ("rate decision", 22),
    ("interest rate", 20),
    ("fomc", 20),
    ("federal reserve", 18),
    ("fed ", 15),          # trailing space avoids "feed", "feedback"
    ("ecb ", 15),
    ("boe ", 12),
    ("central bank", 15),
    ("quantitative easing", 18),
    ("quantitative tightening", 18),
    ("tapering", 15),
    ("pivot", 12),

    # ── Macro data ──────────────────────────────────────────────────────────
    ("inflation", 18),
    ("cpi", 18),
    ("pce", 16),
    ("ppi", 15),
    ("gdp", 15),
    ("nonfarm payroll", 18),
    ("jobs report", 18),
    ("unemployment", 15),
    ("recession", 22),
    ("stagflation", 20),
    ("debt ceiling", 20),
    ("credit rating", 18),
    ("downgrade", 20),
    ("upgrade", 10),
    ("sovereign debt", 18),

    # ── Earnings / corporate ────────────────────────────────────────────────
    ("earnings beat", 22),
    ("earnings miss", 22),
    ("earnings surprise", 20),
    ("revenue beat", 18),
    ("revenue miss", 18),
    ("guidance cut", 20),
    ("guidance raise", 18),
    ("profit warning", 22),
    ("layoffs", 15),
    ("job cuts", 15),
    ("acquisition", 12),
    ("merger", 12),
    ("ipo", 10),
    ("buyback", 10),
    ("dividend cut", 18),

    # ── Geopolitical / sanctions ────────────────────────────────────────────
    ("sanctions", 22),
    ("war", 18),
    ("military action", 20),
    ("trade war", 20),
    ("tariff", 16),
    ("embargo", 18),
    ("geopolitical", 12),
    ("nuclear", 20),
    ("coup", 20),
    ("election", 10),

    # ── Energy / commodities ────────────────────────────────────────────────
    ("oil spike", 20),
    ("crude oil", 12),
    ("opec", 18),
    ("energy crisis", 22),
    ("gas price", 12),
    ("commodity", 10),
    ("gold price", 10),

    # ── Banking / financial stability ───────────────────────────────────────
    ("bank collapse", 30),
    ("bank rescue", 25),
    ("capital requirements", 15),
    ("stress test", 12),
    ("basel", 10),
    ("fdic", 15),
    ("bailout", 22),
    ("contagion", 20),

    # ── Crypto ──────────────────────────────────────────────────────────────
    ("sec charges", 20),
    ("crypto ban", 20),
    ("exchange collapse", 28),
    ("stablecoin", 15),
    ("bitcoin etf", 18),
    ("crypto regulation", 16),
    ("defi hack", 20),
]

# Multiplier applied when keyword found in title (vs body)
TITLE_MULTIPLIER: float = 1.5

# Source priority bonus: priority 1 = +15, priority 5 = +3
def source_priority_bonus(priority: int) -> int:
    return max(0, (6 - priority) * 3)

# Recency bonus (age in minutes)
def recency_bonus(age_minutes: float) -> int:
    if age_minutes < 10:
        return 10
    if age_minutes < 30:
        return 5
    if age_minutes < 120:
        return 2
    return 0
