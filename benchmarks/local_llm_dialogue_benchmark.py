from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3.5:4b"
KEEP_ALIVE = "30m"

INTENTS = [
    "provide_or_modify_needs",
    "request_recommendation",
    "request_comparison",
    "ask_reason",
    "reject_product",
    "reject_color",
    "general_product_question",
    "other",
]

STATE_FIELDS = [
    "room_type",
    "style",
    "budget",
    "has_pets",
    "has_floor_heating",
    "has_children",
    "has_elderly",
    "humid_environment",
]

PRIORITIES = [
    "防水",
    "耐磨",
    "环保",
    "价格",
    "脚感",
    "好清洁",
    "地暖适配",
]

INTENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "intent": {"type": "string", "enum": INTENTS},
        "is_question": {"type": "boolean"},
        "explicit_self_context": {"type": "boolean"},
        "recommendation_requested": {"type": "boolean"},
        "mentioned_products": {"type": "array", "items": {"type": "string"}},
        "mentioned_colors": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": [
        "intent",
        "is_question",
        "explicit_self_context",
        "recommendation_requested",
        "mentioned_products",
        "mentioned_colors",
        "confidence",
    ],
}

FACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "field_updates": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "field": {"type": "string", "enum": STATE_FIELDS},
                    "value": {"type": "string"},
                    "scope": {"type": "string", "enum": ["persistent", "turn_only"]},
                    "evidence": {"type": "string"},
                },
                "required": ["field", "value", "scope", "evidence"],
            },
        },
        "priority_updates": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "enum": PRIORITIES},
                    "level": {"type": "string", "enum": ["high", "medium", "low", "remove"]},
                    "scope": {"type": "string", "enum": ["persistent", "turn_only"]},
                    "evidence": {"type": "string"},
                },
                "required": ["name", "level", "scope", "evidence"],
            },
        },
        "color_preferences": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "color": {"type": "string"},
                    "preference": {"type": "string", "enum": ["prefer", "reject"]},
                    "scope": {"type": "string", "enum": ["persistent", "turn_only"]},
                    "evidence": {"type": "string"},
                },
                "required": ["color", "preference", "scope", "evidence"],
            },
        },
        "product_preferences": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "product": {"type": "string"},
                    "preference": {"type": "string", "enum": ["prefer", "reject"]},
                    "scope": {"type": "string", "enum": ["persistent", "turn_only"]},
                    "evidence": {"type": "string"},
                },
                "required": ["product", "preference", "scope", "evidence"],
            },
        },
    },
    "required": [
        "field_updates",
        "priority_updates",
        "color_preferences",
        "product_preferences",
    ],
}

INTENT_SYSTEM_PROMPT = r"""
你是木地板导购系统的意图分类器。只做分类和提及对象提取，不修改客户画像。

意图定义：
- provide_or_modify_needs：陈述、补充、纠正自己的房间、预算、家庭情况或偏好。
- request_recommendation：明确要求推荐产品。
- request_comparison：比较两个或更多产品/品类，常见词包括“哪种更适合”“区别”“对比”。
- ask_reason：询问为什么推荐或不推荐某产品。
- reject_product：顾客明确说自己不要、不喜欢、不考虑某产品。
- reject_color：顾客明确说自己不要、不喜欢某颜色。
- general_product_question：询问产品事实，但不是比较、推荐理由或个人需求更新。
- other：其他情况。

严格规则：
1. “为什么你不推荐多层实木？”是 ask_reason，不是 reject_product，也不是需求修改。
2. “SPC 和多层实木哪一种更适合有地暖和宠物的家庭？”是 request_comparison。
3. “我不喜欢灰色，还有原木色或暖色吗？”是 reject_color，同时提取灰色、原木色、暖色。
4. “我不要 SPC”才是 reject_product。
5. explicit_self_context 只有在用户明确描述自己/自己家，或用“客厅用、卧室用、预算中等”等省略主语但明显是本人需求时才为 true。
6. 泛指“有宠物的家庭”不等于用户本人有宠物，explicit_self_context 应为 false。
7. recommendation_requested 对 request_recommendation 和 request_comparison 为 true；其他意图通常为 false。
8. mentioned_products 只列原话明确提到的产品或品类，不推断。
9. mentioned_colors 只列原话明确提到的颜色，不推断。
10. 只输出符合 JSON Schema 的 JSON。
""".strip()

