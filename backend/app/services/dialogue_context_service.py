from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

PendingSlot = Literal["room_type", "budget", "style", "preferred_color", "priority"]


class DialogueContext(BaseModel):
    session_id: str = "demo-session-001"
    pending_slot: PendingSlot | None = None
    last_assistant_question: str | None = None
    last_response_type: str | None = None
    last_user_text: str = ""
    turn_index: int = 0


class DialogueContextService:
    def __init__(self) -> None:
        self.sessions_dir = Path(__file__).resolve().parents[1] / "data" / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def load(self, session_id: str = "demo-session-001") -> DialogueContext:
        path = self._path(session_id)
        if not path.exists():
            return DialogueContext(session_id=session_id)
        try:
            with path.open("r", encoding="utf-8") as f:
                return DialogueContext.model_validate(json.load(f))
        except (OSError, ValueError):
            return DialogueContext(session_id=session_id)

    def save(self, context: DialogueContext) -> DialogueContext:
        path = self._path(context.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(context.model_dump(), f, ensure_ascii=False, indent=2)
        return context

    def reset(self, session_id: str = "demo-session-001") -> DialogueContext:
        return self.save(DialogueContext(session_id=session_id))

    def advance(
        self,
        *,
        context: DialogueContext,
        user_text: str,
        pending_slot: PendingSlot | None,
        assistant_question: str | None,
        response_type: str,
    ) -> DialogueContext:
        updated = context.model_copy(
            update={
                "pending_slot": pending_slot,
                "last_assistant_question": assistant_question,
                "last_response_type": response_type,
                "last_user_text": user_text,
                "turn_index": context.turn_index + 1,
            }
        )
        return self.save(updated)

    def _path(self, session_id: str) -> Path:
        safe_id = "".join(ch for ch in session_id if ch.isalnum() or ch in {"-", "_"}) or "demo-session-001"
        return self.sessions_dir / f"{safe_id}.dialogue.json"
