from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from .models import ChatRequest, DialogueProvider, SessionState
from .services.turn_router import TurnRoute, TurnRouter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["realtime-agent-routing"])
turn_router = TurnRouter()


class InteractionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str
    response_language: str = "zh"
    session_id: str = "demo-session-001"
    provider_mode: DialogueProvider | None = None
    asr_confirmed: bool = False


def _language(value: str) -> str:
    normalized = (value or "zh").strip().lower()
    return "en" if normalized.startswith("en") else "zh"


def _visible_products(profile: Any, product_service: Any) -> list[Any]:
    products: list[Any] = []
    for product_id in profile.recommended_product_ids:
        product = product_service.get_product(product_id)
        if product is not None:
            products.append(product)
    return products


def _route_metadata(route: TurnRoute) -> dict[str, Any]:
    return {
        "response_route": route.route,
        "route_intent": route.intent,
        "route_reason": route.reason,
        "realtime_instruction": route.realtime_instruction,
    }


def _direct_payload(request: InteractionRequest, route: TurnRoute) -> dict[str, Any]:
    # Imported lazily to avoid a module cycle while main.py is constructing the app.
    from .main import lead_service, product_service, runtime_service, state_machine

    profile = lead_service.load_profile(session_id=request.session_id)
    runtime = runtime_service.load(request.session_id)
    return {
        "answer": route.answer or "",
        "recommended_products": [item.model_dump() for item in _visible_products(profile, product_service)],
        "customer_profile": profile.model_dump(),
        "follow_up_suggestion": profile.follow_up_suggestion,
        "state": state_machine.state.value,
        "provider_mode": runtime.provider_mode,
        "provider_label": runtime_service.provider_label(runtime.provider_mode),
        "llm_degraded": False,
        "needs_clarification": False,
        "pending_slot": None,
        "last_assistant_question": None,
        "sales_stage": profile.sales_stage,
        "sales_objective": "安全处理简单语音交互，不进入产品推荐或客户状态更新",
        **_route_metadata(route),
    }


@router.post("/api/interaction/classify")
def classify_interaction(request: InteractionRequest) -> dict[str, Any]:
    """Return an authoritative route without waiting for Terra.

    Direct routes include a complete ChatResponse-shaped payload. Terra routes
    return metadata only, allowing the frontend to begin a short progress cue
    while the guarded business request executes concurrently.
    """

    started = time.perf_counter()
    decision = turn_router.route(request.text, language=_language(request.response_language))
    payload = (
        _direct_payload(request, decision)
        if decision.route != "terra"
        else {"answer": "", **_route_metadata(decision)}
    )
    logger.info(
        "interaction_classify session=%s route=%s intent=%s latency_ms=%.1f reason=%s",
        request.session_id,
        decision.route,
        decision.intent,
        (time.perf_counter() - started) * 1000,
        decision.reason,
    )
    return payload


@router.post("/api/interaction/route")
def route_interaction(request: InteractionRequest) -> dict[str, Any]:
    started = time.perf_counter()
    language = _language(request.response_language)
    decision = turn_router.route(request.text, language=language)

    if decision.route != "terra":
        payload = _direct_payload(request, decision)
        logger.info(
            "interaction_route session=%s route=%s intent=%s latency_ms=%.1f reason=%s",
            request.session_id,
            decision.route,
            decision.intent,
            (time.perf_counter() - started) * 1000,
            decision.reason,
        )
        return payload

    # Terra/Qwen remain strict session-level providers. This route does not create
    # a hidden Terra<->Qwen fallback; it delegates to the provider already selected
    # for the session, while the default cloud session remains Terra.
    from .main import customer_memory_service, dialogue_orchestrator

    chat_request = ChatRequest(
        text=request.text,
        response_language=language,
        session_id=request.session_id,
        provider_mode=request.provider_mode,
        asr_confirmed=request.asr_confirmed,
    )
    response = dialogue_orchestrator.handle_turn(chat_request)
    try:
        customer_memory_service.record_turn(
            session_id=request.session_id,
            user_text=request.text,
            assistant_text=response.answer,
            profile=response.customer_profile,
        )
        if response.state == SessionState.SESSION_END:
            customer_memory_service.finish_session(response.customer_profile)
    except Exception:
        # Memory persistence must never break the customer-facing route.
        pass

    payload = response.model_dump()
    payload.update(_route_metadata(decision))
    logger.info(
        "interaction_route session=%s route=terra intent=%s latency_ms=%.1f reason=%s",
        request.session_id,
        decision.intent,
        (time.perf_counter() - started) * 1000,
        decision.reason,
    )
    return payload
