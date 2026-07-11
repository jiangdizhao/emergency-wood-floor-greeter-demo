from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DialogueProviderName = Literal["terra", "qwen"]
IntentName = Literal[
    "provide_or_modify_needs",
    "request_recommendation",
    "request_comparison",
    "ask_reason",
    "reject_product",
    "reject_color",
    "general_product_question",
    "other",
]
ActionKind = Literal[
    "set_field",
    "set_priority",
    "prefer_color",
    "reject_color",
    "prefer_product",
    "reject_product",
]
ActionScope = Literal["persistent", "turn_only"]


class SemanticAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ActionKind
    name: str
    value: str
    evidence: str


class SemanticTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: IntentName
    is_question: bool
    explicit_self_context: bool
    recommendation_requested: bool
    mentioned_products: list[str]
    mentioned_colors: list[str]
    actions: list[SemanticAction]
    uncertain: bool
    confidence: float = Field(ge=0.0, le=1.0)


class ValidatedAction(SemanticAction):
    scope: ActionScope
    product_ids: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    ok: bool
    normalized_text: str
    semantic_turn: SemanticTurn
    backend_self_context: bool
    actions: list[ValidatedAction] = Field(default_factory=list)
    mentioned_product_ids: list[str] = Field(default_factory=list)
    mentioned_colors: list[str] = Field(default_factory=list)
    missing_claims: list[str] = Field(default_factory=list)
    rejected_actions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    clarification_question: str | None = None


class ApprovedProductFact(BaseModel):
    product_id: str
    name: str
    product_type: str
    color: str
    price_range: str
    approved_facts: list[str] = Field(default_factory=list)
    match_reasons: list[str] = Field(default_factory=list)


class AnswerPlan(BaseModel):
    response_type: Literal[
        "recommendation",
        "comparison",
        "product_answer",
        "clarification",
        "acknowledgement",
        "service_unavailable",
    ]
    customer_need_summary: list[str] = Field(default_factory=list)
    products: list[ApprovedProductFact] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    next_question: str | None = None
    direct_message: str | None = None


SEMANTIC_TURN_JSON_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "intent": {
            "type": "string",
            "enum": [
                "provide_or_modify_needs",
                "request_recommendation",
                "request_comparison",
                "ask_reason",
                "reject_product",
                "reject_color",
                "general_product_question",
                "other",
            ],
        },
        "is_question": {"type": "boolean"},
        "explicit_self_context": {"type": "boolean"},
        "recommendation_requested": {"type": "boolean"},
        "mentioned_products": {"type": "array", "items": {"type": "string"}},
        "mentioned_colors": {"type": "array", "items": {"type": "string"}},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": [
                            "set_field",
                            "set_priority",
                            "prefer_color",
                            "reject_color",
                            "prefer_product",
                            "reject_product",
                        ],
                    },
                    "name": {"type": "string"},
                    "value": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": ["kind", "name", "value", "evidence"],
            },
        },
        "uncertain": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": [
        "intent",
        "is_question",
        "explicit_self_context",
        "recommendation_requested",
        "mentioned_products",
        "mentioned_colors",
        "actions",
        "uncertain",
        "confidence",
    ],
}
