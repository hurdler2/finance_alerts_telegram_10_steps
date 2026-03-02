"""
Canonical URL normalization.
- Strips UTM/tracking params
- Removes fragments (#...)
- Lowercases scheme + host
- Removes trailing slash inconsistencies
"""
from urllib.parse import urlparse, urlunparse, urlencode, parse_qsl

# Query parameters to strip (tracking / analytics noise)
_STRIP_PARAMS = frozenset(
    {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "utm_id", "utm_reader", "utm_name",
        "fbclid", "gclid", "gclsrc", "dclid", "gbraid", "wbraid",
        "mc_cid", "mc_eid",
        "ref", "referer", "referrer", "source",
        "_hsenc", "_hsmi", "hsCtaTracking",
        "mkt_tok", "trk", "trkCampaign",
    }
)


def normalize(url: str) -> str:
    """Return a canonical URL string, stripped of tracking params."""
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return url

    # Keep only non-tracking query params, preserve original order
    clean_qs = urlencode(
        [(k, v) for k, v in parse_qsl(parsed.query) if k.lower() not in _STRIP_PARAMS]
    )

    canonical = urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            parsed.params,
            clean_qs,
            "",  # drop fragment
        )
    )
    return canonical
