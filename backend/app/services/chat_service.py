from __future__ import annotations

from typing import Any

from ..models import CustomerProfile, FlooringProduct
from ..response_language import set_current_response_language
from .product_service import ProductService
from .recommendation_service import RecommendationService

EN_PRODUCT_DISPLAY: dict[str, dict[str, Any]] = {
    "WF-SPC-001": {
        "name": "Light Grey Spruce SPC Click Flooring",
        "points": ["strong water resistance", "high wear resistance", "easy daily cleaning"],
    },
    "WF-WOOD-002": {
        "name": "Natural Oak Engineered Wood Flooring",
        "points": ["natural oak texture", "comfortable underfoot feel", "underfloor-heating compatibility"],
    },
    "WF-LAM-003": {
        "name": "Morning Mist Grey Laminate Flooring",
        "points": ["strong value for money", "modern grey tone", "good wear resistance"],
    },
    "WF-SPC-004": {
        "name": "Dark Walnut Waterproof SPC Flooring",
        "points": ["water-resistant SPC structure", "premium dark-walnut tone", "pet-friendly maintenance"],
    },
    "WF-WOOD-005": {
        "name": "Warm Light Oak Three-Layer Wood Flooring",
        "points": ["premium natural wood feel", "warm light-oak tone", "comfortable bedroom character"],
    },
    "WF-LAM-006": {
        "name": "Cream White High-Wear Laminate Flooring",
        "points": ["soft cream-white colour", "high-wear laminate surface", "suitable for bedrooms and children's rooms"],
    },
}

EN_TYPE = {
    "SPC": "SPC",
    "多层实木": "engineered wood",
    "三层实木": "three-layer wood",
    "强化": "laminate",
    "强化复合": "laminate",
    "实木": "solid wood",
}

EN_PRICE = {
    "经济": "economy",
    "中等": "mid-range",
    "偏高": "upper-mid range",
    "高端": "premium",
}

EN_COLOR = {
    "浅灰": "light grey",
    "原木色": "natural oak",
    "灰调": "grey tone",
    "深胡桃色": "dark walnut",
    "浅橡木色": "light oak",
    "奶油白": "cream white",
}


