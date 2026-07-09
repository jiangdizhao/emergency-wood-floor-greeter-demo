from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


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
    customer_name: str | None = None
    phone: str | None = None
    room_type: str | None = None
    style: str | None = None
    budget: str | None = None
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


class ChatRequest(BaseModel):
    text: str
    session_id: str = "demo-session-001"
    response_language: Literal["zh", "en"] | None = None


class ChatResponse(BaseModel):
    answer: str
    recommended_products: list[FlooringProduct]
    customer_profile: CustomerProfile
    follow_up_suggestion: str
    state: SessionState


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


class CustomerSaveRequest(BaseModel):
    session_id: str = "demo-session-001"
    customer_name: str | None = None
    phone: str | None = None