FACT_SYSTEM_PROMPT = r"""
你是木地板导购系统的事实提取器。你只从顾客最新一句话中提取有明确原文证据的事实。

输出规则：
1. evidence 必须逐字复制顾客原话中的连续片段；不得改写、总结或补充。
2. 没有明确证据就不要输出该项。
3. “没有提到”绝不等于 no。
4. 宠物不能推出潮湿、耐磨、好清洁或儿童情况。
5. 询问“为什么不推荐某产品”不代表顾客拒绝该产品。
6. 比较两个产品不代表顾客偏好或拒绝其中任何一个。
7. scope=persistent 仅用于顾客明确描述自己/自己家或明确纠正以前状态。
8. scope=turn_only 用于泛指比较条件，例如“哪种更适合有地暖和宠物的家庭”。
9. “防水不是最重要”应输出 防水=low；“不需要防水”应输出 防水=remove。
10. “更看重脚感”应输出 脚感=high。
11. “预算可以稍微高一些”在当前预算为中等时，可输出 budget=偏高。
12. “我不喜欢灰色，还有原木色或暖色吗”应输出：灰色 reject，原木色 prefer，暖色 prefer。
13. 产品拒绝必须有“我不要/我不喜欢/我不考虑/排除”等顾客立场证据。
14. 颜色与产品偏好也必须带原文 evidence。
15. field_updates 的 value 必须使用以下规范值：
    - room_type：客厅/卧室/全屋/厨房/书房/儿童房/老人房
    - budget：经济/中等/偏高/高端
    - has_pets、has_floor_heating、has_children、has_elderly、humid_environment：yes 或 no
    - style：顾客明确说出的风格原词
16. 只输出符合 JSON Schema 的 JSON。
""".strip()


@dataclass(frozen=True)
class TestCase:
    case_id: str
    text: str
    current_state: dict[str, Any]
    expected_intent: str
    expected_products: tuple[str, ...] = ()
    expected_colors: tuple[str, ...] = ()
    expected_fields: tuple[tuple[str, str, str], ...] = ()  # field, value, scope
    forbidden_fields: tuple[str, ...] = ()
    expected_priorities: tuple[tuple[str, str, str], ...] = ()  # name, level, scope
    expected_color_preferences: tuple[tuple[str, str, str], ...] = ()
    expected_product_preferences: tuple[tuple[str, str, str], ...] = ()
    require_no_persistent_changes: bool = False


