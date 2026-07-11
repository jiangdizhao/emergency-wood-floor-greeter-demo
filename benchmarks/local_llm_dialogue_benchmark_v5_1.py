from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import local_llm_dialogue_benchmark as engine
import local_llm_dialogue_benchmark_v4 as v4
import local_llm_dialogue_benchmark_v5 as v5

VERSION = "5.1-compact-cascade"
DEFAULT_QWEN_MODEL = "qwen3.5:4b"
DEFAULT_LUNA_MODEL = "gpt-5.6-luna"
DEFAULT_TERRA_MODEL = "gpt-5.6-terra"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_OPENAI_URL = "https://api.openai.com/v1"
KEEP_ALIVE = "30m"

MODES = (
    "qwen_only",
    "luna_only",
    "terra_only",
    "qwen_luna",
    "qwen_luna_terra",
)

INTENTS = v5.INTENTS
FIELDS = v5.FIELDS
ROOMS = v5.ROOMS
BUDGETS = v5.BUDGETS
BOOLEAN_FIELDS = v5.BOOLEAN_FIELDS
PRIORITIES = v5.PRIORITIES
QUESTION_INTENTS = v5.QUESTION_INTENTS
RECOMMENDATION_INTENTS = v5.RECOMMENDATION_INTENTS
UPDATE_KINDS = v5.UPDATE_KINDS

OPENAI_PRICES_PER_MTOK = {
    "luna": {"input": 1.0, "output": 6.0},
    "terra": {"input": 2.5, "output": 15.0},
}

ACTION_KINDS = (
    "set_field",
    "set_priority",
    "prefer_color",
    "reject_color",
    "prefer_product",
    "reject_product",
)

COMPACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "intent": {"type": "string", "enum": list(INTENTS)},
        "is_question": {"type": "boolean"},
        "explicit_self_context": {"type": "boolean"},
        "recommendation_requested": {"type": "boolean"},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {"type": "string", "enum": list(ACTION_KINDS)},
                    "name": {"type": "string"},
                    "value": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": ["kind", "name", "value", "evidence"],
            },
        },
        "uncertain": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": [
        "intent",
        "is_question",
        "explicit_self_context",
        "recommendation_requested",
        "actions",
        "uncertain",
        "confidence",
    ],
}

SYSTEM_PROMPT = """
你是木地板门店对话系统的单轮结构化解析器。只解析顾客最新一句话，不推荐产品，不补充用户未明确表达的信息。

意图：
- provide_or_modify_needs：陈述或修改需求，没有要求立即推荐；
- request_recommendation：明确要求推荐或选择最合适方案；
- request_comparison：比较两个或更多产品；
- ask_reason：追问之前为何推荐或未推荐某产品；
- reject_product：明确排除某个产品；
- reject_color：明确拒绝颜色，可同时表达替代颜色；
- general_product_question：询问某产品的属性或能力；
- other：以上都不符合。

只输出紧凑 actions：
- set_field：name 为 room_type/budget/style/has_pets/has_floor_heating/has_children/has_elderly/humid_environment，value 为规范值；
- set_priority：name 为优先级，value 为 high/medium/low/remove；
- prefer_color/reject_color：name 为颜色，value 留空；
- prefer_product/reject_product：name 为产品，value 留空。

规则：
1. 一句话可产生多个 action；主意图不得阻止提取同句里的需求修改。
2. 当前状态只用于理解“改成、不是、其实”等纠正，不能复制旧状态。
3. 只输出最终含义；未提到不等于 no；不得从宠物推断耐磨、潮湿或好清洁。
4. evidence 必须逐字复制当前提供的规范化话语中的连续片段，不能为空，不得改写。
5. 规范值：房间=客厅/卧室/全屋/厨房/书房/儿童房/老人房；预算=经济/中等/偏高/高端；布尔=yes/no。
6. 风格必须用 set_field/style，不能当颜色；北欧风、现代风、原木风属于 style。
7. 拒绝宠物状态、老人状态等不等于 reject_product；只有明确拒绝具体地板产品才是 reject_product。
8. recommendation_requested 只在 request_recommendation/request_comparison 时为 true。
9. uncertain 表示存在无法可靠解析的关键片段；不要固定输出高 confidence。
10. 不要输出空 action、占位符、未知产品或解释文字。
""".strip()

COLOR_TERMS = (
    "浅灰色", "深灰色", "灰色", "浅灰", "深灰", "原木色", "暖色", "冷色",
    "白色", "黑色", "棕色", "米色", "胡桃色", "橡木色",
)
STYLE_TERMS = ("北欧风", "现代风", "现代简约", "原木风", "工业风", "轻奢风", "中式", "新中式")

PRIORITY_SYNONYMS = {
    "耐磨": ("耐磨", "耐造"),
    "好清洁": ("好清洁", "好打理", "易清洁"),
    "脚感": ("脚感", "舒适"),
    "防水": ("防水",),
    "环保": ("环保",),
}

SELF_PATTERNS = (
    "我家", "我们家", "家里", "家中", "给我", "我想", "我不", "我更", "我的", "按我", "我讲", "我说",
)


@dataclass
class Sanitized:
    parse: dict[str, Any]
    accepted: dict[str, list[dict[str, Any]]]
    rejected: list[dict[str, Any]]
    validation_errors: list[str]
    expected_claims: list[dict[str, str]]
    missing_claims: list[dict[str, str]]
    claim_coverage: float
    gate_reasons: list[str]
    gate_passed: bool


