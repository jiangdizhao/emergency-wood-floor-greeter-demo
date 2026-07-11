from __future__ import annotations

from ..llm.schemas import DialogueDecision, SalesDecision, ValidationResult
from ..models import CustomerProfile
from .dialogue_context_service import DialogueContext


class SalesConversationPolicy:
    """Selects the next senior-sales objective without giving the LLM business control."""

    def decide(
        self,
        *,
        validation: ValidationResult,
        profile: CustomerProfile,
        context: DialogueContext,
        dialogue_decision: DialogueDecision,
    ) -> SalesDecision:
        if dialogue_decision.action == "clarify":
            return SalesDecision(
                stage="discovery",
                next_best_action="clarify_customer_input",
                objective="只澄清一个没有听清或存在冲突的条件，同时保留已经确认的信息",
                reason="shared validation guard requires clarification",
            )

        if dialogue_decision.action in {"recommend_now", "compare_now"}:
            return SalesDecision(
                stage="recommendation",
                next_best_action="present_main_and_backup",
                objective=(
                    "围绕客户最重要的购买驱动，给出主推款与备选款，说明实际价值和至少一个诚实取舍"
                ),
                reason="profile is ready or customer explicitly requested a recommendation",
            )

        if validation.semantic_turn.intent == "ask_reason":
            return SalesDecision(
                stage="objection_handling",
                next_best_action="explain_tradeoff",
                objective="解释推荐依据和材料取舍，帮助客户排除不合适的选择",
                reason="customer asked for rationale",
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
