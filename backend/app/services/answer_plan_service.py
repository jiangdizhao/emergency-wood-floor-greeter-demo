from __future__ import annotations

from ..llm.schemas import (
    AnswerPlan,
    ApprovedCollectionFact,
    ApprovedProductFact,
    ApprovedPromotion,
    DialogueDecision,
    SalesDecision,
    ValidationResult,
)
from ..models import CustomerProfile, FlooringProduct
from .product_service import ProductService
from .promotion_service import PromotionService
from .sales_knowledge_service import SalesKnowledgeService


class AnswerPlanService:
    def __init__(
        self,
        product_service: ProductService,
        sales_knowledge_service: SalesKnowledgeService | None = None,
        promotion_service: PromotionService | None = None,
    ) -> None:
        self.product_service = product_service
        self.sales_knowledge_service = sales_knowledge_service or SalesKnowledgeService()
        self.promotion_service = promotion_service or PromotionService()

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
            context = self._sales_context(profile=profile, products=products, sales_decision=sales_decision)
            promotions = self._promotion_facts(profile=profile, products=products, context=context, force=False)
            return AnswerPlan(
                response_type="comparison",
                customer_need_summary=self._need_summary(profile),
                products=[
                    self._approved_product_fact(product, profile, presentation_role="对比款")
                    for product in products
                ],
                approved_promotions=promotions,
                constraints=self._constraints(),
                next_question=self._decision_question(profile, products),
                direct_message=None,
                must_recommend_now=bool(products),
                **context,
            )

        if decision.action == "recommend_now":
            products = recommended_products[:2]
            context = self._sales_context(profile=profile, products=products, sales_decision=sales_decision)
            promotions = self._promotion_facts(
                profile=profile,
                products=products,
                context=context,
                force=profile.promotion_interest is True,
            )
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
                approved_promotions=promotions,
                constraints=self._constraints(),
                next_question=self._decision_question(profile, products),
                direct_message=None,
                must_recommend_now=True,
                **context,
            )

        intent = validation.semantic_turn.intent
        products = self._select_products(
            intent=intent,
            validation=validation,
            profile=profile,
            recommended_products=recommended_products,
        )
        context = self._sales_context(profile=profile, products=products, sales_decision=sales_decision)

        if intent == "ask_promotion" or sales_decision.stage == "promotion":
            promotions = self._promotion_facts(profile=profile, products=products, context=context, force=True)
            if promotions:
                return AnswerPlan(
                    response_type="promotion",
                    customer_need_summary=self._need_summary(profile),
                    products=[
                        self._approved_product_fact(
                            product,
                            profile,
                            presentation_role="主推款" if index == 0 else "备选款",
                        )
                        for index, product in enumerate(products)
                    ],
                    approved_promotions=promotions,
                    constraints=self._constraints(),
                    call_to_action=promotions[0].call_to_action,
                    next_question=self._promotion_question(profile, promotions[0]),
                    direct_message=None,
                    **context,
                )
            return AnswerPlan(
                response_type="promotion",
                customer_need_summary=self._need_summary(profile),
                products=[],
                constraints=self._constraints(),
                next_question=(
                    "请先告诉我大概面积和当前更倾向的产品方向，我再按批准活动条件判断。"
                    if profile.estimated_area_sqm is None
                    else "您愿意先调整产品方向、房间范围，还是继续按当前方案核对正式报价？"
                ),
                direct_message=(
                    "当前批准的演示活动中，没有一项能在现有信息下确认适用。"
                    "我不会自行编造折扣或活动条件。"
                ),
                **context,
            )

        if intent in {"express_objection", "ask_reason"} or sales_decision.stage == "objection_handling":
            objection_response = self._objection_response(profile=profile, products=products)
            return AnswerPlan(
                response_type="objection_response",
                customer_need_summary=self._need_summary(profile),
                products=[
                    self._approved_product_fact(
                        product,
                        profile,
                        presentation_role="主推款" if index == 0 else "备选款",
                    )
                    for index, product in enumerate(products)
                ],
                objection_response=objection_response,
                constraints=self._constraints(),
                call_to_action="我们可以保留核心需求，只调整一个维度重新比较。",
                next_question=self._objection_question(profile),
                direct_message=None,
                **context,
            )

        if intent == "accept_recommendation" or sales_decision.stage in {"soft_close", "lead_capture", "follow_up"}:
            ask_contact = sales_decision.stage == "lead_capture" and not profile.contact_opt_in
            response_type = "lead_capture" if ask_contact else "soft_close"
            if profile.contact_opt_in:
                response_type = "soft_close"
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
                call_to_action=(
                    "您可以点击页面上的“获取方案与后续联系”，自愿选择联系方式和授权范围。"
                    if ask_contact
                    else "下一步可以确认面积、样板、正式报价或到店安排。"
                ),
                ask_contact_consent=ask_contact,
                contact_request_reason=(
                    "用于发送本次主推与备选方案，并在您授权的范围内跟进报价、样板或到店安排。"
                    if ask_contact
                    else None
                ),
                next_question=(
                    None
                    if ask_contact or profile.contact_opt_in
                    else self._decision_question(profile, products)
                ),
                direct_message=(
                    "您的本次方案联系授权已经保存，我不会重复索取联系方式。门店会按您授权的用途和时间安排后续。"
                    if profile.contact_opt_in
                    else None
                ),
                **context,
            )

        response_type = "product_answer" if intent == "general_product_question" else "acknowledgement"
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
            **context,
        )

    def unavailable(self, *, provider_mode: str) -> AnswerPlan:
        message = (
            "云端智能服务暂时不可用。本次不会自动切换到本地模型，请稍后重试或重新开始并选择本地隐私模式。"
            if provider_mode == "terra"
            else "本地 Qwen 服务暂时不可用。请确认 Ollama 已启动并加载 qwen3.5:4b，然后再试一次。"
        )
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
            text = answer_plan.direct_message
            if answer_plan.next_question:
                text += answer_plan.next_question
            return text

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
            if answer_plan.approved_promotions:
                text += answer_plan.approved_promotions[0].approved_message
            if answer_plan.next_question:
                text += answer_plan.next_question
            return text

        if answer_plan.response_type == "promotion":
            if answer_plan.approved_promotions:
                promotion = answer_plan.approved_promotions[0]
                text = promotion.approved_message
                if promotion.call_to_action:
                    text += promotion.call_to_action
                return text
            return "当前没有可以确认适用的批准演示活动，我不会自行编造折扣或条件。"

        if answer_plan.response_type == "objection_response":
            text = "我理解您的顾虑。" + "".join(answer_plan.objection_response[:2])
            tradeoff = next((item for product in answer_plan.products for item in product.tradeoffs), None)
            if tradeoff:
                text += f"需要同时考虑的是，{tradeoff}。"
            if answer_plan.next_question:
                text += answer_plan.next_question
            return text

        if answer_plan.response_type in {"soft_close", "lead_capture"}:
            text = answer_plan.call_to_action or "下一步可以确认面积、样板和正式报价。"
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

    def _promotion_facts(
        self,
        *,
        profile: CustomerProfile,
        products: list[FlooringProduct],
        context: dict,
        force: bool,
    ) -> list[ApprovedPromotion]:
        if not force and profile.estimated_area_sqm is None:
            return []
        collection_ids = [item.collection_id for item in context.get("featured_collections", [])]
        promotions = self.promotion_service.eligible_promotions(
            profile=profile,
            products=products,
            collection_ids=collection_ids,
            limit=2,
        )
        return [self._approved_promotion(item) for item in promotions]

    @staticmethod
    def _approved_promotion(promotion: dict) -> ApprovedPromotion:
        return ApprovedPromotion(
            promotion_id=str(promotion.get("promotion_id") or "unknown"),
            title=str(promotion.get("title") or "演示活动"),
            approved_message=str(promotion.get("approved_message") or ""),
            conditions=[str(item) for item in promotion.get("conditions", [])[:4]],
            call_to_action=str(promotion.get("call_to_action") or "") or None,
            area_status=str(promotion.get("area_status") or "not_required"),
            simulated=bool(promotion.get("simulated", True)),
        )

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
        prior = [
            product
            for product_id in profile.recommended_product_ids
            if (product := self.product_service.get_product(product_id)) is not None
        ]
        if intent == "request_comparison":
            return self._unique_products(mentioned or recommended_products or prior)[:2]
        if intent in {
            "general_product_question",
            "ask_reason",
            "ask_promotion",
            "express_objection",
            "accept_recommendation",
        }:
            return self._unique_products(mentioned or prior or recommended_products)[:2]
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
        driver_reason = self._driver_match_reason(product, profile.primary_purchase_driver)
        if driver_reason:
            reasons.append(driver_reason)
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

        tradeoffs = self.sales_knowledge_service.product_tradeoffs(product)
        if profile.primary_purchase_driver == "环保":
            disclaimer = "当前演示产品数据未提供可核验的环保认证或检测信息，不能据此作环保承诺"
            if disclaimer not in tradeoffs:
                tradeoffs.append(disclaimer)

        return ApprovedProductFact(
            product_id=product.id,
            name=product.name,
            product_type=product.type,
            color=product.color,
            price_range=product.price_range,
            presentation_role=presentation_role,  # type: ignore[arg-type]
            approved_facts=facts,
            match_reasons=self._unique_strings(reasons),
            tradeoffs=self._unique_strings(tradeoffs)[:3],
        )

    @staticmethod
    def _driver_match_reason(product: FlooringProduct, driver: str | None) -> str | None:
        if driver == "防水" and product.waterproof:
            return "符合您把防水放在首位的要求"
        if driver == "耐磨" and product.wear_level.upper() in {"AC4", "AC5", "高"}:
            return "符合您把耐磨放在首位的要求"
        if driver == "价格" and product.price_range in {"经济", "中等"}:
            return "符合您优先控制预算的要求"
        if driver == "脚感" and product.type in {"多层实木", "三层实木", "实木"}:
            return "符合您把脚感放在首位的要求"
        if driver == "好清洁" and (product.waterproof or product.pet_friendly):
            return "符合您把日常好清洁放在首位的要求"
        if driver == "环保" and any(
            marker in point
            for point in product.selling_points
            for marker in ("环保", "低醛", "认证", "检测")
        ):
            return "产品资料中包含与环保相关的批准信息"
        return None

    @staticmethod
    def _need_summary(profile: CustomerProfile) -> list[str]:
        summary: list[str] = []
        if profile.primary_purchase_driver:
            summary.append(f"首要购买驱动：{profile.primary_purchase_driver}")
        if profile.project_type:
            summary.append(f"项目类型：{profile.project_type}")
        if profile.room_type:
            summary.append(f"使用空间：{profile.room_type}")
        if profile.estimated_area_sqm is not None:
            summary.append(f"预计面积：{profile.estimated_area_sqm:g}㎡")
        if profile.purchase_timeline:
            summary.append(f"计划铺装：{profile.purchase_timeline}")
        if profile.decision_stage:
            summary.append(f"决策阶段：{profile.decision_stage}")
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
        if profile.objections:
            summary.append("当前顾虑：" + "、".join(profile.objections))
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
        if profile.estimated_area_sqm is not None:
            known.append(f"约{profile.estimated_area_sqm:g}㎡")
        if profile.purchase_timeline:
            known.append(profile.purchase_timeline)
        if profile.preferred_colors:
            known.append("偏好" + "、".join(profile.preferred_colors))
        prefix = (
            "明白了，我已经抓住您关于" + "、".join(known) + "的重点。"
            if known
            else "好的，我先从您最重要的购买标准开始了解。"
        )
        return prefix + (question or "")

    @staticmethod
    def _acknowledgement(profile: CustomerProfile) -> str:
        summary = AnswerPlanService._need_summary(profile)
        return (
            "好的，我已经记录并整理为：" + "；".join(summary) + "。"
            if summary
            else "好的，我已经记录了您刚才确认的内容。"
        )

    @staticmethod
    def _decision_question(profile: CustomerProfile, products: list[FlooringProduct]) -> str | None:
        if profile.estimated_area_sqm is None:
            return "为了判断活动条件、报价范围和铺装工作量，请问预计铺装面积大约多少平方米？"
        if not profile.purchase_timeline:
            return "您计划什么时候铺装：1个月内、1到3个月、3个月以上，还是时间待定？"
        if len(products) >= 2:
            primary = products[0]
            backup = products[1]
            return (
                f"在{primary.name}和{backup.name}这两个方向里，"
                "您现在更想保留核心性能，还是在脚感、外观或预算上做调整？"
            )
        if not profile.preferred_colors and not profile.rejected_colors:
            return "这个性能方向您是否认可？如果认可，我再帮您把颜色和整体风格收窄。"
        return "这个主推方向是否符合您的预期，还是有哪一点仍然让您犹豫？"

    @staticmethod
    def _promotion_question(profile: CustomerProfile, promotion: ApprovedPromotion) -> str | None:
        if promotion.area_status == "needs_area" and profile.estimated_area_sqm is None:
            return "请告诉我大概面积，我才能确认是否达到这项演示活动的建议条件。"
        return promotion.call_to_action

    @staticmethod
    def _objection_response(*, profile: CustomerProfile, products: list[FlooringProduct]) -> list[str]:
        objections = profile.objections or ["需要进一步确认"]
        messages: list[str] = []
        for objection in objections[-2:]:
            if objection == "价格顾虑":
                messages.append("价格顾虑是合理的；我们应比较主推款解决的核心风险，以及备选款能节省预算时牺牲了什么。")
            elif objection == "环保顾虑":
                messages.append("环保问题必须以可核验的检测或认证资料为准；当前演示数据不足以支持额外环保承诺。")
            elif objection == "防水顾虑":
                messages.append("防水标记只能说明当前产品资料中的能力方向，最终仍需确认铺装边界、接缝和使用环境。")
            elif objection == "维护顾虑":
                messages.append("维护成本应结合水渍、宠物、清洁频率和材料脚感一起判断，不能只看一个参数。")
            elif objection == "脚感顾虑":
                messages.append("脚感与耐磨、防水和预算往往存在取舍，可以保留核心性能后再比较实木类备选。")
            elif objection == "需要商量":
                messages.append("可以先保留主推款与备选款的差异摘要，方便您和家人围绕同一组标准讨论。")
            elif objection == "需要比较":
                messages.append("比较时应固定空间和核心需求，只改变材质或预算一个变量，避免被无关参数干扰。")
            elif objection == "颜色顾虑":
                messages.append("颜色必须结合采光、墙面和家具确认；当前建议只用于收窄方向，不能替代现场样板。")
        if not messages and products:
            messages.append("我会把推荐依据和材料取舍分开说明，帮助您判断哪一点值得保留。")
        return messages

    @staticmethod
    def _objection_question(profile: CustomerProfile) -> str:
        if "价格顾虑" in profile.objections:
            return "您更希望控制总预算，还是愿意为核心性能保留一定预算空间？"
        if "需要商量" in profile.objections:
            return "您和家人最可能分歧的是预算、颜色、脚感，还是材料性能？"
        return "在目前的顾虑里，哪一点如果不能解决，您就不会继续考虑这个方案？"

    @staticmethod
    def _constraints() -> list[str]:
        return [
            "只能使用批准的产品、系列、促销、匹配原因和取舍信息",
            "不得更换 Backend 选择的产品或主推款/备选款角色",
            "不得声称完全防水、零甲醛、免维护或提供未批准承诺",
            "不得虚构价格、库存、折扣、质保、认证、案例或安装日期",
            "促销只能来自 approved_promotions，且必须保留演示数据和门店确认限定",
            "必须如实表达至少一个相关材料取舍，不得把所有产品描述为完美",
            "联系方式只能通过独立表单收集，不得要求客户在聊天或语音中直接提供",
            "本次方案联系授权与长期营销授权必须分开，不得默认营销授权",
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

    @staticmethod
    def _unique_strings(values: list[str]) -> list[str]:
        output: list[str] = []
        for value in values:
            if value and value not in output:
                output.append(value)
        return output
