"""
Text normalization: strip HTML, unicode normalize, collapse whitespace.
Intentionally minimal — no stopword removal, no stemming at this layer.
"""
import re
import unicodedata


# Matches any HTML/XML tag
_HTML_TAG = re.compile(r"<[^>]+>")
# Collapses runs of whitespace (including \n \t) to a single space
_WHITESPACE = re.compile(r"\s+")
# Common HTML entities we care about
_ENTITIES = {
    "&amp;": "&", "&lt;": "<", "&gt;": ">",
    "&quot;": '"', "&#39;": "'", "&nbsp;": " ",
    "&apos;": "'",
}


def clean(text: str | None) -> str:
    """Return a clean, unicode-normalized plain-text string."""
    if not text:
        return ""

    # Decode HTML entities
    for entity, replacement in _ENTITIES.items():
        text = text.replace(entity, replacement)

    # Strip remaining HTML tags
    text = _HTML_TAG.sub(" ", text)

    # Unicode NFKC normalization (e.g. curly quotes → straight, ligatures)
    text = unicodedata.normalize("NFKC", text)

    # Collapse whitespace
    text = _WHITESPACE.sub(" ", text).strip()

    return text
