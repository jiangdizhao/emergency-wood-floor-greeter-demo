from __future__ import annotations

from ..llm.schemas import (
    AnswerPlan,
    ApprovedCollectionFact,
    ApprovedProductFact,
    DialogueDecision,
    SalesDecision,
    ValidationResult,
)
from ..models import CustomerProfile, FlooringProduct
from .product_service import ProductService
from .sales_knowledge_service import SalesKnowledgeService


class AnswerPlanService:
    def __init__(
        self,
        product_service: ProductService,
        sales_knowledge_service: SalesKnowledgeService | None = None,
    ) -> None:
        self.product_service = product_service
        self.sales_knowledge_service = sales_knowledge_service or SalesKnowledgeService()

    def build(
        self,
        *,
        user_text: str,
        validation: ValidationResult,
        profile: CustomerProfile,
        recommended_products: list[FlooringProduct],
        decision: DialogueDecision,
        sales_decision: SalesDecision,
    ) -> AnswerPlan:
        common = self._sales_context(
            profile=profile,
            products=recommended_products,
            sales_decision=sales_decision,
        )

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
                **common,
            )

        if decision.action == "ask_missing_slot":
            return AnswerPlan(
                response_type="acknowledgement",
                customer_need_summary=self._need_summary(profile),
                products=[],
                constraints=self._constraints(),
                next_question=decision.question,
                direct_message=self._acknowledge_and_ask(profile=profile, question=decision.question),
                **common,
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
                products=[
                    self._approved_product_fact(
                        product,
                        profile,
                        presentation_role="对比款",
                    )
                    for product in products
                ],
                constraints=self._constraints(),
                next_question=self._decision_question(profile, products),
                direct_message=None,
                must_recommend_now=bool(products),
                **self._sales_context(profile=profile, products=products, sales_decision=sales_decision),
            )

        if decision.action == "recommend_now":
            products = recommended_products[:2]
            approved_products = [
                self._approved_product_fact(
                    product,
                    profile,
                    presentation_role="主推款" if index == 0 else "备选款",
                )
                for index, product in enumerate(products)
            ]
            return AnswerPlan(
                response_type="recommendation",
                customer_need_summary=self._need_summary(profile),
                products=approved_products,
                constraints=self._constraints(),
                next_question=self._decision_question(profile, products),
                direct_message=None,
                must_recommend_now=True,
                **self._sales_context(profile=profile, products=products, sales_decision=sales_decision),
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
            products=[
                self._approved_product_fact(
                    product,
                    profile,
                    presentation_role="主推款" if index == 0 else "备选款",
                )
                for index, product in enumerate(products)
            ],
            constraints=self._constraints(),
            next_question=None,
            direct_message=direct_message,
            **self._sales_context(profile=profile, products=products, sales_decision=sales_decision),
        )

    def unavailable(self, *, provider_mode: str) -> AnswerPlan:
        if provider_mode == "terra":
            message = "云端智能服务暂时不可用。本次不会自动切换到本地模型，请稍后重试或重新开始并选择本地隐私模式。"
        else:
            message = "本地 Qwen 服务暂时不可用。请确认 Ollama 已启动并加载 qwen3.5:4b，然后再试一次。"
        return AnswerPlan(
            response_type="service_unavailable",
            sales_stage="discovery",
            sales_objective="清楚说明当前服务状态",
            next_best_action="clarify_customer_input",
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
            reason = "、".join(first.match_reasons[:3]) or "与您目前最重要的需求较匹配"
            text = f"围绕您最重视的条件，我把{first.name}作为{first.presentation_role}，因为它{reason}。"
            if len(answer_plan.products) > 1:
                second = answer_plan.products[1]
                second_reason = "、".join(second.match_reasons[:2]) or "可以从另一个维度补充比较"
                text += f"{second.name}作为{second.presentation_role}，它{second_reason}。"
            tradeoff = next((item for product in answer_plan.products for item in product.tradeoffs), None)
            if tradeoff:
                text += f"需要提前说明的是，{tradeoff}。"
            if answer_plan.next_question:
                text += answer_plan.next_question
            return text
        if answer_plan.products:
            first = answer_plan.products[0]
            facts = "；".join(first.approved_facts[:2])
            tradeoff = first.tradeoffs[0] if first.tradeoffs else None
            text = f"{first.name}的已确认信息包括：{facts}。"
            if tradeoff:
                text += f"同时需要考虑：{tradeoff}。"
            return text
        return "好的，我已经记录了您刚才确认的需求。"

    def _sales_context(
        self,
        *,
        profile: CustomerProfile,
        products: list[FlooringProduct],
        sales_decision: SalesDecision,
    ) -> dict:
        collections = self.sales_knowledge_service.relevant_collections(
            profile=profile,
            products=products,
        )
        return {
            "sales_stage": sales_decision.stage,
            "sales_objective": sales_decision.objective,
            "next_best_action": sales_decision.next_best_action,
            "company_highlights": self.sales_knowledge_service.company_highlights(limit=2),
            "featured_collections": [self._approved_collection_fact(item) for item in collections],
        }

    @staticmethod
    def _approved_collection_fact(collection: dict) -> ApprovedCollectionFact:
        return ApprovedCollectionFact(
            collection_id=str(collection.get("collection_id") or "unknown"),
            name=str(collection.get("name") or "门店特色系列"),
            tagline=str(collection.get("tagline") or ""),
            strengths=[str(item) for item in collection.get("strengths", [])[:3]],
            tradeoffs=[str(item) for item in collection.get("tradeoffs", [])[:2]],
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
        return []

    def _approved_product_fact(
        self,
        product: FlooringProduct,
        profile: CustomerProfile,
        *,
        presentation_role: str,
    ) -> ApprovedProductFact:
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
        if profile.primary_purchase_driver:
            reasons.append(f"围绕您最重视的{profile.primary_purchase_driver}进行匹配")
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
            presentation_role=presentation_role,  # type: ignore[arg-type]
            approved_facts=facts,
            match_reasons=reasons,
            tradeoffs=self.sales_knowledge_service.product_tradeoffs(product),
        )

    @staticmethod
    def _need_summary(profile: CustomerProfile) -> list[str]:
        summary: list[str] = []
        if profile.primary_purchase_driver:
            summary.append(f"首要购买驱动：{profile.primary_purchase_driver}")
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
        if profile.primary_purchase_driver:
            known.append(f"最重视{profile.primary_purchase_driver}")
        if profile.room_type:
            known.append(profile.room_type)
        if profile.budget:
            known.append(f"{profile.budget}预算")
        if profile.style:
            known.append(profile.style)
        if profile.preferred_colors:
            known.append("偏好" + "、".join(profile.preferred_colors))
        prefix = "明白了，我已经抓住您关于" + "、".join(known) + "的重点。" if known else "好的，我先从您最重要的购买标准开始了解。"
        return prefix + (question or "")

    @staticmethod
    def _acknowledgement(profile: CustomerProfile) -> str:
        summary = AnswerPlanService._need_summary(profile)
        if summary:
            return "好的，我已经记录并整理为：" + "；".join(summary) + "。"
        return "好的，我已经记录了您刚才确认的内容。"

    @staticmethod
    def _decision_question(profile: CustomerProfile, products: list[FlooringProduct]) -> str | None:
        if len(products) >= 2:
            primary = products[0]
            backup = products[1]
            return (
                f"在{primary.name}和{backup.name}这两个方向里，"
                "您更想优先保留核心性能，还是更看重脚感、外观或预算上的平衡？"
            )
        if not profile.preferred_colors and not profile.rejected_colors:
            return "这个性能方向您是否认可？如果认可，我再帮您把颜色和整体风格收窄。"
        return "这个主推方向是否符合您的预期，还是有哪一点仍然让您犹豫？"

    @staticmethod
    def _constraints() -> list[str]:
        return [
            "只能使用 approved_facts、match_reasons、tradeoffs、company_highlights 和 featured_collections 中的批准信息",
            "不得更换 Backend 选择的产品或主推款/备选款角色",
            "不得声称完全防水、零甲醛、免维护或提供未批准承诺",
            "不得虚构价格、库存、折扣、质保、认证、案例或安装日期",
            "必须如实表达至少一个相关材料取舍，不得把所有产品描述为完美",
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