@dataclass
class Attempt:
    provider: str
    model: str
    ok: bool
    seconds: float
    usage: dict[str, int]
    estimated_cost_usd: float
    response_status: str
    error: str
    raw_parse: dict[str, Any]
    normalized_text: str
    sanitized_parse: dict[str, Any]
    accepted: dict[str, list[dict[str, Any]]]
    rejected: list[dict[str, Any]]
    validation_errors: list[str]
    expected_claims: list[dict[str, str]]
    missing_claims: list[dict[str, str]]
    claim_coverage: float
    gate_reasons: list[str]
    gate_passed: bool
    hard_failures: list[str]
    metadata_failures: list[str]
    state_pollution_count: int
    critical_state_pollution_count: int


@dataclass
class ModeCaseResult:
    case_id: str
    category: str
    mode: str
    hard_task_pass: bool
    metadata_pass: bool
    hard_failures: list[str]
    metadata_failures: list[str]
    state_pollution_count: int
    critical_state_pollution_count: int
    selected_provider: str
    selected_model: str
    escalated: bool
    attempts: list[Attempt]
    final_parse: dict[str, Any]
    accepted: dict[str, list[dict[str, Any]]]
    latency_seconds: float
    estimated_cost_usd: float


def normalize_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"(?i)ＳＰＣ", "SPC", text)
    return text


def user_prompt(text: str, state: dict[str, Any]) -> str:
    return (
        "当前客户状态（只用于理解纠正）：\n"
        + json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        + "\n规范化后的顾客最新话语：\n"
        + text
    )


def canonical_product(value: str) -> str:
    normalized = engine.norm(value)
    if normalized in {"spc", "spc地板", "石塑", "石塑地板"}:
        return "SPC"
    if "多层实木" in normalized or "实木复合" in normalized:
        return "多层实木"
    return re.sub(r"\s+", "", str(value or "")).strip()


def products_in_text(text: str) -> list[str]:
    normalized = engine.norm(text)
    out: list[str] = []
    if "spc" in normalized or "石塑" in normalized:
        out.append("SPC")
    if "多层实木" in normalized or "实木复合" in normalized:
        out.append("多层实木")
    return out


def colors_in_text(text: str) -> list[str]:
    out: list[str] = []
    for color in COLOR_TERMS:
        if color in text and color not in out:
            out.append(color)
    return out


def backend_self_context(text: str, intent: str) -> bool:
    if any(pattern in text for pattern in SELF_PATTERNS):
        return True
    if intent in {"reject_product", "reject_color"}:
        return True
    if intent == "provide_or_modify_needs":
        return True
    return False


def canonical_field_value(field_name: str, value: str) -> str:
    raw = re.sub(r"\s+", "", str(value or "")).strip()
    low = raw.lower()
    if field_name == "budget":
        mapping = {
            "economic": "经济", "economy": "经济", "low": "经济", "经济档": "经济",
            "medium": "中等", "mid": "中等", "middle": "中等", "中等档": "中等",
            "medium-high": "偏高", "upper-middle": "偏高", "偏高档": "偏高",
            "high": "高端", "premium": "高端", "高端档": "高端",
        }
        return raw if raw in BUDGETS else mapping.get(low, mapping.get(raw, raw))
    if field_name == "room_type":
        for room in ROOMS:
            if room in raw:
                return room
        return raw
    if field_name in BOOLEAN_FIELDS:
        return {"true": "yes", "false": "no", "有": "yes", "没有": "no", "是": "yes", "否": "no"}.get(low, raw)
    return raw


def negative_evidence(evidence: str) -> bool:
    return any(marker in evidence for marker in ("不", "没", "无", "未", "否"))


def provider_scope(intent: str, self_context: bool) -> str:
    if intent in {"reject_product", "reject_color", "provide_or_modify_needs"}:
        return "persistent"
    if intent in RECOMMENDATION_INTENTS:
        return "persistent" if self_context else "turn_only"
    return "persistent"


def high_level(text: str, token: str) -> str:
    clauses = re.split(r"[，,。；;！？!?]", text)
    clause = next((part for part in clauses if token in part), text)
    remove_patterns = (
        token + "不用考虑", token + "不考虑", token + "不需要",
        "不考虑" + token, "取消" + token,
    )
    if any(pattern in clause for pattern in remove_patterns):
        return "remove"
    if any(marker in clause for marker in ("不是最重要", "没那么重要", "次要")):
        return "low"
    if any(marker in clause for marker in ("第一位", "最重要", "优先", "更看重", "更在意", "主要要")):
        return "high"
    return "medium"


