from __future__ import annotations

import logging
import re
import time

from ..llm.providers import DialogueProviderError, ProviderRegistry
from ..llm.schemas import AnswerPlan, DialogueDecision
from ..models import ChatRequest, ChatResponse, CustomerProfile, DialogueProvider
from .answer_plan_service import AnswerPlanService
from .chat_service import ChatService
from .customer_state_service import CustomerStateService
from .dialogue_context_service import DialogueContext, DialogueContextService
from .dialogue_policy import DialoguePolicy
from .lead_service import LeadService
from .recommendation_service import RecommendationService
from .sales_conversation_policy import SalesConversationPolicy
from .session_runtime_service import SessionRuntimeService
from .state_machine import StoreSessionStateMachine
from .validation_guard import ValidationGuard

logger = logging.getLogger(__name__)

EMPTY_COMMITMENT_PATTERNS = (
    "我会为您推荐",
    "我会推荐",
    "接下来为您推荐",
    "接下来给您方案",
    "稍后为您推荐",
    "随后为您推荐",
    "我将为您推荐",
)


class DialogueOrchestrator:
    def __init__(
        self,
        *,
        provider_registry: ProviderRegistry,
        runtime_service: SessionRuntimeService,
        lead_service: LeadService,
        recommendation_service: RecommendationService,
        validation_guard: ValidationGuard,
        customer_state_service: CustomerStateService,
        answer_plan_service: AnswerPlanService,
        chat_service: ChatService,
        state_machine: StoreSessionStateMachine,
    ) -> None:
        self.provider_registry = provider_registry
        self.runtime_service = runtime_service
        self.lead_service = lead_service
        self.recommendation_service = recommendation_service
        self.validation_guard = validation_guard
        self.customer_state_service = customer_state_service
        self.answer_plan_service = answer_plan_service
        self.chat_service = chat_service
        self.state_machine = state_machine
        self.context_service = DialogueContextService()
        self.dialogue_policy = DialoguePolicy()
        self.sales_policy = SalesConversationPolicy()

    def handle_turn(self, request: ChatRequest) -> ChatResponse:
        provider_mode = self._resolve_provider(request.session_id, request.provider_mode)
        provider = self.provider_registry.get(provider_mode)
        provider_label = self.runtime_service.provider_label(provider_mode)
        lang = self.chat_service.normalize_response_language(request.text, request.response_language)

        if self.chat_service.is_session_end(request.text):
            self.state_machine.handle_event("end")
            profile = self.lead_service.load_profile(session_id=request.session_id)
            context = self.context_service.reset(request.session_id)
            answer = (
                "Thanks for visiting. The sales team can continue follow-up based on this requirement record."
                if lang == "en"
                else "好的，感谢您的咨询。我已经整理好本次核心需求和推荐方向，门店顾问后续可以据此继续确认面积、报价与安装安排。"
            )
            follow_up = (
                "Sales should follow up within 24 hours to confirm area, budget, and installation schedule."
                if lang == "en"
                else "建议销售在 24 小时内发送主推款与备选款对比，并确认房间面积、最终预算和安装时间。"
            )
            return ChatResponse(
                answer=answer,
                recommended_products=[],
                customer_profile=profile,
                follow_up_suggestion=follow_up,
                state=self.state_machine.state,
                provider_mode=provider_mode,
                provider_label=provider_label,
                pending_slot=context.pending_slot,
                last_assistant_question=context.last_assistant_question,
                sales_stage=profile.sales_stage,
                sales_objective=profile.sales_objective,
            )

        if self.state_machine.state.value not in {"CONVERSATION_ACTIVE", "INTRODUCING_PRODUCTS"}:
            self.state_machine.handle_event("greeting")
            self.state_machine.handle_event("intro_finished")

        profile = self.lead_service.load_profile(session_id=request.session_id)
        context = self.context_service.load(request.session_id)
        if self._is_fresh_profile(profile) and context.turn_index > 0:
            context = self.context_service.reset(request.session_id)
        if self._is_fresh_profile(profile) and context.turn_index == 0:
            context = context.model_copy(
                update={
                    "pending_slot": "priority",
                    "last_assistant_question": (
                        "这次选地板，您最不愿意妥协的是哪一点："
                        "预算、耐磨、防水、脚感、环保，还是日常好清洁？"
                    ),
                }
            )

        normalized_text = self.validation_guard.normalize_text(request.text)
        asr_confirmation = self._asr_confirmation(
            request=request,
            context=context,
            normalized_text=normalized_text,
        )
        if asr_confirmation is not None:
            question, suggested = asr_confirmation
            context = self.context_service.advance(
                context=context,
                user_text=request.text,
                pending_slot=context.pending_slot,
                assistant_question=question,
                response_type="clarification",
            )
            return ChatResponse(
                answer=question,
                recommended_products=self._saved_recommendations(profile),
                customer_profile=profile,
                follow_up_suggestion=profile.follow_up_suggestion,
                state=self.state_machine.state,
                provider_mode=provider_mode,
                provider_label=provider_label,
                needs_clarification=True,
                pending_slot=context.pending_slot,
                last_assistant_question=question,
                asr_confirmation_required=True,
                asr_suggested_text=suggested,
                sales_stage="discovery",
                sales_objective="澄清语音识别结果并保护已经确认的需求",
            )

        parse_started = time.perf_counter()
        try:
            semantic_turn = provider.parse_turn(
                user_text=normalized_text,
                current_profile=profile,
                dialogue_context=context.model_dump(),
            )
            parse_ms = (time.perf_counter() - parse_started) * 1000
        except DialogueProviderError as exc:
            parse_ms = (time.perf_counter() - parse_started) * 1000
            logger.warning(
                "dialogue_parse_failed provider=%s session=%s latency_ms=%.1f error=%s",
                provider_mode,
                request.session_id,
                parse_ms,
                exc,
            )
            return self._provider_unavailable_response(
                provider_mode=provider_mode,
                provider_label=provider_label,
                profile=profile,
                context=context,
            )

        validation_started = time.perf_counter()
        validation = self.validation_guard.validate(
            user_text=normalized_text,
            semantic_turn=semantic_turn,
            pending_slot=context.pending_slot,
        )
        validation_ms = (time.perf_counter() - validation_started) * 1000

        updated_profile = self.customer_state_service.apply(profile=profile, validation=validation)
        decision = self.dialogue_policy.decide(
            validation=validation,
            profile=updated_profile,
            context=context,
        )
        sales_decision = self.sales_policy.decide(
            validation=validation,
            profile=updated_profile,
            context=context,
            dialogue_decision=decision,
        )

        recommendation_started = time.perf_counter()
        recommended = self.recommendation_service.recommend(updated_profile)
        recommendation_ms = (time.perf_counter() - recommendation_started) * 1000

        answer_plan = self.answer_plan_service.build(
            user_text=request.text,
            validation=validation,
            profile=updated_profile,
            recommended_products=recommended,
            decision=decision,
            sales_decision=sales_decision,
        )

        if answer_plan.must_recommend_now and not answer_plan.products:
            answer_plan = AnswerPlan(
                response_type="clarification",
                sales_stage="qualification",
                sales_objective="确认可以放宽的条件，避免虚构不匹配产品",
                next_best_action="clarify_customer_input",
                company_highlights=answer_plan.company_highlights,
                featured_collections=answer_plan.featured_collections,
                customer_need_summary=answer_plan.customer_need_summary,
                products=[],
                constraints=answer_plan.constraints,
                direct_message=(
                    "我已经记录了您的核心需求，但当前产品库没有可安全推荐的匹配项。"
                    "为了不勉强推荐不合适的产品，请确认可以优先放宽颜色、预算还是材质限制。"
                ),
                next_question="您愿意优先放宽颜色、预算还是材质限制？",
            )
            decision = DialogueDecision(
                action="clarify",
                reason="deterministic recommender returned no candidates",
                question=answer_plan.next_question,
            )

        render_started = time.perf_counter()
        degraded = False
        try:
            answer = provider.render_answer(answer_plan=answer_plan)
            render_ms = (time.perf_counter() - render_started) * 1000
        except DialogueProviderError as exc:
            render_ms = (time.perf_counter() - render_started) * 1000
            degraded = True
            logger.warning(
                "dialogue_render_failed provider=%s session=%s latency_ms=%.1f error=%s",
                provider_mode,
                request.session_id,
                render_ms,
                exc,
            )
            answer = self.answer_plan_service.fallback_text(answer_plan)

        answer = self._enforce_answer_contract(answer=answer, answer_plan=answer_plan)

        if answer_plan.products:
            updated_profile.recommended_product_ids = [product.product_id for product in answer_plan.products]
        updated_profile.primary_purchase_driver = updated_profile.primary_purchase_driver or self._primary_driver(updated_profile)
        updated_profile.sales_stage = answer_plan.sales_stage
        updated_profile.sales_objective = answer_plan.sales_objective
        updated_profile.featured_collection_ids = [
            collection.collection_id for collection in answer_plan.featured_collections
        ]
        updated_profile.conversation_summary = self.customer_state_service.build_summary(updated_profile)
        updated_profile.follow_up_suggestion = self.customer_state_service.build_follow_up(updated_profile)
        saved_profile = self.lead_service.save_profile(updated_profile)

        pending_slot = decision.pending_slot
        assistant_question = decision.question
        if answer_plan.next_question:
            assistant_question = answer_plan.next_question
            pending_slot = self._slot_from_question(answer_plan.next_question)

        context = self.context_service.advance(
            context=context,
            user_text=request.text,
            pending_slot=pending_slot,
            assistant_question=assistant_question,
            response_type=answer_plan.response_type,
        )

        logger.info(
            "dialogue_turn provider=%s session=%s parse_ms=%.1f validation_ms=%.1f "
            "recommendation_ms=%.1f render_ms=%.1f guard_ok=%s can_apply=%s "
            "decision=%s sales_stage=%s next_best_action=%s degraded=%s intent=%s pending_slot=%s",
            provider_mode,
            request.session_id,
            parse_ms,
            validation_ms,
            recommendation_ms,
            render_ms,
            validation.ok,
            validation.can_apply,
            decision.action,
            answer_plan.sales_stage,
            answer_plan.next_best_action,
            degraded,
            validation.semantic_turn.intent,
            context.pending_slot,
        )

        visible_products = [
            product
            for fact in answer_plan.products
            if (product := self.recommendation_service.product_service.get_product(fact.product_id)) is not None
        ] or self._saved_recommendations(saved_profile)

        return ChatResponse(
            answer=answer,
            recommended_products=visible_products,
            customer_profile=saved_profile,
            follow_up_suggestion=saved_profile.follow_up_suggestion,
            state=self.state_machine.state,
            provider_mode=provider_mode,
            provider_label=provider_label,
            llm_degraded=degraded,
            needs_clarification=decision.action == "clarify",
            pending_slot=context.pending_slot,
            last_assistant_question=context.last_assistant_question,
            sales_stage=answer_plan.sales_stage,
            sales_objective=answer_plan.sales_objective,
            featured_collections=[collection.model_dump() for collection in answer_plan.featured_collections],
        )

    def _resolve_provider(self, session_id: str, requested: DialogueProvider | None) -> DialogueProvider:
        if requested is not None:
            return self.runtime_service.set_provider(session_id, requested).provider_mode
        return self.runtime_service.load(session_id).provider_mode

    def _provider_unavailable_response(
        self,
        *,
        provider_mode: DialogueProvider,
        provider_label: str,
        profile: CustomerProfile,
        context: DialogueContext,
    ) -> ChatResponse:
        plan = self.answer_plan_service.unavailable(provider_mode=provider_mode)
        return ChatResponse(
            answer=plan.direct_message or "当前模型服务暂时不可用。",
            recommended_products=self._saved_recommendations(profile),
            customer_profile=profile,
            follow_up_suggestion=profile.follow_up_suggestion,
            state=self.state_machine.state,
            provider_mode=provider_mode,
            provider_label=provider_label,
            llm_degraded=True,
            needs_clarification=False,
            pending_slot=context.pending_slot,
            last_assistant_question=context.last_assistant_question,
            sales_stage=plan.sales_stage,
            sales_objective=plan.sales_objective,
        )

    def _asr_confirmation(
        self,
        *,
        request: ChatRequest,
        context: DialogueContext,
        normalized_text: str,
    ) -> tuple[str, str | None] | None:
        if request.asr_confirmed:
            return None

        alternatives = [
            (self.validation_guard.normalize_text(item.transcript), item.confidence)
            for item in request.asr_alternatives
            if item.transcript.strip()
        ]
        best_domain_candidate = self._best_domain_candidate(
            [normalized_text, *[text for text, _ in alternatives]],
            context.pending_slot,
        )
        top_confidence = alternatives[0][1] if alternatives else None
        low_confidence = top_confidence is not None and top_confidence < 0.72
        ambiguous_short = self._ambiguous_short_answer(normalized_text, context.pending_slot)

        if not alternatives and not ambiguous_short:
            return None
        if not (low_confidence or ambiguous_short):
            return None

        suggested = best_domain_candidate if best_domain_candidate and best_domain_candidate != normalized_text else None
        if suggested:
            question = f"我听到的内容可能是“{suggested}”。请确认后再发送，或者直接编辑文字。"
        else:
            slot_hint = {
                "room_type": "客厅、卧室或全屋",
                "budget": "经济、中等、偏高或高端",
                "style": "现代简约、北欧原木或新中式",
                "preferred_color": "浅灰色、原木色或深色系",
                "priority": "防水、耐磨、环保、价格、脚感或好清洁",
            }.get(context.pending_slot, "您的主要需求")
            question = f"我没有把这段语音听清。请确认识别文字，或直接回答“{slot_hint}”。"
        return question, suggested

    @staticmethod
    def _ambiguous_short_answer(text: str, pending_slot: str | None) -> bool:
        if pending_slot is None:
            return False
        ambiguous = {
            "preferred_color": {"钱", "浅", "灰", "原", "深"},
            "budget": {"中", "高", "低", "钱"},
            "style": {"现代", "原木"},
            "priority": {"水", "磨", "钱", "脚", "清洁"},
        }
        return text in ambiguous.get(pending_slot, set())

    @staticmethod
    def _best_domain_candidate(candidates: list[str], pending_slot: str | None) -> str | None:
        vocab = {
            "room_type": ("客厅", "卧室", "全屋", "厨房", "书房"),
            "budget": ("经济", "中等", "中档", "偏高", "高端"),
            "style": ("现代简约", "北欧", "原木风", "新中式", "轻奢"),
            "preferred_color": ("浅灰色", "浅灰", "灰色", "原木色", "深灰色", "深色系"),
            "priority": ("防水", "耐磨", "环保", "价格", "脚感", "好清洁"),
        }.get(pending_slot, ())
        for candidate in candidates:
            for term in vocab:
                if term in candidate:
                    return candidate
        return None

    def _enforce_answer_contract(self, *, answer: str, answer_plan: AnswerPlan) -> str:
        cleaned = re.sub(r"\s+", " ", answer or "").strip()
        if not cleaned:
            return self.answer_plan_service.fallback_text(answer_plan)
        if answer_plan.must_recommend_now and answer_plan.products:
            if not any(product.name in cleaned for product in answer_plan.products):
                return self.answer_plan_service.fallback_text(answer_plan)
        if not answer_plan.products and any(phrase in cleaned for phrase in EMPTY_COMMITMENT_PATTERNS):
            return self.answer_plan_service.fallback_text(answer_plan)
        return cleaned

    @staticmethod
    def _slot_from_question(question: str | None):
        if not question:
            return None
        if "最不愿意妥协" in question or "最重视" in question or "核心需求" in question:
            return "priority"
        if "房间" in question or "客厅" in question or "铺在" in question:
            return "room_type"
        if "预算" in question or "经济" in question:
            return "budget"
        if "风格" in question or "现代简约" in question:
            return "style"
        if "颜色" in question or "浅灰" in question:
            return "preferred_color"
        return None

    @staticmethod
    def _primary_driver(profile: CustomerProfile) -> str | None:
        if not profile.priorities:
            return None
        rank = {"high": 3, "medium": 2, "low": 1}
        return max(profile.priorities.items(), key=lambda item: rank.get(item[1], 0))[0]

    @staticmethod
    def _is_fresh_profile(profile: CustomerProfile) -> bool:
        return not any(
            [
                profile.room_type,
                profile.style,
                profile.budget,
                profile.has_pets is not None,
                profile.has_floor_heating is not None,
                profile.has_children is not None,
                profile.has_elderly is not None,
                profile.humid_environment is not None,
                profile.priorities,
                profile.preferred_colors,
                profile.rejected_colors,
                profile.preferred_product_ids,
                profile.rejected_product_ids,
                profile.recommended_product_ids,
            ]
        )

    def _saved_recommendations(self, profile: CustomerProfile):
        products = []
        for product_id in profile.recommended_product_ids:
            product = self.recommendation_service.product_service.get_product(product_id)
            if product is not None:
                products.append(product)
        return products
