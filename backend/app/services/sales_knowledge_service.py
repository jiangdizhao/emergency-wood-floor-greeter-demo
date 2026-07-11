from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..models import CustomerProfile, FlooringProduct


class SalesKnowledgeService:
    """Loads approved sales knowledge used by both Terra and Qwen.

    The bundled JSON is deliberately simulated demo data. Replacing the JSON files
    with approved business content changes the customer-facing company and product
    story without changing dialogue orchestration code.
    """

    def __init__(self) -> None:
        self.data_dir = Path(__file__).resolve().parents[1] / "data"
        self.company_path = self.data_dir / "company_profile.json"
        self.collections_path = self.data_dir / "product_collections.json"
        self._company: dict[str, Any] | None = None
        self._collections: list[dict[str, Any]] | None = None

    def company_profile(self) -> dict[str, Any]:
        if self._company is None:
            self._company = self._read_json(self.company_path)
        return dict(self._company)

    def collections(self) -> list[dict[str, Any]]:
        if self._collections is None:
            payload = self._read_json(self.collections_path)
            rows = payload.get("collections", [])
            self._collections = [dict(item) for item in rows if isinstance(item, dict)]
        return [dict(item) for item in self._collections]

    def customer_catalog(self) -> dict[str, Any]:
        company = self.company_profile()
        return {
            "simulated": bool(company.get("simulated", True)),
            "company_name": str(company.get("company_name") or "演示门店"),
            "positioning": str(company.get("positioning") or "木地板整体选购顾问门店"),
            "strengths": list(company.get("strengths") or []),
            "featured_collections": [
                {
                    "collection_id": item.get("collection_id"),
                    "name": item.get("name"),
                    "tagline": item.get("tagline"),
                    "best_for": list(item.get("best_for") or []),
                }
                for item in self.collections()
            ],
        }

    def new_customer_greeting(self) -> str:
        company = self.company_profile()
        consultant = str(company.get("consultant_name") or "小木")
        role = str(company.get("consultant_role") or "地板选购顾问")
        positioning = str(company.get("positioning") or "木地板整体选购顾问门店")
        value = str(company.get("consultant_value_proposition") or "帮助您比较不同地板方案的价值与取舍")
        highlights = list(company.get("opening_highlights") or [])[:4]
        highlight_text = "、".join(str(item) for item in highlights if str(item).strip())
        question = str(
            company.get("opening_question")
            or "这次选地板，您最重视预算、耐磨、防水、脚感、环保，还是日常好清洁？"
        )
        return (
            f"您好，欢迎来到{company.get('company_name', '木地板体验店')}。"
            f"我是{consultant}，也是这里的{role}。我们是一家{positioning}，"
            f"我会{value}。"
            + (f"门店目前重点提供{highlight_text}。" if highlight_text else "")
            + question
        )

    def company_highlights(self, limit: int = 3) -> list[str]:
        company = self.company_profile()
        return [str(item) for item in list(company.get("strengths") or [])[:limit] if str(item).strip()]

    def relevant_collections(
        self,
        *,
        profile: CustomerProfile,
        products: list[FlooringProduct],
        limit: int = 2,
    ) -> list[dict[str, Any]]:
        product_ids = {product.id for product in products}
        driver = profile.primary_purchase_driver or self._primary_driver(profile)
        scores: list[tuple[int, str, dict[str, Any]]] = []
        for collection in self.collections():
            score = 0
            collection_products = {str(item) for item in collection.get("product_ids", [])}
            score += 4 * len(product_ids.intersection(collection_products))
            searchable = " ".join(
                [
                    str(collection.get("name") or ""),
                    str(collection.get("tagline") or ""),
                    *[str(item) for item in collection.get("best_for", [])],
                    *[str(item) for item in collection.get("strengths", [])],
                ]
            )
            if driver and driver in searchable:
                score += 5
            if profile.has_pets and "宠物" in searchable:
                score += 4
            if profile.has_floor_heating and "地暖" in searchable:
                score += 4
            if profile.humid_environment and ("防水" in searchable or "潮湿" in searchable):
                score += 4
            if profile.budget == "经济" and ("经济" in searchable or "预算" in searchable):
                score += 3
            if profile.style and profile.style in searchable:
                score += 2
            if score > 0:
                scores.append((score, str(collection.get("collection_id") or ""), collection))
        scores.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [dict(item[2]) for item in scores[:limit]]

    def product_tradeoffs(self, product: FlooringProduct) -> list[str]:
        tradeoffs: list[str] = []
        for collection in self.collections():
            if product.id not in {str(item) for item in collection.get("product_ids", [])}:
                continue
            for tradeoff in collection.get("tradeoffs", []):
                text = str(tradeoff).strip()
                if text and text not in tradeoffs:
                    tradeoffs.append(text)
        return tradeoffs[:2]

    @staticmethod
    def _primary_driver(profile: CustomerProfile) -> str | None:
        if not profile.priorities:
            return None
        rank = {"high": 3, "medium": 2, "low": 1}
        return max(profile.priorities.items(), key=lambda item: rank.get(item[1], 0))[0]

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
