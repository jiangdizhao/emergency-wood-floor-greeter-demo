from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Iterator

import cv2
import numpy as np

from ..models import SessionState
from ..services.state_machine import StoreSessionStateMachine
from .face_distance import FaceDistanceEstimator, FaceDistanceStatus
from .wave_detector import WaveDetector


@dataclass
class VisionConfig:
    camera_index: int = 0
    frame_width: int = 640
    frame_height: int = 480
    fps: int = 30
    mirror: bool = True
    jpeg_quality: int = 80
    loop_sleep_seconds: float = 0.005
    greeting_banner_seconds: float = 2.0
    greeting_state_hold_seconds: float = 4.0
    reset_state_on_start: bool = True


@dataclass
class VisionStatus:
    ok: bool = True
    running: bool = False
    camera_opened: bool = False
    person_detected: bool = False
    distance: str = "NONE"
    face_height_ratio: float = 0.0
    face_area_ratio: float = 0.0
    face_close_votes: int = 0
    face_window_size: int = 0
    stable_close: bool = False
    wave_detected: bool = False
    raw_wave_event: str | None = None
    raw_wave_ignored_reason: str | None = None
    greeting_recent: bool = False
    last_wave_event: str | None = None
    last_wave_at: float | None = None
    state: str = SessionState.IDLE.value
    error: str | None = None
    fps_estimate: float = 0.0
    wave_debug: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "running": self.running,
            "camera_opened": self.camera_opened,
            "person_detected": self.person_detected,
            "distance": self.distance,
            "face_height_ratio": self.face_height_ratio,
            "face_area_ratio": self.face_area_ratio,
            "face_close_votes": self.face_close_votes,
            "face_window_size": self.face_window_size,
            "stable_close": self.stable_close,
            "wave_detected": self.wave_detected,
            "raw_wave_event": self.raw_wave_event,
            "raw_wave_ignored_reason": self.raw_wave_ignored_reason,
            "greeting_recent": self.greeting_recent,
            "last_wave_event": self.last_wave_event,
            "last_wave_at": self.last_wave_at,
            "state": self.state,
            "error": self.error,
            "fps_estimate": self.fps_estimate,
            "wave_debug": self.wave_debug,
        }


