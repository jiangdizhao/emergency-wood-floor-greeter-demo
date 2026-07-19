from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .interaction_api import router as interaction_router
from .models import (
    LeadCaptureRequest,
    LeadConsentUpdateRequest,
    LeadDeleteRequest,
    LeadFollowUpUpdateRequest,
)
from .realtime_api import router as realtime_router
from .services.crm_repository import CRMRepository
from .services.crm_service import CRMService
from .services.lead_service import LeadService
from .services.promotion_service import PromotionService
from .services.sales_knowledge_service import SalesKnowledgeService

router = APIRouter(tags=["sales-and-crm"])
router.include_router(realtime_router)
router.include_router(interaction_router)

sales_lead_service = LeadService()
crm_repository = CRMRepository()
crm_service = CRMService(repository=crm_repository, lead_service=sales_lead_service)
promotion_service = PromotionService()
sales_knowledge_service = SalesKnowledgeService()


@router.get("/api/sales/catalog")
def sales_catalog() -> dict:
    """Approved company, collection and simulated promotion data for the UI."""
    return {
        "ok": True,
        "company": sales_knowledge_service.customer_catalog(),
        "promotions": promotion_service.customer_catalog(),
        "data_mode": "simulated_demo_data",
    }


@router.get("/api/promotions/active")
def active_promotions() -> dict:
    catalog = promotion_service.customer_catalog()
    return {"ok": True, **catalog}


@router.post("/api/leads/contact")
def capture_contact(request: LeadCaptureRequest) -> dict:
    try:
        return crm_service.capture(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/leads/contact/status")
def contact_status(session_id: str) -> dict:
    return crm_service.status(session_id)


@router.patch("/api/leads/contact/consent")
def update_contact_consent(request: LeadConsentUpdateRequest) -> dict:
    try:
        return crm_service.update_consents(request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/api/leads/contact")
def delete_contact(request: LeadDeleteRequest) -> dict:
    return crm_service.delete_contact(request.session_id)


@router.get("/api/crm/status")
def crm_status() -> dict:
    return {
        "ok": True,
        "active_lead_count": crm_repository.count_active(),
        "due_follow_up_count": len(crm_repository.due_follow_ups(limit=500)),
        "database": "local_sqlite",
        "contact_values_sent_to_llm": False,
        "production_auth_enabled": False,
    }


@router.get("/api/crm/leads")
def list_crm_leads(
    status: str | None = None,
    include_contact: bool = False,
    limit: int = 100,
) -> dict:
    return crm_service.workbench(
        status=status,
        include_contact=include_contact,
        limit=limit,
    )


@router.get("/api/crm/reminders/due")
def due_crm_reminders(include_contact: bool = False, limit: int = 100) -> dict:
    return crm_service.due_reminders(include_contact=include_contact, limit=limit)


@router.post("/api/crm/leads/follow-up")
def update_crm_follow_up(request: LeadFollowUpUpdateRequest) -> dict:
    try:
        return crm_service.update_follow_up(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
