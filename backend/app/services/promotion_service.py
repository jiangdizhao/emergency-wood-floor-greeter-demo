from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..models import CustomerProfile, FlooringProduct


class PromotionService:
    """Loads approved promotions and applies deterministic eligibility checks.

    Promotions are business data, not LLM knowledge. The LLM only receives the
    already-approved message and conditions for promotions selected here.
    """

    def __init__(self, data_path: str | Path | None = None) -> None:
        default_path = Path(__file__).resolve().parents[1] / "data" / "promotions.json"
        self.data_path = Path(data_path or default_path)
        self._payload: dict[str, Any] | None = None

    def catalog(self) -> dict[str, Any]:
        payload = self._load()
        return {
            "simulated": bool(payload.get("simulated", True)),
            "disclaimer": str(payload.get("disclaimer") or ""),
            "promotions": [dict(item) for item in payload.get("promotions", []) if isinstance(item, dict)],
        }

    def active_promotions(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        current = now or datetime.now(timezone.utc)
        output: list[dict[str, Any]] = []
        for promotion in self.catalog()["promotions"]:
            if not bool(promotion.get("active", False)):
                continue
            start = self._parse_datetime(promotion.get("start_at"))
            end = self._parse_datetime(promotion.get("end_at"))
            if start and current < start:
                continue
            if end and current > end:
                continue
            output.append(promotion)
        return output

    def eligible_promotions(
        self,
        *,
        profile: CustomerProfile,
        products: list[FlooringProduct],
        collection_ids: list[str] | None = None,
        now: datetime | None = None,
        limit: int = 2,
    ) -> list[dict[str, Any]]:
        product_ids = {product.id for product in products}
        collection_set = set(collection_ids or [])
        scored: list[tuple[int, str, dict[str, Any]]] = []

        for promotion in self.active_promotions(now=now):
            eligible_products = {str(item) for item in promotion.get("eligible_product_ids", [])}
            eligible_collections = {str(item) for item in promotion.get("eligible_collection_ids", [])}
            eligible_rooms = {str(item) for item in promotion.get("eligible_room_types", [])}
            minimum_area = promotion.get("minimum_area_sqm")

            score = 0
            if product_ids and product_ids.intersection(eligible_products):
                score += 8
            elif eligible_products:
                continue

            if collection_set and collection_set.intersection(eligible_collections):
                score += 4

            if profile.room_type:
                if eligible_rooms and profile.room_type not in eligible_rooms:
                    continue
                if profile.room_type in eligible_rooms:
                    score += 3

            area_status = "not_required"
            if minimum_area is not None:
                try:
                    minimum = float(minimum_area)
                except (TypeError, ValueError):
                    minimum = 0.0
                if profile.estimated_area_sqm is None:
                    area_status = "needs_area"
                    score += 1
                elif profile.estimated_area_sqm >= minimum:
                    area_status = "eligible"
                    score += 5
                else:
                    # Do not present a promotion as applicable when a known area
                    # clearly misses its threshold.
                    continue

            item = dict(promotion)
            item["area_status"] = area_status
            item["simulated"] = True
            scored.append((score, str(item.get("promotion_id") or ""), item))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in scored[: max(1, int(limit))]]

    def customer_catalog(self) -> dict[str, Any]:
        payload = self.catalog()
        return {
            "simulated": payload["simulated"],
            "disclaimer": payload["disclaimer"],
            "promotions": [
                {
                    "promotion_id": item.get("promotion_id"),
                    "title": item.get("title"),
                    "summary": item.get("summary"),
                    "conditions": list(item.get("conditions") or []),
                    "start_at": item.get("start_at"),
                    "end_at": item.get("end_at"),
                }
                for item in self.active_promotions()
            ],
        }

    def _load(self) -> dict[str, Any]:
        if self._payload is None:
            if not self.data_path.exists():
                self._payload = {"simulated": True, "promotions": []}
            else:
                with self.data_path.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
                self._payload = data if isinstance(data, dict) else {"simulated": True, "promotions": []}
        return self._payload

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
