from __future__ import annotations

import json
import os
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse

from .llm.providers import ProviderRegistry
from .models import (
    ChatRequest,
    ChatResponse,
    CompareRequest,
    CustomerSaveRequest,
    DemoEventRequest,
    GreetingRequest,
    ProductCompareResponse,
    ProductsResponse,
    ProviderModeRequest,
    ProviderModeResponse,
    SessionStatusResponse,
    TTSRequest,
)
from .services.answer_plan_service import AnswerPlanService
from .services.chat_service import ChatService
from .services.customer_state_service import CustomerStateService
from .services.dialogue_orchestrator import DialogueOrchestrator
from .services.lead_service import LeadService
from .services.product_service import ProductService
from .services.recommendation_service import RecommendationService
from .services.session_runtime_service import SessionRuntimeService
from .services.state_machine import StoreSessionStateMachine
from .services.validation_guard import ValidationGuard
from .vision.vision_service import VisionConfig, VisionService


class UTF8JSONResponse(JSONResponse):
    """JSON response class that explicitly declares UTF-8 for Windows PowerShell."""

    media_type = "application/json; charset=utf-8"

    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")


app = FastAPI(
    title="Emergency Wood Floor Greeter Demo API",
    version="0.2.0",
    description="Wood-floor retail AI greeter with parallel Terra cloud and Qwen local dialogue modes.",
    default_response_class=UTF8JSONResponse,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def force_utf8_json_content_type(request: Request, call_next):  # type: ignore[no-untyped-def]
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("application/json") and "charset=" not in content_type.lower():
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response


product_service = ProductService()
lead_service = LeadService()
recommendation_service = RecommendationService(product_service=product_service)
chat_service = ChatService(product_service=product_service, recommendation_service=recommendation_service)
state_machine = StoreSessionStateMachine()
vision_service = VisionService(state_machine=state_machine, config=VisionConfig())

provider_registry = ProviderRegistry()
runtime_service = SessionRuntimeService()
validation_guard = ValidationGuard(product_service=product_service)
customer_state_service = CustomerStateService()
answer_plan_service = AnswerPlanService(product_service=product_service)
dialogue_orchestrator = DialogueOrchestrator(
    provider_registry=provider_registry,
    runtime_service=runtime_service,
    lead_service=lead_service,
    recommendation_service=recommendation_service,
    validation_guard=validation_guard,
    customer_state_service=customer_state_service,
    answer_plan_service=answer_plan_service,
    chat_service=chat_service,
    state_machine=state_machine,
)


def _local_tts_url() -> str:
    return os.getenv("LOCAL_TTS_URL", "http://127.0.0.1:8010/tts")


def _local_tts_health_url() -> str:
    return os.getenv("LOCAL_TTS_HEALTH_URL", "http://127.0.0.1:8010/health")


def _local_tts_available() -> bool:
    try:
        response = requests.get(_local_tts_health_url(), timeout=1.0)
        return response.ok
    except requests.RequestException:
        return False


def _call_local_tts(request: TTSRequest, text: str) -> Response:
    local_url = _local_tts_url()
    timeout = float(os.getenv("LOCAL_TTS_TIMEOUT_SECONDS", "45"))
    upstream = requests.post(
        local_url,
        json={
            "text": text,
            "language": request.language,
            "voice": request.voice,
            "speed": 1.0,
        },
        timeout=timeout,
    )
    if upstream.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Local Kokoro TTS error {upstream.status_code}: {upstream.text[:500]}")
    return Response(
        content=upstream.content,
        media_type=upstream.headers.get("content-type", "audio/wav"),
        headers={
            "Cache-Control": "no-store",
            "X-TTS-Provider": "local-kokoro",
            "X-Local-TTS-URL": local_url,
        },
    )


def _call_openai_tts(request: TTSRequest, text: str) -> Response:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not set. Frontend should fall back to browser TTS.")

    model = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
    voice = request.voice or os.getenv("OPENAI_TTS_VOICE", "marin")
    instructions = (
        "Speak in warm, natural, professional retail-consultant English. Keep the pace relaxed and friendly."
        if request.language == "en"
        else "请用自然、亲切、专业的中文门店导购语气朗读，语速适中，像真人销售顾问。"
    )

    upstream = requests.post(
        "https://api.openai.com/v1/audio/speech",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "voice": voice,
            "input": text,
            "instructions": instructions,
            "response_format": "mp3",
        },
        timeout=45,
    )
    if upstream.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"OpenAI TTS error {upstream.status_code}: {upstream.text[:500]}")

    return Response(
        content=upstream.content,
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-store",
            "X-TTS-Provider": "openai",
            "X-TTS-Model": model,
            "X-TTS-Voice": voice,
        },
    )


