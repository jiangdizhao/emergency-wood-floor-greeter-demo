from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.llm.schemas import DialogueDecision, SalesDecision, SemanticTurn, ValidationResult
from app.models import CustomerProfile
from app.services.answer_plan_service import AnswerPlanService
from app.services.product_service import ProductService
from app.services.recommendation_service import RecommendationService
from app.services.sales_knowledge_service import SalesKnowledgeService


def main() -> None:
    product_service = ProductService()
    knowledge = SalesKnowledgeService()
    answer_plans = AnswerPlanService(product_service, knowledge)
    recommender = RecommendationService(product_service)

    company = knowledge.company_profile()
    collections = knowledge.collections()
    greeting = knowledge.new_customer_greeting()
    assert company.get("simulated") is True
    assert len(collections) >= 4
    assert "高级地板选购顾问" in greeting
    assert "最不愿意妥协" in greeting

    profile = CustomerProfile(
        session_id="sales-static-check",
        room_type="客厅",
        budget="中等",
        style="现代简约",
        has_pets=True,
        priorities={"耐磨": "high", "好清洁": "medium"},
        primary_purchase_driver="耐磨",
    )
    products = recommender.recommend(profile)
    assert len(products) >= 1

    semantic_turn = SemanticTurn(
        intent="request_recommendation",
        is_question=True,
        explicit_self_context=True,
        recommendation_requested=True,
        mentioned_products=[],
        mentioned_colors=[],
        actions=[],
        uncertain=False,
        confidence=0.99,
    )
    validation = ValidationResult(
        ok=True,
        can_apply=False,
        normalized_text="请给我推荐",
        semantic_turn=semantic_turn,
        backend_self_context=True,
    )
    decision = DialogueDecision(
        action="recommend_now",
        reason="offline static check",
    )
    sales_decision = SalesDecision(
        stage="recommendation",
        next_best_action="present_main_and_backup",
        objective="给出主推款、备选款和真实取舍",
        reason="offline static check",
    )
    plan = answer_plans.build(
        user_text="请给我推荐",
        validation=validation,
        profile=profile,
        recommended_products=products,
        decision=decision,
        sales_decision=sales_decision,
    )

    assert plan.must_recommend_now is True
    assert plan.products
    assert plan.products[0].presentation_role == "主推款"
    assert plan.products[0].tradeoffs
    assert plan.featured_collections
    assert plan.sales_stage == "recommendation"
    assert plan.next_best_action == "present_main_and_backup"

    print("Senior sales phase-one static check passed.")
    print(f"Company: {company.get('company_name')}")
    print(f"Greeting: {greeting}")
    print(f"Main product: {plan.products[0].name}")
    if len(plan.products) > 1:
        print(f"Backup product: {plan.products[1].name}")
    print("Featured collections: " + ", ".join(item.name for item in plan.featured_collections))
    print("Tradeoff: " + plan.products[0].tradeoffs[0])


if __name__ == "__main__":
    main()
