from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DialogueProviderName = Literal["terra", "qwen"]
IntentName = Literal[
    "provide_or_modify_needs",
    "request_recommendation",
    "request_comparison",
    "ask_reason",
    "ask_promotion",
    "express_objection",
    "accept_recommendation",
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
DecisionAction = Literal[
    "clarify",
    "ask_missing_slot",
    "acknowledge",
    "recommend_now",
    "compare_now",
]
SalesStage = Literal[
    "introduction",
    "discovery",
    "qualification",
    "recommendation",
    "objection_handling",
    "promotion",
    "soft_close",
    "lead_capture",
    "follow_up",
]
SalesNextBestAction = Literal[
    "introduce_company",
    "ask_primary_priority",
    "ask_usage_context",
    "ask_project_area",
    "ask_purchase_timeline",
    "qualify_needs",
    "present_main_and_backup",
    "explain_tradeoff",
    "mention_approved_promotion",
    "soft_close",
    "offer_contact_form",
    "prepare_follow_up",
    "clarify_customer_input",
]
PendingSlotName = Literal[
    "room_type",
    "budget",
    "style",
    "preferred_color",
    "priority",
    "estimated_area_sqm",
    "purchase_timeline",
    "project_type",
]


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
    can_apply: bool = False
    needs_clarification: bool = False
    critical_conflict: bool = False
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


class DialogueDecision(BaseModel):
    action: DecisionAction
    reason: str
    pending_slot: PendingSlotName | None = None
    question: str | None = None


class SalesDecision(BaseModel):
    stage: SalesStage
    next_best_action: SalesNextBestAction
    objective: str
    reason: str


class ApprovedCollectionFact(BaseModel):
    collection_id: str
    name: str
    tagline: str
    strengths: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)


class ApprovedProductFact(BaseModel):
    product_id: str
    name: str
    product_type: str
    color: str
    price_range: str
    presentation_role: Literal["主推款", "备选款", "对比款"] = "主推款"
    approved_facts: list[str] = Field(default_factory=list)
    match_reasons: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)


class ApprovedPromotion(BaseModel):
    promotion_id: str
    title: str
    approved_message: str
    conditions: list[str] = Field(default_factory=list)
    call_to_action: str | None = None
    area_status: Literal["not_required", "needs_area", "eligible"] | str = "not_required"
    simulated: bool = True


class AnswerPlan(BaseModel):
    response_type: Literal[
        "recommendation",
        "comparison",
        "product_answer",
        "promotion",
        "objection_response",
        "soft_close",
        "lead_capture",
        "clarification",
        "acknowledgement",
        "service_unavailable",
    ]
    sales_stage: SalesStage = "discovery"
    sales_objective: str = "准确回应客户当前问题"
    next_best_action: SalesNextBestAction = "qualify_needs"
    company_highlights: list[str] = Field(default_factory=list)
    featured_collections: list[ApprovedCollectionFact] = Field(default_factory=list)
    customer_need_summary: list[str] = Field(default_factory=list)
    products: list[ApprovedProductFact] = Field(default_factory=list)
    approved_promotions: list[ApprovedPromotion] = Field(default_factory=list)
    objection_response: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    call_to_action: str | None = None
    ask_contact_consent: bool = False
    contact_request_reason: str | None = None
    next_question: str | None = None
    direct_message: str | None = None
    must_recommend_now: bool = False
    allow_future_commitment: bool = False


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
                "ask_promotion",
                "express_objection",
                "accept_recommendation",
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