TEST_CASES: tuple[TestCase, ...] = (
    TestCase(
        case_id="T01_basic_needs",
        text="客厅用，家里有一只狗，预算中等，我最关注耐磨和好清洁。",
        current_state={},
        expected_intent="provide_or_modify_needs",
        expected_fields=(("room_type", "客厅", "persistent"), ("budget", "中等", "persistent"), ("has_pets", "yes", "persistent")),
        forbidden_fields=("has_children", "has_elderly", "humid_environment"),
        expected_priorities=(("耐磨", "high", "persistent"), ("好清洁", "high", "persistent")),
    ),
    TestCase(
        case_id="T02_correction",
        text="刚才说错了，不是客厅，是卧室，而且我家没有地暖。",
        current_state={"room_type": "客厅", "has_floor_heating": "yes"},
        expected_intent="provide_or_modify_needs",
        expected_fields=(("room_type", "卧室", "persistent"), ("has_floor_heating", "no", "persistent")),
    ),
    TestCase(
        case_id="T03_priority_rerank",
        text="防水不是最重要，我更看重脚感，预算可以稍微高一些。",
        current_state={"budget": "中等", "priorities": {"防水": "high"}},
        expected_intent="provide_or_modify_needs",
        expected_fields=(("budget", "偏高", "persistent"),),
        expected_priorities=(("防水", "low", "persistent"), ("脚感", "high", "persistent")),
    ),
    TestCase(
        case_id="T04_color_change",
        text="我不喜欢灰色，还有原木色或者暖色的吗？",
        current_state={"preferred_colors": ["浅灰"]},
        expected_intent="reject_color",
        expected_colors=("灰色", "原木色", "暖色"),
        expected_color_preferences=(("灰色", "reject", "persistent"), ("原木色", "prefer", "persistent"), ("暖色", "prefer", "persistent")),
    ),
    TestCase(
        case_id="T05_ask_reason",
        text="为什么你不推荐多层实木？",
        current_state={},
        expected_intent="ask_reason",
        expected_products=("多层实木",),
        require_no_persistent_changes=True,
    ),
    TestCase(
        case_id="T06_comparison_generic",
        text="SPC 和多层实木哪一种更适合有地暖和宠物的家庭？",
        current_state={},
        expected_intent="request_comparison",
        expected_products=("SPC", "多层实木"),
        expected_fields=(("has_floor_heating", "yes", "turn_only"), ("has_pets", "yes", "turn_only")),
        require_no_persistent_changes=True,
    ),
    TestCase(
        case_id="T07_explicit_product_reject",
        text="我不想要 SPC，换一款脚感更舒服的。",
        current_state={"recommended_products": ["SPC"]},
        expected_intent="reject_product",
        expected_products=("SPC",),
        expected_priorities=(("脚感", "high", "persistent"),),
        expected_product_preferences=(("SPC", "reject", "persistent"),),
    ),
    TestCase(
        case_id="T08_general_question",
        text="SPC 地板防水吗？",
        current_state={},
        expected_intent="general_product_question",
        expected_products=("SPC",),
        require_no_persistent_changes=True,
    ),
    TestCase(
        case_id="T09_explicit_no_children",
        text="家里没有小孩，但有一位老人，卧室用。",
        current_state={},
        expected_intent="provide_or_modify_needs",
        expected_fields=(("has_children", "no", "persistent"), ("has_elderly", "yes", "persistent"), ("room_type", "卧室", "persistent")),
    ),
    TestCase(
        case_id="T10_omitted_is_unknown",
        text="客厅用，预算中等。",
        current_state={},
        expected_intent="provide_or_modify_needs",
        expected_fields=(("room_type", "客厅", "persistent"), ("budget", "中等", "persistent")),
        forbidden_fields=("has_children", "has_elderly", "has_pets", "has_floor_heating", "humid_environment"),
    ),
)


@dataclass
class ApiCallResult:
    data: dict[str, Any]
    wall_seconds: float
    load_seconds: float
    prompt_tokens: int
    output_tokens: int
    output_tps: float
    done_reason: str


@dataclass
class GuardResult:
    accepted: dict[str, list[dict[str, Any]]]
    rejected: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    failures: list[str]
    guard_rejections: list[dict[str, Any]]
    intent: dict[str, Any]
    raw_facts: dict[str, Any]
    accepted_facts: dict[str, list[dict[str, Any]]]
    intent_wall_seconds: float
    facts_wall_seconds: float
    total_wall_seconds: float
    output_tokens: int
    done_reasons: tuple[str, str]


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout_seconds: float = 90.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def preload(self) -> float:
        body = {
            "model": self.model,
            "messages": [],
            "stream": False,
            "keep_alive": KEEP_ALIVE,
        }
        started = time.perf_counter()
        self._post_json("/api/chat", body)
        return time.perf_counter() - started

    def structured_chat(self, system_prompt: str, user_prompt: str, schema: dict[str, Any], num_predict: int) -> ApiCallResult:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "think": False,
            "format": schema,
            "keep_alive": KEEP_ALIVE,
            "options": {
                "num_ctx": 4096,
                "num_predict": num_predict,
                "temperature": 0,
            },
        }
        started = time.perf_counter()
        response = self._post_json("/api/chat", body)
        wall_seconds = time.perf_counter() - started
        content = response.get("message", {}).get("content", "")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Model returned invalid JSON: {exc}: {content!r}") from exc

        eval_duration = float(response.get("eval_duration") or 0) / 1e9
        output_tokens = int(response.get("eval_count") or 0)
        return ApiCallResult(
            data=parsed,
            wall_seconds=wall_seconds,
            load_seconds=float(response.get("load_duration") or 0) / 1e9,
            prompt_tokens=int(response.get("prompt_eval_count") or 0),
            output_tokens=output_tokens,
            output_tps=(output_tokens / eval_duration) if eval_duration > 0 else 0.0,
            done_reason=str(response.get("done_reason") or ""),
        )

    def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cannot reach Ollama at {self.base_url}: {exc}") from exc


