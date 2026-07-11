from __future__ import annotations

import math
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np


@dataclass
class FaceEmbeddingResult:
    embedding: np.ndarray
    quality_score: float
    detector_score: float
    face_box: tuple[int, int, int, int]
    blur_score: float
    face_size_ratio: float


class FaceEmbedder:
    """OpenCV YuNet detector + SFace recognizer.

    Raw camera frames and aligned face crops are processed in memory only. The
    caller receives a normalized float32 embedding and quality metadata.
    """

    MODEL_NAME = "opencv-sface"
    MODEL_VERSION = "2021dec"

    def __init__(self, model_dir: str | Path | None = None) -> None:
        default_dir = Path(__file__).resolve().parents[1] / "data" / "models"
        self.model_dir = Path(model_dir or os.getenv("FACE_MODEL_DIR", default_dir))
        self.detector_path = Path(
            os.getenv(
                "FACE_DETECTOR_MODEL",
                self.model_dir / "face_detection_yunet_2023mar.onnx",
            )
        )
        self.recognizer_path = Path(
            os.getenv(
                "FACE_RECOGNIZER_MODEL",
                self.model_dir / "face_recognition_sface_2021dec.onnx",
            )
        )
        self.min_face_pixels = int(os.getenv("FACE_MIN_SIZE_PIXELS", "96"))
        self.min_blur_score = float(os.getenv("FACE_MIN_BLUR_SCORE", "35"))
        self.detector_score_threshold = float(os.getenv("FACE_DETECTOR_SCORE_THRESHOLD", "0.82"))
        self._lock = threading.RLock()
        self._detector: Any | None = None
        self._recognizer: Any | None = None
        self._load_error: str | None = None

    @property
    def available(self) -> bool:
        return self._ensure_loaded()

    @property
    def load_error(self) -> str | None:
        self._ensure_loaded()
        return self._load_error

    def status(self) -> dict[str, Any]:
        loaded = self._ensure_loaded()
        return {
            "available": loaded,
            "model_name": self.MODEL_NAME,
            "model_version": self.MODEL_VERSION,
            "detector_model": str(self.detector_path),
            "recognizer_model": str(self.recognizer_path),
            "detector_model_exists": self.detector_path.exists(),
            "recognizer_model_exists": self.recognizer_path.exists(),
            "error": self._load_error,
        }

    def extract(self, frame_bgr: np.ndarray) -> FaceEmbeddingResult | None:
        if frame_bgr is None or frame_bgr.size == 0:
            return None
        if not self._ensure_loaded():
            return None

        height, width = frame_bgr.shape[:2]
        with self._lock:
            self._detector.setInputSize((width, height))
            _, faces = self._detector.detect(frame_bgr)
            if faces is None or len(faces) == 0:
                return None

            face = self._choose_face(faces)
            x, y, w, h = [int(round(value)) for value in face[:4]]
            x = max(0, min(x, width - 1))
            y = max(0, min(y, height - 1))
            w = max(1, min(w, width - x))
            h = max(1, min(h, height - y))
            if min(w, h) < self.min_face_pixels:
                return None

            crop = frame_bgr[y : y + h, x : x + w]
            if crop.size == 0:
                return None
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            if blur_score < self.min_blur_score:
                return None

            aligned = self._recognizer.alignCrop(frame_bgr, face)
            feature = self._recognizer.feature(aligned)

        vector = np.asarray(feature, dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(vector))
        if not math.isfinite(norm) or norm <= 1e-8:
            return None
        vector = vector / norm

        detector_score = float(face[-1])
        face_size_ratio = float((w * h) / max(width * height, 1))
        quality_score = self._quality_score(
            detector_score=detector_score,
            blur_score=blur_score,
            face_size_ratio=face_size_ratio,
            width=w,
            height=h,
        )
        return FaceEmbeddingResult(
            embedding=vector.astype(np.float32, copy=False),
            quality_score=quality_score,
            detector_score=detector_score,
            face_box=(x, y, w, h),
            blur_score=blur_score,
            face_size_ratio=face_size_ratio,
        )

    def _ensure_loaded(self) -> bool:
        if self._detector is not None and self._recognizer is not None:
            return True
        with self._lock:
            if self._detector is not None and self._recognizer is not None:
                return True
            if self._load_error is not None:
                return False
            if not self.detector_path.exists() or not self.recognizer_path.exists():
                missing = []
                if not self.detector_path.exists():
                    missing.append(str(self.detector_path))
                if not self.recognizer_path.exists():
                    missing.append(str(self.recognizer_path))
                self._load_error = "Face model files are missing: " + ", ".join(missing)
                return False
            try:
                detector_factory = getattr(cv2, "FaceDetectorYN", None)
                recognizer_factory = getattr(cv2, "FaceRecognizerSF", None)
                if detector_factory is not None and hasattr(detector_factory, "create"):
                    self._detector = detector_factory.create(
                        str(self.detector_path),
                        "",
                        (320, 320),
                        self.detector_score_threshold,
                        0.3,
                        5000,
                    )
                else:
                    self._detector = cv2.FaceDetectorYN_create(
                        str(self.detector_path),
                        "",
                        (320, 320),
                        self.detector_score_threshold,
                        0.3,
                        5000,
                    )

                if recognizer_factory is not None and hasattr(recognizer_factory, "create"):
                    self._recognizer = recognizer_factory.create(str(self.recognizer_path), "")
                else:
                    self._recognizer = cv2.FaceRecognizerSF_create(str(self.recognizer_path), "")
                self._load_error = None
                return True
            except Exception as exc:  # OpenCV raises cv2.error, but keep startup resilient.
                self._detector = None
                self._recognizer = None
                self._load_error = f"Could not load YuNet/SFace models: {type(exc).__name__}: {exc}"
                return False

    @staticmethod
    def _choose_face(faces: np.ndarray) -> np.ndarray:
        # Prefer a large, confident face. The score is the last YuNet column.
        return max(
            faces,
            key=lambda row: float(row[2] * row[3]) * max(float(row[-1]), 0.0),
        )

    @staticmethod
    def _quality_score(
        *,
        detector_score: float,
        blur_score: float,
        face_size_ratio: float,
        width: int,
        height: int,
    ) -> float:
        detector_component = min(max((detector_score - 0.7) / 0.3, 0.0), 1.0)
        blur_component = min(max((blur_score - 25.0) / 175.0, 0.0), 1.0)
        size_component = min(max((face_size_ratio - 0.025) / 0.18, 0.0), 1.0)
        aspect = min(width, height) / max(width, height)
        aspect_component = min(max((aspect - 0.55) / 0.35, 0.0), 1.0)
        score = (
            detector_component * 0.35
            + blur_component * 0.25
            + size_component * 0.25
            + aspect_component * 0.15
        )
        return float(min(max(score, 0.0), 1.0))