@app.on_event("shutdown")
def shutdown_event() -> None:
    vision_service.stop()


@app.get("/")
def root() -> dict:
    return {
        "name": "Emergency Wood Floor Greeter Demo API",
        "status": "running",
        "docs": "/docs",
        "dialogue_architecture": "parallel Terra cloud mode and Qwen local mode; no hidden cross-provider fallback",
        "important_endpoints": [
            "GET /api/health",
            "GET /api/llm/status",
            "POST /api/session/provider",
            "GET /api/products",
            "POST /api/chat",
            "POST /api/tts",
            "GET /api/tts/status",
            "POST /api/greeting/voice",
            "POST /api/demo/event",
            "GET /api/session/status",
            "POST /api/session/reset",
            "POST /api/vision/start",
            "POST /api/vision/stop",
            "GET /api/vision/status",
            "GET /api/vision/stream",
        ],
    }


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "state": state_machine.state.value,
        "product_count": len(product_service.list_products()),
        "vision_running": vision_service.get_status().get("running", False),
        "openai_tts_configured": bool(os.getenv("OPENAI_API_KEY")),
        "local_tts_available": _local_tts_available(),
        "default_dialogue_provider": runtime_service.load("demo-session-001").provider_mode,
    }


@app.get("/api/llm/status")
def llm_status(session_id: str = "demo-session-001") -> dict:
    runtime = runtime_service.load(session_id)
    return {
        "ok": True,
        "session_id": session_id,
        "active_provider": runtime.provider_mode,
        "active_provider_label": runtime_service.provider_label(runtime.provider_mode),
        "cross_provider_fallback": False,
        "providers": provider_registry.status(),
    }


@app.get("/api/debug/encoding")
def debug_encoding() -> dict:
    return {
        "ok": True,
        "encoding_expected": "utf-8",
        "chinese_sample": "你好，木地板，云杉浅灰 SPC 锁扣地板，客厅，现代简约。",
        "product_name_sample": product_service.list_products()[0].name if product_service.list_products() else None,
        "powershell_tip": "Use backend/scripts/smoke_test_backend.ps1 or decode RawContentStream as UTF-8.",
    }


@app.get("/api/debug/plain-utf8")
def debug_plain_utf8() -> PlainTextResponse:
    text = "你好，木地板，云杉浅灰 SPC 锁扣地板，客厅，现代简约。\n"
    return PlainTextResponse(text, media_type="text/plain; charset=utf-8")


@app.get("/api/debug/product-names")
def debug_product_names() -> dict:
    return {
        "names": [product.name for product in product_service.list_products()],
        "types": [product.type for product in product_service.list_products()],
    }


@app.get("/api/tts/status")
def tts_status() -> dict:
    return {
        "ok": True,
        "local_tts_available": _local_tts_available(),
        "local_tts_url": _local_tts_url(),
        "local_tts_health_url": _local_tts_health_url(),
        "openai_tts_configured": bool(os.getenv("OPENAI_API_KEY")),
        "openai_model": os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
        "openai_voice": os.getenv("OPENAI_TTS_VOICE", "marin"),
        "auto_order": ["local_kokoro", "openai", "frontend_browser_speech_synthesis"],
    }


@app.post("/api/tts")
def tts(request: TTSRequest) -> Response:
    if request.provider == "browser":
        raise HTTPException(status_code=400, detail="Browser TTS should be handled by the frontend, not /api/tts.")

    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="TTS text is empty.")

    errors: list[str] = []
    if request.provider in {"local", "auto"}:
        try:
            return _call_local_tts(request, text)
        except HTTPException as exc:
            errors.append(f"local: {exc.detail}")
            if request.provider == "local":
                raise
        except requests.RequestException as exc:
            errors.append(f"local: {exc}")
            if request.provider == "local":
                raise HTTPException(status_code=502, detail=f"Local Kokoro TTS request failed: {exc}") from exc

    if request.provider in {"openai", "auto"}:
        try:
            return _call_openai_tts(request, text)
        except HTTPException as exc:
            errors.append(f"openai: {exc.detail}")
            if request.provider == "openai":
                raise
        except requests.RequestException as exc:
            errors.append(f"openai: {exc}")
            if request.provider == "openai":
                raise HTTPException(status_code=502, detail=f"OpenAI TTS request failed: {exc}") from exc

    raise HTTPException(status_code=503, detail="; ".join(errors) or "No TTS provider available. Frontend should fall back to browser TTS.")


