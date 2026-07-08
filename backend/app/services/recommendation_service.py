from __future__ import annotations

from ..models import CustomerProfile, FlooringProduct
from .product_service import ProductService


class RecommendationService:
    def __init__(self, product_service: ProductService) -> None:
        self.product_service = product_service

    def extract_needs_from_text(self, text: str, profile: CustomerProfile) -> CustomerProfile:
        normalized = text.lower().replace(" ", "")
        updated = profile.model_copy(deep=True)

        room_keywords = ["客厅", "卧室", "书房", "全屋", "厨房", "儿童房", "老人房"]
        for room in room_keywords:
            if room in text:
                updated.room_type = room
                break

        style_keywords = ["现代简约", "北欧", "新中式", "轻奢", "日式", "原木", "自然风", "灰调"]
        for style in style_keywords:
            if style in text:
                updated.style = style
                break

        if any(k in text for k in ["便宜", "预算有限", "性价比", "经济", "出租"]):
            updated.budget = "经济"
        elif any(k in text for k in ["中等", "适中", "不要太贵", "普通预算"]):
            updated.budget = "中等"
        elif any(k in text for k in ["高端", "贵一点", "预算高", "品质好"]):
            updated.budget = "偏高"

        special_map = {
            "宠物": ["宠物", "猫", "狗", "猫狗"],
            "地暖": ["地暖", "地热", "采暖"],
            "儿童": ["孩子", "儿童", "小孩", "宝宝"],
            "老人": ["老人", "父母", "长辈"],
            "潮湿环境": ["潮湿", "南方", "回南天", "湿气"],
            "好打理": ["好打理", "好清洁", "容易清洁", "维护简单"],
        }
        concern_map = {
            "防水": ["防水", "怕水", "泡水"],
            "耐磨": ["耐磨", "划痕", "耐刮", "磨损"],
            "环保": ["环保", "甲醛", "气味"],
            "价格": ["价格", "多少钱", "预算", "贵", "便宜"],
            "脚感": ["脚感", "舒服", "质感"],
        }

        for label, keywords in special_map.items():
            if any(keyword in normalized for keyword in keywords):
                self._append_unique(updated.special_needs, label)

        for label, keywords in concern_map.items():
            if any(keyword in normalized for keyword in keywords):
                self._append_unique(updated.concerns, label)

        return updated

    def recommend(self, profile: CustomerProfile, limit: int = 2) -> list[FlooringProduct]:
        scored: list[tuple[int, FlooringProduct]] = []
        for product in self.product_service.list_products():
            score = self._score_product(product, profile)
            scored.append((score, product))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [product for score, product in scored[:limit] if score > 0] or [p for _, p in scored[:limit]]

    def _score_product(self, product: FlooringProduct, profile: CustomerProfile) -> int:
        score = 0
        if profile.room_type and profile.room_type in product.suitable_rooms:
            score += 2
        if profile.style and any(profile.style in s or s in profile.style for s in product.style):
            score += 2
        if profile.budget and profile.budget == product.price_range:
            score += 2

        needs = set(profile.special_needs)
        concerns = set(profile.concerns)
        if "宠物" in needs and product.pet_friendly:
            score += 3
        if "地暖" in needs and product.floor_heating:
            score += 3
        if "儿童" in needs and product.child_friendly:
            score += 2
        if "老人" in needs and product.child_friendly:
            score += 1
        if "潮湿环境" in needs and product.waterproof:
            score += 3
        if "好打理" in needs and (product.waterproof or product.pet_friendly):
            score += 2
        if "防水" in concerns and product.waterproof:
            score += 3
        if "耐磨" in concerns and product.wear_level.upper() in {"AC4", "AC5", "高"}:
            score += 2
        if "价格" in concerns and product.price_range in {"经济", "中等"}:
            score += 1
        if "脚感" in concerns and product.type in {"多层实木", "实木"}:
            score += 2
        return score

    @staticmethod
    def _append_unique(values: list[str], value: str) -> None:
        if value not in values:
            values.append(value)