def normalize_text(text: str) -> str:
    return re.sub(r"[\s，。！？、；：,.!?;:'\"“”‘’（）()\-—]", "", text).lower()


def evidence_is_verbatim(text: str, evidence: str) -> bool:
    normalized_evidence = normalize_text(evidence)
    return bool(normalized_evidence) and normalized_evidence in normalize_text(text)


def has_first_person_context(text: str) -> bool:
    normalized = normalize_text(text)
    self_markers = ("我", "我家", "家里", "客厅用", "卧室用", "全屋用", "预算")
    generic_markers = ("哪一种更适合", "哪种更适合", "什么家庭", "适合有")
    return any(marker in normalized for marker in self_markers) and not any(marker in normalized for marker in generic_markers)


def has_explicit_rejection(text: str) -> bool:
    normalized = normalize_text(text)
    if "为什么" in normalized and ("你不推荐" in normalized or "不推荐" in normalized):
        return False
    return any(marker in normalized for marker in ("我不要", "我不想要", "我不喜欢", "我不考虑", "排除", "不要这个"))


def validate_boolean_evidence(field_name: str, value: str, evidence: str) -> bool:
    normalized = normalize_text(evidence)
    field_terms = {
        "has_pets": ("宠物", "狗", "猫"),
        "has_floor_heating": ("地暖",),
        "has_children": ("小孩", "孩子", "儿童"),
        "has_elderly": ("老人", "长辈"),
        "humid_environment": ("潮湿", "回南天", "湿气"),
    }
    terms = field_terms.get(field_name)
    if terms is None:
        return True
    if not any(term in normalized for term in terms):
        return False
    if value == "no":
        return any(marker in normalized for marker in ("没有", "无", "不是", "不需要"))
    if value == "yes":
        return not any(marker in normalized for marker in ("没有", "无", "不是", "不需要"))
    return False


