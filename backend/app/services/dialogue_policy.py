from __future__ import annotations

from ..llm.schemas import DialogueDecision, ValidationResult
from ..models import CustomerProfile
from .dialogue_context_service import DialogueContext


class DialoguePolicy:
    """Backend policy for clarification, slot collection and immediate recommendation."""

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

        if self._profile_is_ready(profile):
            if context.pending_slot is not None or validation.can_apply:
                return DialogueDecision(
                    action="recommend_now",
                    reason="profile is sufficient for a useful recommendation",
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

        missing_slot = self._next_missing_slot(profile)
        if missing_slot is not None:
            return DialogueDecision(
                action="ask_missing_slot",
                reason=f"collect one missing slot: {missing_slot}",
                pending_slot=missing_slot,
                question=self._question_for_slot(missing_slot),
            )

        return DialogueDecision(
            action="acknowledge",
            reason="state update acknowledged; no further slot is required",
        )

    @staticmethod
    def _profile_is_ready(profile: CustomerProfile) -> bool:
        if not profile.room_type:
            return False
        signals = 0
        signals += int(bool(profile.budget))
        signals += int(bool(profile.style))
        signals += int(bool(profile.preferred_colors))
        signals += int(bool(profile.priorities))
        signals += int(
            any(
                value is not None
                for value in (
                    profile.has_pets,
                    profile.has_floor_heating,
                    profile.has_children,
                    profile.has_elderly,
                    profile.humid_environment,
                )
            )
        )
        return signals >= 2

    @staticmethod
    def _next_missing_slot(profile: CustomerProfile):
        if not profile.room_type:
            return "room_type"
        if not profile.budget:
            return "budget"
        if not profile.style:
            return "style"
        if not profile.preferred_colors and not profile.rejected_colors:
            return "preferred_color"
        return None

    @staticmethod
    def _question_for_slot(slot):
        questions = {
            "room_type": "您这次主要铺在客厅、卧室还是全屋？",
            "budget": "您的预算更接近经济、中等、偏高还是高端？",
            "style": "您更喜欢现代简约、北欧原木、新中式还是其他风格？",
            "preferred_color": "您更喜欢浅灰色、原木色还是深色系？",
            "priority": "您最重视防水、耐磨、环保、价格、脚感还是好清洁？",
        }
        return questions.get(slot)
