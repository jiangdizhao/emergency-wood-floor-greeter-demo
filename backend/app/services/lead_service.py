from __future__ import annotations

import json
from pathlib import Path

from ..models import CustomerProfile


class LeadService:
    def __init__(self) -> None:
        self.sessions_dir = Path(__file__).resolve().parents[1] / "data" / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def load_profile(self, session_id: str = "demo-session-001") -> CustomerProfile:
        path = self._profile_path(session_id)
        if not path.exists():
            return CustomerProfile(session_id=session_id)
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return CustomerProfile.model_validate(data)

    def save_profile(self, profile: CustomerProfile) -> CustomerProfile:
        path = self._profile_path(profile.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(profile.model_dump(), f, ensure_ascii=False, indent=2)
        return profile

    def reset_profile(self, session_id: str = "demo-session-001") -> CustomerProfile:
        profile = CustomerProfile(session_id=session_id)
        self.save_profile(profile)
        return profile

    def _profile_path(self, session_id: str) -> Path:
        safe_id = "".join(ch for ch in session_id if ch.isalnum() or ch in {"-", "_"}) or "demo-session-001"
        return self.sessions_dir / f"{safe_id}.json"
