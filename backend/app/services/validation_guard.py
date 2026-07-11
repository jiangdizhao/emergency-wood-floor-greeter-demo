from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from ..llm.schemas import SemanticAction, SemanticTurn, ValidatedAction, ValidationResult
from .product_service import ProductService

ROOM_VALUES = {"客厅", "卧室", "全屋", "厨房", "书房", "儿童房", "老人房"}
BUDGET_VALUES = {"经济", "中等", "偏高", "高端"}
BOOLEAN_FIELDS = {
    "has_pets",
    "has_floor_heating",
    "has_children",
    "has_elderly",
    "humid_environment",
}
FIELD_NAMES = {
    "room_type",
    "style",
    "budget",
    *BOOLEAN_FIELDS,
}
PRIORITIES = {"防水", "耐磨", "环保", "价格", "脚感", "好清洁"}
SELF_MARKERS = ("我", "我们", "我家", "我们家", "家里", "家中", "自己家", "我的")
NEGATIVE_MARKERS = ("没有", "没", "不", "无", "未", "不是", "别", "不要")

ROOM_PATTERNS = {
    "客厅": ("客厅",),
    "卧室": ("卧室", "主卧", "次卧"),
    "全屋": ("全屋", "整个家", "整屋"),
    "厨房": ("厨房",),
    "书房": ("书房", "家庭办公室"),
    "儿童房": ("儿童房", "孩子房", "小孩房"),
    "老人房": ("老人房", "父母房", "长辈房"),
}
BUDGET_PATTERNS = {
    "经济": ("经济", "预算有限", "便宜", "性价比", "价位低"),
    "中等": ("中等", "适中", "普通预算", "不要太贵"),
    "偏高": ("偏高", "高一点", "往上提一档", "预算可以高", "品质优先"),
    "高端": ("高端", "不差钱", "顶配", "豪华"),
}
BOOLEAN_CLAIMS = {
    "has_pets": {
        "yes": ("有宠物", "养猫", "养狗", "有猫", "有狗", "两只猫", "两只狗"),
        "no": ("没有宠物", "没养猫", "没养狗", "不养猫", "不养狗", "无宠物"),
    },
    "has_floor_heating": {
        "yes": ("有地暖", "装了地暖", "用地暖", "地热"),
        "no": ("没有地暖", "没装地暖", "不装地暖", "无地暖"),
    },
    "has_children": {
        "yes": ("有孩子", "有小孩", "有儿童", "有宝宝", "两个小孩"),
        "no": ("没有孩子", "没有小孩", "没孩子", "没小孩", "无儿童"),
    },
    "has_elderly": {
        "yes": ("有老人", "有长辈", "父母同住", "老人住"),
        "no": ("没有老人", "没老人", "无老人", "父母不住"),
    },
    "humid_environment": {
        "yes": ("潮湿", "回南天", "湿气重", "南方梅雨"),
        "no": ("不潮湿", "没有回南天", "环境干燥"),
    },
}
PRIORITY_ALIASES = {
    "防水": ("防水", "怕水", "泡水"),
    "耐磨": ("耐磨", "耐刮", "划痕", "磨损"),
    "环保": ("环保", "甲醛", "气味"),
    "价格": ("价格", "价钱", "预算", "性价比"),
    "脚感": ("脚感", "舒服", "舒适", "质感"),
    "好清洁": ("好清洁", "好打理", "容易清洁", "维护简单"),
}
COLOR_TOKENS = ("浅灰", "深灰", "灰色", "原木色", "奶油白", "白色", "深胡桃", "胡桃色", "浅橡木")
STYLE_PATTERNS = {
    "现代简约": ("现代简约",),
    "北欧": ("北欧", "北欧风"),
    "新中式": ("新中式",),
    "轻奢": ("轻奢",),
    "日式": ("日式", "日系"),
    "原木": ("原木风", "自然木纹"),
    "自然风": ("自然风",),
    "灰调": ("灰调",),
}


@dataclass(frozen=True)
class Claim:
    kind: str
    name: str
    value: str

    def key(self) -> str:
        return f"{self.kind}:{self.name}={self.value}"