def apply_guard(text: str, intent_data: dict[str, Any], facts: dict[str, Any]) -> GuardResult:
    accepted: dict[str, list[dict[str, Any]]] = {
        "field_updates": [],
        "priority_updates": [],
        "color_preferences": [],
        "product_preferences": [],
    }
    rejected: list[dict[str, Any]] = []
    intent = str(intent_data.get("intent", "other"))
    explicit_self = bool(intent_data.get("explicit_self_context")) or has_first_person_context(text)

    def reject(kind: str, item: dict[str, Any], reason: str) -> None:
        rejected.append({"kind": kind, "item": item, "reason": reason})

    for item in facts.get("field_updates", []):
        if not isinstance(item, dict):
            reject("field_updates", {"raw": item}, "not_an_object")
            continue
        evidence = str(item.get("evidence", ""))
        field_name = str(item.get("field", ""))
        value = str(item.get("value", ""))
        scope = str(item.get("scope", ""))
        if not evidence_is_verbatim(text, evidence):
            reject("field_updates", item, "evidence_not_verbatim")
            continue
        if field_name not in STATE_FIELDS:
            reject("field_updates", item, "unknown_field")
            continue
        if field_name.startswith("has_") or field_name == "humid_environment":
            if not validate_boolean_evidence(field_name, value, evidence):
                reject("field_updates", item, "boolean_evidence_not_supported")
                continue
        if scope == "persistent" and not explicit_self:
            item = {**item, "scope": "turn_only"}
        if intent in {"ask_reason", "general_product_question"} and item.get("scope") == "persistent":
            reject("field_updates", item, "intent_disallows_persistent_state")
            continue
        if intent == "request_comparison" and item.get("scope") == "persistent" and not explicit_self:
            item = {**item, "scope": "turn_only"}
        accepted["field_updates"].append(item)

    for item in facts.get("priority_updates", []):
        if not isinstance(item, dict):
            reject("priority_updates", {"raw": item}, "not_an_object")
            continue
        evidence = str(item.get("evidence", ""))
        if not evidence_is_verbatim(text, evidence):
            reject("priority_updates", item, "evidence_not_verbatim")
            continue
        if str(item.get("name", "")) not in PRIORITIES:
            reject("priority_updates", item, "unknown_priority")
            continue
        if intent in {"ask_reason", "general_product_question"}:
            reject("priority_updates", item, "intent_disallows_priority_change")
            continue
        if item.get("scope") == "persistent" and not explicit_self:
            item = {**item, "scope": "turn_only"}
        accepted["priority_updates"].append(item)

    for item in facts.get("color_preferences", []):
        if not isinstance(item, dict):
            reject("color_preferences", {"raw": item}, "not_an_object")
            continue
        evidence = str(item.get("evidence", ""))
        if not evidence_is_verbatim(text, evidence):
            reject("color_preferences", item, "evidence_not_verbatim")
            continue
        if item.get("preference") == "reject" and not has_explicit_rejection(text):
            reject("color_preferences", item, "no_explicit_rejection")
            continue
        if item.get("scope") == "persistent" and not explicit_self:
            item = {**item, "scope": "turn_only"}
        accepted["color_preferences"].append(item)

    for item in facts.get("product_preferences", []):
        if not isinstance(item, dict):
            reject("product_preferences", {"raw": item}, "not_an_object")
            continue
        evidence = str(item.get("evidence", ""))
        if not evidence_is_verbatim(text, evidence):
            reject("product_preferences", item, "evidence_not_verbatim")
            continue
        if item.get("preference") == "reject" and (intent != "reject_product" or not has_explicit_rejection(text)):
            reject("product_preferences", item, "no_explicit_product_rejection")
            continue
        if item.get("scope") == "persistent" and not explicit_self:
            item = {**item, "scope": "turn_only"}
        accepted["product_preferences"].append(item)

    return GuardResult(accepted=accepted, rejected=rejected)


def canonical_product(value: str) -> str:
    normalized = normalize_text(value)
    if "spc" in normalized:
        return "SPC"
    if "多层实木" in normalized:
        return "多层实木"
    return value.strip()


def canonical_color(value: str) -> str:
    normalized = normalize_text(value)
    if "灰" in normalized:
        return "灰色"
    for color in ("原木色", "暖色"):
        if color in normalized:
            return color
    return value.strip()


def tuple_set(items: Iterable[tuple[str, str, str]]) -> set[str]:
    return {"|".join(item) for item in items}


def actual_field_set(accepted: dict[str, list[dict[str, Any]]]) -> set[str]:
    return {
        f"{item.get('field')}|{item.get('value')}|{item.get('scope')}"
        for item in accepted["field_updates"]
    }


def actual_priority_set(accepted: dict[str, list[dict[str, Any]]]) -> set[str]:
    return {
        f"{item.get('name')}|{item.get('level')}|{item.get('scope')}"
        for item in accepted["priority_updates"]
    }


def actual_color_pref_set(accepted: dict[str, list[dict[str, Any]]]) -> set[str]:
    return {
        f"{canonical_color(str(item.get('color', '')))}|{item.get('preference')}|{item.get('scope')}"
        for item in accepted["color_preferences"]
    }


def actual_product_pref_set(accepted: dict[str, list[dict[str, Any]]]) -> set[str]:
    return {
        f"{canonical_product(str(item.get('product', '')))}|{item.get('preference')}|{item.get('scope')}"
        for item in accepted["product_preferences"]
    }


