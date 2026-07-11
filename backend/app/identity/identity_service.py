from __future__ import annotations

import os
import secrets
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from .face_embedder import FaceEmbedder, FaceEmbeddingResult
from .repository import IdentityRepository

FrameSupplier = Callable[[], np.ndarray | None]


@dataclass
class IdentityCandidate:
    token: str
    customer_id: str
    score: float
    margin: float
    votes: int
    sample_count: int
    expires_at: float


class IdentityService:
    """Consent-based local face-memory service.

    Recognition only creates a short-lived candidate. A customer profile is not
    restored until the frontend explicitly confirms the candidate token.
    """

    def __init__(self, *, repository: IdentityRepository, embedder: FaceEmbedder) -> None:
        self.repository = repository
        self.embedder = embedder
        self.accept_threshold = float(os.getenv("FACE_ACCEPT_THRESHOLD", "0.45"))
        self.duplicate_threshold = float(os.getenv("FACE_DUPLICATE_THRESHOLD", "0.50"))
        self.margin_threshold = float(os.getenv("FACE_MARGIN_THRESHOLD", "0.04"))
        self.sample_count = max(3, int(os.getenv("FACE_RECOGNITION_SAMPLES", "8")))
        self.min_votes = max(2, int(os.getenv("FACE_MIN_VOTES", "3")))
        self.enrollment_samples = max(4, int(os.getenv("FACE_ENROLLMENT_SAMPLES", "10")))
        self.max_templates_per_customer = max(3, int(os.getenv("FACE_MAX_TEMPLATES", "5")))
        self.capture_interval_seconds = float(os.getenv("FACE_CAPTURE_INTERVAL_SECONDS", "0.16"))
        # Thirty seconds was too short for a customer-facing confirmation dialog.
        # Keep the token local and temporary, but allow a realistic decision window.
        self.candidate_ttl_seconds = float(os.getenv("FACE_CANDIDATE_TTL_SECONDS", "180"))
        self._operation_lock = threading.RLock()
        self._candidate_lock = threading.RLock()
        self._candidates: dict[str, IdentityCandidate] = {}

    def status(self) -> dict[str, Any]:
        self._purge_expired_candidates()
        return {
            "enabled": True,
            "model": self.embedder.status(),
            "customer_count": self.repository.customer_count(),
            "face_template_count": self.repository.face_template_count(),
            "accept_threshold": self.accept_threshold,
            "margin_threshold": self.margin_threshold,
            "min_votes": self.min_votes,
            "recognition_samples": self.sample_count,
            "candidate_count": len(self._candidates),
            "candidate_ttl_seconds": int(self.candidate_ttl_seconds),
            "stores_raw_photos": False,
            "requires_confirmation": True,
        }

    def recognize(self, frame_supplier: FrameSupplier) -> dict[str, Any]:
        if not self.embedder.available:
            return {
                "status": "unavailable",
                "candidate_found": False,
                "message": "人脸识别模型尚未安装。",
                "error": self.embedder.load_error,
            }
        templates = self.repository.load_active_templates(
            model_name=self.embedder.MODEL_NAME,
            model_version=self.embedder.MODEL_VERSION,
        )
        if not templates:
            return {
                "status": "no_enrolled_customers",
                "candidate_found": False,
                "message": "当前还没有已同意保存的人脸记忆。",
            }

        with self._operation_lock:
            samples = self._capture_samples(frame_supplier, self.sample_count)
        if len(samples) < self.min_votes:
            return {
                "status": "no_face",
                "candidate_found": False,
                "valid_samples": len(samples),
                "message": "没有采集到足够清晰的人脸，请正对屏幕后重试。",
            }

        per_sample_results: list[tuple[str, float, float]] = []
        scores_by_customer: dict[str, list[float]] = defaultdict(list)
        for sample in samples:
            customer_scores: dict[str, float] = {}
            for template in templates:
                score = self._cosine(sample.embedding, template["embedding"])
                customer_id = str(template["customer_id"])
                customer_scores[customer_id] = max(customer_scores.get(customer_id, -1.0), score)
            ranked = sorted(customer_scores.items(), key=lambda item: item[1], reverse=True)
            if not ranked:
                continue
            top_customer, top_score = ranked[0]
            second_score = ranked[1][1] if len(ranked) > 1 else -1.0
            margin = top_score - second_score
            per_sample_results.append((top_customer, top_score, margin))
            scores_by_customer[top_customer].append(top_score)

        accepted_votes = [
            customer_id
            for customer_id, score, margin in per_sample_results
            if score >= self.accept_threshold and margin >= self.margin_threshold
        ]
        if not accepted_votes:
            best_score = max((score for _, score, _ in per_sample_results), default=-1.0)
            self.repository.record_identity_event(
                event_type="recognition_no_match",
                score=best_score if best_score >= 0 else None,
                detail=f"valid_samples={len(samples)}",
            )
            return {
                "status": "no_match",
                "candidate_found": False,
                "valid_samples": len(samples),
                "message": "没有找到可信的历史客户匹配，将按新客户开始。",
            }

        vote_counts = Counter(accepted_votes)
        customer_id, votes = vote_counts.most_common(1)[0]
        winning_rows = [row for row in per_sample_results if row[0] == customer_id]
        mean_score = float(np.mean([row[1] for row in winning_rows]))
        mean_margin = float(np.mean([row[2] for row in winning_rows]))
        if votes < self.min_votes or mean_score < self.accept_threshold or mean_margin < self.margin_threshold:
            self.repository.record_identity_event(
                event_type="recognition_unstable",
                customer_id=customer_id,
                score=mean_score,
                detail=f"votes={votes};samples={len(samples)};margin={mean_margin:.4f}",
            )
            return {
                "status": "unstable_match",
                "candidate_found": False,
                "valid_samples": len(samples),
                "message": "识别结果不够稳定，将按新客户开始。",
            }

        token = secrets.token_urlsafe(24)
        candidate = IdentityCandidate(
            token=token,
            customer_id=customer_id,
            score=mean_score,
            margin=mean_margin,
            votes=votes,
            sample_count=len(samples),
            expires_at=time.time() + self.candidate_ttl_seconds,
        )
        with self._candidate_lock:
            self._purge_expired_candidates_locked()
            self._candidates[token] = candidate
        self.repository.record_identity_event(
            event_type="candidate_created",
            customer_id=customer_id,
            score=mean_score,
            detail=f"votes={votes};samples={len(samples)};margin={mean_margin:.4f}",
        )
        return {
            "status": "candidate_found",
            "candidate_found": True,
            "candidate_token": token,
            "expires_in_seconds": int(self.candidate_ttl_seconds),
            "requires_confirmation": True,
            "confidence_band": "high",
            "valid_samples": len(samples),
            "message": "可能找到了之前的本地选购记录，请由客户确认是否继续。",
        }

    def get_candidate(self, token: str) -> IdentityCandidate | None:
        """Read a live candidate without consuming it.

        Session creation can still fail because of a transient file, database, or
        frontend interruption. Keeping the token until the confirmation flow has
        completed makes the dialog safely retryable instead of trapping the user.
        """
        with self._candidate_lock:
            self._purge_expired_candidates_locked()
            return self._candidates.get(token)

    def finalize_candidate(self, token: str, *, accepted: bool) -> IdentityCandidate | None:
        with self._candidate_lock:
            self._purge_expired_candidates_locked()
            candidate = self._candidates.pop(token, None)
        if candidate is None:
            return None
        self.repository.record_identity_event(
            event_type="candidate_confirmed" if accepted else "candidate_rejected",
            customer_id=candidate.customer_id,
            score=candidate.score,
            detail=f"votes={candidate.votes};samples={candidate.sample_count}",
        )
        return candidate

    def consume_candidate(self, token: str, *, accepted: bool) -> IdentityCandidate | None:
        """Backward-compatible alias for callers that truly want one-step consume."""
        return self.finalize_candidate(token, accepted=accepted)

    def enroll(
        self,
        *,
        frame_supplier: FrameSupplier,
        display_name: str | None,
        consent: bool,
    ) -> dict[str, Any]:
        if not consent:
            return {
                "status": "consent_required",
                "enrolled": False,
                "message": "只有在客户明确同意后才能保存本地人脸特征。",
            }
        if not self.embedder.available:
            return {
                "status": "unavailable",
                "enrolled": False,
                "message": "人脸识别模型尚未安装。",
                "error": self.embedder.load_error,
            }

        with self._operation_lock:
            samples = self._capture_samples(frame_supplier, self.enrollment_samples)
        minimum_enrollment_samples = min(5, self.enrollment_samples)
        if len(samples) < minimum_enrollment_samples:
            return {
                "status": "insufficient_quality",
                "enrolled": False,
                "valid_samples": len(samples),
                "required_samples": minimum_enrollment_samples,
                "message": "没有采集到足够清晰的人脸。请正对屏幕、保持光线充足后重试。",
            }

        samples = self._deduplicate_and_rank(samples)
        templates = self.repository.load_active_templates(
            model_name=self.embedder.MODEL_NAME,
            model_version=self.embedder.MODEL_VERSION,
        )
        duplicate = self._find_duplicate(samples, templates)
        if duplicate is not None:
            customer_id, score = duplicate
            return {
                "status": "already_enrolled",
                "enrolled": False,
                "existing_customer_id": customer_id,
                "score": score,
                "message": "该人脸可能已经保存。请先使用回访识别，避免重复建档。",
            }

        customer_id = self.repository.create_customer(display_name=display_name)
        selected = samples[: self.max_templates_per_customer]
        for sample in selected:
            self.repository.add_face_template(
                customer_id=customer_id,
                embedding=sample.embedding,
                quality_score=sample.quality_score,
                model_name=self.embedder.MODEL_NAME,
                model_version=self.embedder.MODEL_VERSION,
            )
        self.repository.record_identity_event(
            event_type="enrolled",
            customer_id=customer_id,
            detail=f"templates={len(selected)};valid_samples={len(samples)}",
        )
        return {
            "status": "enrolled",
            "enrolled": True,
            "customer_id": customer_id,
            "template_count": len(selected),
            "valid_samples": len(samples),
            "stores_raw_photos": False,
            "message": "已在本机保存人脸特征和选购记忆。未保存原始人脸照片。",
        }

    def _capture_samples(self, frame_supplier: FrameSupplier, requested: int) -> list[FaceEmbeddingResult]:
        samples: list[FaceEmbeddingResult] = []
        attempts = max(requested * 2, requested + 4)
        for _ in range(attempts):
            frame = frame_supplier()
            if frame is not None:
                result = self.embedder.extract(frame)
                if result is not None:
                    samples.append(result)
                    if len(samples) >= requested:
                        break
            time.sleep(max(self.capture_interval_seconds, 0.02))
        return samples

    @staticmethod
    def _deduplicate_and_rank(samples: list[FaceEmbeddingResult]) -> list[FaceEmbeddingResult]:
        ranked = sorted(samples, key=lambda sample: sample.quality_score, reverse=True)
        selected: list[FaceEmbeddingResult] = []
        for sample in ranked:
            if all(IdentityService._cosine(sample.embedding, item.embedding) < 0.995 for item in selected):
                selected.append(sample)
        return selected or ranked

    def _find_duplicate(
        self,
        samples: list[FaceEmbeddingResult],
        templates: list[dict[str, Any]],
    ) -> tuple[str, float] | None:
        if not templates:
            return None
        best_customer: str | None = None
        best_score = -1.0
        for sample in samples[: self.max_templates_per_customer]:
            for template in templates:
                score = self._cosine(sample.embedding, template["embedding"])
                if score > best_score:
                    best_customer = str(template["customer_id"])
                    best_score = score
        if best_customer and best_score >= self.duplicate_threshold:
            return best_customer, float(best_score)
        return None

    def _purge_expired_candidates(self) -> None:
        with self._candidate_lock:
            self._purge_expired_candidates_locked()

    def _purge_expired_candidates_locked(self) -> None:
        now = time.time()
        expired = [token for token, candidate in self._candidates.items() if candidate.expires_at <= now]
        for token in expired:
            self._candidates.pop(token, None)

    @staticmethod
    def _cosine(left: np.ndarray, right: np.ndarray) -> float:
        left_vector = np.asarray(left, dtype=np.float32).reshape(-1)
        right_vector = np.asarray(right, dtype=np.float32).reshape(-1)
        if left_vector.size != right_vector.size or left_vector.size == 0:
            return -1.0
        left_norm = float(np.linalg.norm(left_vector))
        right_norm = float(np.linalg.norm(right_vector))
        if left_norm <= 1e-8 or right_norm <= 1e-8:
            return -1.0
        return float(np.dot(left_vector, right_vector) / (left_norm * right_norm))
