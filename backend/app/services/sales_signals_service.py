from __future__ import annotations

from ..models import CustomerProfile


class SalesSignalsService:
    """Derives sales signals from validated state and customer wording.

    This layer never changes product facts. It only tracks objections, buying stage,
    promotion interest and a coarse lead temperature used to choose the next action.
    """

    OBJECTION_TERMS: dict[str, tuple[str, ...]] = {
        "价格顾虑": ("太贵", "贵了", "价格高", "预算不够", "便宜一点", "超预算"),
        "需要比较": ("再比较", "看看别家", "其他品牌", "再看看", "对比一下"),
        "需要商量": ("和家人商量", "回去商量", "再考虑", "想一想", "不能决定"),
        "防水顾虑": ("真的防水", "会不会进水", "怕水", "防水靠谱吗"),
        "环保顾虑": ("甲醛", "环保吗", "环保认证", "检测报告", "气味"),
        "维护顾虑": ("难打理", "维护麻烦", "容易脏", "不好清洁"),
        "脚感顾虑": ("太硬", "脚感不好", "不舒服", "冰冷"),
        "颜色顾虑": ("颜色不喜欢", "太深", "太浅", "不好搭配"),
    }

    def update(self, *, profile: CustomerProfile, user_text: str, intent: str) -> CustomerProfile:
        updated = profile.model_copy(deep=True)
        normalized = "".join(user_text.lower().split())

        for objection, terms in self.OBJECTION_TERMS.items():
            if any("".join(term.lower().split()) in normalized for term in terms):
                self._append_unique(updated.objections, objection)

        if any(term in normalized for term in ("优惠", "促销", "折扣", "活动", "便宜多少")):
            updated.promotion_interest = True

        if any(term in normalized for term in ("马上装", "尽快", "这个月", "近期就装")):
            updated.purchase_timeline = updated.purchase_timeline or "1个月内"
        elif any(term in normalized for term in ("三个月内", "1到3个月", "一到三个月")):
            updated.purchase_timeline = updated.purchase_timeline or "1-3个月"
        elif any(term in normalized for term in ("半年后", "以后再说", "还没定时间")):
            updated.purchase_timeline = updated.purchase_timeline or "待定"

        if any(term in normalized for term in ("准备买", "准备下单", "可以定", "想订", "报价")):
            updated.decision_stage = "准备购买"
        elif any(term in normalized for term in ("对比", "比较", "看看别家")):
            updated.decision_stage = "正在比较"
        elif updated.decision_stage is None:
            updated.decision_stage = "初步了解"

        updated.lead_temperature = self._lead_temperature(updated, intent=intent)
        updated.contact_prompt_eligible = self._contact_prompt_eligible(updated)
        return updated

    @staticmethod
    def _lead_temperature(profile: CustomerProfile, *, intent: str) -> str:
        score = 0
        score += int(bool(profile.primary_purchase_driver))
        score += int(bool(profile.room_type))
        score += int(bool(profile.budget))
        score += int(bool(profile.style))
        score += int(bool(profile.estimated_area_sqm))
        score += int(bool(profile.purchase_timeline and profile.purchase_timeline != "待定"))
        score += 2 * int(bool(profile.recommended_product_ids))
        score += 2 * int(profile.decision_stage == "准备购买")
        score += int(intent in {"request_recommendation", "request_comparison", "ask_reason"})
        score += int(profile.promotion_interest is True)
        score -= min(2, len(profile.objections))
        if score >= 8:
            return "hot"
        if score >= 4:
            return "warm"
        return "cold"

    @staticmethod
    def _contact_prompt_eligible(profile: CustomerProfile) -> bool:
        if profile.contact_opt_in:
            return False
        return bool(
            profile.recommended_product_ids
            and (
                profile.lead_temperature in {"warm", "hot"}
                or profile.promotion_interest is True
                or profile.decision_stage in {"正在比较", "准备购买"}
            )
        )

    @staticmethod
    def _append_unique(values: list[str], value: str) -> None:
        if value not in values:
            values.append(value)