def expected_claims(text: str, intent: str) -> list[dict[str, str]]:
    claims: list[dict[str, str]] = []

    def add(kind: str, name: str, value: str = "") -> None:
        item = {"kind": kind, "name": name, "value": value}
        if item not in claims:
            claims.append(item)

    room_candidates = []
    for room in ROOMS:
        position = text.rfind(room)
        if position >= 0:
            local = text[max(0, position - 3):position + len(room) + 3]
            if "不要" + room in local or room + "不要" in local:
                continue
            room_candidates.append((position, room))
    if room_candidates:
        add("field", "room_type", max(room_candidates)[1])

    budget_candidates = [(text.rfind(value), value) for value in BUDGETS if value in text]
    budget_value = max(budget_candidates)[1] if budget_candidates else None
    if budget_value:
        add("field", "budget", budget_value)
    elif any(token in text for token in ("往上提一档", "高一点", "提高预算")):
        add("field", "budget", "偏高")

    if any(token in text for token in ("地暖", "地采暖")):
        add("field", "has_floor_heating", "no" if negative_evidence(text) and any(x in text for x in ("没装", "没有地暖", "无地暖")) else "yes")
    if any(token in text for token in ("宠物", "养猫", "养狗", "猫", "狗")):
        no_pet = any(token in text for token in ("不养猫也不养狗", "没养猫也没养狗", "没有宠物", "无宠物"))
        add("field", "has_pets", "no" if no_pet else "yes")
    if any(token in text for token in ("小孩", "孩子", "儿童")):
        no_child = any(token in text for token in ("没有小孩", "没小孩", "没有孩子", "没孩子"))
        add("field", "has_children", "no" if no_child else "yes")
    if any(token in text for token in ("老人", "长辈")):
        no_elderly = any(token in text for token in ("没有老人", "没老人", "无老人", "没有长辈", "没长辈"))
        add("field", "has_elderly", "no" if no_elderly else "yes")
    if any(token in text for token in ("返潮", "潮湿", "湿气")):
        add("field", "humid_environment", "yes")
    for style in STYLE_TERMS:
        if style in text:
            add("field", "style", style)
            break

    for priority, synonyms in PRIORITY_SYNONYMS.items():
        matched = next((token for token in synonyms if token in text), None)
        if matched:
            add("priority", priority, high_level(text, matched))

    text_products = products_in_text(text)
    if intent == "reject_product" and text_products:
        add("product", text_products[0], "reject")
    if intent == "reject_color":
        text_colors = colors_in_text(text)
        if text_colors:
            add("color", text_colors[0], "reject")
            for color in text_colors[1:]:
                add("color", color, "prefer")
    return claims


def accepted_claims(accepted: dict[str, list[dict[str, Any]]]) -> set[tuple[str, str, str]]:
    claims: set[tuple[str, str, str]] = set()
    for item in accepted["field_updates"]:
        claims.add(("field", str(item.get("field")), str(item.get("value"))))
    for item in accepted["priority_updates"]:
        claims.add(("priority", str(item.get("name")), str(item.get("level"))))
    for item in accepted["color_preferences"]:
        claims.add(("color", str(item.get("color")), str(item.get("preference"))))
    for item in accepted["product_preferences"]:
        claims.add(("product", str(item.get("product")), str(item.get("preference"))))
    return claims


