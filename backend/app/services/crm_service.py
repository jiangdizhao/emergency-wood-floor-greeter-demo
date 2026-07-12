from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from typing import Any

from ..models import (
    LeadCaptureRequest,
    LeadConsentUpdateRequest,
    LeadFollowUpUpdateRequest,
)
from .crm_identity_bridge import CRMIdentityBridge
from .crm_repository import CRMRepository
from .lead_service import LeadService


class CRMService:
    ALLOWED_CHANNELS = {"phone", "wechat", "email"}
    ALLOWED_STATUSES = {
        "待发送方案",
        "已发送方案",
        "待报价",
        "待回访",
        "客户考虑中",
        "已预约到店",
        "已完成",
        "已关闭",
    }

    def __init__(self, *, repository: CRMRepository, lead_service: LeadService) -> None:
        self.repository = repository
        self.lead_service = lead_service
        self.identity_bridge = CRMIdentityBridge(repository)

    def capture(self, request: LeadCaptureRequest) -> dict[str, Any]:
        if not request.contact_opt_in:
            raise ValueError("请先同意针对本次方案进行联系。")

        channel = request.contact_channel.strip().lower()
        if channel not in self.ALLOWED_CHANNELS:
            raise ValueError("联系方式类型必须是手机、微信或邮箱。")
        contact_value = self._validate_contact(channel, request.contact_value)

        profile = self.lead_service.load_profile(session_id=request.session_id)
        purposes = self._clean_purposes(request.contact_purposes)
        lead = self.repository.upsert_lead(
            session_id=request.session_id,
            customer_id=profile.customer_id,
            display_name=request.display_name,
            contact_channel=channel,
            contact_value=contact_value,
            contact_opt_in=True,
            marketing_opt_in=request.marketing_opt_in,
            contact_purposes=purposes,
            preferred_contact_time=request.preferred_contact_time,
            lead_temperature=profile.lead_temperature,
            sales_stage=profile.sales_stage,
            promotion_ids=profile.promotion_ids_presented,
            next_follow_up_days=3,
        )

        profile.contact_opt_in = True
        profile.marketing_opt_in = bool(request.marketing_opt_in)
        profile.contact_consent_at = str(lead.get("contact_consent_at") or "") or None
        profile.preferred_contact_channel = channel
        profile.preferred_contact_time = request.preferred_contact_time
        profile.follow_up_status = str(lead.get("follow_up_status") or "待发送方案")
        profile.next_follow_up_at = lead.get("next_follow_up_at")
        profile.sales_stage = "follow_up"
        profile.sales_objective = "按客户授权发送本次方案并在约定时间跟进"
        self.lead_service.save_profile(profile)

        return {
            "ok": True,
            "message": (
                "已在本机保存联系方式和本次方案联系授权。"
                + ("您同时同意接收新品和优惠信息。" if request.marketing_opt_in else "未开启后续营销信息推送。")
            ),
            "lead": self._customer_view(lead),
            "customer_profile": profile.model_dump(),
        }

    def status(self, session_id: str) -> dict[str, Any]:
        lead = self.repository.get_by_session(session_id, include_inactive=True)
        if lead is None:
            return {
                "ok": True,
                "exists": False,
                "session_id": session_id,
                "contact_opt_in": False,
                "marketing_opt_in": False,
            }
        return {"ok": True, "exists": True, "lead": self._customer_view(lead)}

    def update_consents(self, request: LeadConsentUpdateRequest) -> dict[str, Any]:
        lead = self.repository.update_consents(
            session_id=request.session_id,
            contact_opt_in=request.contact_opt_in,
            marketing_opt_in=request.marketing_opt_in,
        )
        if lead is None:
            raise ValueError("当前会话没有可更新的联系方式授权记录。")

        profile = self.lead_service.load_profile(session_id=request.session_id)
        profile.contact_opt_in = bool(request.contact_opt_in)
        profile.marketing_opt_in = bool(request.marketing_opt_in and request.contact_opt_in)
        profile.follow_up_status = str(lead.get("follow_up_status") or "已撤回")
        if not request.contact_opt_in:
            profile.next_follow_up_at = None
            profile.sales_stage = "follow_up"
            profile.sales_objective = "尊重客户撤回授权，不再主动联系"
        self.lead_service.save_profile(profile)

        return {
            "ok": True,
            "message": (
                "联系方式及全部主动联系授权已撤回。"
                if not request.contact_opt_in
                else "联系方式授权偏好已更新。"
            ),
            "lead": self._customer_view(lead),
            "customer_profile": profile.model_dump(),
        }

    def delete_contact(self, session_id: str) -> dict[str, Any]:
        deleted = self.repository.delete_by_session(session_id)
        profile = self.lead_service.load_profile(session_id=session_id)
        profile.contact_opt_in = False
        profile.marketing_opt_in = False
        profile.contact_consent_at = None
        profile.preferred_contact_channel = None
        profile.preferred_contact_time = None
        profile.next_follow_up_at = None
        profile.follow_up_status = "未建档"
        self.lead_service.save_profile(profile)
        return {
            "ok": deleted,
            "deleted": deleted,
            "message": "已永久删除当前会话关联的联系方式和跟进记录。" if deleted else "当前会话没有联系方式记录。",
        }

    def workbench(self, *, status: str | None, include_contact: bool, limit: int) -> dict[str, Any]:
        leads = self.repository.list_leads(status=status, active_only=True, limit=limit)
        return {
            "ok": True,
            "count": len(leads),
            "include_contact": include_contact,
            "leads": [self._staff_view(lead, include_contact=include_contact) for lead in leads],
        }

    def due_reminders(self, *, include_contact: bool, limit: int) -> dict[str, Any]:
        leads = self.repository.due_follow_ups(limit=limit)
        return {
            "ok": True,
            "count": len(leads),
            "leads": [self._staff_view(lead, include_contact=include_contact) for lead in leads],
        }

    def update_follow_up(self, request: LeadFollowUpUpdateRequest) -> dict[str, Any]:
        if request.status not in self.ALLOWED_STATUSES:
            raise ValueError("不支持的跟进状态。")
        if request.next_follow_up_at:
            try:
                datetime.fromisoformat(request.next_follow_up_at.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("next_follow_up_at 必须是 ISO 8601 时间。") from exc
        lead = self.repository.update_follow_up(
            lead_id=request.lead_id,
            status=request.status,
            note=request.note,
            next_follow_up_at=request.next_follow_up_at,
        )
        if lead is None:
            raise ValueError("找不到该有效销售线索。")
        return {"ok": True, "lead": self._staff_view(lead, include_contact=True)}

    def delete_for_identity(self, *, session_id: str, customer_id: str | None) -> int:
        # Delete the current session lead first. For a confirmed customer, also
        # delete CRM rows attached through any historical conversation session,
        # including leads captured before optional face enrollment.
        deleted = 1 if self.repository.delete_by_session(session_id) else 0
        if customer_id:
            deleted += self.identity_bridge.delete_customer_records(customer_id=customer_id)
        return deleted

    @staticmethod
    def _validate_contact(channel: str, raw_value: str) -> str:
        value = raw_value.strip()
        if not value:
            raise ValueError("请填写联系方式。")
        if len(value) > 120:
            raise ValueError("联系方式过长。")
        if channel == "email":
            if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
                raise ValueError("邮箱格式不正确。")
            return value.lower()
        if channel == "phone":
            normalized = re.sub(r"[\s()\-]", "", value)
            if not re.fullmatch(r"\+?\d{7,18}", normalized):
                raise ValueError("手机号格式不正确。")
            return normalized
        if not re.fullmatch(r"[A-Za-z0-9_\-\.\u4e00-\u9fff]{2,60}", value):
            raise ValueError("微信号格式不正确。")
        return value

    @staticmethod
    def _clean_purposes(values: list[str]) -> list[str]:
        allowed = {
            "发送本次选购方案",
            "跟进报价与样板",
            "预约到店或测量",
            "发送新品和优惠信息",
        }
        output = [value for value in values if value in allowed]
        if "发送本次选购方案" not in output:
            output.insert(0, "发送本次选购方案")
        return output

    def _customer_view(self, lead: dict[str, Any]) -> dict[str, Any]:
        return {
            "lead_id": lead.get("lead_id"),
            "session_id": lead.get("session_id"),
            "display_name": lead.get("display_name"),
            "contact_channel": lead.get("contact_channel"),
            "contact_masked": self.repository.masked_contact(lead),
            "contact_opt_in": bool(lead.get("contact_opt_in")),
            "marketing_opt_in": bool(lead.get("marketing_opt_in")),
            "contact_purposes": list(lead.get("contact_purposes") or []),
            "preferred_contact_time": lead.get("preferred_contact_time"),
            "follow_up_status": lead.get("follow_up_status"),
            "next_follow_up_at": lead.get("next_follow_up_at"),
            "active": bool(lead.get("active")),
            "revoked_at": lead.get("revoked_at"),
        }

    def _staff_view(self, lead: dict[str, Any], *, include_contact: bool) -> dict[str, Any]:
        output = dict(lead)
        output["contact_masked"] = self.repository.masked_contact(lead)
        output.update(self._session_sales_context(str(lead.get("session_id") or "")))
        if not include_contact:
            output.pop("contact_value", None)
        return output

    def _session_sales_context(self, session_id: str) -> dict[str, Any]:
        if not session_id:
            return {}
        try:
            with self.repository._connect() as connection:
                row = connection.execute(
                    """
                    SELECT summary, profile_json, returning_context
                    FROM conversation_sessions
                    WHERE session_id = ?
                    """,
                    (session_id,),
                ).fetchone()
        except sqlite3.Error:
            return {}
        if row is None:
            return {}

        try:
            profile = json.loads(row["profile_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            profile = {}
        if not isinstance(profile, dict):
            profile = {}

        return {
            "conversation_summary": str(
                row["summary"]
                or profile.get("conversation_summary")
                or row["returning_context"]
                or ""
            ),
            "primary_purchase_driver": profile.get("primary_purchase_driver"),
            "project_type": profile.get("project_type"),
            "room_type": profile.get("room_type"),
            "budget": profile.get("budget"),
            "style": profile.get("style"),
            "estimated_area_sqm": profile.get("estimated_area_sqm"),
            "purchase_timeline": profile.get("purchase_timeline"),
            "decision_stage": profile.get("decision_stage"),
            "recommended_product_ids": list(profile.get("recommended_product_ids") or []),
            "objections": list(profile.get("objections") or []),
        }
