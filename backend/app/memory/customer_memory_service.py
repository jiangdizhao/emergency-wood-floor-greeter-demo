from __future__ import annotations

import uuid
from typing import Any

from ..identity.identity_service import IdentityService
from ..identity.repository import IdentityRepository
from ..models import CustomerProfile, DialogueProvider, IdentityChoice, IdentitySessionResponse
from ..services.dialogue_context_service import DialogueContextService
from ..services.lead_service import LeadService
from ..services.sales_knowledge_service import SalesKnowledgeService
from ..services.session_runtime_service import SessionRuntimeService


class CustomerMemoryService:
    """Binds confirmed face candidates to new conversation sessions.

    Identity and conversation session are deliberately separate. Every visit gets
    a fresh session_id, even when a returning customer continues a previous project.
    Contact and marketing consent are also session-scoped and are never silently
    copied into a newly created visit.
    """

    def __init__(
        self,
        *,
        repository: IdentityRepository,
        identity_service: IdentityService,
        lead_service: LeadService,
        runtime_service: SessionRuntimeService,
        context_service: DialogueContextService,
    ) -> None:
        self.repository = repository
        self.identity_service = identity_service
        self.lead_service = lead_service
        self.runtime_service = runtime_service
        self.context_service = context_service
        self.sales_knowledge_service = SalesKnowledgeService()

    def new_anonymous_session(
        self,
        *,
        provider_mode: DialogueProvider | None = None,
    ) -> IdentitySessionResponse:
        session_id = self._new_session_id()
        provider = self._provider(provider_mode)
        profile = CustomerProfile(session_id=session_id)
        self.lead_service.save_profile(profile)
        self._set_opening_question_context(session_id)
        self.runtime_service.set_provider(session_id, provider)
        self.repository.create_or_update_session(
            session_id=session_id,
            customer_id=None,
            provider_mode=provider,
            profile=profile.model_dump(),
        )
        return IdentitySessionResponse(
            session_id=session_id,
            customer_profile=profile,
            returning_customer=False,
            greeting=self.sales_knowledge_service.new_customer_greeting(),
            provider_mode=provider,
            provider_label=self.runtime_service.provider_label(provider),
            memory_loaded=False,
        )

    def confirm_candidate(
        self,
        *,
        candidate_token: str,
        choice: IdentityChoice,
        provider_mode: DialogueProvider | None = None,
    ) -> IdentitySessionResponse:
        # Read first and consume only after the new session is fully prepared. The
        # previous implementation popped the token before file/database work, so a
        # transient error left the confirmation dialog permanently unrecoverable.
        candidate = self.identity_service.get_candidate(candidate_token)
        if candidate is None:
            raise ValueError("Identity candidate is missing or expired. Please recognize again.")

        if choice == "not_me":
            response = self.new_anonymous_session(provider_mode=provider_mode)
            self.identity_service.finalize_candidate(candidate_token, accepted=False)
            return response

        customer = self.repository.get_customer(candidate.customer_id)
        if customer is None:
            raise ValueError("The matched customer record no longer exists.")

        provider = self._provider(provider_mode)
        session_id = self._new_session_id()
        latest_data = self.repository.latest_customer_profile(candidate.customer_id) or {}
        recent_memories = self.repository.recent_session_memories(candidate.customer_id, limit=3)
        previous_summaries = [
            str(item.get("summary") or item.get("profile", {}).get("conversation_summary") or "").strip()
            for item in recent_memories
        ]
        previous_summaries = [summary for summary in previous_summaries if summary]

        if choice == "continue_previous":
            profile = self._continued_profile(
                latest_data=latest_data,
                session_id=session_id,
                customer_id=candidate.customer_id,
                customer=customer,
                previous_summaries=previous_summaries,
            )
            greeting = self._continued_greeting(profile)
            returning_context = profile.memory_summary
            self.context_service.reset(session_id)
        else:
            profile = self._new_project_profile(
                latest_data=latest_data,
                session_id=session_id,
                customer_id=candidate.customer_id,
                customer=customer,
                previous_summaries=previous_summaries,
            )
            greeting = self._new_project_greeting(profile)
            returning_context = profile.memory_summary
            self._set_opening_question_context(session_id)

        self.lead_service.save_profile(profile)
        self.runtime_service.set_provider(session_id, provider)
        self.repository.create_or_update_session(
            session_id=session_id,
            customer_id=candidate.customer_id,
            provider_mode=provider,
            profile=profile.model_dump(),
            returning_context=returning_context,
        )
        self.repository.mark_seen(candidate.customer_id)
        self.identity_service.finalize_candidate(candidate_token, accepted=True)
        return IdentitySessionResponse(
            session_id=session_id,
            customer_profile=profile,
            returning_customer=True,
            greeting=greeting,
            provider_mode=provider,
            provider_label=self.runtime_service.provider_label(provider),
            memory_loaded=True,
        )

    def bind_enrollment(
        self,
        *,
        session_id: str,
        customer_id: str,
        display_name: str | None,
    ) -> CustomerProfile:
        profile = self.lead_service.load_profile(session_id=session_id)
        profile.customer_id = customer_id
        profile.customer_name = display_name or profile.customer_name
        profile.is_returning_customer = False
        profile.memory_summary = profile.conversation_summary or self._profile_memory_sentence(profile)
        saved = self.lead_service.save_profile(profile)
        provider = self.runtime_service.load(session_id).provider_mode
        self.repository.create_or_update_session(
            session_id=session_id,
            customer_id=customer_id,
            provider_mode=provider,
            profile=saved.model_dump(),
            summary=saved.conversation_summary,
            returning_context=saved.memory_summary,
        )
        return saved

    def record_turn(
        self,
        *,
        session_id: str,
        user_text: str,
        assistant_text: str,
        profile: CustomerProfile,
    ) -> None:
        provider = self.runtime_service.load(session_id).provider_mode
        self.repository.create_or_update_session(
            session_id=session_id,
            customer_id=profile.customer_id,
            provider_mode=provider,
            profile=profile.model_dump(),
            summary=profile.conversation_summary,
            returning_context=profile.memory_summary,
        )
        if user_text.strip():
            self.repository.append_turn(session_id=session_id, role="customer", text=user_text)
        if assistant_text.strip():
            self.repository.append_turn(session_id=session_id, role="assistant", text=assistant_text)

    def finish_session(self, profile: CustomerProfile) -> None:
        self.repository.finish_session(
            session_id=profile.session_id,
            summary=profile.conversation_summary,
            profile=profile.model_dump(),
        )

    def delete_current_customer(self, *, session_id: str, delete_history: bool) -> bool:
        profile = self.lead_service.load_profile(session_id=session_id)
        customer_id = profile.customer_id or self.repository.get_session_customer_id(session_id)
        if not customer_id:
            return False
        deleted = self.repository.delete_customer(customer_id, delete_history=delete_history)
        if deleted:
            profile.customer_id = None
            profile.is_returning_customer = False
            profile.memory_summary = ""
            profile.previous_visit_summaries = []
            self.lead_service.save_profile(profile)
        return deleted

    def _set_opening_question_context(self, session_id: str) -> None:
        context = self.context_service.reset(session_id)
        self.context_service.save(
            context.model_copy(
                update={
                    "pending_slot": "priority",
                    "last_assistant_question": (
                        "这次选地板，您最不愿意妥协的是哪一点："
                        "预算、耐磨、防水、脚感、环保，还是日常好清洁？"
                    ),
                }
            )
        )

    def _provider(self, requested: DialogueProvider | None) -> DialogueProvider:
        if requested is not None:
            return requested
        return self.runtime_service._default_provider()

    @staticmethod
    def _new_session_id() -> str:
        return f"session-{uuid.uuid4().hex}"

    def _continued_profile(
        self,
        *,
        latest_data: dict[str, Any],
        session_id: str,
        customer_id: str,
        customer: dict[str, Any],
        previous_summaries: list[str],
    ) -> CustomerProfile:
        data = dict(latest_data)
        data.update(
            {
                "session_id": session_id,
                "customer_id": customer_id,
                "is_returning_customer": True,
                "customer_name": customer.get("display_name") or data.get("customer_name"),
                "previous_visit_summaries": previous_summaries,
                "last_seen_at": customer.get("last_seen_at"),
            }
        )
        profile = CustomerProfile.model_validate(data)
        self._reset_session_scoped_contact_state(profile)
        profile.memory_summary = self._build_memory_summary(profile, previous_summaries)
        return profile

    def _new_project_profile(
        self,
        *,
        latest_data: dict[str, Any],
        session_id: str,
        customer_id: str,
        customer: dict[str, Any],
        previous_summaries: list[str],
    ) -> CustomerProfile:
        previous = CustomerProfile.model_validate(
            {**latest_data, "session_id": str(latest_data.get("session_id") or "previous-session")}
        )
        profile = CustomerProfile(
            session_id=session_id,
            customer_id=customer_id,
            is_returning_customer=True,
            customer_name=customer.get("display_name") or previous.customer_name,
            has_pets=previous.has_pets,
            has_floor_heating=previous.has_floor_heating,
            has_children=previous.has_children,
            has_elderly=previous.has_elderly,
            humid_environment=previous.humid_environment,
            special_needs=list(previous.special_needs),
            previous_visit_summaries=previous_summaries,
            last_seen_at=customer.get("last_seen_at"),
        )
        self._reset_session_scoped_contact_state(profile)
        stable_bits = []
        for label, value in [
            ("家里有宠物", profile.has_pets),
            ("家里有地暖", profile.has_floor_heating),
            ("家里有孩子", profile.has_children),
            ("家里有老人", profile.has_elderly),
            ("居住环境较潮湿", profile.humid_environment),
        ]:
            if value is True:
                stable_bits.append(label)
        profile.memory_summary = (
            "这是回访客户的新项目。可沿用的稳定家庭背景："
            + ("、".join(stable_bits) if stable_bits else "暂无明确稳定条件")
            + "。不要自动沿用上次项目的房间、预算、风格、面积、时间、颜色、推荐结果或联系授权。"
        )
        return profile

    @staticmethod
    def _reset_session_scoped_contact_state(profile: CustomerProfile) -> None:
        # A prior visit's contact/marketing consent belongs to that CRM record. A
        # fresh visit must never imply a new outreach authorization automatically.
        profile.phone = None
        profile.contact_prompt_eligible = bool(profile.recommended_product_ids)
        profile.contact_opt_in = False
        profile.marketing_opt_in = False
        profile.contact_consent_at = None
        profile.preferred_contact_channel = None
        profile.preferred_contact_time = None
        profile.next_follow_up_at = None
        profile.follow_up_status = "未建档"

    def _build_memory_summary(self, profile: CustomerProfile, previous_summaries: list[str]) -> str:
        core = self._profile_memory_sentence(profile)
        recent = "；".join(previous_summaries[:2])
        if recent:
            return f"已确认的回访客户。上次结构化需求：{core}。最近咨询摘要：{recent}"
        return f"已确认的回访客户。上次结构化需求：{core}。"

    @staticmethod
    def _profile_memory_sentence(profile: CustomerProfile) -> str:
        parts: list[str] = []
        if profile.primary_purchase_driver:
            parts.append(f"首要需求={profile.primary_purchase_driver}")
        if profile.project_type:
            parts.append(f"项目类型={profile.project_type}")
        if profile.room_type:
            parts.append(f"空间={profile.room_type}")
        if profile.estimated_area_sqm is not None:
            parts.append(f"面积={profile.estimated_area_sqm:g}㎡")
        if profile.purchase_timeline:
            parts.append(f"铺装时间={profile.purchase_timeline}")
        if profile.decision_stage:
            parts.append(f"决策阶段={profile.decision_stage}")
        if profile.style:
            parts.append(f"风格={profile.style}")
        if profile.budget:
            parts.append(f"预算={profile.budget}")
        if profile.preferred_colors:
            parts.append("偏好颜色=" + "、".join(profile.preferred_colors))
        if profile.recommended_product_ids:
            parts.append("上次推荐=" + "、".join(profile.recommended_product_ids))
        if profile.objections:
            parts.append("上次顾虑=" + "、".join(profile.objections))
        if profile.has_pets is True:
            parts.append("有宠物")
        if profile.has_floor_heating is True:
            parts.append("有地暖")
        if profile.has_children is True:
            parts.append("有儿童")
        if profile.has_elderly is True:
            parts.append("有老人")
        return "；".join(parts) if parts else "历史需求尚不完整"

    @staticmethod
    def _continued_greeting(profile: CustomerProfile) -> str:
        summary = profile.conversation_summary or profile.memory_summary
        if summary:
            return (
                "欢迎回来。您已确认继续上次的选购记录。"
                f"我记得的重点是：{summary} "
                "这次您想继续看上次的主推方案，还是先告诉我哪一点发生了变化？"
            )
        return "欢迎回来。您已确认继续上次的选购记录。您想先看上次的主推方案，还是调整核心需求？"

    @staticmethod
    def _new_project_greeting(profile: CustomerProfile) -> str:
        stable = []
        if profile.has_pets is True:
            stable.append("宠物家庭")
        if profile.has_floor_heating is True:
            stable.append("有地暖")
        if profile.has_children is True:
            stable.append("有孩子")
        if profile.has_elderly is True:
            stable.append("有老人")
        background = "、".join(stable)
        prefix = (
            f"欢迎回来。这次我们开始一个新的选购项目，我会保留“{background}”这些家庭背景。"
            if background
            else "欢迎回来。这次我们开始一个新的选购项目。"
        )
        return (
            prefix
            + "为了避免沿用上次项目的判断，请先告诉我：这次您最不愿意妥协的是预算、耐磨、防水、脚感、环保，还是日常好清洁？"
        )