def sanitize(text: str, raw: dict[str, Any], min_confidence: float, min_claim_coverage: float) -> Sanitized:
    accepted = {kind: [] for kind in UPDATE_KINDS}
    rejected: list[dict[str, Any]] = []
    validation_errors: list[str] = []

    raw_intent = str(raw.get("intent") or "other")
    intent = raw_intent if raw_intent in INTENTS else "other"
    if raw_intent != intent:
        validation_errors.append(f"invalid_intent:{raw_intent!r}")

    recommendation_requested = intent in RECOMMENDATION_INTENTS
    if bool(raw.get("recommendation_requested")) != recommendation_requested:
        validation_errors.append("recommendation_requested_inconsistent")

    model_self = bool(raw.get("explicit_self_context"))
    derived_self = backend_self_context(text, intent)
    scope = provider_scope(intent, derived_self)
    text_products = products_in_text(text)
    text_colors = colors_in_text(text)

    field_seen: dict[str, dict[str, Any]] = {}
    priority_seen: dict[str, dict[str, Any]] = {}

    def reject(action: Any, reason: str, severity: str = "noise") -> None:
        rejected.append({"action": action, "reason": reason, "severity": severity})

    for action in raw.get("actions", []) or []:
        if not isinstance(action, dict):
            reject(action, "action_not_object", "dangerous")
            continue
        kind = str(action.get("kind") or "")
        name = re.sub(r"\s+", "", str(action.get("name") or "")).strip()
        value = re.sub(r"\s+", "", str(action.get("value") or "")).strip()
        evidence = str(action.get("evidence") or "")
        if kind not in ACTION_KINDS:
            reject(action, "unknown_action_kind", "dangerous")
            continue
        if not name or not evidence:
            reject(action, "empty_name_or_evidence", "noise")
            continue
        if not engine.verbatim(text, evidence):
            reject(action, "evidence_not_verbatim", "dangerous")
            continue

        if kind == "set_field":
            if name not in FIELDS:
                reject(action, "unknown_field", "dangerous")
                continue
            canonical = canonical_field_value(name, value)
            if name == "room_type" and canonical not in ROOMS:
                reject(action, "invalid_room_value", "dangerous")
                continue
            if name == "budget" and canonical not in BUDGETS:
                reject(action, "invalid_budget_value", "dangerous")
                continue
            if name in BOOLEAN_FIELDS and canonical not in {"yes", "no"}:
                reject(action, "invalid_boolean_value", "dangerous")
                continue
            if name == "style" and not canonical:
                reject(action, "empty_style", "dangerous")
                continue
            if name in BOOLEAN_FIELDS and canonical == "no" and not negative_evidence(evidence):
                reject(action, "negative_without_negative_evidence", "dangerous")
                continue
            if name in BOOLEAN_FIELDS and canonical == "yes" and negative_evidence(evidence):
                reject(action, "positive_with_negative_evidence", "dangerous")
                continue
            item = {"field": name, "value": canonical, "scope": scope, "evidence": evidence}
            previous = field_seen.get(name)
            if previous and previous["value"] != canonical:
                validation_errors.append(f"conflicting_field_values:{name}")
                reject(action, "conflicting_field_values", "dangerous")
                continue
            field_seen[name] = item

        elif kind == "set_priority":
            if name not in PRIORITIES or value not in {"high", "medium", "low", "remove"}:
                reject(action, "invalid_priority_action", "dangerous")
                continue
            item = {"name": name, "level": value, "scope": scope, "evidence": evidence}
            previous = priority_seen.get(name)
            if previous and previous["level"] != value:
                validation_errors.append(f"conflicting_priority_levels:{name}")
                reject(action, "conflicting_priority_levels", "dangerous")
                continue
            priority_seen[name] = item

        elif kind in {"prefer_color", "reject_color"}:
            if name not in text_colors:
                reject(action, "color_not_in_text", "dangerous")
                continue
            accepted["color_preferences"].append({
                "color": name,
                "preference": "prefer" if kind == "prefer_color" else "reject",
                "scope": "persistent",
                "evidence": evidence,
            })

        elif kind in {"prefer_product", "reject_product"}:
            product = canonical_product(name)
            if product not in text_products:
                reject(action, "product_not_in_text", "dangerous")
                continue
            if kind == "reject_product" and intent != "reject_product":
                reject(action, "reject_product_action_without_intent", "dangerous")
                continue
            accepted["product_preferences"].append({
                "product": product,
                "preference": "prefer" if kind == "prefer_product" else "reject",
                "scope": "persistent",
                "evidence": evidence,
            })

    accepted["field_updates"].extend(field_seen.values())
    accepted["priority_updates"].extend(priority_seen.values())

    if intent in QUESTION_INTENTS:
        for kind in UPDATE_KINDS:
            if accepted[kind]:
                for item in accepted[kind]:
                    reject(item, "question_intent_disallows_state_change", "dangerous")
                accepted[kind] = []

    claims = expected_claims(text, intent)
    actual = accepted_claims(accepted)
    missing = [claim for claim in claims if (claim["kind"], claim["name"], claim["value"]) not in actual]
    claim_coverage = 1.0 if not claims else (len(claims) - len(missing)) / len(claims)

    parse = {
        "intent": intent,
        "is_question": bool(raw.get("is_question")),
        "explicit_self_context": model_self,
        "backend_self_context": derived_self,
        "recommendation_requested": recommendation_requested,
        "mentioned_products": text_products,
        "mentioned_colors": text_colors,
        "uncertain": bool(raw.get("uncertain")),
        "confidence": float(raw.get("confidence") or 0.0),
        "claim_coverage": claim_coverage,
    }

    gate_reasons = list(validation_errors)
    if parse["confidence"] < min_confidence:
        gate_reasons.append(f"low_confidence:{parse['confidence']:.3f}<{min_confidence:.3f}")
    if parse["uncertain"]:
        gate_reasons.append("provider_uncertain")
    if claim_coverage < min_claim_coverage:
        gate_reasons.append(f"claim_coverage:{claim_coverage:.3f}<{min_claim_coverage:.3f}")
    if missing:
        gate_reasons.append("missing_claims:" + ",".join(f"{x['kind']}:{x['name']}={x['value']}" for x in missing))

    dangerous_rejections = [item for item in rejected if item["severity"] == "dangerous"]
    if dangerous_rejections:
        gate_reasons.append(f"dangerous_rejections:{len(dangerous_rejections)}")

    if intent == "reject_product":
        if not text_products:
            gate_reasons.append("reject_product_without_product_entity")
        if not any(x.get("preference") == "reject" for x in accepted["product_preferences"]):
            gate_reasons.append("reject_product_without_reject_action")
    if intent == "reject_color" and not any(x.get("preference") == "reject" for x in accepted["color_preferences"]):
        gate_reasons.append("reject_color_without_reject_action")
    if intent == "request_comparison" and len(text_products) < 2:
        gate_reasons.append("comparison_without_two_products")
    if intent == "general_product_question" and not text_products:
        gate_reasons.append("product_question_without_product")
    if intent == "reject_product" and not text_products and accepted["field_updates"]:
        gate_reasons.append("household_correction_misclassified_as_product_rejection")

    gate_reasons = list(dict.fromkeys(gate_reasons))
    return Sanitized(
        parse=parse,
        accepted=accepted,
        rejected=rejected,
        validation_errors=validation_errors,
        expected_claims=claims,
        missing_claims=missing,
        claim_coverage=claim_coverage,
        gate_reasons=gate_reasons,
        gate_passed=not gate_reasons,
    )


def empty_sanitized(error: str) -> Sanitized:
    return Sanitized(
        parse={
            "intent": "other",
            "is_question": False,
            "explicit_self_context": False,
            "backend_self_context": False,
            "recommendation_requested": False,
            "mentioned_products": [],
            "mentioned_colors": [],
            "uncertain": True,
            "confidence": 0.0,
            "claim_coverage": 0.0,
        },
        accepted={kind: [] for kind in UPDATE_KINDS},
        rejected=[],
        validation_errors=[error],
        expected_claims=[],
        missing_claims=[],
        claim_coverage=0.0,
        gate_reasons=[error],
        gate_passed=False,
    )


class CompactOllamaProvider(v5.OllamaProvider):
    def parse(self, text: str, state: dict[str, Any]) -> v5.ProviderCall:
        normalized = normalize_text(text)
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt(normalized, state)},
            ],
            "stream": False,
            "think": False,
            "format": COMPACT_SCHEMA,
            "keep_alive": KEEP_ALIVE,
            "options": {"num_ctx": 4096, "num_predict": 500, "temperature": 0},
        }
        started = time.perf_counter()
        try:
            response = self._post(body)
            content = str(response.get("message", {}).get("content") or "")
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise RuntimeError("Ollama structured output is not an object")
            return v5.ProviderCall(
                provider="qwen",
                model=self.model,
                ok=True,
                seconds=time.perf_counter() - started,
                raw_parse=parsed,
                usage=v5.Usage(
                    input_tokens=int(response.get("prompt_eval_count") or 0),
                    output_tokens=int(response.get("eval_count") or 0),
                ),
                response_status=str(response.get("done_reason") or ""),
            )
        except Exception as exc:
            return v5.ProviderCall(
                provider="qwen", model=self.model, ok=False,
                seconds=time.perf_counter() - started, raw_parse={},
                error=f"{type(exc).__name__}: {exc}",
            )


