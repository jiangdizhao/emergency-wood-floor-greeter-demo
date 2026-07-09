from __future__ import annotations

import json
import os
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse

from .models import (
    ChatRequest,
    ChatResponse,
    CompareRequest,
    CustomerSaveRequest,
    DemoEventRequest,
    GreetingRequest,
    ProductCompareResponse,
    ProductsResponse,
    SessionStatusResponse,
    TTSRequest,
)
from .services.chat_service import ChatService
from .services.lead_service import LeadService
from .services.product_service import ProductService
from .services.recommendation_service import RecommendationService
from .services.state_machine import StoreSessionStateMachine
from .vision.vision_service import VisionConfig, VisionService


class UTF8JSONResponse(JSONResponse):
    """JSON response class that explicitly declares UTF-8 for Windows PowerShell.

    JSON is UTF-8 by default, but some Windows PowerShell versions decode
    application/json without a charset incorrectly. The explicit charset keeps
    Chinese product names readable in Invoke-RestMethod / Invoke-WebRequest.
    """

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
    version="0.1.0",
    description="Backend for the 2-day wood-floor retail AI greeter demo.",
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
        "important_endpoints": [
            "GET /api/health",
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
            "GET /api/debug/encoding",
            "GET /api/debug/plain-utf8",
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
    return SessionStatusResponse(
        state=state_machine.state,
        status=state_machine.to_status_dict(),
        customer_profile=profile,
    )


@app.post("/api/session/reset", response_model=SessionStatusResponse)
def reset_session(session_id: str = "demo-session-001") -> SessionStatusResponse:
    state_machine.reset()
    profile = lead_service.reset_profile(session_id=session_id)
    return SessionStatusResponse(
        state=state_machine.state,
        status=state_machine.to_status_dict(),
        customer_profile=profile,
    )


@app.post("/api/demo/event", response_model=SessionStatusResponse)
def handle_demo_event(request: DemoEventRequest) -> SessionStatusResponse:
    result = state_machine.handle_event(request.event)
    profile = lead_service.load_profile(session_id=request.session_id)
    return SessionStatusResponse(
        state=state_machine.state,
        status={**state_machine.to_status_dict(), **result},
        customer_profile=profile,
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
    lang = chat_service.normalize_response_language(request.text, request.response_language)

    if chat_service.is_session_end(request.text):
        state_machine.handle_event("end")
        profile = lead_service.load_profile(session_id=request.session_id)
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
            state=state_machine.state,
        )

    if state_machine.state.value not in {"CONVERSATION_ACTIVE", "INTRODUCING_PRODUCTS"}:
        state_machine.handle_event("greeting")
        state_machine.handle_event("intro_finished")

    current_profile = lead_service.load_profile(session_id=request.session_id)
    updated_profile = recommendation_service.extract_needs_from_text(request.text, current_profile)
    recommended = recommendation_service.recommend(updated_profile)
    answer = chat_service.answer_user_message(
        user_text=request.text,
        customer_profile=updated_profile,
        recommended_products=recommended,
        response_language=lang,
    )
    updated_profile.recommended_product_ids = [p.id for p in recommended]
    updated_profile.conversation_summary = chat_service.build_conversation_summary(updated_profile)
    updated_profile.follow_up_suggestion = chat_service.build_follow_up_suggestion(updated_profile)
    saved_profile = lead_service.save_profile(updated_profile)

    return ChatResponse(
        answer=answer,
        recommended_products=recommended,
        customer_profile=saved_profile,
        follow_up_suggestion=saved_profile.follow_up_suggestion,
        state=state_machine.state,
    )


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