class ValidationGuard:
    def __init__(self, product_service: ProductService) -> None:
        self.product_service = product_service

    @staticmethod
    def normalize_text(text: str) -> str:
        # Character-spaced ASR text such as “S P C” and “我 家” becomes usable,
        # while punctuation remains available to the model and evidence checker.
        return re.sub(r"\s+", "", text or "").strip()

    def validate(self, *, user_text: str, semantic_turn: SemanticTurn) -> ValidationResult:
        normalized_text = self.normalize_text(user_text)
        backend_self_context = self._backend_self_context(normalized_text, semantic_turn)
        target_scope = (
            "turn_only"
            if semantic_turn.intent in {"request_recommendation", "request_comparison"}
            and not backend_self_context
            else "persistent"
        )

        accepted: list[ValidatedAction] = []
        rejected: list[str] = []
        warnings: list[str] = []
        seen_updates: dict[tuple[str, str], str] = {}

        for action in semantic_turn.actions:
            validated, reason = self._validate_action(
                text=normalized_text,
                action=action,
                scope=target_scope,
            )
            if validated is None:
                rejected.append(reason)
                continue
            conflict_key = (validated.kind, validated.name)
            previous_value = seen_updates.get(conflict_key)
            if previous_value is not None and previous_value != validated.value:
                rejected.append(f"conflicting action for {validated.kind}:{validated.name}")
                continue
            seen_updates[conflict_key] = validated.value
            accepted.append(validated)

        provider_product_mentions = [
            value
            for value in semantic_turn.mentioned_products
            if self.normalize_text(value).lower() in normalized_text.lower()
        ]
        mentioned_products = self._canonical_product_mentions(
            [*provider_product_mentions, *self._detect_product_mentions(normalized_text)]
        )
        mentioned_product_ids = [
            product.id for product in self.product_service.resolve_product_references(mentioned_products)
        ]
        provider_color_mentions = [
            value
            for value in semantic_turn.mentioned_colors
            if self.normalize_text(value) in normalized_text
        ]
        mentioned_colors = self._unique(
            [*provider_color_mentions, *self._detect_color_mentions(normalized_text)]
        )

        expected_claims = self._detect_claims(normalized_text)
        actual_claims = self._claims_from_actions(accepted)
        missing_claims = sorted(claim.key() for claim in expected_claims if claim not in actual_claims)

        expected_recommendation = semantic_turn.intent in {"request_recommendation", "request_comparison"}
        if semantic_turn.recommendation_requested != expected_recommendation:
            warnings.append("recommendation_requested did not match intent and was normalized by backend")

        semantic_turn = semantic_turn.model_copy(
            update={
                "recommendation_requested": expected_recommendation,
                "mentioned_products": mentioned_products,
                "mentioned_colors": mentioned_colors,
            }
        )

        if semantic_turn.intent == "request_comparison" and len(mentioned_product_ids) < 2:
            missing_claims.append("comparison requires two resolvable products")
        if semantic_turn.intent == "reject_product" and not any(a.kind == "reject_product" for a in accepted):
            missing_claims.append("reject_product intent requires a validated reject_product action")
        if semantic_turn.intent == "reject_color" and not any(a.kind == "reject_color" for a in accepted):
            missing_claims.append("reject_color intent requires a validated reject_color action")

        if semantic_turn.uncertain:
            warnings.append("provider marked the parse as uncertain")
        if semantic_turn.confidence < 0.80:
            warnings.append(f"provider confidence too low: {semantic_turn.confidence:.2f}")

        ok = not rejected and not missing_claims and not semantic_turn.uncertain and semantic_turn.confidence >= 0.80
        clarification = None if ok else self._clarification_question(missing_claims, rejected)

        return ValidationResult(
            ok=ok,
            normalized_text=normalized_text,
            semantic_turn=semantic_turn,
            backend_self_context=backend_self_context,
            actions=accepted if ok else [],
            mentioned_product_ids=self._unique(mentioned_product_ids),
            mentioned_colors=mentioned_colors,
            missing_claims=missing_claims,
            rejected_actions=rejected,
            warnings=warnings,
            clarification_question=clarification,
        )

    def _validate_action(
        self,
        *,
        text: str,
        action: SemanticAction,
        scope: str,
    ) -> tuple[ValidatedAction | None, str]:
        evidence = self.normalize_text(action.evidence)
        if not evidence or evidence not in text:
            return None, f"evidence is not verbatim for {action.kind}:{action.name}"

        name = self.normalize_text(action.name)
        value = self.normalize_text(action.value)
        product_ids: list[str] = []

        if action.kind == "set_field":
            if name not in FIELD_NAMES:
                return None, f"unknown field: {name}"
            value = self._canonical_field_value(name, value)
            if name == "room_type" and value not in ROOM_VALUES:
                return None, f"invalid room value: {value}"
            if name == "budget" and value not in BUDGET_VALUES:
                return None, f"invalid budget value: {value}"
            if name in BOOLEAN_FIELDS:
                if value not in {"yes", "no"}:
                    return None, f"invalid boolean value for {name}: {value}"
                evidence_has_negative = any(marker in evidence for marker in NEGATIVE_MARKERS)
                if value == "no" and not evidence_has_negative:
                    return None, f"negative value lacks negative evidence for {name}"
                if value == "yes" and evidence_has_negative:
                    return None, f"positive value conflicts with negative evidence for {name}"
            if name == "style" and not value:
                return None, "style cannot be empty"

        elif action.kind == "set_priority":
            if name not in PRIORITIES:
                return None, f"unknown priority: {name}"
            if value not in {"high", "medium", "low", "remove"}:
                return None, f"invalid priority level for {name}: {value}"

        elif action.kind in {"prefer_color", "reject_color"}:
            if not name:
                return None, "color cannot be empty"
            value = "prefer" if action.kind == "prefer_color" else "reject"

        elif action.kind in {"prefer_product", "reject_product"}:
            products = self.product_service.resolve_product_reference(name)
            if not products:
                return None, f"unresolvable product reference: {name}"
            product_ids = [product.id for product in products]
            value = "prefer" if action.kind == "prefer_product" else "reject"
        else:
            return None, f"unsupported action kind: {action.kind}"

        return (
            ValidatedAction(
                kind=action.kind,
                name=name,
                value=value,
                evidence=evidence,
                scope=scope,
                product_ids=product_ids,
            ),
            "",
        )

    def _detect_claims(self, text: str) -> set[Claim]:
        claims: set[Claim] = set()
        for room, patterns in ROOM_PATTERNS.items():
            if any(pattern in text for pattern in patterns):
                claims.add(Claim("field", "room_type", room))
                break
        for budget, patterns in BUDGET_PATTERNS.items():
            if any(pattern in text for pattern in patterns):
                claims.add(Claim("field", "budget", budget))
                break
        for style, patterns in STYLE_PATTERNS.items():
            if any(pattern in text for pattern in patterns):
                claims.add(Claim("field", "style", style))
                break
        for field_name, value_patterns in BOOLEAN_CLAIMS.items():
            negative_patterns = value_patterns["no"]
            positive_patterns = value_patterns["yes"]
            if any(pattern in text for pattern in negative_patterns):
                claims.add(Claim("field", field_name, "no"))
            elif any(pattern in text for pattern in positive_patterns):
                claims.add(Claim("field", field_name, "yes"))
        for priority, patterns in PRIORITY_ALIASES.items():
            if not any(pattern in text for pattern in patterns):
                continue
            if priority == "价格" and not any(
                phrase in text
                for phrase in (
                    "价格最重要", "价格优先", "重点看价格", "更在意价格", "性价比最重要",
                    "价格不重要", "不用考虑价格", "去掉价格", "不需要考虑价格",
                )
            ):
                continue
            if any(marker in text for marker in ("不重要", "不用考虑", "去掉", "不需要", "取消")):
                level = "remove"
            elif any(marker in text for marker in ("最重要", "第一", "优先", "重点", "更在意", "必须")):
                level = "high"
            elif any(marker in text for marker in ("希望", "关注", "在意", "需要", "想要")):
                level = "medium"
            else:
                continue
            claims.add(Claim("priority", priority, level))
        return claims

    @staticmethod
    def _claims_from_actions(actions: Iterable[ValidatedAction]) -> set[Claim]:
        claims: set[Claim] = set()
        for action in actions:
            if action.kind == "set_field":
                claims.add(Claim("field", action.name, action.value))
            elif action.kind == "set_priority":
                claims.add(Claim("priority", action.name, action.value))
        return claims

    def _backend_self_context(self, text: str, semantic_turn: SemanticTurn) -> bool:
        if semantic_turn.intent in {"provide_or_modify_needs", "reject_product", "reject_color"}:
            return True
        return semantic_turn.explicit_self_context or any(marker in text for marker in SELF_MARKERS)

    @staticmethod
    def _canonical_field_value(field_name: str, value: str) -> str:
        lower = value.lower()
        if field_name == "budget":
            mapping = {
                "economic": "经济",
                "economy": "经济",
                "low": "经济",
                "medium": "中等",
                "mid": "中等",
                "middle": "中等",
                "medium-high": "偏高",
                "upper-middle": "偏高",
                "high": "高端",
                "premium": "高端",
                "经济档": "经济",
                "中等档": "中等",
                "偏高档": "偏高",
                "高端档": "高端",
            }
            return mapping.get(lower, mapping.get(value, value))
        if field_name in BOOLEAN_FIELDS:
            mapping = {"true": "yes", "false": "no", "有": "yes", "是": "yes", "没有": "no", "无": "no", "否": "no"}
            return mapping.get(lower, mapping.get(value, value))
        if field_name == "style":
            for style, patterns in STYLE_PATTERNS.items():
                if style in value or any(pattern in value for pattern in patterns):
                    return style
        for room in ROOM_VALUES:
            if room in value:
                return room
        return value

    def _detect_product_mentions(self, text: str) -> list[str]:
        upper_text = text.upper()
        found: list[str] = []
        if "SPC" in upper_text or "石塑" in text:
            found.append("SPC")
        if "多层实木" in text or "实木复合" in text:
            found.append("多层实木")
        if "三层实木" in text:
            found.append("三层实木")
        elif "实木" in text and "多层实木" not in text and "实木复合" not in text:
            found.append("实木")
        if "强化" in text:
            found.append("强化")
        for product in self.product_service.list_products():
            if product.id in text or product.name in text:
                found.append(product.id)
        return self._unique(found)

    @staticmethod
    def _detect_color_mentions(text: str) -> list[str]:
        return [token for token in COLOR_TOKENS if token in text]

    @staticmethod
    def _canonical_product_mentions(values: Iterable[str]) -> list[str]:
        aliases = {
            "spc地板": "SPC",
            "spc": "SPC",
            "石塑": "SPC",
            "石塑地板": "SPC",
            "实木复合": "多层实木",
            "实木复合地板": "多层实木",
            "强化复合": "强化",
            "强化复合地板": "强化",
        }
        output: list[str] = []
        for value in values:
            compact = re.sub(r"\s+", "", str(value or "")).strip()
            canonical = aliases.get(compact.lower(), aliases.get(compact, compact))
            if canonical and canonical not in output:
                output.append(canonical)
        return output

    @staticmethod
    def _unique(values: Iterable[str]) -> list[str]:
        output: list[str] = []
        for value in values:
            if value and value not in output:
                output.append(value)
        return output

    @staticmethod
    def _clarification_question(missing_claims: list[str], rejected: list[str]) -> str:
        if missing_claims:
            first = missing_claims[0]
            if "has_floor_heating" in first:
                return "我没有完全确认地暖条件。请问您家是有地暖，还是没有安装地暖？"
            if "has_pets" in first:
                return "我没有完全确认宠物条件。请问您家目前有养猫或养狗吗？"
            if "priority" in first:
                return "我可能漏掉了您最关注的性能。请再确认一下，您最重视防水、耐磨、环保、价格、脚感还是好清洁？"
            if "comparison" in first:
                return "请再告诉我您想比较的两个产品或材质，例如 SPC 和多层实木。"
        if rejected:
            return "我没有完全理解这句话中的修改。请用一句更直接的话确认您要新增、修改或取消的条件。"
        return "我没有完全理解您的需求。请再说一次房间、预算和最重要的使用条件。"
