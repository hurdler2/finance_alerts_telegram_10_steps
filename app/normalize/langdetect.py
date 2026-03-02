"""
Language detection wrapper.
Returns ISO 639-1 code (e.g. "en", "de") or "unknown" on failure.
"""
from langdetect import detect, LangDetectException


def detect_lang(text: str) -> str:
    """Detect language of text. Returns 'unknown' if detection fails or text is too short."""
    if not text or len(text.split()) < 5:
        return "unknown"
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"
