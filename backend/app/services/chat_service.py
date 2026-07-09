from __future__ import annotations

from typing import Any

from ..models import CustomerProfile, FlooringProduct
from .product_service import ProductService
from .recommendation_service import RecommendationService


EN_PRODUCT_DISPLAY: dict[str, dict[str, Any]] = {
    "WF-SPC-001": {
        "name": "Light Grey Spruce SPC Click Flooring",
        "points": ["strong waterproof performance", "high wear resistance", "easy daily cleaning"],
    },
    "WF-WOOD-002": {
        "name": "Natural Oak Engineered Wood Flooring",
        "points": ["natural oak texture", "comfortable underfoot feel", "floor-heating compatibility"],
    },
    "WF-LAM-003": {
        "name": "Morning Mist Grey Laminate Flooring",
        "points": ["cost-effective", "modern grey tone", "good wear resistance"],
    },
    "WF-SPC-004": {
        "name": "Dark Walnut Waterproof SPC Flooring",
        "points": ["waterproof SPC structure", "premium dark walnut tone", "pet-friendly maintenance"],
    },
    "WF-WOOD-005": {
        "name": "Warm Light Oak Three-Layer Wood Flooring",
        "points": ["premium natural wood feel", "warm light oak tone", "comfortable bedroom style"],
    },
    "WF-LAM-006": {
        "name": "Cream White High-Wear Laminate Flooring",
        "points": ["soft cream-white color", "high-wear laminate surface", "suitable for bedrooms and kids rooms"],
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
        return response_language if response_language in {"zh", "en"} else self.detect_language(text)

    def is_greeting(self, text: str) -> bool:
        normalized = text.lower().replace(" ", "")
        english = text.lower()
        return any(
            k in normalized
            for k in ["你好", "您好", "hi", "hello", "hey", "嗨", "介绍一下", "有人吗"]
        ) or any(k in english for k in ["good morning", "good afternoon", "good evening", "can you help"])

    def is_session_end(self, text: str) -> bool:
        normalized = text.lower().replace(" ", "")
        return any(k in normalized for k in ["再见", "结束", "谢谢", "不用了", "bye", "goodbye", "thanks", "thankyou"])

    def build_welcome_message(self, text: str = "", response_language: str | None = None) -> str:
        if self.normalize_response_language(text, response_language) == "en":
            return (
                "Hello, welcome to the wood flooring experience area. I can help you compare materials, colors, "
                "wear resistance, waterproof performance, floor-heating compatibility, and maintenance. You can ask me "
                "questions like: which floor is better for pets, which one supports underfloor heating, or which option is best for a limited budget."
            )
        return (
            "你好，欢迎来到木地板体验区。我可以帮你了解不同木地板的材质、颜色、耐磨、防水和地暖适配情况。"
            "你可以直接问我，比如：家里有宠物怎么选，哪种适合地暖，或者预算有限应该怎么选。"
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
        lang = self.normalize_response_language(user_text, response_language)

        if any(k in text for k in ["对比", "区别", "哪个好"]) or any(
            k in english for k in ["compare", "difference", "which is better", "better"]
        ):
            return self._answer_comparison(recommended_products, lang)

        if any(k in text for k in ["防水", "怕水", "潮湿", "回南天"]) or any(
            k in english for k in ["waterproof", "water resistant", "humid", "damp", "moisture", "wet"]
        ):
            return self._answer_waterproof(recommended_products, customer_profile, lang)

        if any(k in text for k in ["地暖", "地热", "采暖"]) or any(
            k in english for k in ["floor heating", "underfloor heating", "radiant heating"]
        ):
            return self._answer_floor_heating(recommended_products, customer_profile, lang)

        if any(k in text for k in ["宠物", "猫", "狗", "好打理", "好清洁"]) or any(
            k in english for k in ["pet", "pets", "cat", "dog", "easy to clean", "easy clean", "maintenance"]
        ):
            return self._answer_pet_friendly(recommended_products, customer_profile, lang)

        if any(k in text for k in ["预算", "便宜", "多少钱", "价格", "性价比"]) or any(
            k in english for k in ["budget", "cheap", "affordable", "price", "cost", "cost-effective"]
        ):
            return self._answer_budget(recommended_products, customer_profile, lang)

        if recommended_products:
            main = recommended_products[0]
            backup = recommended_products[1] if len(recommended_products) > 1 else None
            if lang == "en":
                main_display = self._display_product(main, lang)
                answer = (
                    f"Based on your current needs, I would first recommend {main_display['name']}. "
                    f"Its main advantages are {self._points(main, lang)}."
                )
                if backup:
                    backup_display = self._display_product(backup, lang)
                    answer += (
                        f" As a backup, you can also consider {backup_display['name']}, especially if you prefer "
                        f"a {backup_display['price_range']} price range or a {backup_display['color']} tone."
                    )
                answer += self._next_question(customer_profile, lang)
                return answer

            answer = f"根据您目前的需求，我会优先推荐{main.name}。它的主要优势是{self._points(main, lang)}。"
            if backup:
                answer += f" 备选可以看{backup.name}，它更适合对{backup.price_range}预算或{backup.color}风格有偏好的客户。"
            answer += self._next_question(customer_profile, lang)
            return answer

        if lang == "en":
            return "I can help you choose flooring based on room type, style, budget, waterproof needs, floor heating, pets, children, and elderly family members. Is it mainly for the living room, bedroom, or the whole home?"
        return "我可以帮您从房间类型、装修风格、预算、防水、地暖、宠物和老人儿童这些方面来选地板。您可以先告诉我主要铺在客厅还是卧室？"

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
        missing = []
        if not profile.room_type:
            missing.append("铺装空间")
        if not profile.budget:
            missing.append("预算")
        if not profile.style:
            missing.append("装修风格")
        if missing:
            return "建议销售继续确认" + "、".join(missing) + "，再给出正式报价和安装建议。"
        return "建议销售在 24 小时内发送主推款与备选款对比方案，并确认面积、安装时间和最终预算。"

    def _answer_waterproof(self, products: list[FlooringProduct], profile: CustomerProfile, lang: str) -> str:
        waterproof = [p for p in products if p.waterproof] or [p for p in self.product_service.list_products() if p.waterproof]
        if waterproof:
            p = waterproof[0]
            if lang == "en":
                display = self._display_product(p, lang)
                return f"If waterproof performance is important, I would first recommend {display['name']}. It is a {display['type']} floor with better water resistance and easier daily cleaning, suitable for living rooms or humid environments. Final installation still needs proper edge sealing and moisture treatment. {self._next_question(profile, lang)}"
            return f"如果您比较关注防水，我会优先推荐{p.name}。它属于{p.type}地板，防水和日常清洁表现更好，适合厨房外侧、客厅或潮湿环境。最终安装仍要注意收边和基层防潮。{self._next_question(profile, lang)}"
        return "SPC is usually more suitable than solid wood for humid areas." if lang == "en" else "目前模拟产品库里没有标记为强防水的产品。一般来说，SPC 会比实木更适合潮湿环境。"

    def _answer_floor_heating(self, products: list[FlooringProduct], profile: CustomerProfile, lang: str) -> str:
        suitable = [p for p in products if p.floor_heating] or [p for p in self.product_service.list_products() if p.floor_heating]
        if suitable:
            p = suitable[0]
            if lang == "en":
                display = self._display_product(p, lang)
                return f"For underfloor heating, I would suggest a product with better dimensional stability, such as {display['name']}. It is marked as floor-heating compatible, but the store should still confirm leveling, moisture content, and temperature-control requirements. {self._next_question(profile, lang)}"
            return f"地暖场景建议看稳定性更好的产品，例如{p.name}。它标记为支持地暖，铺装时还需要确认地面找平、含水率和温控条件。{self._next_question(profile, lang)}"
        return "Please choose a floor-heating compatible product and confirm installation details with sales." if lang == "en" else "可以选地暖适配产品，但需要销售进一步确认安装环境、辅材和温控要求。"

    def _answer_pet_friendly(self, products: list[FlooringProduct], profile: CustomerProfile, lang: str) -> str:
        suitable = [p for p in products if p.pet_friendly] or [p for p in self.product_service.list_products() if p.pet_friendly]
        if suitable:
            p = suitable[0]
            if lang == "en":
                display = self._display_product(p, lang)
                return f"For a home with pets, I recommend {display['name']} first. It is more wear-resistant and easier to clean, so daily scratches and water marks are easier to manage. {self._next_question(profile, lang)}"
            return f"家里有宠物的话，我建议优先看{p.name}。它更耐磨，也更容易清洁，日常爪痕和水渍维护压力会小一些。{self._next_question(profile, lang)}"
        return "For pets, prioritize SPC or laminate flooring with high wear resistance and easy cleaning." if lang == "en" else "宠物家庭建议优先考虑耐磨等级高、好清洁的 SPC 或强化地板。"

    def _answer_budget(self, products: list[FlooringProduct], profile: CustomerProfile, lang: str) -> str:
        economic = [p for p in products if p.price_range in {"经济", "中等"}] or [p for p in self.product_service.list_products() if p.price_range in {"经济", "中等"}]
        if economic:
            p = economic[0]
            if lang == "en":
                display = self._display_product(p, lang)
                return f"If you want to control the budget, you can start with {display['name']}. Its price range is {display['price_range']}, while still keeping practical wear resistance and maintenance advantages. {self._next_question(profile, lang)}"
            return f"如果希望控制预算，可以先看{p.name}，它的价格区间是{p.price_range}，同时保留了比较实用的耐磨和维护优势。{self._next_question(profile, lang)}"
        return "For a limited budget, laminate and some SPC products are usually more cost-effective." if lang == "en" else "预算有限时通常优先比较强化地板和部分 SPC 产品，性价比会更高。"

    def _answer_comparison(self, products: list[FlooringProduct], lang: str) -> str:
        if len(products) >= 2:
            a, b = products[0], products[1]
            if lang == "en":
                da = self._display_product(a, lang)
                db = self._display_product(b, lang)
                return f"In simple terms, {da['name']} is stronger in {self._points(a, lang)}, while {db['name']} is stronger in {self._points(b, lang)}. If you care more about waterproofing and wear resistance, start with SPC or laminate. If you care more about natural feel and wood texture, consider engineered wood."
            return f"简单对比，{a.name}更突出{self._points(a, lang)}；{b.name}更突出{self._points(b, lang)}。如果重视防水耐磨，优先看 SPC 或强化；如果重视自然脚感和木纹质感，可以看多层实木。"
        return "SPC is usually more waterproof and easy to maintain; engineered wood gives a more natural feel; laminate is usually more cost-effective." if lang == "en" else "可以的。一般 SPC 更偏防水、耐磨、好打理；多层实木更偏自然脚感和真实木纹；强化地板通常性价比更高。"

    def _display_product(self, product: FlooringProduct, lang: str) -> dict[str, Any]:
        if lang != "en":
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

    def _points(self, product: FlooringProduct, lang: str) -> str:
        display = self._display_product(product, lang)
        points = display.get("points") or []
        if not points:
            return "clear use case and easy maintenance" if lang == "en" else "适用场景明确、维护方便"
        return ", ".join(points[:3]) if lang == "en" else "、".join(points[:3])

    @staticmethod
    def _next_question(profile: CustomerProfile, lang: str) -> str:
        if lang == "en":
            if not profile.room_type:
                return " Is it mainly for the living room, bedroom, or the whole home?"
            if not profile.style:
                return " Is your home style more modern minimalist, Nordic, or Chinese style?"
            if not profile.budget:
                return " Is your budget more economy, medium, or premium?"
            return " I can also help you compare two products."
        if not profile.room_type:
            return " 您主要是客厅、卧室还是全屋铺装？"
        if not profile.style:
            return " 您家装修更偏现代简约、北欧，还是新中式风格？"
        if not profile.budget:
            return " 您的预算更偏经济、中等，还是希望品质高一些？"
        return " 我也可以继续帮您比较两款产品的区别。"
