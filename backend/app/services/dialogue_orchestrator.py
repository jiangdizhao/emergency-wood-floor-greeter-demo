from __future__ import annotations

import logging
import time

from ..llm.providers import DialogueProviderError, ProviderRegistry
from ..llm.schemas import ValidationResult
from ..models import ChatRequest, ChatResponse, DialogueProvider
from .answer_plan_service import AnswerPlanService
from .chat_service import ChatService
from .customer_state_service import CustomerStateService
from .lead_service import LeadService
from .recommendation_service import RecommendationService
from .session_runtime_service import SessionRuntimeService
from .state_machine import StoreSessionStateMachine
from .validation_guard import ValidationGuard

logger = logging.getLogger(__name__)


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

    def handle_turn(self, request: ChatRequest) -> ChatResponse:
        provider_mode = self._resolve_provider(request.session_id, request.provider_mode)
        provider = self.provider_registry.get(provider_mode)
        provider_label = self.runtime_service.provider_label(provider_mode)
        lang = self.chat_service.normalize_response_language(request.text, request.response_language)

        if self.chat_service.is_session_end(request.text):
            self.state_machine.handle_event("end")
            profile = self.lead_service.load_profile(session_id=request.session_id)
            answer = (
                "Thanks for visiting. The sales team can continue follow-up based on this requirement record."
                if lang == "en"
                else "好的，感谢您的咨询。稍后销售可以根据本次需求记录继续跟进。"
            )
            follow_up = (
                "Sales should follow up within 24 hours to confirm area, budget, and installation schedule."
                if lang == "en"
                else "建议销售在 24 小时内回访，确认房间面积、预算和安装时间。"
            )
            return ChatResponse(
                answer=answer,
                recommended_products=[],
                customer_profile=profile,
                follow_up_suggestion=follow_up,
                state=self.state_machine.state,
                provider_mode=provider_mode,
                provider_label=provider_label,
            )

        if self.state_machine.state.value not in {"CONVERSATION_ACTIVE", "INTRODUCING_PRODUCTS"}:
            self.state_machine.handle_event("greeting")
            self.state_machine.handle_event("intro_finished")

        profile = self.lead_service.load_profile(session_id=request.session_id)
        normalized_text = self.validation_guard.normalize_text(request.text)
        parse_started = time.perf_counter()
        try:
            semantic_turn = provider.parse_turn(
                user_text=normalized_text,
                current_profile=profile,
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
            )

        validation_started = time.perf_counter()
        validation = self.validation_guard.validate(
            user_text=normalized_text,
            semantic_turn=semantic_turn,
        )
        validation_ms = (time.perf_counter() - validation_started) * 1000

        if validation.ok:
            updated_profile = self.customer_state_service.apply(
                profile=profile,
                validation=validation,
            )
        else:
            updated_profile = profile.model_copy(deep=True)

        recommendation_started = time.perf_counter()
        recommended = self.recommendation_service.recommend(updated_profile)
        recommendation_ms = (time.perf_counter() - recommendation_started) * 1000

        answer_plan = self.answer_plan_service.build(
            user_text=request.text,
            validation=validation,
            profile=updated_profile,
            recommended_products=recommended,
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
            answer = self._template_answer(
                request=request,
                validation=validation,
                profile=updated_profile,
                recommended=recommended,
                language=lang,
            )

        if validation.ok:
            updated_profile.recommended_product_ids = [product.id for product in recommended]
            updated_profile.conversation_summary = self.customer_state_service.build_summary(updated_profile)
            updated_profile.follow_up_suggestion = self.customer_state_service.build_follow_up(updated_profile)
            saved_profile = self.lead_service.save_profile(updated_profile)
        else:
            saved_profile = profile

        logger.info(
            "dialogue_turn provider=%s session=%s parse_ms=%.1f validation_ms=%.1f "
            "recommendation_ms=%.1f render_ms=%.1f guard_ok=%s degraded=%s intent=%s",
            provider_mode,
            request.session_id,
            parse_ms,
            validation_ms,
            recommendation_ms,
            render_ms,
            validation.ok,
            degraded,
            semantic_turn.intent,
        )

        return ChatResponse(
            answer=answer,
            recommended_products=recommended if validation.ok else self._saved_recommendations(profile),
            customer_profile=saved_profile,
            follow_up_suggestion=saved_profile.follow_up_suggestion,
            state=self.state_machine.state,
            provider_mode=provider_mode,
            provider_label=provider_label,
            llm_degraded=degraded,
            needs_clarification=not validation.ok,
        )

    def _resolve_provider(
        self,
        session_id: str,
        requested: DialogueProvider | None,
    ) -> DialogueProvider:
        if requested is not None:
            return self.runtime_service.set_provider(session_id, requested).provider_mode
        return self.runtime_service.load(session_id).provider_mode

    def _provider_unavailable_response(
        self,
        *,
        provider_mode: DialogueProvider,
        provider_label: str,
        profile,
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
        )

    def _template_answer(
        self,
        *,
        request: ChatRequest,
        validation: ValidationResult,
        profile,
        recommended,
        language: str,
    ) -> str:
        if not validation.ok:
            return validation.clarification_question or "我没有完全理解，请再说一次您的主要需求。"
        return self.chat_service.answer_user_message(
            user_text=request.text,
            customer_profile=profile,
            recommended_products=recommended,
            response_language=language,
        )

    def _saved_recommendations(self, profile):
        products = []
        for product_id in profile.recommended_product_ids:
            product = self.recommendation_service.product_service.get_product(product_id)
            if product is not None:
                products.append(product)
        return products
