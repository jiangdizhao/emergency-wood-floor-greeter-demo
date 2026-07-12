from __future__ import annotations

from contextvars import ContextVar
from typing import Literal

ResponseLanguage = Literal["zh", "en"]

_current_response_language: ContextVar[ResponseLanguage] = ContextVar(
    "woodfloor_response_language",
    default="zh",
)


def set_current_response_language(language: str | None) -> ResponseLanguage:
    normalized: ResponseLanguage = "en" if str(language or "").lower().startswith("en") else "zh"
    _current_response_language.set(normalized)
    return normalized


def get_current_response_language() -> ResponseLanguage:
    return _current_response_language.get()