class CompactOpenAIProvider(v5.OpenAIProvider):
    def parse(self, text: str, state: dict[str, Any]) -> v5.ProviderCall:
        normalized = normalize_text(text)
        body = {
            "model": self.model,
            "input": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt(normalized, state)},
            ],
            "reasoning": {"effort": "none"},
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "flooring_dialogue_compact_parse",
                    "strict": True,
                    "schema": COMPACT_SCHEMA,
                }
            },
            "max_output_tokens": 900,
            "store": False,
        }
        started = time.perf_counter()
        try:
            response = self._post(body)
            content = self.output_text(response)
            if not content.strip():
                raise RuntimeError(f"OpenAI response contained no output_text; status={response.get('status')}")
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise RuntimeError("OpenAI structured output is not an object")
            usage_raw = response.get("usage") or {}
            details = usage_raw.get("input_tokens_details") or {}
            usage = v5.Usage(
                input_tokens=int(usage_raw.get("input_tokens") or 0),
                output_tokens=int(usage_raw.get("output_tokens") or 0),
                cached_input_tokens=int(details.get("cached_tokens") or 0),
            )
            estimated_cost = (
                usage.input_tokens * self.input_price_per_mtok
                + usage.output_tokens * self.output_price_per_mtok
            ) / 1_000_000
            return v5.ProviderCall(
                provider=self.provider_name,
                model=self.model,
                ok=True,
                seconds=time.perf_counter() - started,
                raw_parse=parsed,
                usage=usage,
                estimated_cost_usd=estimated_cost,
                response_status=str(response.get("status") or ""),
            )
        except Exception as exc:
            return v5.ProviderCall(
                provider=self.provider_name, model=self.model, ok=False,
                seconds=time.perf_counter() - started, raw_parse={},
                error=f"{type(exc).__name__}: {exc}",
            )


def expected_state_sets(spec: v4.Spec) -> dict[str, set[tuple[str, ...]]]:
    case = spec.case
    return {
        "field_updates": set(case.fields),
        "priority_updates": set(case.priorities),
        "color_preferences": set(case.color_prefs),
        "product_preferences": set(case.product_prefs),
    }


def actual_state_sets(accepted: dict[str, list[dict[str, Any]]]) -> dict[str, set[tuple[str, ...]]]:
    return {
        "field_updates": {
            (str(x.get("field")), str(x.get("value")), str(x.get("scope")))
            for x in accepted["field_updates"]
        },
        "priority_updates": {
            (str(x.get("name")), str(x.get("level")), str(x.get("scope")))
            for x in accepted["priority_updates"]
        },
        "color_preferences": {
            (str(x.get("color")), str(x.get("preference")), str(x.get("scope")))
            for x in accepted["color_preferences"]
        },
        "product_preferences": {
            (str(x.get("product")), str(x.get("preference")), str(x.get("scope")))
            for x in accepted["product_preferences"]
        },
    }


def evaluate_hard(spec: v4.Spec, parse: dict[str, Any], accepted: dict[str, list[dict[str, Any]]]) -> list[str]:
    case = spec.case
    failures: list[str] = []
    if parse.get("intent") != case.intent:
        failures.append(f"intent expected={case.intent} actual={parse.get('intent')}")
    if spec.recommendation is not None and bool(parse.get("recommendation_requested")) != spec.recommendation:
        failures.append(
            f"recommendation_requested expected={spec.recommendation} actual={bool(parse.get('recommendation_requested'))}"
        )
    for product in case.products:
        if product not in parse.get("mentioned_products", []):
            failures.append(f"missing mentioned product: {product}")
    for color in case.colors:
        if color not in parse.get("mentioned_colors", []):
            failures.append(f"missing mentioned color: {color}")

    expected = expected_state_sets(spec)
    actual = actual_state_sets(accepted)
    singular = {
        "field_updates": "field update",
        "priority_updates": "priority update",
        "color_preferences": "color preference",
        "product_preferences": "product preference",
    }
    for kind in UPDATE_KINDS:
        for item in expected[kind] - actual[kind]:
            failures.append(f"missing {singular[kind]}: " + "|".join(item))
    for forbidden in case.forbidden_fields:
        if any(item[0] == forbidden for item in actual["field_updates"]):
            failures.append(f"forbidden field update accepted: {forbidden}")
    if case.no_persistent and any(
        item.get("scope") == "persistent" for values in accepted.values() for item in values
    ):
        failures.append("unexpected persistent state change")
    return failures


