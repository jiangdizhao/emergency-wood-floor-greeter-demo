from __future__ import annotations

from ..models import CustomerProfile, FlooringProduct
from .product_service import ProductService


class RecommendationService:
    def __init__(self, product_service: ProductService) -> None:
        self.product_service = product_service

    def extract_needs_from_text(self, text: str, profile: CustomerProfile) -> CustomerProfile:
        """Legacy keyword parser retained only as a deterministic fallback/debug helper."""
        normalized = text.lower().replace(" ", "")
        english = text.lower()
        updated = profile.model_copy(deep=True)

        room_map = {
            "客厅": ["客厅", "living room", "lounge"],
            "卧室": ["卧室", "bedroom", "master room"],
            "书房": ["书房", "study", "home office", "office"],
            "全屋": ["全屋", "whole house", "whole home", "entire home"],
            "厨房": ["厨房", "kitchen"],
            "儿童房": ["儿童房", "kids room", "children room", "child room"],
            "老人房": ["老人房", "elderly room", "parents room"],
        }
        for room, keywords in room_map.items():
            if any(keyword in text or keyword in english for keyword in keywords):
                updated.room_type = room
                break

        style_map = {
            "现代简约": ["现代简约", "modern minimalist", "modern", "minimalist", "simple style"],
            "北欧": ["北欧", "nordic", "scandinavian"],
            "新中式": ["新中式", "new chinese", "chinese style"],
            "轻奢": ["轻奢", "light luxury", "luxury"],
            "日式": ["日式", "japanese", "japan style"],
            "原木": ["原木", "natural wood", "wood tone", "oak look"],
            "自然风": ["自然风", "natural style", "nature style"],
            "灰调": ["灰调", "grey", "gray"],
        }
        for style, keywords in style_map.items():
            if any(keyword in text or keyword in english for keyword in keywords):
                updated.style = style
                break

        if any(k in text for k in ["便宜", "预算有限", "性价比", "经济", "出租"]) or any(
            k in english for k in ["cheap", "affordable", "budget", "economy", "cost-effective", "rental"]
        ):
            updated.budget = "经济"
        elif any(k in text for k in ["中等", "适中", "不要太贵", "普通预算"]) or any(
            k in english for k in ["medium", "mid-range", "moderate", "not too expensive"]
        ):
            updated.budget = "中等"
        elif any(k in text for k in ["高端", "贵一点", "预算高", "品质好"]) or any(
            k in english for k in ["premium", "high-end", "quality", "better quality"]
        ):
            updated.budget = "偏高"

        special_map = {
            "宠物": ["宠物", "猫", "狗", "猫狗", "pet", "pets", "cat", "cats", "dog", "dogs"],
            "地暖": ["地暖", "地热", "采暖", "floor heating", "underfloor heating", "radiant heating"],
            "儿童": ["孩子", "儿童", "小孩", "宝宝", "kid", "kids", "child", "children", "baby"],
            "老人": ["老人", "父母", "长辈", "elderly", "senior", "parents"],
            "潮湿环境": ["潮湿", "南方", "回南天", "湿气", "humid", "humidity", "damp", "moisture", "wet"],
            "好打理": ["好打理", "好清洁", "容易清洁", "维护简单", "easy to clean", "easy clean", "easy maintenance", "low maintenance"],
        }
        concern_map = {
            "防水": ["防水", "怕水", "泡水", "waterproof", "water resistant", "water-resistant", "water"],
            "耐磨": ["耐磨", "划痕", "耐刮", "磨损", "wear", "scratch", "scratches", "scratch resistant", "durable"],
            "环保": ["环保", "甲醛", "气味", "eco", "environment", "formaldehyde", "odor", "smell"],
            "价格": ["价格", "多少钱", "预算", "贵", "便宜", "price", "cost", "budget", "expensive", "cheap"],
            "脚感": ["脚感", "舒服", "质感", "comfort", "comfortable", "feel", "texture", "natural feel"],
        }

        for label, keywords in special_map.items():
            if any(keyword in normalized or keyword in english for keyword in keywords):
                self._append_unique(updated.special_needs, label)
        for label, keywords in concern_map.items():
            if any(keyword in normalized or keyword in english for keyword in keywords):
                self._append_unique(updated.concerns, label)
        return updated

    def recommend(self, profile: CustomerProfile, limit: int = 2) -> list[FlooringProduct]:
        candidates = [
            product
            for product in self.product_service.list_products()
            if product.id not in profile.rejected_product_ids
            and not self._color_matches_any(product.color, profile.rejected_colors)
        ]
        if not candidates:
            return []

        scored = [(self._score_product(product, profile), product) for product in candidates]
        scored.sort(key=lambda item: (item[0], item[1].id), reverse=True)
        positive = [product for score, product in scored if score > 0]
        return (positive or [product for _, product in scored])[:limit]

    def _score_product(self, product: FlooringProduct, profile: CustomerProfile) -> int:
        score = 0
        if product.id in profile.preferred_product_ids:
            score += 8
        if self._color_matches_any(product.color, profile.preferred_colors):
            score += 3
        if profile.room_type and profile.room_type in product.suitable_rooms:
            score += 3
        if profile.style and any(profile.style in style or style in profile.style for style in product.style):
            score += 2
        if profile.budget and profile.budget == product.price_range:
            score += 3

        if profile.has_pets is True and product.pet_friendly:
            score += 4
        if profile.has_floor_heating is True and product.floor_heating:
            score += 4
        if profile.has_children is True and product.child_friendly:
            score += 3
        if profile.has_elderly is True and product.child_friendly:
            score += 2
        if profile.humid_environment is True and product.waterproof:
            score += 4

        weights = {"high": 4, "medium": 2, "low": 1}
        for priority, level in profile.priorities.items():
            weight = weights.get(level, 0)
            if priority == "防水" and product.waterproof:
                score += weight
            elif priority == "耐磨" and product.wear_level.upper() in {"AC4", "AC5", "高"}:
                score += weight
            elif priority == "价格" and product.price_range in {"经济", "中等"}:
                score += weight
            elif priority == "脚感" and product.type in {"多层实木", "三层实木", "实木"}:
                score += weight
            elif priority == "好清洁" and (product.waterproof or product.pet_friendly):
                score += weight
            elif priority == "环保" and any("环保" in point or "低醛" in point for point in product.selling_points):
                score += weight

        # Backward-compatible signals from older session files.
        needs = set(profile.special_needs)
        concerns = set(profile.concerns)
        if "宠物" in needs and product.pet_friendly:
            score += 2
        if "地暖" in needs and product.floor_heating:
            score += 2
        if "儿童" in needs and product.child_friendly:
            score += 1
        if "老人" in needs and product.child_friendly:
            score += 1
        if "潮湿环境" in needs and product.waterproof:
            score += 2
        if "好打理" in needs and (product.waterproof or product.pet_friendly):
            score += 1
        if "防水" in concerns and product.waterproof:
            score += 1
        if "耐磨" in concerns and product.wear_level.upper() in {"AC4", "AC5", "高"}:
            score += 1
        if "脚感" in concerns and product.type in {"多层实木", "三层实木", "实木"}:
            score += 1
        return score

    @staticmethod
    def _color_matches_any(product_color: str, preferences: list[str]) -> bool:
        normalized_product = product_color.replace("色", "")
        return any(
            preference.replace("色", "") in normalized_product
            or normalized_product in preference.replace("色", "")
            for preference in preferences
            if preference
        )

    @staticmethod
    def _append_unique(values: list[str], value: str) -> None:
        if value not in values:
            values.append(value)