@app.get("/api/products", response_model=ProductsResponse)
def list_products() -> ProductsResponse:
    return ProductsResponse(products=product_service.list_products())


@app.post("/api/products/compare", response_model=ProductCompareResponse)
def compare_products(request: CompareRequest) -> ProductCompareResponse:
    if len(request.product_ids) < 2:
        raise HTTPException(status_code=400, detail="At least two product_ids are required for comparison.")
    return ProductCompareResponse(comparison=product_service.compare_products(request.product_ids))


@app.get("/api/session/status", response_model=SessionStatusResponse)
def get_session_status(session_id: str = "demo-session-001") -> SessionStatusResponse:
    profile = lead_service.load_profile(session_id=session_id)
    runtime = runtime_service.load(session_id)
    label = runtime_service.provider_label(runtime.provider_mode)
    return SessionStatusResponse(
        state=state_machine.state,
        status={**state_machine.to_status_dict(), "provider_mode": runtime.provider_mode, "provider_label": label},
        customer_profile=profile,
        provider_mode=runtime.provider_mode,
        provider_label=label,
    )


@app.post("/api/session/provider", response_model=ProviderModeResponse)
def set_session_provider(request: ProviderModeRequest) -> ProviderModeResponse:
    runtime = runtime_service.set_provider(request.session_id, request.provider_mode)
    return ProviderModeResponse(
        session_id=runtime.session_id,
        provider_mode=runtime.provider_mode,
        provider_label=runtime_service.provider_label(runtime.provider_mode),
    )


@app.post("/api/session/reset", response_model=SessionStatusResponse)
def reset_session(session_id: str = "demo-session-001") -> SessionStatusResponse:
    state_machine.reset()
    profile = lead_service.reset_profile(session_id=session_id)
    runtime = runtime_service.load(session_id)
    label = runtime_service.provider_label(runtime.provider_mode)
    return SessionStatusResponse(
        state=state_machine.state,
        status={**state_machine.to_status_dict(), "provider_mode": runtime.provider_mode, "provider_label": label},
        customer_profile=profile,
        provider_mode=runtime.provider_mode,
        provider_label=label,
    )


@app.post("/api/demo/event", response_model=SessionStatusResponse)
def handle_demo_event(request: DemoEventRequest) -> SessionStatusResponse:
    result = state_machine.handle_event(request.event)
    profile = lead_service.load_profile(session_id=request.session_id)
    runtime = runtime_service.load(request.session_id)
    label = runtime_service.provider_label(runtime.provider_mode)
    return SessionStatusResponse(
        state=state_machine.state,
        status={**state_machine.to_status_dict(), **result, "provider_mode": runtime.provider_mode, "provider_label": label},
        customer_profile=profile,
        provider_mode=runtime.provider_mode,
        provider_label=label,
    )


@app.post("/api/greeting/voice")
def voice_greeting(request: GreetingRequest) -> dict:
    accepted = chat_service.is_greeting(request.text)
    if accepted:
        result = state_machine.handle_event("greeting")
        return {
            "accepted": True,
            "state": state_machine.state.value,
            "message": chat_service.build_welcome_message(request.text),
            "status": {**state_machine.to_status_dict(), **result},
        }
    lang = chat_service.detect_language(request.text)
    message = (
        "Greeting not recognized. Please say: hello, hi, or wave to the screen."
        if lang == "en"
        else "未识别到明确问候。请说：你好、hi、hello，或向屏幕挥手。"
    )
    return {
        "accepted": False,
        "state": state_machine.state.value,
        "message": message,
        "status": state_machine.to_status_dict(),
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    return dialogue_orchestrator.handle_turn(request)


@app.post("/api/customer/save")
def save_customer(request: CustomerSaveRequest) -> dict:
    profile = lead_service.load_profile(session_id=request.session_id)
    profile.customer_name = request.customer_name or profile.customer_name
    profile.phone = request.phone or profile.phone
    profile.follow_up_status = "待联系"
    profile = lead_service.save_profile(profile)
    return {
        "ok": True,
        "message": "客户需求已保存到本地模拟档案。",
        "customer_profile": profile.model_dump(),
    }


@app.post("/api/vision/start")
def vision_start() -> dict:
    return vision_service.start()


@app.post("/api/vision/stop")
def vision_stop() -> dict:
    return vision_service.stop()


@app.get("/api/vision/status")
def vision_status() -> dict:
    return vision_service.get_status()


@app.get("/api/vision/stream")
def vision_stream() -> StreamingResponse:
    if not vision_service.get_status().get("running"):
        vision_service.start()
    return StreamingResponse(
        vision_service.mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
