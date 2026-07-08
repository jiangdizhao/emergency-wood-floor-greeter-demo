from __future__ import annotations

from ..models import CustomerProfile, FlooringProduct
from .product_service import ProductService
from .recommendation_service import RecommendationService


class ChatService:
    def __init__(self, product_service: ProductService, recommendation_service: RecommendationService) -> None:
        self.product_service = product_service
        self.recommendation_service = recommendation_service

    def is_greeting(self, text: str) -> bool:
        normalized = text.lower().replace(" ", "")
        return any(k in normalized for k in ["你好", "您好", "hi", "hello", "hey", "嗨", "介绍一下", "有人吗"])

    def is_session_end(self, text: str) -> bool:
        normalized = text.lower().replace(" ", "")
        return any(k in normalized for k in ["再见", "结束", "谢谢", "不用了", "bye", "goodbye"])

    def build_welcome_message(self) -> str:
        return (
            "你好，欢迎来到木地板体验区。我可以帮你了解不同木地板的材质、颜色、耐磨、防水和地暖适配情况。"
            "你可以直接问我，比如：家里有宠物怎么选，哪种适合地暖，或者预算有限应该怎么选。"
        )

    def answer_user_message(
        self,
        user_text: str,
        customer_profile: CustomerProfile,
        recommended_products: list[FlooringProduct],
    ) -> str:
        text = user_text.lower().replace(" ", "")

        if any(k in text for k in ["对比", "区别", "哪个好"]):
            return self._answer_comparison(recommended_products)

        if any(k in text for k in ["防水", "怕水", "潮湿", "回南天"]):
            return self._answer_waterproof(recommended_products, customer_profile)

        if any(k in text for k in ["地暖", "地热", "采暖"]):
            return self._answer_floor_heating(recommended_products, customer_profile)

        if any(k in text for k in ["宠物", "猫", "狗", "好打理", "好清洁"]):
            return self._answer_pet_friendly(recommended_products, customer_profile)

        if any(k in text for k in ["预算", "便宜", "多少钱", "价格", "性价比"]):
            return self._answer_budget(recommended_products, customer_profile)

        if recommended_products:
            main = recommended_products[0]
            backup = recommended_products[1] if len(recommended_products) > 1 else None
            answer = (
                f"根据您目前的需求，我会优先推荐{main.name}。它的主要优势是{self._points(main)}。"
            )
            if backup:
                answer += f" 备选可以看{backup.name}，它更适合对{backup.price_range}预算或{backup.color}风格有偏好的客户。"
            answer += self._next_question(customer_profile)
            return answer

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

    def _answer_waterproof(self, products: list[FlooringProduct], profile: CustomerProfile) -> str:
        waterproof = [p for p in products if p.waterproof] or [p for p in self.product_service.list_products() if p.waterproof]
        if waterproof:
            p = waterproof[0]
            return f"如果您比较关注防水，我会优先推荐{p.name}。它属于{p.type}地板，防水和日常清洁表现更好，适合厨房外侧、客厅或潮湿环境。最终安装仍要注意收边和基层防潮。{self._next_question(profile)}"
        return "目前模拟产品库里没有标记为强防水的产品。一般来说，SPC 会比实木更适合潮湿环境。"

    def _answer_floor_heating(self, products: list[FlooringProduct], profile: CustomerProfile) -> str:
        suitable = [p for p in products if p.floor_heating] or [p for p in self.product_service.list_products() if p.floor_heating]
        if suitable:
            p = suitable[0]
            return f"地暖场景建议看稳定性更好的产品，例如{p.name}。它标记为支持地暖，铺装时还需要确认地面找平、含水率和温控条件。{self._next_question(profile)}"
        return "可以选地暖适配产品，但需要销售进一步确认安装环境、辅材和温控要求。"

    def _answer_pet_friendly(self, products: list[FlooringProduct], profile: CustomerProfile) -> str:
        suitable = [p for p in products if p.pet_friendly] or [p for p in self.product_service.list_products() if p.pet_friendly]
        if suitable:
            p = suitable[0]
            return f"家里有宠物的话，我建议优先看{p.name}。它更耐磨，也更容易清洁，日常爪痕和水渍维护压力会小一些。{self._next_question(profile)}"
        return "宠物家庭建议优先考虑耐磨等级高、好清洁的 SPC 或强化地板。"

    def _answer_budget(self, products: list[FlooringProduct], profile: CustomerProfile) -> str:
        economic = [p for p in products if p.price_range in {"经济", "中等"}] or [p for p in self.product_service.list_products() if p.price_range in {"经济", "中等"}]
        if economic:
            p = economic[0]
            return f"如果希望控制预算，可以先看{p.name}，它的价格区间是{p.price_range}，同时保留了比较实用的耐磨和维护优势。{self._next_question(profile)}"
        return "预算有限时通常优先比较强化地板和部分 SPC 产品，性价比会更高。"

    def _answer_comparison(self, products: list[FlooringProduct]) -> str:
        if len(products) >= 2:
            a, b = products[0], products[1]
            return f"简单对比，{a.name}更突出{self._points(a)}；{b.name}更突出{self._points(b)}。如果重视防水耐磨，优先看 SPC 或强化；如果重视自然脚感和木纹质感，可以看多层实木。"
        return "可以的。一般 SPC 更偏防水、耐磨、好打理；多层实木更偏自然脚感和真实木纹；强化地板通常性价比更高。"

    @staticmethod
    def _points(product: FlooringProduct) -> str:
        return "、".join(product.selling_points[:3]) if product.selling_points else "适用场景明确、维护方便"

    @staticmethod
    def _next_question(profile: CustomerProfile) -> str:
        if not profile.room_type:
            return " 您主要是客厅、卧室还是全屋铺装？"
        if not profile.style:
            return " 您家装修更偏现代简约、北欧，还是新中式风格？"
        if not profile.budget:
            return " 您的预算更偏经济、中等，还是希望品质高一些？"
        return " 我也可以继续帮您比较两款产品的区别。"
