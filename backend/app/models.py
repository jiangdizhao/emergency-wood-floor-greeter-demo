from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

DialogueProvider = Literal["terra", "qwen"]
PendingSlot = Literal["room_type", "budget", "style", "preferred_color", "priority"]
IdentityChoice = Literal["continue_previous", "new_project", "not_me"]


class SessionState(str, Enum):
    IDLE = "IDLE"
    PERSON_DETECTED_FAR = "PERSON_DETECTED_FAR"
    PERSON_CLOSE_WAITING_GREETING = "PERSON_CLOSE_WAITING_GREETING"
    GREETING_RECEIVED = "GREETING_RECEIVED"
    INTRODUCING_PRODUCTS = "INTRODUCING_PRODUCTS"
    CONVERSATION_ACTIVE = "CONVERSATION_ACTIVE"
    SESSION_END = "SESSION_END"


class FlooringProduct(BaseModel):
    id: str
    name: str
    type: str
    color: str
    style: list[str] = Field(default_factory=list)
    suitable_rooms: list[str] = Field(default_factory=list)
    waterproof: bool = False
    floor_heating: bool = False
    pet_friendly: bool = False
    child_friendly: bool = False
    wear_level: str = "未知"
    price_range: Literal["经济", "中等", "偏高", "高端"] | str = "未知"
    spec: str = "待确认"
    selling_points: list[str] = Field(default_factory=list)


class CustomerProfile(BaseModel):
    session_id: str = "demo-session-001"
    customer_id: str | None = None
    is_returning_customer: bool = False
    memory_summary: str = ""
    previous_visit_summaries: list[str] = Field(default_factory=list)
    last_seen_at: str | None = None

    customer_name: str | None = None
    phone: str | None = None
    room_type: str | None = None
    style: str | None = None
    budget: str | None = None

    has_pets: bool | None = None
    has_floor_heating: bool | None = None
    has_children: bool | None = None
    has_elderly: bool | None = None
    humid_environment: bool | None = None
    priorities: dict[str, str] = Field(default_factory=dict)
    preferred_colors: list[str] = Field(default_factory=list)
    rejected_colors: list[str] = Field(default_factory=list)
    preferred_product_ids: list[str] = Field(default_factory=list)
    rejected_product_ids: list[str] = Field(default_factory=list)

    # Kept for backward compatibility with the current UI and deterministic scorer.
    special_needs: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    recommended_product_ids: list[str] = Field(default_factory=list)
    conversation_summary: str = ""
    follow_up_status: str = "未建档"
    follow_up_suggestion: str = ""


class ProductsResponse(BaseModel):
    products: list[FlooringProduct]


class CompareRequest(BaseModel):
    product_ids: list[str]


class ProductCompareRow(BaseModel):
    field: str
    values: dict[str, Any]


class ProductCompareResponse(BaseModel):
    comparison: list[ProductCompareRow]


class ASRAlternative(BaseModel):
    transcript: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ChatRequest(BaseModel):
    text: str
    session_id: str = "demo-session-001"
    response_language: Literal["zh", "en"] | None = None
    provider_mode: DialogueProvider | None = None
    asr_alternatives: list[ASRAlternative] = Field(default_factory=list)
    asr_confirmed: bool = False


class ChatResponse(BaseModel):
    answer: str
    recommended_products: list[FlooringProduct]
    customer_profile: CustomerProfile
    follow_up_suggestion: str
    state: SessionState
    provider_mode: DialogueProvider = "qwen"
    provider_label: str = "Private Local AI · Qwen 3.5"
    llm_degraded: bool = False
    needs_clarification: bool = False
    pending_slot: PendingSlot | None = None
    last_assistant_question: str | None = None
    asr_confirmation_required: bool = False
    asr_suggested_text: str | None = None


class TTSRequest(BaseModel):
    text: str
    language: Literal["zh", "en"] = "en"
    provider: Literal["local", "openai", "browser", "auto"] = "auto"
    voice: str | None = None


class GreetingRequest(BaseModel):
    text: str
    session_id: str = "demo-session-001"


class DemoEventRequest(BaseModel):
    event: str
    session_id: str = "demo-session-001"


class SessionStatusResponse(BaseModel):
    state: SessionState
    status: dict[str, Any]
    customer_profile: CustomerProfile
    provider_mode: DialogueProvider = "qwen"
    provider_label: str = "Private Local AI · Qwen 3.5"


class ProviderModeRequest(BaseModel):
    session_id: str = "demo-session-001"
    provider_mode: DialogueProvider


class ProviderModeResponse(BaseModel):
    ok: bool = True
    session_id: str
    provider_mode: DialogueProvider
    provider_label: str


class CustomerSaveRequest(BaseModel):
    session_id: str = "demo-session-001"
    customer_name: str | None = None
    phone: str | None = None


class IdentityRecognizeRequest(BaseModel):
    provider_mode: DialogueProvider | None = None


class IdentityCandidateChoiceRequest(BaseModel):
    candidate_token: str
    choice: IdentityChoice
    provider_mode: DialogueProvider | None = None


class IdentityNewSessionRequest(BaseModel):
    provider_mode: DialogueProvider | None = None


class IdentityEnrollRequest(BaseModel):
    session_id: str
    consent: bool
    display_name: str | None = None


class IdentityForgetRequest(BaseModel):
    session_id: str
    delete_history: bool = True


class IdentitySessionResponse(BaseModel):
    ok: bool = True
    session_id: str
    customer_profile: CustomerProfile
    returning_customer: bool = False
    greeting: str
    provider_mode: DialogueProvider
    provider_label: str
    memory_loaded: bool = False
