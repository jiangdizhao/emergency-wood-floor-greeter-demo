from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, StreamingResponse

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
    """Add charset=utf-8 to JSON responses for Windows PowerShell clients.

    Some PowerShell versions decode `application/json` incorrectly when the
    charset is not explicit. This middleware is a defensive backstop in addition
    to `UTF8JSONResponse`.
    """
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
    }


@app.get("/api/debug/encoding")
def debug_encoding() -> dict:
    """Small UTF-8 JSON endpoint for diagnosing terminal/client encoding."""
    return {
        "ok": True,
        "encoding_expected": "utf-8",
        "chinese_sample": "你好，木地板，云杉浅灰 SPC 锁扣地板，客厅，现代简约。",
        "product_name_sample": product_service.list_products()[0].name if product_service.list_products() else None,
        "powershell_tip": "Use backend/scripts/smoke_test_backend.ps1 or decode RawContentStream as UTF-8.",
    }


@app.get("/api/debug/plain-utf8")
def debug_plain_utf8() -> PlainTextResponse:
    """Plain-text UTF-8 endpoint to separate backend encoding from JSON decoding."""
    text = "你好，木地板，云杉浅灰 SPC 锁扣地板，客厅，现代简约。\n"
    return PlainTextResponse(text, media_type="text/plain; charset=utf-8")


@app.get("/api/debug/product-names")
def debug_product_names() -> dict:
    return {
        "names": [product.name for product in product_service.list_products()],
        "types": [product.type for product in product_service.list_products()],
    }


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
    """Manual fallback endpoint for the demo UI.

    Supported events:
    - person_far
    - person_close
    - wave
    - greeting
    - intro_finished
    - end
    - reset
    """
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
    if chat_service.is_session_end(request.text):
        state_machine.handle_event("end")
        profile = lead_service.load_profile(session_id=request.session_id)
        lang = chat_service.detect_language(request.text)
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
