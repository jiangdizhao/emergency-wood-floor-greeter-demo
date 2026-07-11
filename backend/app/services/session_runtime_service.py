from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel

from ..models import DialogueProvider


class SessionRuntimeConfig(BaseModel):
    session_id: str = "demo-session-001"
    provider_mode: DialogueProvider


class SessionRuntimeService:
    def __init__(self) -> None:
        self.sessions_dir = Path(__file__).resolve().parents[1] / "data" / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def load(self, session_id: str = "demo-session-001") -> SessionRuntimeConfig:
        path = self._path(session_id)
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return SessionRuntimeConfig.model_validate(json.load(f))
        return SessionRuntimeConfig(session_id=session_id, provider_mode=self._default_provider())

    def set_provider(self, session_id: str, provider_mode: DialogueProvider) -> SessionRuntimeConfig:
        config = SessionRuntimeConfig(session_id=session_id, provider_mode=provider_mode)
        path = self._path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(config.model_dump(), f, ensure_ascii=False, indent=2)
        return config

    @staticmethod
    def provider_label(provider_mode: DialogueProvider) -> str:
        return "Cloud Intelligence · Terra" if provider_mode == "terra" else "Private Local AI · Qwen 3.5"

    @staticmethod
    def _default_provider() -> DialogueProvider:
        configured = os.getenv("DEFAULT_DIALOGUE_PROVIDER", "").strip().lower()
        if configured in {"terra", "qwen"}:
            return configured  # type: ignore[return-value]
        return "terra" if os.getenv("OPENAI_API_KEY", "").strip() else "qwen"

    def _path(self, session_id: str) -> Path:
        safe_id = "".join(ch for ch in session_id if ch.isalnum() or ch in {"-", "_"}) or "demo-session-001"
        return self.sessions_dir / f"{safe_id}.runtime.json"
