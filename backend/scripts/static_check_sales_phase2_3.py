from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

if sys.version_info < (3, 10):
    print("Sales phase-two/three static check requires Python 3.10 or newer.")
    print(f"Current interpreter: {sys.executable}")
    print(f"Current version: {sys.version}")
    raise SystemExit(2)

from app.llm.prompts import build_parse_user_prompt
from app.llm.schemas import DialogueDecision, SalesDecision, SemanticTurn, ValidationResult
from app.models import CustomerProfile
from app.services.answer_plan_service import AnswerPlanService
from app.services.crm_identity_bridge import CRMIdentityBridge
from app.services.crm_repository import CRMRepository
from app.services.product_service import ProductService
from app.services.promotion_service import PromotionService
from app.services.recommendation_service import RecommendationService
from app.services.sales_knowledge_service import SalesKnowledgeService
from app.services.sales_signals_service import SalesSignalsService


def main() -> None:
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version.split()[0]}")

    product_service = ProductService()
    recommendation_service = RecommendationService(product_service)
    knowledge_service = SalesKnowledgeService()
    promotion_service = PromotionService()
    answer_plans = AnswerPlanService(
        product_service,
        knowledge_service,
        promotion_service,
    )
    sales_signals = SalesSignalsService()

    profile = CustomerProfile(
        session_id="phase23-static-session",
        room_type="客厅",
        budget="中等",
        style="现代简约",
        project_type="旧房翻新",
        estimated_area_sqm=80,
        purchase_timeline="1个月内",
        decision_stage="正在比较",
        has_pets=True,
        priorities={"耐磨": "high", "好清洁": "medium"},
        primary_purchase_driver="耐磨",
        promotion_interest=True,
    )
    products = recommendation_service.recommend(profile)[:2]
    assert products, "Deterministic recommender returned no products."

    relevant_collections = knowledge_service.relevant_collections(
        profile=profile,
        products=products,
    )
    promotions = promotion_service.eligible_promotions(
        profile=profile,
        products=products,
        collection_ids=[str(item.get("collection_id")) for item in relevant_collections],
        now=datetime(2026, 7, 15, tzinfo=timezone.utc),
    )
    assert promotions, "Expected at least one eligible simulated promotion."
    assert all(item.get("simulated") is True for item in promotions)
    assert all(item.get("approved_message") for item in promotions)

    semantic_turn = SemanticTurn(
        intent="ask_promotion",
        is_question=True,
        explicit_self_context=True,
        recommendation_requested=False,
        mentioned_products=[],
        mentioned_colors=[],
        actions=[],
        uncertain=False,
        confidence=0.99,
    )
    validation = ValidationResult(
        ok=True,
        can_apply=False,
        normalized_text="现在有什么优惠活动",
        semantic_turn=semantic_turn,
        backend_self_context=True,
    )
    dialogue_decision = DialogueDecision(
        action="acknowledge",
        reason="promotion static check",
    )
    sales_decision = SalesDecision(
        stage="promotion",
        next_best_action="mention_approved_promotion",
        objective="只介绍批准且适用的演示活动",
        reason="promotion static check",
    )
    plan = answer_plans.build(
        user_text="现在有什么优惠活动",
        validation=validation,
        profile=profile,
        recommended_products=products,
        decision=dialogue_decision,
        sales_decision=sales_decision,
    )
    assert plan.response_type == "promotion"
    assert plan.approved_promotions
    assert plan.approved_promotions[0].simulated is True
    assert "演示" in plan.approved_promotions[0].approved_message

    profile.recommended_product_ids = [product.id for product in products]
    qualified = sales_signals.update(
        profile=profile,
        user_text="我认可这个方案，想尽快报价",
        intent="accept_recommendation",
    )
    assert qualified.lead_temperature in {"warm", "hot"}
    assert qualified.contact_prompt_eligible is True

    # Contact details must be stripped before any LLM prompt is constructed.
    prompt = build_parse_user_prompt(
        "请继续讲方案",
        {
            **qualified.model_dump(),
            "customer_name": "测试客户",
            "phone": "+61412345678",
            "contact_value": "private@example.com",
        },
        {"pending_slot": None},
    )
    assert "+61412345678" not in prompt
    assert "private@example.com" not in prompt
    assert "测试客户" not in prompt

    with tempfile.TemporaryDirectory(prefix="woodfloor-crm-") as temporary_directory:
        database_path = Path(temporary_directory) / "crm-test.db"
        repository = CRMRepository(database_path)
        # Simulate a lead captured before optional face enrollment. The later
        # conversation-session binding must still make it deletable by customer.
        with repository._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_sessions(
                    session_id TEXT PRIMARY KEY,
                    customer_id TEXT
                )
                """
            )
            connection.execute(
                "INSERT INTO conversation_sessions(session_id, customer_id) VALUES (?, ?)",
                ("phase23-static-session", "customer-static"),
            )

        lead = repository.upsert_lead(
            session_id="phase23-static-session",
            customer_id=None,
            display_name="测试客户",
            contact_channel="email",
            contact_value="private@example.com",
            contact_opt_in=True,
            marketing_opt_in=False,
            contact_purposes=["发送本次选购方案", "跟进报价与样板"],
            preferred_contact_time="工作日下午",
            lead_temperature=qualified.lead_temperature,
            sales_stage="lead_capture",
            promotion_ids=[item["promotion_id"] for item in promotions],
            next_follow_up_days=3,
        )
        assert lead["contact_opt_in"] is True
        assert lead["marketing_opt_in"] is False
        assert repository.masked_contact(lead) != lead["contact_value"]
        assert repository.count_active() == 1

        consent_updated = repository.update_consents(
            session_id="phase23-static-session",
            contact_opt_in=True,
            marketing_opt_in=True,
        )
        assert consent_updated is not None
        assert consent_updated["marketing_opt_in"] is True

        due = repository.due_follow_ups(
            now=datetime(2100, 1, 1, tzinfo=timezone.utc),
        )
        assert len(due) == 1

        updated = repository.update_follow_up(
            lead_id=str(lead["lead_id"]),
            status="已发送方案",
            note="静态检查",
            next_follow_up_at=None,
        )
        assert updated is not None
        assert updated["follow_up_status"] == "已发送方案"

        revoked = repository.update_consents(
            session_id="phase23-static-session",
            contact_opt_in=False,
            marketing_opt_in=False,
        )
        assert revoked is not None
        assert revoked["active"] is False
        assert revoked["contact_opt_in"] is False

        bridge = CRMIdentityBridge(repository)
        assert bridge.delete_customer_records(customer_id="customer-static") == 1
        assert repository.get_by_session("phase23-static-session", include_inactive=True) is None

    # Import the complete FastAPI application last, so schema and route wiring are
    # checked without opening the camera or calling Terra/Qwen.
    from app.main import app

    route_paths = {route.path for route in app.routes}
    expected_routes = {
        "/api/sales/catalog",
        "/api/promotions/active",
        "/api/leads/contact",
        "/api/leads/contact/status",
        "/api/leads/contact/consent",
        "/api/crm/status",
        "/api/crm/leads",
        "/api/crm/reminders/due",
        "/api/crm/leads/follow-up",
    }
    missing_routes = expected_routes.difference(route_paths)
    assert not missing_routes, f"Missing sales/CRM routes: {sorted(missing_routes)}"

    print("Sales phase-two/three static check passed.")
    print("Approved promotion: " + plan.approved_promotions[0].title)
    print("Lead temperature: " + qualified.lead_temperature)
    print("Contact PII excluded from LLM prompt: yes")
    print("Separate contact and marketing consent: yes")
    print("Three-day local follow-up reminder: yes")
    print("Identity-linked CRM deletion: yes")
    print("FastAPI sales/CRM routes registered: yes")


if __name__ == "__main__":
    main()