def evaluate_case(case: TestCase, intent_result: ApiCallResult, facts_result: ApiCallResult, guard: GuardResult) -> list[str]:
    failures: list[str] = []
    intent = str(intent_result.data.get("intent"))
    if intent != case.expected_intent:
        failures.append(f"intent expected={case.expected_intent} actual={intent}")

    products = {canonical_product(str(value)) for value in intent_result.data.get("mentioned_products", [])}
    for expected in case.expected_products:
        if canonical_product(expected) not in products:
            failures.append(f"missing mentioned product: {expected}")

    colors = {canonical_color(str(value)) for value in intent_result.data.get("mentioned_colors", [])}
    for expected in case.expected_colors:
        if canonical_color(expected) not in colors:
            failures.append(f"missing mentioned color: {expected}")

    fields = actual_field_set(guard.accepted)
    for expected in tuple_set(case.expected_fields):
        if expected not in fields:
            failures.append(f"missing field update: {expected}")

    actual_field_names = {item.get("field") for item in guard.accepted["field_updates"]}
    for forbidden in case.forbidden_fields:
        if forbidden in actual_field_names:
            failures.append(f"forbidden field update accepted: {forbidden}")

    priorities = actual_priority_set(guard.accepted)
    for expected in tuple_set(case.expected_priorities):
        if expected not in priorities:
            failures.append(f"missing priority update: {expected}")

    color_prefs = actual_color_pref_set(guard.accepted)
    for expected in tuple_set(case.expected_color_preferences):
        if expected not in color_prefs:
            failures.append(f"missing color preference: {expected}")

    product_prefs = actual_product_pref_set(guard.accepted)
    for expected in tuple_set(case.expected_product_preferences):
        if expected not in product_prefs:
            failures.append(f"missing product preference: {expected}")

    if case.require_no_persistent_changes:
        persistent_items = []
        for items in guard.accepted.values():
            persistent_items.extend(item for item in items if item.get("scope") == "persistent")
        if persistent_items:
            failures.append(f"unexpected persistent changes: {persistent_items}")

    if case.expected_intent in {"ask_reason", "general_product_question"}:
        accepted_items = [item for items in guard.accepted.values() for item in items]
        if accepted_items:
            failures.append(f"question intent must not modify state: {accepted_items}")

    if case.expected_intent == "request_comparison":
        if not bool(intent_result.data.get("recommendation_requested")):
            failures.append("comparison must set recommendation_requested=true")
        if len(products) < 2:
            failures.append("comparison must mention at least two products")

    if intent_result.done_reason != "stop":
        failures.append(f"intent done_reason={intent_result.done_reason}")
    if facts_result.done_reason not in {"stop", "skipped"}:
        failures.append(f"facts done_reason={facts_result.done_reason}")

    return failures


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(p * len(ordered)) - 1))
    return ordered[index]


def format_current_state(state: dict[str, Any]) -> str:
    return json.dumps(state, ensure_ascii=False, separators=(",", ":"))


def run_case(client: OllamaClient, case: TestCase) -> CaseResult:
    intent_user_prompt = (
        f"当前客户状态：{format_current_state(case.current_state)}\n"
        f"顾客最新话语：{case.text}\n"
        "请完成意图分类。"
    )
    intent_result = client.structured_chat(
        INTENT_SYSTEM_PROMPT,
        intent_user_prompt,
        INTENT_SCHEMA,
        num_predict=220,
    )

    intent_name = str(intent_result.data.get("intent", "other"))
    explicit_self = bool(intent_result.data.get("explicit_self_context")) or has_first_person_context(case.text)
    should_extract_facts = intent_name not in {"ask_reason", "general_product_question", "other"} or explicit_self

    if should_extract_facts:
        facts_user_prompt = (
            f"当前客户状态：{format_current_state(case.current_state)}\n"
            f"已分类意图：{json.dumps(intent_result.data, ensure_ascii=False, separators=(',', ':'))}\n"
            f"顾客最新话语：{case.text}\n"
            "请提取有原文证据的事实。"
        )
        facts_result = client.structured_chat(
            FACT_SYSTEM_PROMPT,
            facts_user_prompt,
            FACT_SCHEMA,
            num_predict=420,
        )
    else:
        facts_result = ApiCallResult(
            data={
                "field_updates": [],
                "priority_updates": [],
                "color_preferences": [],
                "product_preferences": [],
            },
            wall_seconds=0.0,
            load_seconds=0.0,
            prompt_tokens=0,
            output_tokens=0,
            output_tps=0.0,
            done_reason="skipped",
        )
    guard = apply_guard(case.text, intent_result.data, facts_result.data)
    failures = evaluate_case(case, intent_result, facts_result, guard)
    return CaseResult(
        case_id=case.case_id,
        passed=not failures,
        failures=failures,
        guard_rejections=guard.rejected,
        intent=intent_result.data,
        raw_facts=facts_result.data,
        accepted_facts=guard.accepted,
        intent_wall_seconds=intent_result.wall_seconds,
        facts_wall_seconds=facts_result.wall_seconds,
        total_wall_seconds=intent_result.wall_seconds + facts_result.wall_seconds,
        output_tokens=intent_result.output_tokens + facts_result.output_tokens,
        done_reasons=(intent_result.done_reason, facts_result.done_reason),
    )


