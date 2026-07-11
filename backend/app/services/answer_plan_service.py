from __future__ import annotations

from ..llm.schemas import AnswerPlan, ApprovedProductFact, ValidationResult
from ..models import CustomerProfile, FlooringProduct
from .product_service import ProductService


class AnswerPlanService:
    def __init__(self, product_service: ProductService) -> None:
        self.product_service = product_service

    def build(
        self,
        *,
        user_text: str,
        validation: ValidationResult,
        profile: CustomerProfile,
        recommended_products: list[FlooringProduct],
    ) -> AnswerPlan:
        if not validation.ok:
            return AnswerPlan(
                response_type="clarification",
                customer_need_summary=self._need_summary(profile),
                products=[],
                constraints=self._constraints(),
                next_question=None,
                direct_message=validation.clarification_question
                or "我没有完全理解您的需求，请换一种更直接的说法。",
            )

        intent = validation.semantic_turn.intent
        products = self._select_products(
            intent=intent,
            validation=validation,
            profile=profile,
            recommended_products=recommended_products,
        )

        if intent == "request_comparison":
            response_type = "comparison"
        elif intent == "general_product_question":
            response_type = "product_answer"
        elif intent == "ask_reason":
            response_type = "product_answer"
        elif validation.semantic_turn.recommendation_requested:
            response_type = "recommendation"
        else:
            response_type = "acknowledgement"

        return AnswerPlan(
            response_type=response_type,
            customer_need_summary=self._need_summary(profile),
            products=[self._approved_product_fact(product, profile) for product in products],
            constraints=self._constraints(),
            next_question=self._next_question(profile),
            direct_message=None,
        )

    def unavailable(self, *, provider_mode: str) -> AnswerPlan:
        if provider_mode == "terra":
            message = "云端智能服务暂时不可用。本次不会自动切换到本地模型，请稍后重试或重新开始并选择本地隐私模式。"
        else:
            message = "本地 Qwen 服务暂时不可用。请确认 Ollama 已启动并加载 qwen3.5:4b，然后再试一次。"
        return AnswerPlan(
            response_type="service_unavailable",
            customer_need_summary=[],
            products=[],
            constraints=self._constraints(),
            next_question=None,
            direct_message=message,
        )

    def _select_products(
        self,
        *,
        intent: str,
        validation: ValidationResult,
        profile: CustomerProfile,
        recommended_products: list[FlooringProduct],
    ) -> list[FlooringProduct]:
        mentioned = [
            product
            for product_id in validation.mentioned_product_ids
            if (product := self.product_service.get_product(product_id)) is not None
        ]
        if intent == "request_comparison":
            return self._unique_products(mentioned or recommended_products)[:2]
        if intent in {"general_product_question", "ask_reason"}:
            if mentioned:
                return self._unique_products(mentioned)[:2]
            prior = [
                product
                for product_id in profile.recommended_product_ids
                if (product := self.product_service.get_product(product_id)) is not None
            ]
            return self._unique_products(prior or recommended_products)[:2]
        if intent in {"reject_product", "reject_color", "provide_or_modify_needs", "other"}:
            return []
        return recommended_products[:2]

    @staticmethod
    def _approved_product_fact(product: FlooringProduct, profile: CustomerProfile) -> ApprovedProductFact:
        facts = [
            f"材质：{product.type}",
            f"颜色：{product.color}",
            f"价格区间：{product.price_range}",
            f"适合空间：{'、'.join(product.suitable_rooms)}",
            f"耐磨等级：{product.wear_level}",
            f"地暖适配：{'支持' if product.floor_heating else '不支持'}",
            f"宠物友好：{'是' if product.pet_friendly else '否'}",
            f"防水标记：{'是' if product.waterproof else '否'}",
        ]
        if product.spec:
            facts.append(f"规格：{product.spec}")
        facts.extend(product.selling_points[:3])

        reasons: list[str] = []
        if profile.room_type and profile.room_type in product.suitable_rooms:
            reasons.append(f"适合{profile.room_type}")
        if profile.budget and profile.budget == product.price_range:
            reasons.append(f"符合{profile.budget}预算")
        if profile.has_pets and product.pet_friendly:
            reasons.append("符合宠物家庭需求")
        if profile.has_floor_heating and product.floor_heating:
            reasons.append("支持地暖")
        if profile.humid_environment and product.waterproof:
            reasons.append("适合关注防水的环境")
        if profile.priorities.get("耐磨") and product.wear_level.upper() in {"AC4", "AC5", "高"}:
            reasons.append("符合耐磨优先要求")
        if profile.priorities.get("脚感") and product.type in {"多层实木", "三层实木", "实木"}:
            reasons.append("符合脚感优先要求")
        if profile.priorities.get("好清洁") and (product.waterproof or product.pet_friendly):
            reasons.append("日常维护相对容易")

        return ApprovedProductFact(
            product_id=product.id,
            name=product.name,
            product_type=product.type,
            color=product.color,
            price_range=product.price_range,
            approved_facts=facts,
            match_reasons=reasons,
        )

    @staticmethod
    def _need_summary(profile: CustomerProfile) -> list[str]:
        summary: list[str] = []
        if profile.room_type:
            summary.append(f"使用空间：{profile.room_type}")
        if profile.style:
            summary.append(f"风格：{profile.style}")
        if profile.budget:
            summary.append(f"预算：{profile.budget}")
        bool_fields = [
            ("宠物", profile.has_pets),
            ("地暖", profile.has_floor_heating),
            ("儿童", profile.has_children),
            ("老人", profile.has_elderly),
            ("潮湿环境", profile.humid_environment),
        ]
        for label, value in bool_fields:
            if value is True:
                summary.append(f"有{label}需求")
            elif value is False:
                summary.append(f"无{label}需求")
        for priority, level in profile.priorities.items():
            summary.append(f"{priority}优先级：{level}")
        return summary

    @staticmethod
    def _next_question(profile: CustomerProfile) -> str | None:
        if not profile.room_type:
            return "您这次主要铺在客厅、卧室还是全屋？"
        if not profile.budget:
            return "您的预算更接近经济、中等、偏高还是高端？"
        if not profile.style:
            return "您更喜欢现代简约、北欧原木、新中式还是其他风格？"
        if not profile.preferred_colors and not profile.rejected_colors:
            return "您更喜欢浅灰、原木色还是深色系？"
        return None

    @staticmethod
    def _constraints() -> list[str]:
        return [
            "只能使用 approved_facts 中的产品事实",
            "不得更换 Backend 选择的产品",
            "不得声称完全防水、零甲醛、免维护或提供未批准承诺",
            "不得虚构价格、库存、折扣、质保或安装日期",
        ]

    @staticmethod
    def _unique_products(products: list[FlooringProduct]) -> list[FlooringProduct]:
        seen: set[str] = set()
        output: list[FlooringProduct] = []
        for product in products:
            if product.id not in seen:
                output.append(product)
                seen.add(product.id)
        return output
