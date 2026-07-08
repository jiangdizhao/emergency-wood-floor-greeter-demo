from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

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

app = FastAPI(
    title="Emergency Wood Floor Greeter Demo API",
    version="0.1.0",
    description="Backend for the 2-day wood-floor retail AI greeter demo.",
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

product_service = ProductService()
lead_service = LeadService()
recommendation_service = RecommendationService(product_service=product_service)
chat_service = ChatService(product_service=product_service, recommendation_service=recommendation_service)
state_machine = StoreSessionStateMachine()


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
        ],
    }


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "state": state_machine.state.value,
        "product_count": len(product_service.list_products()),
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
            "message": chat_service.build_welcome_message(),
            "status": {**state_machine.to_status_dict(), **result},
        }
    return {
        "accepted": False,
        "state": state_machine.state.value,
        "message": "未识别到明确问候。请说：你好、hi、hello，或向屏幕挥手。",
        "status": state_machine.to_status_dict(),
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    if chat_service.is_session_end(request.text):
        state_machine.handle_event("end")
        profile = lead_service.load_profile(session_id=request.session_id)
        return ChatResponse(
            answer="好的，感谢您的咨询。稍后销售可以根据本次需求记录继续跟进。",
            recommended_products=[],
            customer_profile=profile,
            follow_up_suggestion="建议销售在 24 小时内回访，确认房间面积、预算和安装时间。",
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


@app.get("/api/vision/status")
def vision_status() -> dict:
    """Placeholder status for Day-1 backend startup.

    Real camera processing will be attached next. For now this endpoint lets the UI
    and the demo controls run without blocking backend startup on camera drivers.
    """
    status = state_machine.to_status_dict()
    return {
        "ok": True,
        "mode": "simulated_until_vision_service_is_enabled",
        "person_detected": status.get("person_detected", False),
        "distance": status.get("distance", "UNKNOWN"),
        "wave_detected": status.get("wave_detected", False),
        "state": state_machine.state.value,
    }
