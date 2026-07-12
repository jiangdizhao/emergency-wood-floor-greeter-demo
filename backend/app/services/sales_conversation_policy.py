from __future__ import annotations

from ..llm.schemas import DialogueDecision, SalesDecision, ValidationResult
from ..models import CustomerProfile
from .dialogue_context_service import DialogueContext


class SalesConversationPolicy:
    """Selects the next sales objective without giving the LLM business control."""

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
                objective="只澄清一个没有听清或存在冲突的条件，同时保留已经确认的信息",
                reason="shared validation guard requires clarification",
            )

        if intent == "ask_promotion":
            return SalesDecision(
                stage="promotion",
                next_best_action="mention_approved_promotion",
                objective="只介绍 Backend 当前批准且适用的演示活动，并明确适用条件和门店确认要求",
                reason="customer explicitly asked about promotions",
            )

        # Historical objections remain in the profile for summaries and CRM context,
        # but only the current turn can enter objection-handling mode. Otherwise one
        # earlier price concern would trap every later turn in the same stage.
        if intent in {"express_objection", "ask_reason"}:
            return SalesDecision(
                stage="objection_handling",
                next_best_action="explain_tradeoff",
                objective="先承认顾虑，再用批准事实解释价值与取舍，并给出可验证的下一步",
                reason="customer expressed an objection or requested rationale",
            )

        if intent == "general_product_question":
            return SalesDecision(
                stage="qualification",
                next_best_action="qualify_needs",
                objective="先准确回答客户当前产品问题，再决定是否推进销售下一步",
                reason="explicit product question takes priority over follow-up state",
            )

        if dialogue_decision.action in {"recommend_now", "compare_now"}:
            return SalesDecision(
                stage="recommendation",
                next_best_action="present_main_and_backup",
                objective="围绕客户最重要的购买驱动，给出主推款与备选款，说明实际价值和至少一个诚实取舍",
                reason="profile is ready or customer explicitly requested a recommendation",
            )

        if intent == "accept_recommendation":
            if profile.contact_opt_in:
                return SalesDecision(
                    stage="follow_up",
                    next_best_action="prepare_follow_up",
                    objective="尊重客户已经保存的授权，确认方案发送和后续联系安排，不重复索取联系方式",
                    reason="customer accepted recommendation and contact consent already exists",
                )
            if profile.contact_prompt_eligible:
                return SalesDecision(
                    stage="lead_capture",
                    next_best_action="offer_contact_form",
                    objective="在客户已获得价值后，邀请其自愿使用独立表单接收方案和授权后续联系",
                    reason="customer accepted the recommendation and is eligible for contact offer",
                )
            return SalesDecision(
                stage="soft_close",
                next_best_action="soft_close",
                objective="确认客户对主推方向的认可，并推动面积、时间或门店确认等低压力下一步",
                reason="customer accepted the recommendation",
            )

        if profile.recommended_product_ids:
            if profile.estimated_area_sqm is None:
                return SalesDecision(
                    stage="qualification",
                    next_best_action="ask_project_area",
                    objective="确认大概面积，以便判断促销条件、报价范围和铺装工作量",
                    reason="recommendation exists but project area is unknown",
                )
            if not profile.purchase_timeline:
                return SalesDecision(
                    stage="qualification",
                    next_best_action="ask_purchase_timeline",
                    objective="确认计划铺装时间，以便判断跟进优先级和门店安排",
                    reason="recommendation exists but purchase timeline is unknown",
                )
            if profile.promotion_interest is True and not profile.promotion_ids_presented:
                return SalesDecision(
                    stage="promotion",
                    next_best_action="mention_approved_promotion",
                    objective="根据已确认的产品和面积，只介绍适用的批准演示活动",
                    reason="customer is interested in promotions and eligibility data is available",
                )
            if profile.contact_opt_in:
                return SalesDecision(
                    stage="follow_up",
                    next_best_action="prepare_follow_up",
                    objective="尊重客户已经保存的授权，确认方案发送和后续联系安排，不重复索取联系方式",
                    reason="qualification complete and contact consent already exists",
                )
            if profile.contact_prompt_eligible:
                return SalesDecision(
                    stage="lead_capture",
                    next_best_action="offer_contact_form",
                    objective="邀请客户自愿留下联系方式，以便发送本次方案；长期营销授权必须单独选择",
                    reason="customer has a qualified recommendation and sufficient buying signals",
                )
            return SalesDecision(
                stage="soft_close",
                next_best_action="soft_close",
                objective="确认主推方向是否成立，并推动一个清晰、低压力的下一步",
                reason="recommendation and qualification are complete",
            )

        if not profile.priorities:
            return SalesDecision(
                stage="discovery",
                next_best_action="ask_primary_priority",
                objective="找出客户最不愿意妥协的首要需求，避免只做机械式信息登记",
                reason="primary purchase driver is still unknown",
            )

        if not profile.room_type:
            return SalesDecision(
                stage="discovery",
                next_best_action="ask_usage_context",
                objective="确认实际铺装空间，以便把核心需求放到正确使用场景中判断",
                reason="usage space is still unknown",
            )

        return SalesDecision(
            stage="qualification",
            next_best_action="qualify_needs",
            objective="继续确认预算、风格或生活方式条件，并自然复述已理解的核心需求",
            reason=f"continue qualification at turn {context.turn_index}",
        )
