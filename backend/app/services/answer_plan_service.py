from __future__ import annotations

from ..llm.schemas import AnswerPlan, ApprovedProductFact, DialogueDecision, ValidationResult
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
        decision: DialogueDecision,
    ) -> AnswerPlan:
        if decision.action == "clarify":
            return AnswerPlan(
                response_type="clarification",
                customer_need_summary=self._need_summary(profile),
                products=[],
                constraints=self._constraints(),
                next_question=decision.question,
                direct_message=decision.question
                or validation.clarification_question
                or "我没有完全听清。请只确认一个最重要的条件。",
            )

        if decision.action == "ask_missing_slot":
            return AnswerPlan(
                response_type="acknowledgement",
                customer_need_summary=self._need_summary(profile),
                products=[],
                constraints=self._constraints(),
                next_question=decision.question,
                direct_message=self._acknowledge_and_ask(profile=profile, question=decision.question),
            )

        if decision.action == "compare_now":
            products = self._select_products(
                intent="request_comparison",
                validation=validation,
                profile=profile,
                recommended_products=recommended_products,
            )
            return AnswerPlan(
                response_type="comparison",
                customer_need_summary=self._need_summary(profile),
                products=[self._approved_product_fact(product, profile) for product in products],
                constraints=self._constraints(),
                next_question=None,
                direct_message=None,
                must_recommend_now=bool(products),
            )

        if decision.action == "recommend_now":
            products = recommended_products[:2]
            return AnswerPlan(
                response_type="recommendation",
                customer_need_summary=self._need_summary(profile),
                products=[self._approved_product_fact(product, profile) for product in products],
                constraints=self._constraints(),
                next_question=self._optional_follow_up(profile),
                direct_message=None,
                must_recommend_now=True,
            )

        intent = validation.semantic_turn.intent
        products = self._select_products(
            intent=intent,
            validation=validation,
            profile=profile,
            recommended_products=recommended_products,
        )
        response_type = "product_answer" if intent in {"general_product_question", "ask_reason"} else "acknowledgement"
        direct_message = self._acknowledgement(profile) if response_type == "acknowledgement" else None

        return AnswerPlan(
            response_type=response_type,
            customer_need_summary=self._need_summary(profile),
            products=[self._approved_product_fact(product, profile) for product in products],
            constraints=self._constraints(),
            next_question=None,
            direct_message=direct_message,
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

    def fallback_text(self, answer_plan: AnswerPlan) -> str:
        if answer_plan.direct_message:
            return answer_plan.direct_message
        if answer_plan.response_type in {"recommendation", "comparison"} and answer_plan.products:
            first = answer_plan.products[0]
            reason = "、".join(first.match_reasons[:3]) or "与您目前已确认的需求较匹配"
            text = f"根据您目前的需求，我建议优先看{first.name}，它{reason}。"
            if len(answer_plan.products) > 1:
                second = answer_plan.products[1]
                text += f"也可以把{second.name}作为备选进行对比。"
            if answer_plan.next_question:
                text += answer_plan.next_question
            return text
        if answer_plan.products:
            first = answer_plan.products[0]
            facts = "；".join(first.approved_facts[:2])
            return f"{first.name}的已确认信息包括：{facts}。"
        return "好的，我已经记录了您刚才确认的需求。"

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
        return []

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
        if profile.preferred_colors and any(
            preferred.replace("色", "") in product.color.replace("色", "")
            or product.color.replace("色", "") in preferred.replace("色", "")
            for preferred in profile.preferred_colors
        ):
            reasons.append("符合颜色偏好")

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
        for label, value in [
            ("宠物", profile.has_pets),
            ("地暖", profile.has_floor_heating),
            ("儿童", profile.has_children),
            ("老人", profile.has_elderly),
            ("潮湿环境", profile.humid_environment),
        ]:
            if value is True:
                summary.append(f"有{label}需求")
            elif value is False:
                summary.append(f"无{label}需求")
        for priority, level in profile.priorities.items():
            summary.append(f"{priority}优先级：{level}")
        if profile.preferred_colors:
            summary.append("颜色偏好：" + "、".join(profile.preferred_colors))
        return summary

    @staticmethod
    def _acknowledge_and_ask(*, profile: CustomerProfile, question: str | None) -> str:
        known: list[str] = []
        if profile.room_type:
            known.append(profile.room_type)
        if profile.budget:
            known.append(f"{profile.budget}预算")
        if profile.style:
            known.append(profile.style)
        if profile.preferred_colors:
            known.append("偏好" + "、".join(profile.preferred_colors))
        prefix = "好的，已记录您关于" + "、".join(known) + "的需求。" if known else "好的，我正在逐项记录您的需求。"
        return prefix + (question or "")

    @staticmethod
    def _acknowledgement(profile: CustomerProfile) -> str:
        summary = AnswerPlanService._need_summary(profile)
        if summary:
            return "好的，已记录：" + "；".join(summary) + "。"
        return "好的，我已经记录了您刚才确认的内容。"

    @staticmethod
    def _optional_follow_up(profile: CustomerProfile) -> str | None:
        if not profile.preferred_colors and not profile.rejected_colors:
            return "您更喜欢浅灰色、原木色还是深色系？"
        return None

    @staticmethod
    def _constraints() -> list[str]:
        return [
            "只能使用 approved_facts 中的产品事实",
            "不得更换 Backend 选择的产品",
            "不得声称完全防水、零甲醛、免维护或提供未批准承诺",
            "不得虚构价格、库存、折扣、质保或安装日期",
            "products 为空时不得承诺稍后推荐",
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