def evaluate_metadata(spec: v4.Spec, parse: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if spec.self_context is not None and bool(parse.get("explicit_self_context")) != spec.self_context:
        failures.append(
            f"explicit_self_context expected={spec.self_context} actual={bool(parse.get('explicit_self_context'))}"
        )
    return failures


def pollution(spec: v4.Spec, accepted: dict[str, list[dict[str, Any]]]) -> tuple[int, int]:
    expected = expected_state_sets(spec)
    actual = actual_state_sets(accepted)
    extra = sum(len(actual[kind] - expected[kind]) for kind in UPDATE_KINDS)
    critical = 0
    for field_name, value, scope in actual["field_updates"] - expected["field_updates"]:
        if field_name in spec.case.forbidden_fields:
            critical += 1
        if any(item[0] == field_name and (item[1] != value or item[2] != scope) for item in expected["field_updates"]):
            critical += 1
    for kind in ("priority_updates", "color_preferences", "product_preferences"):
        for item in actual[kind] - expected[kind]:
            if any(expected_item[0] == item[0] and expected_item != item for expected_item in expected[kind]):
                critical += 1
            elif kind == "product_preferences" and len(item) > 1 and item[1] == "reject":
                critical += 1
    if spec.case.no_persistent:
        critical += sum(
            1 for values in accepted.values() for item in values if item.get("scope") == "persistent"
        )
    return extra, critical


def to_attempt(
    call: v5.ProviderCall,
    sanitized: Sanitized,
    normalized_text: str,
    spec: v4.Spec,
) -> Attempt:
    hard = evaluate_hard(spec, sanitized.parse, sanitized.accepted)
    metadata = evaluate_metadata(spec, sanitized.parse)
    pollution_count, critical_count = pollution(spec, sanitized.accepted)
    return Attempt(
        provider=call.provider,
        model=call.model,
        ok=call.ok,
        seconds=call.seconds,
        usage=asdict(call.usage),
        estimated_cost_usd=call.estimated_cost_usd,
        response_status=call.response_status,
        error=call.error,
        raw_parse=call.raw_parse,
        normalized_text=normalized_text,
        sanitized_parse=sanitized.parse,
        accepted=sanitized.accepted,
        rejected=sanitized.rejected,
        validation_errors=sanitized.validation_errors,
        expected_claims=sanitized.expected_claims,
        missing_claims=sanitized.missing_claims,
        claim_coverage=sanitized.claim_coverage,
        gate_reasons=sanitized.gate_reasons,
        gate_passed=sanitized.gate_passed,
        hard_failures=hard,
        metadata_failures=metadata,
        state_pollution_count=pollution_count,
        critical_state_pollution_count=critical_count,
    )


def provider_order(mode: str) -> list[str]:
    return {
        "qwen_only": ["qwen"],
        "luna_only": ["luna"],
        "terra_only": ["terra"],
        "qwen_luna": ["qwen", "luna"],
        "qwen_luna_terra": ["qwen", "luna", "terra"],
    }[mode]


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(p * len(ordered)) - 1))]


