from __future__ import annotations

from ..llm.schemas import DialogueDecision, SalesDecision, ValidationResult
from ..models import CustomerProfile
from .dialogue_context_service import DialogueContext


class SalesConversationPolicy:
    """Select the next sales objective without turning the dialogue into a form."""

    def decide(
        self,
        *,
        validation: ValidationResult,
        profile: CustomerProfile,
        context: DialogueContext,
        dialogue_decision: DialogueDecision,
    ) -> SalesDecision:
        intent = validation.semantic_turn.intent

        if dialogue_decision.action == "clarify":
            return SalesDecision(
                stage="discovery",
                next_best_action="clarify_customer_input",
                objective="只澄清一个确实无法继续的冲突，不借机追加其他问题",
                reason="shared validation guard requires clarification",
            )

        if intent == "ask_promotion":
            return SalesDecision(
                stage="promotion",
                next_best_action="mention_approved_promotion",
                objective="只介绍当前批准且适用的活动；只有活动判断确实需要时才询问面积",
                reason="customer explicitly asked about promotions",
            )

        if intent in {"express_objection", "ask_reason"}:
            return SalesDecision(
                stage="objection_handling",
                next_best_action="explain_tradeoff",
                objective="先回应顾虑，再用产品事实和取舍帮助客户判断，不把回答变成新的问卷",
                reason="customer expressed an objection or requested rationale",
            )

        if intent == "general_product_question":
            return SalesDecision(
                stage="recommendation",
                next_best_action="present_main_and_backup",
                objective="准确回答当前产品问题，并顺带补充一个相关的系列或产品亮点",
                reason="explicit product question takes priority",
            )

        if dialogue_decision.action in {"recommend_now", "compare_now"}:
            return SalesDecision(
                stage="recommendation",
                next_best_action="present_main_and_backup",
                objective=(
                    "主动展示主推款、备选款和一个门店特色系列；只复述最相关的一两个客户条件，"
                    "不要逐项盘问预算、风格、面积、时间或颜色；以陈述式邀请结束，不自动追加问题"
                ),
                reason="provide product value now instead of collecting every slot first",
            )

        if intent == "accept_recommendation":
            if profile.contact_opt_in:
                return SalesDecision(
                    stage="follow_up",
                    next_best_action="prepare_follow_up",
                    objective="确认已保存的后续安排，不重复索取联系方式，也不再追加无关问题",
                    reason="customer accepted recommendation and contact consent already exists",
                )
            if profile.contact_prompt_eligible:
                return SalesDecision(
                    stage="lead_capture",
                    next_best_action="offer_contact_form",
                    objective="客户已明确希望推进时，才邀请其自愿使用独立表单接收方案",
                    reason="customer accepted the recommendation and is eligible for contact offer",
                )
            return SalesDecision(
                stage="soft_close",
                next_best_action="soft_close",
                objective="确认客户认可的方向，并给出样板、报价或到店体验等低压力选项",
                reason="customer accepted the recommendation",
            )

        if profile.recommended_product_ids:
            if profile.promotion_interest is True and not profile.promotion_ids_presented:
                return SalesDecision(
                    stage="promotion",
                    next_best_action="mention_approved_promotion",
                    objective="根据已确认的产品条件介绍适用活动，不主动制造紧迫感",
                    reason="customer expressed promotion interest",
                )

            # Do not automatically ask area, timeline, style, colour or contact
            # details after every answer. Keep the customer engaged by adding one
            # fresh product, collection or use-case insight instead.
            return SalesDecision(
                stage="recommendation",
                next_best_action="present_main_and_backup",
                objective=(
                    "围绕现有主推方向补充一个新的产品特点、使用场景或特色系列亮点；"
                    "避免重复完整需求摘要；不要自动询问面积、时间、预算、风格或颜色；"
                    "只有客户主动想继续时，再按其选择的维度收窄"
                ),
                reason=f"maintain a value-first product conversation at turn {context.turn_index}",
            )

        if not profile.priorities and not profile.primary_purchase_driver:
            return SalesDecision(
                stage="discovery",
                next_best_action="ask_primary_priority",
                objective="只确认一个最重要需求，明确表示客户不需要一次回答很多问题",
                reason="primary purchase driver is still unknown",
            )

        return SalesDecision(
            stage="recommendation",
            next_best_action="present_main_and_backup",
            objective="基于已经知道的一点需求先展示产品价值，不等待所有字段齐全",
            reason="one meaningful signal is sufficient to start selling",
        )
