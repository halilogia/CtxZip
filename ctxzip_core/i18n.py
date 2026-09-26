"""Namespace-based localization catalogs with locale fallback and interpolation."""
from __future__ import annotations

from functools import lru_cache
import json
import os
from pathlib import Path
import re

CATALOG_ROOT = Path(__file__).resolve().parent.parent / "locales"
SUPPORTED_LANGUAGES = ("en", "tr")
DEFAULT_LANGUAGE = "tr"
FALLBACK_LANGUAGE = "en"
_PLACEHOLDER = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")

class LocalizationError(ValueError):
    """Raised for unsupported locales or invalid/missing catalog entries."""


def normalize_language(language: str | None) -> str:
    locale = (language or DEFAULT_LANGUAGE).strip().replace("_", "-").lower()
    primary = locale.split("-", 1)[0]
    if primary not in SUPPORTED_LANGUAGES:
        raise LocalizationError(
            f"Unsupported language {language!r}. Choose one of: {', '.join(SUPPORTED_LANGUAGES)}."
        )
    return primary


@lru_cache(maxsize=None)
def _load_catalog(language: str, namespace: str) -> dict[str, str]:
    path = CATALOG_ROOT / language / f"{namespace}.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, (str, dict)) for k, v in data.items()):
        raise LocalizationError(f"Invalid localization catalog: {path}")
    return data


def _catalog_value(language: str, namespace: str, key: str) -> str | dict:
    selected = _load_catalog(language, namespace)
    fallback = _load_catalog(FALLBACK_LANGUAGE, namespace)
    value = selected.get(key, fallback.get(key))
    if value is None:
        raise LocalizationError(f"Missing translation: {language}:{namespace}:{key}")
    return value


def _all_keys(language: str) -> set[tuple[str, str]]:
    result = set()
    locale_dir = CATALOG_ROOT / language
    for path in locale_dir.glob("*.json"):
        values = _load_catalog(language, path.stem)
        result.update((path.stem, key) for key in values)
    return result


def validate_catalogs() -> None:
    """Fail early when locales drift in keys or interpolation placeholders."""
    expected = _all_keys(FALLBACK_LANGUAGE)
    for language in SUPPORTED_LANGUAGES:
        actual = _all_keys(language)
        missing = expected - actual
        extra = actual - expected
        if missing or extra:
            raise LocalizationError(
                f"Catalog {language} key mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
            )
        for namespace, key in expected:
            source = _catalog_value(FALLBACK_LANGUAGE, namespace, key)
            translated = _catalog_value(language, namespace, key)
            if isinstance(source, str) and isinstance(translated, str):
                if sorted(_PLACEHOLDER.findall(source)) != sorted(_PLACEHOLDER.findall(translated)):
                    raise LocalizationError(f"Placeholder mismatch: {language}:{namespace}:{key}")
            elif isinstance(source, dict) and isinstance(translated, dict):
                if set(source) != set(translated):
                    raise LocalizationError(f"Plural form mismatch: {language}:{namespace}:{key}")
                for category, source_form in source.items():
                    translated_form = translated[category]
                    if sorted(_PLACEHOLDER.findall(source_form)) != sorted(_PLACEHOLDER.findall(translated_form)):
                        raise LocalizationError(f"Plural placeholder mismatch: {language}:{namespace}:{key}:{category}")
            else:
                raise LocalizationError(f"Translation type mismatch: {language}:{namespace}:{key}")


def translate(language: str | None, key: str, *, namespace: str | None = None, **values: object) -> str:
    locale = normalize_language(language)
    if ":" in key:
        namespace, message_id = key.split(":", 1)
    else:
        message_id = key
        if namespace is None:
            matches = [
                candidate for candidate in sorted(path.stem for path in (CATALOG_ROOT / FALLBACK_LANGUAGE).glob("*.json"))
                if message_id in _load_catalog(locale, candidate)
                or message_id in _load_catalog(FALLBACK_LANGUAGE, candidate)
            ]
            if len(matches) != 1:
                raise LocalizationError(f"Translation key {message_id!r} found in {len(matches)} namespaces; specify namespace.")
            namespace = matches[0]
    template = _catalog_value(locale, namespace, message_id)
    if isinstance(template, dict):
        count = values.get("count")
        plural_key = "one" if count == 1 else "other"
        template = template.get(plural_key) or template.get("other")
    if not isinstance(template, str):
        raise LocalizationError(f"Invalid message: {locale}:{namespace}:{message_id}")
    return _PLACEHOLDER.sub(lambda match: str(values.get(match.group(1), match.group(0))), template)


def preferred_language(configured: str | None = None, explicit: str | None = None) -> str:
    return normalize_language(explicit or os.environ.get("CTXZIP_LANG") or configured)


def summary_prompt_version(language: str | None) -> str:
    """Version prompts by locale while preserving the existing Turkish ID."""
    return "ozet-v1" if normalize_language(language) == "tr" else "summary-v1"
