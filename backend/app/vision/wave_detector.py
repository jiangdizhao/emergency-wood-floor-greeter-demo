from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WaveDetectorConfig:
    max_buffer_seconds: float = 0.65
    min_motion_seconds: float = 0.04
    min_points: int = 3
    min_dx: float = 0.07
    max_abs_dy: float = 0.38
    min_abs_speed_x: float = 0.10
    cooldown_seconds: float = 1.00
    max_lost_frames: int = 5


@dataclass
class WaveDebugInfo:
    count: int = 0
    x_span: float = 0.0
    speed: float = 0.0
    dy: float = 0.0
    direction_candidate: str = "NONE"
    reason: str = "init"
    lost_frames: int = 0


@dataclass
class WaveDetector:
    """Detect a left/right waving greeting from MediaPipe hand landmarks.

    The detector tracks the palm center trajectory. Any clear horizontal swipe
    is mapped to a greeting wave by the higher-level vision service.
    """

    config: WaveDetectorConfig = field(default_factory=WaveDetectorConfig)

    def __post_init__(self) -> None:
        self.points: deque[tuple[float, float, float]] = deque()
        self.last_trigger_time = 0.0
        self.lost_frames = 0
        self.debug = WaveDebugInfo()

    def reset(self) -> None:
        self.points.clear()
        self.last_trigger_time = 0.0
        self.lost_frames = 0
        self.debug = WaveDebugInfo(reason="reset")

    def update_from_hand_landmarks(self, now: float, hand_landmarks: Any) -> str | None:
        x, y = self._palm_center(hand_landmarks)
        return self.update(now, x, y)

    def update_no_hand(self) -> None:
        self.lost_frames += 1
        if self.lost_frames > self.config.max_lost_frames:
            self.points.clear()
            self.debug.reason = "hand_lost_clear"
        else:
            self.debug.reason = f"hand_lost_keep_{self.lost_frames}"
        self.debug.lost_frames = self.lost_frames
        self.debug.count = len(self.points)

    def update(self, now: float, x: float, y: float) -> str | None:
        self.lost_frames = 0
        self.points.append((now, x, y))

        while self.points and (now - self.points[0][0]) > self.config.max_buffer_seconds:
            self.points.popleft()

        self.debug.count = len(self.points)
        self.debug.lost_frames = self.lost_frames

        if len(self.points) < self.config.min_points:
            self.debug.reason = "not_enough_points"
            return None

        if (now - self.last_trigger_time) < self.config.cooldown_seconds:
            self.debug.reason = "cooldown"
            return None

        pts = list(self.points)
        xs = [p[1] for p in pts]
        min_i = min(range(len(xs)), key=lambda i: xs[i])
        max_i = max(range(len(xs)), key=lambda i: xs[i])

        t_min, x_min, y_min = pts[min_i]
        t_max, x_max, y_max = pts[max_i]
        x_span = x_max - x_min
        self.debug.x_span = x_span

        if x_span < self.config.min_dx:
            self.debug.reason = "x_span_too_small"
            self.debug.direction_candidate = "NONE"
            return None

        if min_i < max_i:
            direction = "SWIPE_RIGHT"
            dt = max(t_max - t_min, 1e-6)
            dy = y_max - y_min
        elif max_i < min_i:
            direction = "SWIPE_LEFT"
            dt = max(t_min - t_max, 1e-6)
            dy = y_min - y_max
        else:
            self.debug.reason = "same_extreme_index"
            self.debug.direction_candidate = "NONE"
            return None

        speed = x_span / dt
        self.debug.speed = speed
        self.debug.dy = dy
        self.debug.direction_candidate = direction

        if dt < self.config.min_motion_seconds:
            self.debug.reason = "too_fast_or_unstable"
            return None

        if abs(dy) > self.config.max_abs_dy:
            self.debug.reason = "dy_too_large"
            return None

        if speed < self.config.min_abs_speed_x:
            self.debug.reason = "speed_too_low"
            return None

        self.last_trigger_time = now
        self.points.clear()
        self.debug.reason = "triggered"
        return direction

    @staticmethod
    def _palm_center(hand_landmarks: Any) -> tuple[float, float]:
        ids = [0, 5, 9, 13, 17]
        x = sum(hand_landmarks.landmark[i].x for i in ids) / len(ids)
        y = sum(hand_landmarks.landmark[i].y for i in ids) / len(ids)
        return float(x), float(y)
