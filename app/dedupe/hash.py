"""
Hash-based exact deduplication.
sha256(normalized_title_lower | canonical_url)
"""
import hashlib


def compute(title: str, canonical_url: str) -> str:
    """Return hex SHA-256 digest for the given title + URL pair."""
    payload = f"{title.lower().strip()}|{canonical_url}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
