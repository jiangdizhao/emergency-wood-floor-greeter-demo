from __future__ import annotations

from ..llm.schemas import ValidationResult
from ..models import CustomerProfile


class CustomerStateService:
    def apply(self, *, profile: CustomerProfile, validation: ValidationResult) -> CustomerProfile:
        # Apply only actions that survived the shared validation guard. A turn
        # may be partially understood: safe actions are retained while the
        # unresolved part is clarified in the next assistant response.
        if not validation.can_apply:
            return profile.model_copy(deep=True)

        updated = profile.model_copy(deep=True)
        for action in validation.actions:
            if action.scope != "persistent":
                continue
            if action.kind == "set_field":
                self._set_field(updated, action.name, action.value)
            elif action.kind == "set_priority":
                if action.value == "remove":
                    updated.priorities.pop(action.name, None)
                else:
                    updated.priorities[action.name] = action.value
            elif action.kind == "prefer_color":
                self._append_unique(updated.preferred_colors, action.name)
                self._remove(updated.rejected_colors, action.name)
            elif action.kind == "reject_color":
                self._append_unique(updated.rejected_colors, action.name)
                self._remove(updated.preferred_colors, action.name)
            elif action.kind == "prefer_product":
                for product_id in action.product_ids:
                    self._append_unique(updated.preferred_product_ids, product_id)
                    self._remove(updated.rejected_product_ids, product_id)
            elif action.kind == "reject_product":
                for product_id in action.product_ids:
                    self._append_unique(updated.rejected_product_ids, product_id)
                    self._remove(updated.preferred_product_ids, product_id)

        self._sync_legacy_fields(updated)
        return updated

    @staticmethod
    def build_summary(profile: CustomerProfile) -> str:
        parts: list[str] = []
        if profile.room_type:
            parts.append(f"使用空间：{profile.room_type}")
        if profile.style:
            parts.append(f"偏好风格：{profile.style}")
        if profile.budget:
            parts.append(f"预算区间：{profile.budget}")
        for label, value in [
            ("宠物", profile.has_pets),
            ("地暖", profile.has_floor_heating),
            ("儿童", profile.has_children),
            ("老人", profile.has_elderly),
            ("潮湿环境", profile.humid_environment),
        ]:
            if value is True:
                parts.append(f"{label}：有")
            elif value is False:
                parts.append(f"{label}：无")
        if profile.priorities:
            parts.append("优先级：" + "、".join(f"{name}={level}" for name, level in profile.priorities.items()))
        if profile.preferred_colors:
            parts.append("偏好颜色：" + "、".join(profile.preferred_colors))
        if profile.rejected_colors:
            parts.append("排除颜色：" + "、".join(profile.rejected_colors))
        return "；".join(parts) if parts else "客户正在了解木地板产品，需求尚未明确。"

    @staticmethod
    def build_follow_up(profile: CustomerProfile) -> str:
        missing: list[str] = []
        if not profile.room_type:
            missing.append("铺装空间")
        if not profile.budget:
            missing.append("预算")
        if not profile.style:
            missing.append("装修风格")
        if missing:
            return "建议销售继续确认" + "、".join(missing) + "，再给出正式报价和安装建议。"
        return "建议销售在 24 小时内发送主推款与备选款对比方案，并确认面积、安装时间和最终预算。"

    @staticmethod
    def _set_field(profile: CustomerProfile, name: str, value: str) -> None:
        if name in {
            "has_pets",
            "has_floor_heating",
            "has_children",
            "has_elderly",
            "humid_environment",
        }:
            setattr(profile, name, value == "yes")
        elif name in {"room_type", "style", "budget"}:
            setattr(profile, name, value)

    @staticmethod
    def _sync_legacy_fields(profile: CustomerProfile) -> None:
        special_map = {
            "宠物": profile.has_pets,
            "地暖": profile.has_floor_heating,
            "儿童": profile.has_children,
            "老人": profile.has_elderly,
            "潮湿环境": profile.humid_environment,
        }
        for label, enabled in special_map.items():
            if enabled is True:
                CustomerStateService._append_unique(profile.special_needs, label)
            elif enabled is False:
                CustomerStateService._remove(profile.special_needs, label)

        for priority in ["防水", "耐磨", "环保", "价格", "脚感", "好清洁"]:
            level = profile.priorities.get(priority)
            if level in {"high", "medium", "low"}:
                CustomerStateService._append_unique(profile.concerns, priority)
            elif level is None:
                CustomerStateService._remove(profile.concerns, priority)

        if profile.priorities.get("好清洁") in {"high", "medium", "low"}:
            CustomerStateService._append_unique(profile.special_needs, "好打理")
        elif "好清洁" not in profile.priorities:
            CustomerStateService._remove(profile.special_needs, "好打理")

    @staticmethod
    def _append_unique(values: list[str], value: str) -> None:
        if value not in values:
            values.append(value)

    @staticmethod
    def _remove(values: list[str], value: str) -> None:
        while value in values:
            values.remove(value)