def show_result(result: ModeCaseResult, verbose: bool) -> None:
    status = "PASS" if result.hard_task_pass else "FAIL"
    metadata = "meta-ok" if result.metadata_pass else "meta-fail"
    print(
        f"[{status}] {result.mode:<22} {result.case_id:<36} "
        f"provider={result.selected_provider:<6} {metadata:<9} "
        f"pollution={result.state_pollution_count}/{result.critical_state_pollution_count} "
        f"latency={result.latency_seconds:6.2f}s cost=${result.estimated_cost_usd:.6f}"
    )
    for failure in result.hard_failures:
        print("       - hard:", failure)
    for failure in result.metadata_failures:
        print("       - metadata:", failure)
    if verbose or not result.hard_task_pass:
        for attempt in result.attempts:
            print(
                f"       attempt {attempt.provider}/{attempt.model}: ok={attempt.ok} "
                f"gate={attempt.gate_passed} hard={not attempt.hard_failures} "
                f"latency={attempt.seconds:.3f}s tokens={attempt.usage.get('output_tokens', 0)}"
            )
            if attempt.error:
                print("         error:", attempt.error)
            if attempt.gate_reasons:
                print("         gate_reasons:", json.dumps(attempt.gate_reasons, ensure_ascii=False))
            if verbose:
                print("         normalized_text:", attempt.normalized_text)
                print("         raw_parse:", json.dumps(attempt.raw_parse, ensure_ascii=False))
                print("         accepted:", json.dumps(attempt.accepted, ensure_ascii=False))
                print("         expected_claims:", json.dumps(attempt.expected_claims, ensure_ascii=False))
                print("         missing_claims:", json.dumps(attempt.missing_claims, ensure_ascii=False))
                if attempt.rejected:
                    print("         rejected:", json.dumps(attempt.rejected, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark v5.1 compact cross-provider cascade and gate diagnostics.")
    parser.add_argument("--mode", action="append", choices=MODES)
    parser.add_argument("--all-modes", action="store_true")
    parser.add_argument("--qwen-model", default=DEFAULT_QWEN_MODEL)
    parser.add_argument("--luna-model", default=DEFAULT_LUNA_MODEL)
    parser.add_argument("--terra-model", default=DEFAULT_TERRA_MODEL)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--openai-base-url", default=os.environ.get("OPENAI_BASE_URL", DEFAULT_OPENAI_URL))
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--category", action="append")
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--list-cases", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--gate-min-confidence", type=float, default=0.80)
    parser.add_argument("--gate-min-claim-coverage", type=float, default=1.0)
    parser.add_argument("--luna-input-price", type=float, default=OPENAI_PRICES_PER_MTOK["luna"]["input"])
    parser.add_argument("--luna-output-price", type=float, default=OPENAI_PRICES_PER_MTOK["luna"]["output"])
    parser.add_argument("--terra-input-price", type=float, default=OPENAI_PRICES_PER_MTOK["terra"]["input"])
    parser.add_argument("--terra-output-price", type=float, default=OPENAI_PRICES_PER_MTOK["terra"]["output"])
    args = parser.parse_args()

    if args.repeat < 1:
        raise SystemExit("--repeat must be >= 1")
    if not 0 <= args.gate_min_confidence <= 1:
        raise SystemExit("--gate-min-confidence must be between 0 and 1")
    if not 0 <= args.gate_min_claim_coverage <= 1:
        raise SystemExit("--gate-min-claim-coverage must be between 0 and 1")

    modes = list(MODES) if args.all_modes else list(dict.fromkeys(args.mode or ["qwen_only"]))
    specs = [spec for spec in v4.CASES if not args.category or spec.category in set(args.category)]
    specs = [spec for spec in specs if not args.case_ids or spec.case.id in set(args.case_ids)]
    if args.list_cases:
        for spec in specs:
            print(f"{spec.case.id}\t{spec.category}\t{spec.case.text}")
        return 0
    if not specs:
        raise SystemExit("No cases selected")

    required = {provider for mode in modes for provider in provider_order(mode)}
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if required & {"luna", "terra"} and not api_key:
        raise SystemExit("OPENAI_API_KEY is not set in this terminal. The key is never accepted on the command line or written to reports.")

    providers: dict[str, Any] = {}
    if "qwen" in required:
        providers["qwen"] = CompactOllamaProvider(args.ollama_url, args.qwen_model, args.timeout)
    if "luna" in required:
        providers["luna"] = CompactOpenAIProvider(
            "luna", args.openai_base_url, args.luna_model, args.timeout, api_key,
            args.luna_input_price, args.luna_output_price,
        )
    if "terra" in required:
        providers["terra"] = CompactOpenAIProvider(
            "terra", args.openai_base_url, args.terra_model, args.timeout, api_key,
            args.terra_input_price, args.terra_output_price,
        )

    print(f"Benchmark v{VERSION}")
    print("Modes:", ", ".join(modes))
    print(f"Cases: {len(specs)} x repeat {args.repeat}")
    print(f"Gate: confidence>={args.gate_min_confidence:.2f}, claim_coverage>={args.gate_min_claim_coverage:.2f}")
    if required & {"luna", "terra"}:
        print("OPENAI_API_KEY: loaded from environment (value hidden)")
    preload_seconds = None
    if "qwen" in providers:
        print("Preloading compact Qwen parser...")
        preload_seconds = providers["qwen"].preload()
        print(f"Qwen preload completed in {preload_seconds:.3f}s")
    print()

    cache: dict[tuple[int, str, str], tuple[v5.ProviderCall, Sanitized, str]] = {}
    results: list[ModeCaseResult] = []
    stopped = False

    def get_call(rep: int, provider_name: str, spec: v4.Spec) -> tuple[v5.ProviderCall, Sanitized, str]:
        key = (rep, provider_name, spec.case.id)
        if key not in cache:
            normalized = normalize_text(spec.case.text)
            call = providers[provider_name].parse(spec.case.text, spec.case.state)
            sanitized = (
                sanitize(normalized, call.raw_parse, args.gate_min_confidence, args.gate_min_claim_coverage)
                if call.ok else empty_sanitized(call.error)
            )
            cache[key] = (call, sanitized, normalized)
        return cache[key]

    for rep in range(1, args.repeat + 1):
        if args.repeat > 1:
            print(f"=== Repetition {rep}/{args.repeat} ===")
        for spec in specs:
            for mode in modes:
                attempts: list[Attempt] = []
                selected_call: v5.ProviderCall | None = None
                selected_sanitized: Sanitized | None = None
                order = provider_order(mode)
                for provider_name in order:
                    call, sanitized, normalized = get_call(rep, provider_name, spec)
                    attempt = to_attempt(call, sanitized, normalized, spec)
                    attempts.append(attempt)
                    selected_call, selected_sanitized = call, sanitized
                    if len(order) == 1 or (call.ok and sanitized.gate_passed):
                        break

                assert selected_call is not None and selected_sanitized is not None
                hard = evaluate_hard(spec, selected_sanitized.parse, selected_sanitized.accepted)
                metadata = evaluate_metadata(spec, selected_sanitized.parse)
                pollution_count, critical_count = pollution(spec, selected_sanitized.accepted)
                if not selected_call.ok:
                    hard.insert(0, f"selected provider failed: {selected_call.error}")
                result = ModeCaseResult(
                    case_id=spec.case.id,
                    category=spec.category,
                    mode=mode,
                    hard_task_pass=not hard,
                    metadata_pass=not metadata,
                    hard_failures=hard,
                    metadata_failures=metadata,
                    state_pollution_count=pollution_count,
                    critical_state_pollution_count=critical_count,
                    selected_provider=selected_call.provider,
                    selected_model=selected_call.model,
                    escalated=len(attempts) > 1,
                    attempts=attempts,
                    final_parse=selected_sanitized.parse,
                    accepted=selected_sanitized.accepted,
                    latency_seconds=sum(attempt.seconds for attempt in attempts),
                    estimated_cost_usd=sum(attempt.estimated_cost_usd for attempt in attempts),
                )
                results.append(result)
                show_result(result, args.verbose)
                if args.fail_fast and not result.hard_task_pass:
                    stopped = True
                    break
            if stopped:
                break
        print()
        if stopped:
            break

    by_mode: dict[str, list[ModeCaseResult]] = defaultdict(list)
    for result in results:
        by_mode[result.mode].append(result)

    summaries: dict[str, Any] = {}
    print("=== Summary by mode ===")
    for mode in modes:
        mode_results = by_mode.get(mode, [])
        if not mode_results:
            continue
        hard_passed = sum(x.hard_task_pass for x in mode_results)
        metadata_passed = sum(x.metadata_pass for x in mode_results)
        latencies = [x.latency_seconds for x in mode_results]
        cost = sum(x.estimated_cost_usd for x in mode_results)
        escalations = sum(x.escalated for x in mode_results)
        selected_counts = Counter(x.selected_provider for x in mode_results)
        pollution_total = sum(x.state_pollution_count for x in mode_results)
        critical_total = sum(x.critical_state_pollution_count for x in mode_results)
        category_total: dict[str, int] = defaultdict(int)
        category_hard: dict[str, int] = defaultdict(int)
        for x in mode_results:
            category_total[x.category] += 1
            category_hard[x.category] += int(x.hard_task_pass)
        summary = {
            "hard_task_passed": hard_passed,
            "metadata_passed": metadata_passed,
            "total": len(mode_results),
            "hard_task_pass_rate": hard_passed / len(mode_results),
            "metadata_pass_rate": metadata_passed / len(mode_results),
            "state_pollution_count": pollution_total,
            "critical_state_pollution_count": critical_total,
            "latency": {
                "mean": statistics.mean(latencies),
                "p50": statistics.median(latencies),
                "p95": percentile(latencies, 0.95),
                "max": max(latencies),
            },
            "estimated_cost_usd": cost,
            "escalations": escalations,
            "escalation_rate": escalations / len(mode_results),
            "selected_provider_counts": dict(selected_counts),
            "category_summary": {
                category: {
                    "hard_task_passed": category_hard[category],
                    "total": category_total[category],
                    "hard_task_pass_rate": category_hard[category] / category_total[category],
                }
                for category in sorted(category_total)
            },
        }
        summaries[mode] = summary
        print(
            f"{mode:<22} hard={hard_passed:>3}/{len(mode_results):<3} "
            f"meta={metadata_passed:>3}/{len(mode_results):<3} "
            f"pollution={pollution_total}/{critical_total} "
            f"mean={summary['latency']['mean']:.3f}s p95={summary['latency']['p95']:.3f}s "
            f"escalation={summary['escalation_rate'] * 100:5.1f}% cost=${cost:.6f}"
        )

    provider_gate: dict[str, Any] = {}
    for provider_name in sorted(required):
        attempts = [
            attempt for result in results for attempt in result.attempts
            if attempt.provider == provider_name
        ]
        dedup: dict[tuple[str, str, float], Attempt] = {}
        for result in results:
            for attempt in result.attempts:
                if attempt.provider == provider_name:
                    dedup[(result.case_id, attempt.model, attempt.seconds)] = attempt
        attempts = list(dedup.values())
        if not attempts:
            continue
        false_accept = sum(a.gate_passed and bool(a.hard_failures) for a in attempts)
        false_reject = sum((not a.gate_passed) and not a.hard_failures for a in attempts)
        true_accept = sum(a.gate_passed and not a.hard_failures for a in attempts)
        true_reject = sum((not a.gate_passed) and bool(a.hard_failures) for a in attempts)
        provider_gate[provider_name] = {
            "attempts": len(attempts),
            "true_accept": true_accept,
            "false_accept": false_accept,
            "true_reject": true_reject,
            "false_reject": false_reject,
            "false_accept_rate_among_hard_failures": false_accept / max(1, false_accept + true_reject),
            "false_reject_rate_among_hard_passes": false_reject / max(1, true_accept + false_reject),
            "gate_accuracy": (true_accept + true_reject) / len(attempts),
        }

    print("=== Gate diagnostics ===")
    for provider_name, values in provider_gate.items():
        print(
            f"{provider_name:<6} TA={values['true_accept']} FA={values['false_accept']} "
            f"TR={values['true_reject']} FR={values['false_reject']} "
            f"accuracy={values['gate_accuracy'] * 100:.1f}%"
        )

    report = {
        "benchmark_version": VERSION,
        "started_at": datetime.now().astimezone().isoformat(),
        "modes": modes,
        "repeat_requested": args.repeat,
        "stopped_early": stopped,
        "models": {"qwen": args.qwen_model, "luna": args.luna_model, "terra": args.terra_model},
        "endpoints": {"ollama": args.ollama_url, "openai": args.openai_base_url},
        "api_key_handling": "OPENAI_API_KEY was read from the process environment and was not logged or written to this report.",
        "compact_parser": {
            "max_qwen_output_tokens": 500,
            "natural_language_coverage_reasons_removed": True,
            "scope_computed_by_backend": True,
            "asr_text_normalization": "remove whitespace before model and evidence validation",
        },
        "gate": {
            "min_confidence": args.gate_min_confidence,
            "min_claim_coverage": args.gate_min_claim_coverage,
            "policy": "Provider-neutral domain claim completeness, semantic coherence, evidence, enums, conflicts, and dangerous rejection checks. Harmless empty noise alone does not escalate.",
        },
        "metrics": {
            "hard_task_pass": "intent, recommendation flag, entities, required state actions, scope, and no persistent pollution",
            "metadata_pass": "explicit_self_context only; not used as a hard business failure",
            "state_pollution_count": "accepted state tuples not present in the benchmark expectation",
            "critical_state_pollution_count": "wrong value/scope for an expected key, forbidden field, unexpected reject, or persistent write in a no-persistent case",
            "gate_false_accept": "gate passed a provider parse that failed hard task evaluation",
            "gate_false_reject": "gate rejected a provider parse that passed hard task evaluation",
        },
        "openai_price_assumptions_per_mtok": {
            "luna": {"input": args.luna_input_price, "output": args.luna_output_price},
            "terra": {"input": args.terra_input_price, "output": args.terra_output_price},
        },
        "qwen_preload_seconds": preload_seconds,
        "summary_by_mode": summaries,
        "gate_diagnostics_by_provider": provider_gate,
        "provider_call_count": dict(Counter(call.provider for call, _, _ in cache.values())),
        "results": [asdict(result) for result in results],
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Report:", args.report)

    return 0 if all(result.hard_task_pass for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