class VisionService:
    """Threaded OpenCV + MediaPipe vision service.

    The backend owns the camera. The frontend should display `/api/vision/stream`
    and poll `/api/vision/status`; it should not open the camera directly.
    """

    def __init__(self, state_machine: StoreSessionStateMachine, config: VisionConfig | None = None) -> None:
        self.state_machine = state_machine
        self.config = config or VisionConfig()
        self.face_estimator = FaceDistanceEstimator()
        self.wave_detector = WaveDetector()

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._cap: cv2.VideoCapture | None = None
        self._latest_jpeg: bytes = self._make_placeholder_frame("Vision service is stopped")
        self._status = VisionStatus(state=self.state_machine.state.value)
        self._last_accepted_wave_at: float | None = None
        self._last_accepted_wave_event: str | None = None
        self._last_raw_wave_event: str | None = None
        self._last_raw_wave_ignored_reason: str | None = None

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return {"ok": True, "message": "vision service already running", "status": self._status.to_dict()}

            self._stop_event.clear()
            self.face_estimator.reset()
            self.wave_detector.reset()
            self._last_accepted_wave_at = None
            self._last_accepted_wave_event = None
            self._last_raw_wave_event = None
            self._last_raw_wave_ignored_reason = None
            if self.config.reset_state_on_start:
                self.state_machine.handle_event("reset")
            self._status = VisionStatus(ok=True, running=True, state=self.state_machine.state.value)
            self._thread = threading.Thread(target=self._run_loop, name="VisionService", daemon=True)
            self._thread.start()
            return {"ok": True, "message": "vision service starting", "status": self._status.to_dict()}

    def stop(self) -> dict[str, Any]:
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        with self._lock:
            self._release_camera_locked()
            self._status.running = False
            self._status.camera_opened = False
            self._status.greeting_recent = False
            self._status.state = self.state_machine.state.value
            self._latest_jpeg = self._make_placeholder_frame("Vision service is stopped")
            status = self._status.to_dict()
        return {"ok": True, "message": "vision service stopped", "status": status}

    def get_status(self) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            status = self._status.to_dict()
        status["state"] = self.state_machine.state.value
        status["greeting_recent"] = self._is_recent_greeting(now)
        return status

    def mjpeg_generator(self) -> Iterator[bytes]:
        while True:
            with self._lock:
                frame = self._latest_jpeg
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            time.sleep(1 / max(self.config.fps, 1))

    def _run_loop(self) -> None:
        try:
            self._open_camera()
            with self._lock:
                camera_opened = bool(self._cap and self._cap.isOpened())
                self._status.camera_opened = camera_opened
                if not camera_opened:
                    self._status.ok = False
                    self._status.error = f"Cannot open camera index {self.config.camera_index}"
                    self._latest_jpeg = self._make_placeholder_frame(self._status.error)
                    self._status.running = False
                    return

            try:
                import mediapipe as mp
            except Exception as exc:
                with self._lock:
                    self._status.ok = False
                    self._status.error = f"MediaPipe import failed: {exc}"
                    self._latest_jpeg = self._make_placeholder_frame(self._status.error)
                    self._status.running = False
                return

            mp_face = mp.solutions.face_detection
            mp_hands = mp.solutions.hands
            mp_drawing = mp.solutions.drawing_utils

            last_fps_time = time.time()
            frame_counter = 0
            fps_estimate = 0.0

            with mp_face.FaceDetection(model_selection=0, min_detection_confidence=0.55) as face_detector, mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=1,
                model_complexity=0,
                min_detection_confidence=0.55,
                min_tracking_confidence=0.55,
            ) as hands:
                while not self._stop_event.is_set():
                    ok, frame = self._read_frame()
                    now = time.time()
                    if not ok or frame is None:
                        self._set_error("Camera frame read failed")
                        time.sleep(0.05)
                        continue

                    if self.config.mirror:
                        frame = cv2.flip(frame, 1)

                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    face_results = face_detector.process(rgb)
                    face_status = self.face_estimator.update_from_mediapipe_detections(face_results.detections)

                    hand_results = hands.process(rgb)
                    raw_wave_event: str | None = None
                    if hand_results.multi_hand_landmarks:
                        hand_landmarks = hand_results.multi_hand_landmarks[0]
                        raw_wave_event = self.wave_detector.update_from_hand_landmarks(now, hand_landmarks)
                        mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                    else:
                        self.wave_detector.update_no_hand()

                    accepted_wave_event = self._update_state_machine(
                        face_status=face_status,
                        raw_wave_event=raw_wave_event,
                        now=now,
                    )
                    greeting_recent = self._is_recent_greeting(now)
                    self._draw_overlay(
                        frame,
                        face_status=face_status,
                        wave_event=accepted_wave_event,
                        greeting_recent=greeting_recent,
                    )

                    encoded = self._encode_jpeg(frame)
                    frame_counter += 1
                    elapsed = now - last_fps_time
                    if elapsed >= 1.0:
                        fps_estimate = frame_counter / elapsed
                        frame_counter = 0
                        last_fps_time = now

                    with self._lock:
                        self._latest_jpeg = encoded
                        self._status = VisionStatus(
                            ok=True,
                            running=True,
                            camera_opened=True,
                            person_detected=face_status.person_detected,
                            distance=face_status.distance,
                            face_height_ratio=face_status.face_height_ratio,
                            face_area_ratio=face_status.face_area_ratio,
                            face_close_votes=face_status.close_votes,
                            face_window_size=face_status.window_size,
                            stable_close=face_status.stable_close,
                            wave_detected=accepted_wave_event is not None,
                            raw_wave_event=self._last_raw_wave_event,
                            raw_wave_ignored_reason=self._last_raw_wave_ignored_reason,
                            greeting_recent=greeting_recent,
                            last_wave_event=self._last_accepted_wave_event,
                            last_wave_at=self._last_accepted_wave_at,
                            state=self.state_machine.state.value,
                            error=None,
                            fps_estimate=fps_estimate,
                            wave_debug=self.wave_detector.debug.__dict__.copy(),
                        )

                    time.sleep(self.config.loop_sleep_seconds)

        except Exception as exc:
            self._set_error(f"Vision loop crashed: {exc}")
        finally:
            with self._lock:
                self._release_camera_locked()
                self._status.running = False
                self._status.camera_opened = False
                self._status.greeting_recent = False
                self._status.state = self.state_machine.state.value

    def _open_camera(self) -> None:
        with self._lock:
            self._release_camera_locked()
            cap = cv2.VideoCapture(self.config.camera_index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(self.config.camera_index)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.frame_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.frame_height)
            cap.set(cv2.CAP_PROP_FPS, self.config.fps)
            self._cap = cap

    def _read_frame(self) -> tuple[bool, np.ndarray | None]:
        cap = self._cap
        if cap is None:
            return False, None
        return cap.read()

    def _release_camera_locked(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def _update_state_machine(self, face_status: FaceDistanceStatus, raw_wave_event: str | None, now: float) -> str | None:
        current = self.state_machine.state
        is_stably_close = face_status.person_detected and face_status.distance == "CLOSE" and face_status.stable_close

        if is_stably_close:
            if current in {SessionState.IDLE, SessionState.PERSON_DETECTED_FAR, SessionState.SESSION_END}:
                self.state_machine.handle_event("person_close")
        elif face_status.person_detected:
            if current in {SessionState.IDLE, SessionState.PERSON_DETECTED_FAR, SessionState.PERSON_CLOSE_WAITING_GREETING, SessionState.SESSION_END}:
                self.state_machine.handle_event("person_far")
            self._clear_pending_greeting_if_needed()
        else:
            if current in {SessionState.IDLE, SessionState.PERSON_DETECTED_FAR, SessionState.PERSON_CLOSE_WAITING_GREETING, SessionState.SESSION_END}:
                self.state_machine.handle_event("person_lost")
            self._clear_pending_greeting_if_needed()

        if self.state_machine.state == SessionState.GREETING_RECEIVED and self._last_accepted_wave_at is not None:
            if now - self._last_accepted_wave_at > self.config.greeting_state_hold_seconds:
                self.state_machine.handle_event("greeting_timeout")

        if raw_wave_event:
            self._last_raw_wave_event = raw_wave_event
            if self.state_machine.state != SessionState.PERSON_CLOSE_WAITING_GREETING:
                self._last_raw_wave_ignored_reason = f"ignored_state_{self.state_machine.state.value}"
                return None
            if not is_stably_close:
                self._last_raw_wave_ignored_reason = f"ignored_distance_{face_status.distance}_stable_{face_status.stable_close}"
                return None

            self.state_machine.handle_event("wave")
            self._last_accepted_wave_at = now
            self._last_accepted_wave_event = raw_wave_event
            self._last_raw_wave_ignored_reason = None
            return raw_wave_event

        return None

    def _clear_pending_greeting_if_needed(self) -> None:
        if self.state_machine.state in {SessionState.IDLE, SessionState.PERSON_DETECTED_FAR, SessionState.PERSON_CLOSE_WAITING_GREETING}:
            self._last_accepted_wave_at = None
            self._last_accepted_wave_event = None

    def _is_recent_greeting(self, now: float) -> bool:
        return self._last_accepted_wave_at is not None and (now - self._last_accepted_wave_at) <= self.config.greeting_banner_seconds

    def _draw_overlay(
        self,
        frame: np.ndarray,
        face_status: FaceDistanceStatus,
        wave_event: str | None,
        greeting_recent: bool,
    ) -> None:
        h, w = frame.shape[:2]
        if face_status.bbox:
            x1 = int(max(face_status.bbox["xmin"], 0.0) * w)
            y1 = int(max(face_status.bbox["ymin"], 0.0) * h)
            x2 = int(min(face_status.bbox["xmin"] + face_status.bbox["width"], 1.0) * w)
            y2 = int(min(face_status.bbox["ymin"] + face_status.bbox["height"], 1.0) * h)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)

        wave_text = wave_event or "NONE"
        if self._last_raw_wave_ignored_reason and not wave_event:
            wave_text = f"IGNORED ({self._last_raw_wave_ignored_reason})"

        lines = [
            f"Person: {'YES' if face_status.person_detected else 'NO'}",
            f"Distance: {face_status.distance} stable={face_status.stable_close}",
            f"Face h={face_status.face_height_ratio:.2f} area={face_status.face_area_ratio:.3f}",
            f"Wave: {wave_text} reason={self.wave_detector.debug.reason}",
            f"State: {self.state_machine.state.value}",
        ]
        y = 28
        for line in lines:
            cv2.putText(frame, line, (18, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
            y += 28

        if greeting_recent:
            cv2.putText(frame, "Greeting detected", (18, h - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

    def _set_error(self, message: str) -> None:
        with self._lock:
            self._status.ok = False
            self._status.error = message
            self._status.state = self.state_machine.state.value
            self._latest_jpeg = self._make_placeholder_frame(message)

    def _encode_jpeg(self, frame: np.ndarray) -> bytes:
        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.config.jpeg_quality])
        if not ok:
            return self._make_placeholder_frame("JPEG encode failed")
        return encoded.tobytes()

    def _make_placeholder_frame(self, message: str) -> bytes:
        frame = np.zeros((self.config.frame_height, self.config.frame_width, 3), dtype=np.uint8)
        cv2.putText(frame, message[:70], (28, self.config.frame_height // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.config.jpeg_quality])
        if not ok:
            return b""
        return encoded.tobytes()
