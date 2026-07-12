from __future__ import annotations

from ..llm.schemas import DialogueDecision, ValidationResult
from ..models import CustomerProfile
from .dialogue_context_service import DialogueContext


class DialoguePolicy:
    """Backend policy for clarification, discovery, qualification and recommendation."""

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

        # Direct product, promotion, objection and acceptance turns are handled by
        # the senior-sales policy before another automatic recommendation starts.
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

        # Once a recommendation exists, a genuine change to room, budget, style,
        # living conditions, priority, colour or product preference must recompute
        # the deterministic recommendation. Area, timeline and decision-stage
        # updates only qualify the project and should not change the SKU ranking.
        if profile.recommended_product_ids and self._changes_recommendation(validation):
            return DialogueDecision(
                action="recommend_now",
                reason="customer changed a recommendation-driving requirement",
            )

        if self._profile_is_ready(profile):
            if context.pending_slot is not None or validation.can_apply:
                return DialogueDecision(
                    action="recommend_now",
                    reason="profile is sufficient for a useful first recommendation",
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
    def _changes_recommendation(validation: ValidationResult) -> bool:
        driving_fields = {
            "room_type",
            "style",
            "budget",
            "has_pets",
            "has_floor_heating",
            "has_children",
            "has_elderly",
            "humid_environment",
        }
        for action in validation.actions:
            if action.scope != "persistent":
                continue
            if action.kind == "set_field" and action.name in driving_fields:
                return True
            if action.kind in {
                "set_priority",
                "prefer_color",
                "reject_color",
                "prefer_product",
                "reject_product",
            }:
                return True
        return False

    @staticmethod
    def _profile_is_ready(profile: CustomerProfile) -> bool:
        # Do not repeatedly auto-recommend after the first product set is stored.
        if profile.recommended_product_ids:
            return False
        if not profile.room_type or not profile.priorities:
            return False
        signals = 0
        signals += int(bool(profile.budget))
        signals += int(bool(profile.style))
        signals += int(bool(profile.preferred_colors))
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
        return signals >= 1

    @staticmethod
    def _next_missing_slot(profile: CustomerProfile):
        if not profile.priorities:
            return "priority"
        if not profile.room_type:
            return "room_type"
        if not profile.budget:
            return "budget"
        if not profile.style:
            return "style"
        if profile.recommended_product_ids and profile.estimated_area_sqm is None:
            return "estimated_area_sqm"
        if profile.recommended_product_ids and not profile.purchase_timeline:
            return "purchase_timeline"
        if not profile.preferred_colors and not profile.rejected_colors:
            return "preferred_color"
        return None

    @staticmethod
    def _question_for_slot(slot):
        questions = {
            "priority": "这次选地板，您最不愿意妥协的是哪一点：预算、耐磨、防水、脚感、环保，还是日常好清洁？",
            "room_type": "明白了您的核心关注点。请问这次主要铺在客厅、卧室还是全屋？",
            "budget": "为了不让推荐偏离实际，您的预算更接近经济、中等、偏高还是高端？",
            "style": "在满足核心使用需求的前提下，您更喜欢现代简约、北欧原木、新中式还是其他风格？",
            "project_type": "这次属于新房装修、旧房翻新、局部改造，还是出租房项目？",
            "estimated_area_sqm": "为了判断组合方案、活动条件和后续报价，请问预计铺装面积大约多少平方米？",
            "purchase_timeline": "您计划什么时候铺装：1个月内、1到3个月、3个月以上，还是时间待定？",
            "preferred_color": "为了让方案更接近最终效果，您更喜欢浅灰色、原木色还是深色系？",
        }
        return questions.get(slot)