class ChatService:
    def __init__(self, product_service: ProductService, recommendation_service: RecommendationService) -> None:
        self.product_service = product_service
        self.recommendation_service = recommendation_service

    def detect_language(self, text: str) -> str:
        ascii_letters = sum(1 for ch in text if ch.isascii() and ch.isalpha())
        cjk_chars = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
        return "en" if ascii_letters > cjk_chars else "zh"

    def normalize_response_language(self, text: str, response_language: str | None = None) -> str:
        language = response_language if response_language in {"zh", "en"} else self.detect_language(text)
        set_current_response_language(language)
        return language

    def is_greeting(self, text: str) -> bool:
        normalized = text.lower().replace(" ", "")
        english = text.lower()
        return any(
            key in normalized
            for key in ["你好", "您好", "hi", "hello", "hey", "嗨", "介绍一下", "有人吗"]
        ) or any(key in english for key in ["good morning", "good afternoon", "good evening", "can you help"])

    def is_session_end(self, text: str) -> bool:
        normalized = text.lower().replace(" ", "")
        return any(
            key in normalized
            for key in ["再见", "结束", "谢谢", "不用了", "bye", "goodbye", "thanks", "thankyou"]
        )

    def build_welcome_message(self, text: str = "", response_language: str | None = None) -> str:
        if self.normalize_response_language(text, response_language) == "en":
            return (
                "Hello, welcome to the wood flooring experience area. I can help you compare materials, colours, "
                "wear resistance, water resistance, underfloor-heating compatibility and maintenance. "
                "Which matters most for this project: budget, wear resistance, water resistance, underfoot feel, "
                "environmental documentation, or easy cleaning?"
            )
        return (
            "你好，欢迎来到木地板体验区。我可以帮你了解不同木地板的材质、颜色、耐磨、防水和地暖适配情况。"
            "这次选地板，您最不愿意妥协的是预算、耐磨、防水、脚感、环保，还是日常好清洁？"
        )

    def answer_user_message(
        self,
        user_text: str,
        customer_profile: CustomerProfile,
        recommended_products: list[FlooringProduct],
        response_language: str | None = None,
    ) -> str:
        text = user_text.lower().replace(" ", "")
        english = user_text.lower()
        language = self.normalize_response_language(user_text, response_language)

        if any(key in text for key in ["对比", "区别", "哪个好"]) or any(
            key in english for key in ["compare", "difference", "which is better", "better"]
        ):
            return self._answer_comparison(recommended_products, language)
        if any(key in text for key in ["防水", "怕水", "潮湿", "回南天"]) or any(
            key in english for key in ["waterproof", "water resistant", "humid", "damp", "moisture", "wet"]
        ):
            return self._answer_waterproof(recommended_products, customer_profile, language)
        if any(key in text for key in ["地暖", "地热", "采暖"]) or any(
            key in english for key in ["floor heating", "underfloor heating", "radiant heating"]
        ):
            return self._answer_floor_heating(recommended_products, customer_profile, language)
        if any(key in text for key in ["宠物", "猫", "狗", "好打理", "好清洁"]) or any(
            key in english for key in ["pet", "pets", "cat", "dog", "easy to clean", "easy clean", "maintenance"]
        ):
            return self._answer_pet_friendly(recommended_products, customer_profile, language)
        if any(key in text for key in ["预算", "便宜", "多少钱", "价格", "性价比"]) or any(
            key in english for key in ["budget", "cheap", "affordable", "price", "cost", "cost-effective"]
        ):
            return self._answer_budget(recommended_products, customer_profile, language)

        if recommended_products:
            main = recommended_products[0]
            backup = recommended_products[1] if len(recommended_products) > 1 else None
            if language == "en":
                main_display = self._display_product(main, language)
                answer = (
                    f"Based on your current needs, my main recommendation is {main_display['name']}. "
                    f"Its strongest approved points are {self._points(main, language)}."
                )
                if backup:
                    backup_display = self._display_product(backup, language)
                    answer += (
                        f" As a backup, consider {backup_display['name']}, particularly if you prefer "
                        f"a {backup_display['price_range']} price range or a {backup_display['color']} tone."
                    )
                return answer + self._next_question(customer_profile, language)

            answer = f"根据您目前的需求，我会优先推荐{main.name}。它的主要优势是{self._points(main, language)}。"
            if backup:
                answer += f" 备选可以看{backup.name}，它更适合对{backup.price_range}预算或{backup.color}风格有偏好的客户。"
            return answer + self._next_question(customer_profile, language)

        if language == "en":
            return (
                "I can help you choose flooring by room, style, budget, water resistance, underfloor heating, "
                "pets, children and older family members. Which requirement matters most to you?"
            )
        return "我可以帮您从房间、风格、预算、防水、地暖和家庭成员等方面来选地板。您最重视哪一点？"

    def build_conversation_summary(self, profile: CustomerProfile) -> str:
        parts: list[str] = []
        if profile.room_type:
            parts.append(f"使用空间：{profile.room_type}")
        if profile.style:
            parts.append(f"偏好风格：{profile.style}")
        if profile.budget:
            parts.append(f"预算区间：{profile.budget}")
        if profile.special_needs:
            parts.append("特殊需求：" + "、".join(profile.special_needs))
        if profile.concerns:
            parts.append("关注点：" + "、".join(profile.concerns))
        return "；".join(parts) if parts else "客户正在了解木地板产品，需求尚未明确。"

    def build_follow_up_suggestion(self, profile: CustomerProfile) -> str:
        missing: list[str] = []
        if not profile.room_type:
            missing.append("铺装空间")
        if not profile.budget:
            missing.append("预算")
        if not profile.style:
            missing.append("装修风格")
        if missing:
            return "建议销售继续确认" + "、".join(missing) + "，再给出正式报价和安装建议。"
        return "建议销售在 24 小时内发送主推款与备选款对比方案，并确认面积、安装时间和最终预算。"

    def _answer_waterproof(
        self,
        products: list[FlooringProduct],
        profile: CustomerProfile,
        language: str,
    ) -> str:
        suitable = [product for product in products if product.waterproof] or [
            product for product in self.product_service.list_products() if product.waterproof
        ]
        if suitable:
            product = suitable[0]
            if language == "en":
                display = self._display_product(product, language)
                return (
                    f"If water resistance is important, start with {display['name']}. It is a {display['type']} floor "
                    "with easier day-to-day cleaning. Final installation still requires correct edge sealing and moisture control."
                    + self._next_question(profile, language)
                )
            return (
                f"如果您关注防水，我会优先推荐{product.name}。它属于{product.type}地板，防水和日常清洁表现更好。"
                "最终安装仍要注意收边和基层防潮。"
                + self._next_question(profile, language)
            )
        return "SPC is usually more suitable than real wood for damp areas." if language == "en" else "潮湿区域通常更适合优先比较 SPC。"

    def _answer_floor_heating(
        self,
        products: list[FlooringProduct],
        profile: CustomerProfile,
        language: str,
    ) -> str:
        suitable = [product for product in products if product.floor_heating] or [
            product for product in self.product_service.list_products() if product.floor_heating
        ]
        if suitable:
            product = suitable[0]
            if language == "en":
                display = self._display_product(product, language)
                return (
                    f"For underfloor heating, consider a dimensionally stable option such as {display['name']}. "
                    "The store still needs to confirm subfloor levelling, moisture and temperature-control requirements."
                    + self._next_question(profile, language)
                )
            return f"地暖场景可以先看{product.name}，但仍需确认找平、含水率和温控要求。" + self._next_question(profile, language)
        return "Please choose an underfloor-heating-compatible product and confirm installation details with the store." if language == "en" else "请优先选择支持地暖的产品，并让门店确认安装条件。"

    def _answer_pet_friendly(
        self,
        products: list[FlooringProduct],
        profile: CustomerProfile,
        language: str,
    ) -> str:
        suitable = [product for product in products if product.pet_friendly] or [
            product for product in self.product_service.list_products() if product.pet_friendly
        ]
        if suitable:
            product = suitable[0]
            if language == "en":
                display = self._display_product(product, language)
                return (
                    f"For a home with pets, I would start with {display['name']}. It is more wear-resistant and easier to clean."
                    + self._next_question(profile, language)
                )
            return f"宠物家庭建议优先看{product.name}，它更耐磨，也更容易清洁。" + self._next_question(profile, language)
        return "For pets, prioritise SPC or laminate with strong wear resistance and easy cleaning." if language == "en" else "宠物家庭建议优先比较高耐磨、好清洁的 SPC 或强化地板。"

    def _answer_budget(
        self,
        products: list[FlooringProduct],
        profile: CustomerProfile,
        language: str,
    ) -> str:
        suitable = [product for product in products if product.price_range in {"经济", "中等"}] or [
            product for product in self.product_service.list_products() if product.price_range in {"经济", "中等"}
        ]
        if suitable:
            product = suitable[0]
            if language == "en":
                display = self._display_product(product, language)
                return (
                    f"To control the budget, start with {display['name']}. It sits in the {display['price_range']} range while retaining practical wear and maintenance benefits."
                    + self._next_question(profile, language)
                )
            return f"如果希望控制预算，可以先看{product.name}，它属于{product.price_range}价格区间。" + self._next_question(profile, language)
        return "For a limited budget, laminate and selected SPC products are usually the most practical starting point." if language == "en" else "预算有限时可以优先比较强化地板和部分 SPC。"

    def _answer_comparison(self, products: list[FlooringProduct], language: str) -> str:
        if len(products) >= 2:
            first, second = products[0], products[1]
            if language == "en":
                first_display = self._display_product(first, language)
                second_display = self._display_product(second, language)
                return (
                    f"{first_display['name']} is stronger in {self._points(first, language)}, while "
                    f"{second_display['name']} is stronger in {self._points(second, language)}. "
                    "Keep the room and core requirement fixed, then compare one variable such as material or budget."
                )
            return f"{first.name}更突出{self._points(first, language)}；{second.name}更突出{self._points(second, language)}。建议固定空间和核心需求后，只比较一个变量。"
        return "SPC usually emphasises water resistance and easy maintenance; real wood emphasises natural feel; laminate usually offers stronger value." if language == "en" else "一般 SPC 更偏防水好打理，实木类更偏自然脚感，强化地板通常性价比更高。"

    def _display_product(self, product: FlooringProduct, language: str) -> dict[str, Any]:
        if language != "en":
            return {
                "name": product.name,
                "type": product.type,
                "color": product.color,
                "price_range": product.price_range,
                "points": product.selling_points,
            }
        display = EN_PRODUCT_DISPLAY.get(product.id, {})
        return {
            "name": display.get("name", f"Product {product.id}"),
            "type": EN_TYPE.get(product.type, "wood flooring"),
            "color": EN_COLOR.get(product.color, "neutral"),
            "price_range": EN_PRICE.get(product.price_range, "standard"),
            "points": display.get("points", ["practical performance", "easy maintenance"]),
        }

    def _points(self, product: FlooringProduct, language: str) -> str:
        points = self._display_product(product, language).get("points") or []
        if not points:
            return "clear use case and easy maintenance" if language == "en" else "适用场景明确、维护方便"
        return ", ".join(points[:3]) if language == "en" else "、".join(points[:3])

    @staticmethod
    def _next_question(profile: CustomerProfile, language: str) -> str:
        if language == "en":
            if not profile.room_type:
                return " Is it mainly for the living room, bedroom, or the whole home?"
            if not profile.style:
                return " Is your interior style modern minimalist, Scandinavian, or contemporary Chinese?"
            if not profile.budget:
                return " Is your budget closer to economy, mid-range, or premium?"
            return " I can also compare two products for you."
        if not profile.room_type:
            return " 您主要是客厅、卧室还是全屋铺装？"
        if not profile.style:
            return " 您家装修更偏现代简约、北欧，还是新中式？"
        if not profile.budget:
            return " 您的预算更偏经济、中等，还是高端？"
        return " 我也可以继续帮您比较两款产品。"
