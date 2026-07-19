from __future__ import annotations

from ..llm.schemas import DialogueDecision, ValidationResult
from ..models import CustomerProfile
from .dialogue_context_service import DialogueContext


class DialoguePolicy:
    """Backend policy for value-first discovery and proactive recommendation.

    The customer should not be forced through a form-like sequence. After one
    meaningful purchase driver is known, the assistant can already show useful
    product directions. Additional details refine the recommendation only when
    the customer volunteers them or explicitly wants to continue.
    """

    def decide(
        self,
        *,
        validation: ValidationResult,
        profile: CustomerProfile,
        context: DialogueContext,
    ) -> DialogueDecision:
        turn = validation.semantic_turn

        if validation.critical_conflict:
            return DialogueDecision(
                action="clarify",
                reason="critical semantic conflict",
                pending_slot=context.pending_slot,
                question=validation.clarification_question
                or "我听到的信息有冲突。请只确认一个要修改的条件。",
            )

        explicit_recommendation = turn.intent in {
            "request_recommendation",
            "request_comparison",
        } or turn.recommendation_requested

        if turn.intent == "request_comparison":
            return DialogueDecision(
                action="compare_now",
                reason="customer explicitly requested a comparison",
            )

        if explicit_recommendation:
            return DialogueDecision(
                action="recommend_now",
                reason="customer explicitly requested a recommendation",
            )

        if validation.needs_clarification and not validation.can_apply:
            return DialogueDecision(
                action="clarify",
                reason="no safe action could be applied",
                pending_slot=context.pending_slot,
                question=validation.clarification_question
                or self._question_for_slot(context.pending_slot)
                or "我没有完全听清。请只说一个最重要的条件。",
            )

        # Direct questions, objections, promotion requests and explicit acceptance
        # are handled before any proactive product story is introduced.
        if turn.intent in {
            "ask_reason",
            "general_product_question",
            "ask_promotion",
            "express_objection",
            "accept_recommendation",
        }:
            return DialogueDecision(
                action="acknowledge",
                reason=f"answer sales intent first: {turn.intent}",
            )

        # Once the customer gives one meaningful priority, provide value immediately
        # instead of asking for room, budget, style, area and timeline in sequence.
        if not profile.recommended_product_ids and self._profile_is_ready(profile):
            return DialogueDecision(
                action="recommend_now",
                reason="one clear purchase driver is enough for a useful first product story",
            )

        # Refresh recommendations only after a confirmed requirement change. The old
        # implementation also treated every `other` turn as a reason to recommend
        # again; that made requests such as “introduce yourself again” inherit the
        # previous flooring story and produce an obviously irrelevant answer.
        if (
            profile.recommended_product_ids
            and validation.can_apply
            and turn.intent == "provide_or_modify_needs"
        ):
            return DialogueDecision(
                action="recommend_now",
                reason="refresh product value after an explicitly validated requirement change",
            )

        if validation.needs_clarification:
            return DialogueDecision(
                action="clarify",
                reason="safe actions applied but one point remains unclear",
                pending_slot=context.pending_slot,
                question=validation.clarification_question
                or self._question_for_slot(context.pending_slot)
                or "我已经记录了听清的部分。请再确认一下刚才没有听清的条件。",
            )

        # Unknown/non-business turns must not mutate state or trigger another product
        # recommendation. The front-door TurnRouter handles common social intents; if
        # an unknown turn still reaches this policy, acknowledge it conservatively.
        if turn.intent == "other":
            return DialogueDecision(
                action="acknowledge",
                reason="unknown turn is non-mutating and must not force a recommendation",
            )

        # Only the primary purchase driver is mandatory. All other fields are
        # optional refinement signals and must not become a forced interview.
        missing_slot = self._next_missing_slot(profile)
        if missing_slot is not None:
            return DialogueDecision(
                action="ask_missing_slot",
                reason=f"collect the single minimum discovery signal: {missing_slot}",
                pending_slot=missing_slot,
                question=self._question_for_slot(missing_slot),
            )

        return DialogueDecision(
            action="acknowledge",
            reason="customer has enough context; do not ask another automatic question",
        )

    @staticmethod
    def _profile_is_ready(profile: CustomerProfile) -> bool:
        if profile.recommended_product_ids:
            return False
        return bool(profile.priorities or profile.primary_purchase_driver)

    @staticmethod
    def _next_missing_slot(profile: CustomerProfile):
        if not profile.priorities and not profile.primary_purchase_driver:
            return "priority"
        return None

    @staticmethod
    def _question_for_slot(slot):
        questions = {
            "priority": (
                "您不用一次回答很多问题。先告诉我最在意的一点就够了："
                "预算、耐磨、防水、脚感、环保，还是日常好清洁？"
            ),
            "room_type": (
                "客厅、卧室和全屋的选法差别很大。您方便时告诉我使用空间，"
                "我就能把不合适的款式直接排除。"
            ),
            "budget": "预算可以稍后再定；有明确范围时，我再帮您比较哪些性能值得保留。",
            "style": "风格不用现在决定；看到产品方向后，再结合采光和家具收窄通常更容易。",
            "project_type": "新房、旧房翻新和局部改造的重点不同，您愿意继续时再补充即可。",
            "estimated_area_sqm": "面积只在核对活动或正式报价时需要，现在不用急着提供。",
            "purchase_timeline": "铺装时间只在安排报价和门店跟进时需要，现在不用急着提供。",
            "preferred_color": "颜色可以等您先看到材质方向后再决定，不需要现在马上选择。",
        }
        return questions.get(slot)
