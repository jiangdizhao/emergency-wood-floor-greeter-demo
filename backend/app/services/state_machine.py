from __future__ import annotations

from ..models import SessionState


class StoreSessionStateMachine:
    def __init__(self) -> None:
        self.state = SessionState.IDLE
        self.person_detected = False
        self.distance = "UNKNOWN"
        self.wave_detected = False
        self.greeting_source: str | None = None

    def reset(self) -> None:
        self.state = SessionState.IDLE
        self.person_detected = False
        self.distance = "UNKNOWN"
        self.wave_detected = False
        self.greeting_source = None

    def handle_event(self, event: str) -> dict:
        event = event.strip().lower()
        message = ""

        if event == "reset":
            self.reset()
            return {"message": "session reset"}

        if event == "person_far":
            self.person_detected = True
            self.distance = "FAR"
            self.wave_detected = False
            self.state = SessionState.PERSON_DETECTED_FAR
            message = "检测到顾客，但距离还不够近。"

        elif event == "person_close":
            self.person_detected = True
            self.distance = "CLOSE"
            if self.state in {SessionState.IDLE, SessionState.PERSON_DETECTED_FAR, SessionState.SESSION_END}:
                self.state = SessionState.PERSON_CLOSE_WAITING_GREETING
            message = "顾客已靠近，等待挥手或语音问候。"

        elif event == "wave":
            self.wave_detected = True
            if self.state == SessionState.PERSON_CLOSE_WAITING_GREETING:
                self.state = SessionState.GREETING_RECEIVED
                self.greeting_source = "wave"
                message = "检测到挥手问候。"
            else:
                message = "检测到挥手，但当前状态未等待问候。"

        elif event == "greeting":
            if self.state == SessionState.IDLE:
                self.person_detected = True
                self.distance = "CLOSE"
            self.state = SessionState.GREETING_RECEIVED
            self.greeting_source = "voice"
            message = "检测到语音问候。"

        elif event == "intro_started":
            self.state = SessionState.INTRODUCING_PRODUCTS
            message = "开始主动介绍产品。"

        elif event == "intro_finished":
            self.state = SessionState.CONVERSATION_ACTIVE
            message = "进入自由对话状态。"

        elif event == "end":
            self.state = SessionState.SESSION_END
            self.person_detected = False
            self.distance = "UNKNOWN"
            self.wave_detected = False
            message = "会话已结束。"

        else:
            message = f"未知事件: {event}"

        return {"message": message}

    def to_status_dict(self) -> dict:
        return {
            "state": self.state.value,
            "person_detected": self.person_detected,
            "distance": self.distance,
            "wave_detected": self.wave_detected,
            "greeting_source": self.greeting_source,
        }
