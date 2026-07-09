from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FaceDistanceConfig:
    mid_height_ratio: float = 0.13
    close_height_ratio: float = 0.23
    mid_area_ratio: float = 0.015
    close_area_ratio: float = 0.035
    stable_window_frames: int = 20
    stable_close_min_frames: int = 12


@dataclass
class FaceDistanceStatus:
    person_detected: bool = False
    distance: str = "NONE"
    face_height_ratio: float = 0.0
    face_area_ratio: float = 0.0
    stable_close: bool = False
    close_votes: int = 0
    window_size: int = 0
    bbox: dict[str, float] | None = None


@dataclass
class FaceDistanceEstimator:
    """Estimate whether a person is close enough by face bbox size.

    This is intentionally a demo-grade distance proxy. It does not estimate
    metric distance; it uses the relative face box height/area in the image.
    """

    config: FaceDistanceConfig = field(default_factory=FaceDistanceConfig)

    def __post_init__(self) -> None:
        self._close_flags: deque[bool] = deque(maxlen=self.config.stable_window_frames)

    def reset(self) -> None:
        self._close_flags.clear()

    def update_from_mediapipe_detections(self, detections: Any) -> FaceDistanceStatus:
        largest = self._largest_relative_bbox(detections)
        if largest is None:
            self._close_flags.append(False)
            return FaceDistanceStatus(
                person_detected=False,
                distance="NONE",
                stable_close=self._is_stable_close(),
                close_votes=sum(self._close_flags),
                window_size=len(self._close_flags),
            )

        width = max(float(largest.get("width", 0.0)), 0.0)
        height = max(float(largest.get("height", 0.0)), 0.0)
        area = width * height

        if height >= self.config.close_height_ratio or area >= self.config.close_area_ratio:
            distance = "CLOSE"
        elif height >= self.config.mid_height_ratio or area >= self.config.mid_area_ratio:
            distance = "MID"
        else:
            distance = "FAR"

        self._close_flags.append(distance == "CLOSE")

        return FaceDistanceStatus(
            person_detected=True,
            distance=distance,
            face_height_ratio=height,
            face_area_ratio=area,
            stable_close=self._is_stable_close(),
            close_votes=sum(self._close_flags),
            window_size=len(self._close_flags),
            bbox=largest,
        )

    def _is_stable_close(self) -> bool:
        return (
            len(self._close_flags) >= min(self.config.stable_window_frames, self.config.stable_close_min_frames)
            and sum(self._close_flags) >= self.config.stable_close_min_frames
        )

    @staticmethod
    def _largest_relative_bbox(detections: Any) -> dict[str, float] | None:
        if not detections:
            return None

        best: dict[str, float] | None = None
        best_area = 0.0
        for detection in detections:
            try:
                box = detection.location_data.relative_bounding_box
                candidate = {
                    "xmin": float(box.xmin),
                    "ymin": float(box.ymin),
                    "width": float(box.width),
                    "height": float(box.height),
                }
            except Exception:
                continue

            area = max(candidate["width"], 0.0) * max(candidate["height"], 0.0)
            if area > best_area:
                best = candidate
                best_area = area
        return best
