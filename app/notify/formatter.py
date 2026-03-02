"""
Telegram message formatter.
Produces HTML-formatted messages (Telegram parse_mode=HTML).
Max message length: 4096 chars (Telegram limit).
"""
from __future__ import annotations

from datetime import datetime, timezone

# Impact score → emoji
def _score_emoji(score: int) -> str:
    if score >= 80:
        return "🚨"
    if score >= 65:
        return "📢"
    return "📌"


def render(
    impact_score: int,
    title: str,
    reasons: list[str],
    source_name: str,
    published_at: datetime | None,
    url: str,
) -> str:
    """
    Render a Telegram alert message.

    Example output:
        🚨 [IMPACT 82] Fed signals rate cut sooner than expected
        • rate cut • Fed • FOMC
        • Reuters | 2026-03-02 14:05 UTC
        https://reuters.com/...
    """
    emoji = _score_emoji(impact_score)

    # Truncate title to 120 chars to keep message compact
    title_display = title[:120] + ("…" if len(title) > 120 else "")

    # Reasons: top 3, bullet-separated
    reasons_line = " • ".join(r for r in reasons[:3]) if reasons else "—"

    # Timestamp
    if published_at:
        # Ensure UTC
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        time_str = published_at.strftime("%Y-%m-%d %H:%M UTC")
    else:
        time_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Escape HTML special chars in user-supplied text
    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    text = (
        f"{emoji} <b>[IMPACT {impact_score}]</b> {esc(title_display)}\n"
        f"• {esc(reasons_line)}\n"
        f"• <i>{esc(source_name)}</i> | {time_str}\n"
        f"{url}"
    )

    # Telegram hard limit
    return text[:4096]
