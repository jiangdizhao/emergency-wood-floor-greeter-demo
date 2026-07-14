from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

if sys.version_info < (3, 10):
    print("Senior sales static check requires Python 3.10 or newer.")
    print(f"Current interpreter: {sys.executable}")
    print(f"Current version: {sys.version}")
    raise SystemExit(2)

from app.llm.prompts import QWEN_RENDER_SYSTEM_PROMPT, RENDER_SYSTEM_PROMPT
from app.llm.providers import _finalize_sales_answer
from app.llm.schemas import DialogueDecision, SemanticTurn, ValidationResult
from app.models import CustomerProfile
from app.services.answer_plan_service import AnswerPlanService
from app.services.dialogue_context_service import DialogueContext
from app.services.dialogue_policy import DialoguePolicy
from app.services.product_service import ProductService
from app.services.recommendation_service import RecommendationService
from app.services.sales_conversation_policy import SalesConversationPolicy
from app.services.sales_knowledge_service import SalesKnowledgeService


def validation_for_priority() -> ValidationResult:
    semantic_turn = SemanticTurn(
        intent="provide_or_modify_needs",
        is_question=False,
        explicit_self_context=True,
        recommendation_requested=False,
        mentioned_products=[],
        mentioned_colors=[],
        actions=[],
        uncertain=False,
        confidence=0.99,
    )
    return ValidationResult(
        ok=True,
        can_apply=True,
        normalized_text="耐磨最重要",
        semantic_turn=semantic_turn,
        backend_self_context=True,
    )


def main() -> None:
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version.split()[0]}")

    product_service = ProductService()
    knowledge = SalesKnowledgeService()
    answer_plans = AnswerPlanService(product_service, knowledge)
    recommender = RecommendationService(product_service)
    dialogue_policy = DialoguePolicy()
    sales_policy = SalesConversationPolicy()

    company = knowledge.company_profile()
    collections = knowledge.collections()
    greeting = knowledge.new_customer_greeting()
    assert company.get("simulated") is True
    assert len(collections) >= 4
    assert "高级地板选购顾问" in greeting
    assert "不会让您一开始就回答一长串问题" in greeting
    assert "直接从产品讲起" in greeting
    assert "。。" not in greeting

    early_profile = CustomerProfile(
        session_id="sales-value-first-check",
        priorities={"耐磨": "high"},
        primary_purchase_driver="耐磨",
    )
    validation = validation_for_priority()
    context = DialogueContext(
        session_id=early_profile.session_id,
        pending_slot="priority",
        last_assistant_question="您最在意哪一点？",
        turn_index=1,
    )
    early_decision = dialogue_policy.decide(
        validation=validation,
        profile=early_profile,
        context=context,
    )
    assert early_decision.action == "recommend_now"
    assert "product story" in early_decision.reason

    early_sales_decision = sales_policy.decide(
        validation=validation,
        profile=early_profile,
        context=context,
        dialogue_decision=early_decision,
    )
    assert early_sales_decision.stage == "recommendation"
    assert "不要逐项盘问" in early_sales_decision.objective
    assert "不自动追加问题" in early_sales_decision.objective

    products = recommender.recommend(early_profile)
    assert products
    plan = answer_plans.build(
        user_text="耐磨最重要",
        validation=validation,
        profile=early_profile,
        recommended_products=products,
        decision=early_decision,
        sales_decision=early_sales_decision,
    )
    assert plan.must_recommend_now is True
    assert plan.products
    assert plan.products[0].presentation_role == "主推款"
    assert plan.products[0].tradeoffs
    assert plan.featured_collections
    assert plan.sales_stage == "recommendation"

    assert "next_question 是可选资料" in RENDER_SYSTEM_PROMPT
    assert "普通推荐和普通需求更新不要以问号结束" in RENDER_SYSTEM_PROMPT
    assert "每轮优先介绍一个新的产品特点" in QWEN_RENDER_SYSTEM_PROMPT
    assert "普通回答不要提问" in QWEN_RENDER_SYSTEM_PROMPT

    # Even when a renderer ignores the prompt and appends the old AnswerPlan
    # question, the provider guard removes that final question and replaces it
    # with a statement-led invitation.
    rendered_with_question = (
        f"我建议先看{plan.products[0].name}，它更符合耐磨优先。"
        "为了判断活动条件，请问预计铺装面积大约多少平方米？"
    )
    guarded = _finalize_sales_answer(rendered_with_question, plan, "zh")
    assert not guarded.endswith(("?", "？"))
    assert "预计铺装面积" not in guarded
    assert "不会重新开始一轮问卷" in guarded

    continued_profile = early_profile.model_copy(
        update={
            "recommended_product_ids": [product.id for product in products[:2]],
            "room_type": "客厅",
        }
    )
    continued_decision = dialogue_policy.decide(
        validation=validation,
        profile=continued_profile,
        context=context.model_copy(update={"turn_index": 3}),
    )
    assert continued_decision.action == "recommend_now"

    continued_sales_decision = sales_policy.decide(
        validation=validation,
        profile=continued_profile,
        context=context.model_copy(update={"turn_index": 3}),
        dialogue_decision=continued_decision,
    )
    assert continued_sales_decision.stage == "recommendation"
    assert "不要逐项盘问" in continued_sales_decision.objective

    print("Senior sales value-first static check passed.")
    print(f"Company: {company.get('company_name')}")
    print(f"Greeting: {greeting}")
    print(f"First product story starts after one priority: {plan.products[0].name}")
    if len(plan.products) > 1:
        print(f"Backup option: {plan.products[1].name}")
    print("Featured collections: " + ", ".join(item.name for item in plan.featured_collections))
    print("Serial room/budget/style/area/timeline questionnaire: disabled")
    print("Forced trailing recommendation questions: removed by provider guard")


if __name__ == "__main__":
    main()
