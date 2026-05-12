from __future__ import annotations

ARTICLE_LANGUAGE_OPTIONS = ("Hebrew", "English")
ARTICLE_PLATFORM_OPTIONS = ("Twitter/X", "LinkedIn", "Reddit", "Hashnode/Dev.to")

_LANGUAGE_ALIASES = {
    "english": "English",
    "hebrew": "Hebrew",
}

_PLATFORM_ALIASES = {
    "twitter": "Twitter/X",
    "x": "Twitter/X",
    "twitterx": "Twitter/X",
    "linkedin": "LinkedIn",
    "linkedinpost": "LinkedIn",
    "reddit": "Reddit",
    "hashnode": "Hashnode/Dev.to",
    "devto": "Hashnode/Dev.to",
    "hashnodedevto": "Hashnode/Dev.to",
}


def _option_key(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def normalize_article_language(value: str) -> str:
    normalized = _LANGUAGE_ALIASES.get(_option_key(value or ""))
    if normalized is None:
        raise ValueError("Choose English or Hebrew.")
    return normalized


def normalize_article_platform(value: str) -> str:
    normalized = _PLATFORM_ALIASES.get(_option_key(value or ""))
    if normalized is None:
        raise ValueError("Choose a supported target platform.")
    return normalized