def print_case_result(result: CaseResult, verbose: bool) -> None:
    status = "PASS" if result.passed else "FAIL"
    print(
        f"[{status}] {result.case_id:<30} "
        f"intent={result.intent.get('intent'):<28} "
        f"latency={result.total_wall_seconds:5.2f}s"
    )
    if result.failures:
        for failure in result.failures:
            print(f"       - {failure}")
    if verbose or not result.passed:
        print("       intent:", json.dumps(result.intent, ensure_ascii=False))
        print("       accepted:", json.dumps(result.accepted_facts, ensure_ascii=False))
        if result.guard_rejections:
            print("       guard_rejections:", json.dumps(result.guard_rejections, ensure_ascii=False))
        if verbose:
            print("       raw_facts:", json.dumps(result.raw_facts, ensure_ascii=False))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Two-stage local LLM benchmark for wood-floor dialogue intent, fact extraction, and validation guards."
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--repeat", type=int, default=1, help="Repeat the full suite N times.")
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--report", type=Path, default=None, help="Optional JSON report path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.repeat < 1:
        raise SystemExit("--repeat must be >= 1")

    client = OllamaClient(args.base_url, args.model, args.timeout)
    print(f"Model: {args.model}")
    print(f"Ollama: {args.base_url}")
    print("Preloading model...")
    preload_seconds = client.preload()
    print(f"Preload completed in {preload_seconds:.3f}s\n")

    all_results: list[CaseResult] = []
    started_at = datetime.now().astimezone().isoformat()
    for repetition in range(1, args.repeat + 1):
        if args.repeat > 1:
            print(f"=== Repetition {repetition}/{args.repeat} ===")
        for case in TEST_CASES:
            try:
                result = run_case(client, case)
            except Exception as exc:  # benchmark must report a failed case instead of stopping the whole suite
                result = CaseResult(
                    case_id=case.case_id,
                    passed=False,
                    failures=[f"exception: {exc}"],
                    guard_rejections=[],
                    intent={},
                    raw_facts={},
                    accepted_facts={
                        "field_updates": [],
                        "priority_updates": [],
                        "color_preferences": [],
                        "product_preferences": [],
                    },
                    intent_wall_seconds=0,
                    facts_wall_seconds=0,
                    total_wall_seconds=0,
                    output_tokens=0,
                    done_reasons=("", ""),
                )
            all_results.append(result)
            print_case_result(result, args.verbose)
        print()

    passed = sum(1 for result in all_results if result.passed)
    total = len(all_results)
    latencies = [result.total_wall_seconds for result in all_results if result.total_wall_seconds > 0]
    print("=== Summary ===")
    print(f"Passed: {passed}/{total} ({(passed / total * 100):.1f}%)")
    if latencies:
        print(f"Latency mean: {statistics.mean(latencies):.3f}s")
        print(f"Latency P50:  {statistics.median(latencies):.3f}s")
        print(f"Latency P95:  {percentile(latencies, 0.95):.3f}s")
        print(f"Latency max:  {max(latencies):.3f}s")

    report = {
        "started_at": started_at,
        "model": args.model,
        "base_url": args.base_url,
        "preload_seconds": preload_seconds,
        "repeat": args.repeat,
        "passed": passed,
        "total": total,
        "pass_rate": passed / total,
        "latency": {
            "mean": statistics.mean(latencies) if latencies else None,
            "p50": statistics.median(latencies) if latencies else None,
            "p95": percentile(latencies, 0.95) if latencies else None,
            "max": max(latencies) if latencies else None,
        },
        "results": [asdict(result) for result in all_results],
    }

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Report: {args.report}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
