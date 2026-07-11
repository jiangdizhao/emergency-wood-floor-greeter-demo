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
FIELD_NAMES = {"room_type", "style", "budget", *BOOLEAN_FIELDS}
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
    "经济": ("经济", "预算有限", "便宜", "性价比", "价位低", "低预算"),
    "中等": ("中等", "中档", "适中", "普通预算", "不要太贵"),
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
COLOR_TOKENS = (
    "浅灰色",
    "浅灰",
    "深灰色",
    "深灰",
    "灰色",
    "原木色",
    "奶油白",
    "白色",
    "深胡桃",
    "胡桃色",
    "浅橡木",
    "深色系",
)
STYLE_PATTERNS = {
    "现代简约": ("现代简约", "现代风", "简约风"),
    "北欧": ("北欧", "北欧风"),
    "新中式": ("新中式",),
    "轻奢": ("轻奢",),
    "日式": ("日式", "日系"),
    "原木": ("原木风", "自然木纹"),
    "自然风": ("自然风",),
    "灰调": ("灰调",),
}
RECOMMENDATION_MARKERS = (
    "推荐",
    "给个方案",
    "给我方案",
    "怎么选",
    "哪个合适",
    "帮我选",
    "直接给个",
    "适合的方案",
)


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
        return re.sub(r"\s+", "", text or "").strip()

    def validate(
        self,
        *,
        user_text: str,
        semantic_turn: SemanticTurn,
        pending_slot: str | None = None,
    ) -> ValidationResult:
        normalized_text = self.normalize_text(user_text)
        semantic_turn = self._normalize_intent_from_text(normalized_text, semantic_turn)
        backend_self_context = self._backend_self_context(normalized_text, semantic_turn, pending_slot)
        target_scope = (
            "turn_only"
            if semantic_turn.intent in {"request_recommendation", "request_comparison"}
            and not backend_self_context
            else "persistent"
        )

        accepted: list[ValidatedAction] = []
        rejected: list[str] = []
        warnings: list[str] = []
        conflicts: list[str] = []
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
                conflicts.append(f"conflicting action for {validated.kind}:{validated.name}")
                accepted = [
                    item
                    for item in accepted
                    if (item.kind, item.name) != conflict_key
                ]
                continue
            seen_updates[conflict_key] = validated.value
            accepted.append(validated)

        recovered = self._recover_pending_slot_action(
            text=normalized_text,
            pending_slot=pending_slot,
            existing=accepted,
        )
        if recovered is not None:
            accepted.append(recovered)
            warnings.append(f"backend recovered short answer for pending slot: {pending_slot}")
            semantic_turn = semantic_turn.model_copy(
                update={
                    "intent": "provide_or_modify_needs",
                    "explicit_self_context": True,
                    "uncertain": False,
                    "confidence": max(semantic_turn.confidence, 0.90),
                }
            )

        provider_product_mentions = [
            value
            for value in semantic_turn.mentioned_products
            if self.normalize_text(value).lower() in normalized_text.lower()
        ]
        mentioned_products = self._canonical_product_mentions(
            [*provider_product_mentions, *self._detect_product_mentions(normalized_text)]
        )
        mentioned_product_ids = [
            product.id
            for product in self.product_service.resolve_product_references(mentioned_products)
        ]

        provider_color_mentions = [
            value
            for value in semantic_turn.mentioned_colors
            if self.normalize_text(value) in normalized_text
        ]
        mentioned_colors = self._unique(
            [*provider_color_mentions, *self._detect_color_mentions(normalized_text)]
        )
        if recovered is not None and recovered.kind in {"prefer_color", "reject_color"}:
            mentioned_colors = self._unique([*mentioned_colors, recovered.name])

        expected_claims = self._detect_claims(normalized_text)
        actual_claims = self._claims_from_actions(accepted)
        missing_claims = sorted(
            claim.key() for claim in expected_claims if claim not in actual_claims
        )

        expected_recommendation = semantic_turn.intent in {
            "request_recommendation",
            "request_comparison",
        }
        if semantic_turn.recommendation_requested != expected_recommendation:
            warnings.append(
                "recommendation_requested did not match intent and was normalized by backend"
            )

        semantic_turn = semantic_turn.model_copy(
            update={
                "recommendation_requested": expected_recommendation,
                "mentioned_products": mentioned_products,
                "mentioned_colors": mentioned_colors,
            }
        )

        if semantic_turn.intent == "request_comparison" and len(mentioned_product_ids) < 2:
            missing_claims.append("comparison requires two resolvable products")
        if semantic_turn.intent == "reject_product" and not any(
            action.kind == "reject_product" for action in accepted
        ):
            missing_claims.append(
                "reject_product intent requires a validated reject_product action"
            )
        if semantic_turn.intent == "reject_color" and not any(
            action.kind == "reject_color" for action in accepted
        ):
            missing_claims.append(
                "reject_color intent requires a validated reject_color action"
            )

        if semantic_turn.uncertain:
            warnings.append("provider marked the parse as uncertain")
        if semantic_turn.confidence < 0.80:
            warnings.append(f"provider confidence below preferred threshold: {semantic_turn.confidence:.2f}")

        critical_conflict = bool(conflicts)
        can_apply = bool(accepted) and not critical_conflict
        needs_clarification = (
            critical_conflict
            or bool(missing_claims)
            or semantic_turn.confidence < 0.65
            or (semantic_turn.uncertain and not can_apply)
            or (
                pending_slot is not None
                and not can_apply
                and semantic_turn.intent in {"other", "provide_or_modify_needs"}
            )
        )
        ok = not needs_clarification
        clarification = (
            None
            if ok
            else self._clarification_question(
                pending_slot=pending_slot,
                missing_claims=missing_claims,
                rejected=rejected,
                conflicts=conflicts,
            )
        )

        return ValidationResult(
            ok=ok,
            can_apply=can_apply,
            needs_clarification=needs_clarification,
            critical_conflict=critical_conflict,
            normalized_text=normalized_text,
            semantic_turn=semantic_turn,
            backend_self_context=backend_self_context,
            actions=accepted,
            mentioned_product_ids=self._unique(mentioned_product_ids),
            mentioned_colors=mentioned_colors,
            missing_claims=missing_claims,
            rejected_actions=[*rejected, *conflicts],
            warnings=warnings,
            clarification_question=clarification,
        )

    def _normalize_intent_from_text(
        self,
        text: str,
        semantic_turn: SemanticTurn,
    ) -> SemanticTurn:
        if any(marker in text for marker in RECOMMENDATION_MARKERS):
            if "对比" in text or "比较" in text or "差别" in text:
                intent = "request_comparison"
            else:
                intent = "request_recommendation"
            return semantic_turn.model_copy(
                update={
                    "intent": intent,
                    "recommendation_requested": True,
                    "uncertain": False,
                    "confidence": max(semantic_turn.confidence, 0.90),
                }
            )
        return semantic_turn

    def _recover_pending_slot_action(
        self,
        *,
        text: str,
        pending_slot: str | None,
        existing: list[ValidatedAction],
    ) -> ValidatedAction | None:
        if pending_slot is None or not text:
            return None

        if pending_slot == "room_type":
            if any(action.kind == "set_field" and action.name == "room_type" for action in existing):
                return None
            for room, patterns in ROOM_PATTERNS.items():
                evidence = next((pattern for pattern in patterns if pattern in text), None)
                if evidence:
                    return ValidatedAction(
                        kind="set_field",
                        name="room_type",
                        value=room,
                        evidence=evidence,
                        scope="persistent",
                    )

        if pending_slot == "budget":
            if any(action.kind == "set_field" and action.name == "budget" for action in existing):
                return None
            for budget, patterns in BUDGET_PATTERNS.items():
                evidence = next((pattern for pattern in patterns if pattern in text), None)
                if evidence:
                    return ValidatedAction(
                        kind="set_field",
                        name="budget",
                        value=budget,
                        evidence=evidence,
                        scope="persistent",
                    )

        if pending_slot == "style":
            if any(action.kind == "set_field" and action.name == "style" for action in existing):
                return None
            for style, patterns in STYLE_PATTERNS.items():
                evidence = next((pattern for pattern in patterns if pattern in text), None)
                if evidence:
                    return ValidatedAction(
                        kind="set_field",
                        name="style",
                        value=style,
                        evidence=evidence,
                        scope="persistent",
                    )

        if pending_slot == "preferred_color":
            if any(action.kind in {"prefer_color", "reject_color"} for action in existing):
                return None
            colors = self._detect_color_mentions(text)
            if colors:
                color = colors[0]
                return ValidatedAction(
                    kind="prefer_color",
                    name=color,
                    value="prefer",
                    evidence=color,
                    scope="persistent",
                )

        if pending_slot == "priority":
            if any(action.kind == "set_priority" for action in existing):
                return None
            for priority, aliases in PRIORITY_ALIASES.items():
                evidence = next((alias for alias in aliases if alias in text), None)
                if evidence:
                    return ValidatedAction(
                        kind="set_priority",
                        name=priority,
                        value="high",
                        evidence=evidence,
                        scope="persistent",
                    )
        return None

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
            if any(pattern in text for pattern in value_patterns["no"]):
                claims.add(Claim("field", field_name, "no"))
            elif any(pattern in text for pattern in value_patterns["yes"]):
                claims.add(Claim("field", field_name, "yes"))
        for priority, patterns in PRIORITY_ALIASES.items():
            if not any(pattern in text for pattern in patterns):
                continue
            if priority == "价格" and not any(
                phrase in text
                for phrase in (
                    "价格最重要",
                    "价格优先",
                    "重点看价格",
                    "更在意价格",
                    "性价比最重要",
                    "价格不重要",
                    "不用考虑价格",
                    "去掉价格",
                    "不需要考虑价格",
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

    def _backend_self_context(
        self,
        text: str,
        semantic_turn: SemanticTurn,
        pending_slot: str | None,
    ) -> bool:
        if pending_slot is not None:
            return True
        if semantic_turn.intent in {
            "provide_or_modify_needs",
            "reject_product",
            "reject_color",
        }:
            return True
        return semantic_turn.explicit_self_context or any(
            marker in text for marker in SELF_MARKERS
        )

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
                "中档": "中等",
            }
            return mapping.get(lower, mapping.get(value, value))
        if field_name in BOOLEAN_FIELDS:
            mapping = {
                "true": "yes",
                "false": "no",
                "有": "yes",
                "是": "yes",
                "没有": "no",
                "无": "no",
                "否": "no",
            }
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
        found = [token for token in COLOR_TOKENS if token in text]
        found.sort(key=len, reverse=True)
        output: list[str] = []
        for color in found:
            if any(color in existing or existing in color for existing in output):
                continue
            output.append(color)
        return output

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
    def _clarification_question(
        *,
        pending_slot: str | None,
        missing_claims: list[str],
        rejected: list[str],
        conflicts: list[str],
    ) -> str:
        pending_questions = {
            "room_type": "我没有听清房间。请只回答：客厅、卧室或全屋。",
            "budget": "我没有听清预算。请只回答：经济、中等、偏高或高端。",
            "style": "我没有听清风格。请只回答：现代简约、北欧原木、新中式或其他风格。",
            "preferred_color": "我没有听清颜色。请只回答：浅灰色、原木色或深色系。",
            "priority": "我没有听清重点。请只回答：防水、耐磨、环保、价格、脚感或好清洁。",
        }
        if pending_slot in pending_questions:
            return pending_questions[pending_slot]
        if conflicts:
            return "我听到同一个条件有两个不同答案。请只确认最终要保留的那个条件。"
        if missing_claims:
            first = missing_claims[0]
            if "has_floor_heating" in first:
                return "我没有完全确认地暖条件。请问您家是有地暖，还是没有安装地暖？"
            if "has_pets" in first:
                return "我没有完全确认宠物条件。请问您家目前有养猫或养狗吗？"
            if "priority" in first:
                return "我可能漏掉了您最关注的性能。请确认您最重视防水、耐磨、环保、价格、脚感还是好清洁？"
            if "comparison" in first:
                return "请再告诉我您想比较的两个产品或材质，例如 SPC 和多层实木。"
        if rejected:
            return "我已经记录了听清的部分。请只用一句话确认刚才要修改的那个条件。"
        return "我没有完全听清。请只说一个最重要的条件。"
