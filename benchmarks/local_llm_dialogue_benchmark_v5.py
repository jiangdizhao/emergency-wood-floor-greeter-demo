from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import local_llm_dialogue_benchmark as engine
import local_llm_dialogue_benchmark_v4 as v4

VERSION = "5.0-cross-provider"
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

# Public standard prices when v5 was implemented. CLI flags can override them.
OPENAI_PRICES_PER_MTOK = {
    "luna": {"input": 1.0, "output": 6.0},
    "terra": {"input": 2.5, "output": 15.0},
}

INTENTS = (
    "provide_or_modify_needs",
    "request_recommendation",
    "request_comparison",
    "ask_reason",
    "reject_product",
    "reject_color",
    "general_product_question",
    "other",
)
FIELDS = (
    "room_type",
    "budget",
    "style",
    "has_pets",
    "has_floor_heating",
    "has_children",
    "has_elderly",
    "humid_environment",
)
ROOMS = ("客厅", "卧室", "全屋", "厨房", "书房", "儿童房", "老人房")
BUDGETS = ("经济", "中等", "偏高", "高端")
BOOLEAN_FIELDS = {
    "has_pets",
    "has_floor_heating",
    "has_children",
    "has_elderly",
    "humid_environment",
}
PRIORITIES = tuple(engine.PRIORITIES)
UPDATE_KINDS = ("field_updates", "priority_updates", "color_preferences", "product_preferences")
QUESTION_INTENTS = {"ask_reason", "general_product_question"}
RECOMMENDATION_INTENTS = {"request_recommendation", "request_comparison"}

PARSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "intent": {"type": "string", "enum": list(INTENTS)},
        "is_question": {"type": "boolean"},
        "explicit_self_context": {"type": "boolean"},
        "recommendation_requested": {"type": "boolean"},
        "mentioned_products": {"type": "array", "items": {"type": "string"}},
        "mentioned_colors": {"type": "array", "items": {"type": "string"}},
        "field_updates": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "field": {"type": "string", "enum": list(FIELDS)},
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
                    "name": {"type": "string", "enum": list(PRIORITIES)},
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
        "coverage_items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "evidence": {"type": "string"},
                    "disposition": {
                        "type": "string",
                        "enum": ["state_change", "intent_only", "context_only", "ambiguous"],
                    },
                    "reason": {"type": "string"},
                },
                "required": ["evidence", "disposition", "reason"],
            },
        },
        "coverage_complete": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "needs_clarification": {"type": "boolean"},
        "clarification_reason": {"type": "string"},
    },
    "required": [
        "intent",
        "is_question",
        "explicit_self_context",
        "recommendation_requested",
        "mentioned_products",
        "mentioned_colors",
        "field_updates",
        "priority_updates",
        "color_preferences",
        "product_preferences",
        "coverage_items",
        "coverage_complete",
        "confidence",
        "needs_clarification",
        "clarification_reason",
    ],
}

SYSTEM_PROMPT = """
你是木地板门店对话系统的单轮结构化解析器。只解析顾客最新一句话，不推荐具体产品，不使用常识补充未表达的信息。

意图定义：
- provide_or_modify_needs：陈述或修改需求，但没有要求立即推荐；
- request_recommendation：明确要求推荐或选择最合适方案；
- request_comparison：比较两个或更多产品或类别；
- ask_reason：追问先前推荐或未推荐某产品的原因；
- reject_product：明确排除某个产品；
- reject_color：明确拒绝颜色，可同时提出替代颜色；
- general_product_question：询问单个产品的属性、能力或事实；
- other：以上均不符合。

解析规则：
1. 一句话可包含多个事实或动作。primary intent 不得阻止你提取同一句中的房间、预算、家庭情况、优先级或拒绝项。
2. 只提取最新话语明确表达的事实；当前状态只用于理解“改成、不是、其实”等修改，不得把旧状态复制成新更新。
3. 纠正或否定时只输出最终含义。没有提到不等于 no；不得从宠物推断耐磨、潮湿或好清洁。
4. evidence 必须逐字复制最新话语中的连续片段。不得改写、补字或输出空 evidence。
5. scope=persistent 仅用于顾客本人或其家庭的长期状态；泛指、假设、比较条件使用 turn_only。
6. 规范值：房间=客厅/卧室/全屋/厨房/书房/儿童房/老人房；预算=经济/中等/偏高/高端；布尔=yes/no。
7. 优先级 name 只能使用 Schema 枚举；level=high/medium/low/remove。
8. 不得输出“未知”、斜杠枚举说明、占位符、空值或不存在的产品。
9. recommendation_requested 只在 request_recommendation 或 request_comparison 时为 true。
10. 对最新话语的每个有意义片段输出 coverage_items：
   - state_change：该片段形成状态或偏好更新；
   - intent_only：只用于判断意图；
   - context_only：明确但不应写入状态；
   - ambiguous：无法可靠解析。
   evidence 仍必须逐字复制。若有未覆盖或含糊片段，coverage_complete=false；需要顾客确认时 needs_clarification=true。
11. confidence 表示整份解析的可靠程度，不要固定输出高置信度。

只输出符合 JSON Schema 的对象。
""".strip()


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0


@dataclass
class ProviderCall:
    provider: str
    model: str
    ok: bool
    seconds: float
    raw_parse: dict[str, Any]
    usage: Usage = field(default_factory=Usage)
    estimated_cost_usd: float = 0.0
    error: str = ""
    response_status: str = ""


@dataclass
class Sanitized:
    parse: dict[str, Any]
    accepted: dict[str, list[dict[str, Any]]]
    rejected: list[dict[str, Any]]
    coverage_items: list[dict[str, str]]
    validation_errors: list[str]
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
    sanitized_parse: dict[str, Any]
    accepted: dict[str, list[dict[str, Any]]]
    rejected: list[dict[str, Any]]
    coverage_items: list[dict[str, str]]
    validation_errors: list[str]
    gate_reasons: list[str]
    gate_passed: bool


@dataclass
class ModeCaseResult:
    case_id: str
    category: str
    mode: str
    passed: bool
    failures: list[str]
    selected_provider: str
    selected_model: str
    escalated: bool
    attempts: list[Attempt]
    final_parse: dict[str, Any]
    accepted: dict[str, list[dict[str, Any]]]
    latency_seconds: float
    estimated_cost_usd: float


class OllamaProvider:
    def __init__(self, base_url: str, model: str, timeout: float):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self.base_url + "/api/chat",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cannot reach Ollama at {self.base_url}: {exc}") from exc

    def preload(self) -> float:
        started = time.perf_counter()
        self._post({"model": self.model, "messages": [], "stream": False, "keep_alive": KEEP_ALIVE})
        return time.perf_counter() - started

    def parse(self, text: str, state: dict[str, Any]) -> ProviderCall:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt(text, state)},
            ],
            "stream": False,
            "think": False,
            "format": PARSE_SCHEMA,
            "keep_alive": KEEP_ALIVE,
            "options": {"num_ctx": 4096, "num_predict": 1200, "temperature": 0},
        }
        started = time.perf_counter()
        try:
            response = self._post(body)
            content = str(response.get("message", {}).get("content") or "")
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise RuntimeError("Ollama structured output is not a JSON object")
            return ProviderCall(
                provider="qwen",
                model=self.model,
                ok=True,
                seconds=time.perf_counter() - started,
                raw_parse=parsed,
                usage=Usage(
                    input_tokens=int(response.get("prompt_eval_count") or 0),
                    output_tokens=int(response.get("eval_count") or 0),
                ),
                response_status=str(response.get("done_reason") or ""),
            )
        except Exception as exc:
            return ProviderCall(
                provider="qwen",
                model=self.model,
                ok=False,
                seconds=time.perf_counter() - started,
                raw_parse={},
                error=f"{type(exc).__name__}: {exc}",
            )


class OpenAIProvider:
    def __init__(
        self,
        provider_name: str,
        base_url: str,
        model: str,
        timeout: float,
        api_key: str,
        input_price_per_mtok: float,
        output_price_per_mtok: float,
    ):
        self.provider_name = provider_name
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.api_key = api_key
        self.input_price_per_mtok = input_price_per_mtok
        self.output_price_per_mtok = output_price_per_mtok

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": "Bearer " + self.api_key,
        }
        project = os.environ.get("OPENAI_PROJECT_ID", "").strip()
        organization = os.environ.get("OPENAI_ORG_ID", "").strip()
        if project:
            headers["OpenAI-Project"] = project
        if organization:
            headers["OpenAI-Organization"] = organization
        request = urllib.request.Request(
            self.base_url + "/responses",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cannot reach OpenAI at {self.base_url}: {exc}") from exc

    @staticmethod
    def output_text(response: dict[str, Any]) -> str:
        direct = response.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct
        parts: list[str] = []
        for item in response.get("output", []) or []:
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []) or []:
                if not isinstance(content, dict):
                    continue
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    parts.append(content["text"])
                elif content.get("type") == "refusal":
                    raise RuntimeError("OpenAI refused the structured parsing request")
        return "".join(parts)

    def parse(self, text: str, state: dict[str, Any]) -> ProviderCall:
        body = {
            "model": self.model,
            "input": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt(text, state)},
            ],
            "reasoning": {"effort": "none"},
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "flooring_dialogue_parse",
                    "strict": True,
                    "schema": PARSE_SCHEMA,
                }
            },
            "max_output_tokens": 1800,
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
                raise RuntimeError("OpenAI structured output is not a JSON object")
            usage_raw = response.get("usage") or {}
            details = usage_raw.get("input_tokens_details") or {}
            usage = Usage(
                input_tokens=int(usage_raw.get("input_tokens") or 0),
                output_tokens=int(usage_raw.get("output_tokens") or 0),
                cached_input_tokens=int(details.get("cached_tokens") or 0),
            )
            estimated_cost = (
                usage.input_tokens * self.input_price_per_mtok
                + usage.output_tokens * self.output_price_per_mtok
            ) / 1_000_000
            return ProviderCall(
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
            return ProviderCall(
                provider=self.provider_name,
                model=self.model,
                ok=False,
                seconds=time.perf_counter() - started,
                raw_parse={},
                error=f"{type(exc).__name__}: {exc}",
            )


def user_prompt(text: str, state: dict[str, Any]) -> str:
    return (
        "当前客户状态（仅用于理解修改，不得把未在最新话语中重申的旧值当作新更新）：\n"
        + json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        + "\n\n顾客最新话语：\n"
        + text
        + "\n\n请解析这一个回合。"
    )


def compact(text: str) -> str:
    return engine.norm(text)


def unique_strings(values: Iterable[Any]) -> list[str]:
    output: list[str] = []
    for value in values:
        item = re.sub(r"\s+", "", str(value or "")).strip()
        if item and item not in output:
            output.append(item)
    return output


def canonical_product(value: str) -> str:
    normalized = compact(value)
    if normalized in {"spc", "spc地板", "石塑", "石塑地板"}:
        return "SPC"
    if any(token in normalized for token in ("多层实木", "实木复合")):
        return "多层实木"
    return re.sub(r"\s+", "", value).strip()


def canonical_color(value: str) -> str:
    return re.sub(r"\s+", "", value).strip()


def canonical_value(field_name: str, value: str) -> str:
    raw = re.sub(r"\s+", "", str(value or "")).strip()
    lower = raw.lower()
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
        return raw if raw in BUDGETS else mapping.get(lower, mapping.get(raw, raw))
    if field_name == "room_type":
        return next((room for room in ROOMS if room in raw), raw)
    if field_name in BOOLEAN_FIELDS:
        mapping = {"true": "yes", "false": "no", "有": "yes", "没有": "no", "是": "yes", "否": "no"}
        return mapping.get(lower, mapping.get(raw, raw))
    return raw


def normalized_spans(text: str, evidence_values: Iterable[str]) -> set[int]:
    """Return character positions covered after whitespace/punctuation normalization."""
    source = compact(text)
    covered: set[int] = set()
    for evidence in evidence_values:
        needle = compact(evidence)
        if not needle:
            continue
        start = source.find(needle)
        if start >= 0:
            covered.update(range(start, start + len(needle)))
    return covered


def generic_negative_marker(evidence: str) -> bool:
    normalized = compact(evidence)
    return any(marker in normalized for marker in ("不", "没", "无", "否", "未"))


def sanitize(text: str, raw: dict[str, Any], min_confidence: float, min_coverage: float) -> Sanitized:
    accepted = {name: [] for name in UPDATE_KINDS}
    rejected: list[dict[str, Any]] = []
    validation_errors: list[str] = []

    raw_intent = str(raw.get("intent") or "other")
    intent = raw_intent if raw_intent in INTENTS else "other"
    if intent != raw_intent:
        validation_errors.append(f"invalid_intent:{raw_intent!r}")

    explicit_self_context = bool(raw.get("explicit_self_context"))
    raw_recommendation = bool(raw.get("recommendation_requested"))
    recommendation_requested = intent in RECOMMENDATION_INTENTS
    if raw_recommendation != recommendation_requested:
        validation_errors.append(
            f"recommendation_requested_inconsistent:provider={raw_recommendation},intent={intent}"
        )

    target_scope = "turn_only" if intent in RECOMMENDATION_INTENTS and not explicit_self_context else "persistent"
    provider_products = [canonical_product(x) for x in raw.get("mentioned_products", []) or []]
    provider_colors = [canonical_color(x) for x in raw.get("mentioned_colors", []) or []]
    mentioned_products = unique_strings([*provider_products, *engine.products(text)])
    mentioned_colors = unique_strings([*provider_colors, *engine.colors(text)])

    def reject(kind: str, item: Any, reason: str) -> None:
        rejected.append({"kind": kind, "item": item, "reason": reason})

    field_candidates: dict[str, dict[str, Any]] = {}
    field_conflicts: set[str] = set()
    for item in raw.get("field_updates", []) or []:
        if not isinstance(item, dict):
            reject("field_updates", item, "not_object")
            continue
        field_name = str(item.get("field") or "")
        value = canonical_value(field_name, str(item.get("value") or ""))
        evidence = str(item.get("evidence") or "")
        if field_name not in FIELDS:
            reject("field_updates", item, "unknown_field")
            continue
        if not engine.verbatim(text, evidence):
            reject("field_updates", item, "evidence_not_verbatim")
            continue
        if field_name == "room_type" and value not in ROOMS:
            reject("field_updates", item, "invalid_room_value")
            continue
        if field_name == "budget" and value not in BUDGETS:
            reject("field_updates", item, "invalid_budget_value")
            continue
        if field_name in BOOLEAN_FIELDS and value not in {"yes", "no"}:
            reject("field_updates", item, "invalid_boolean_value")
            continue
        if field_name == "style" and not value:
            reject("field_updates", item, "empty_style")
            continue
        if field_name in BOOLEAN_FIELDS and value == "no" and not generic_negative_marker(evidence):
            reject("field_updates", item, "negative_value_without_negative_evidence")
            continue
        if field_name in BOOLEAN_FIELDS and value == "yes" and generic_negative_marker(evidence):
            reject("field_updates", item, "positive_value_with_negative_evidence")
            continue
        canonical = {"field": field_name, "value": value, "scope": target_scope, "evidence": evidence}
        previous = field_candidates.get(field_name)
        if previous and previous["value"] != value:
            field_conflicts.add(field_name)
        else:
            field_candidates[field_name] = canonical
    for field_name, item in field_candidates.items():
        if field_name in field_conflicts:
            reject("field_updates", item, "conflicting_values")
            validation_errors.append(f"conflicting_field_values:{field_name}")
        else:
            accepted["field_updates"].append(item)

    priority_candidates: dict[str, dict[str, Any]] = {}
    priority_conflicts: set[str] = set()
    for item in raw.get("priority_updates", []) or []:
        if not isinstance(item, dict):
            reject("priority_updates", item, "not_object")
            continue
        name = str(item.get("name") or "")
        level = str(item.get("level") or "")
        evidence = str(item.get("evidence") or "")
        if name not in PRIORITIES:
            reject("priority_updates", item, "unknown_priority")
            continue
        if level not in {"high", "medium", "low", "remove"}:
            reject("priority_updates", item, "invalid_level")
            continue
        if not engine.verbatim(text, evidence):
            reject("priority_updates", item, "evidence_not_verbatim")
            continue
        canonical = {"name": name, "level": level, "scope": target_scope, "evidence": evidence}
        previous = priority_candidates.get(name)
        if previous and previous["level"] != level:
            priority_conflicts.add(name)
        else:
            priority_candidates[name] = canonical
    for name, item in priority_candidates.items():
        if name in priority_conflicts:
            reject("priority_updates", item, "conflicting_levels")
            validation_errors.append(f"conflicting_priority_levels:{name}")
        else:
            accepted["priority_updates"].append(item)

    color_candidates: dict[tuple[str, str], dict[str, Any]] = {}
    for item in raw.get("color_preferences", []) or []:
        if not isinstance(item, dict):
            reject("color_preferences", item, "not_object")
            continue
        color = canonical_color(str(item.get("color") or ""))
        preference = str(item.get("preference") or "")
        evidence = str(item.get("evidence") or "")
        if not color or preference not in {"prefer", "reject"}:
            reject("color_preferences", item, "invalid_color_preference")
            continue
        if not engine.verbatim(text, evidence):
            reject("color_preferences", item, "evidence_not_verbatim")
            continue
        color_candidates[(color, preference)] = {
            "color": color,
            "preference": preference,
            "scope": target_scope,
            "evidence": evidence,
        }
    accepted["color_preferences"].extend(color_candidates.values())

    product_candidates: dict[tuple[str, str], dict[str, Any]] = {}
    for item in raw.get("product_preferences", []) or []:
        if not isinstance(item, dict):
            reject("product_preferences", item, "not_object")
            continue
        product = canonical_product(str(item.get("product") or ""))
        preference = str(item.get("preference") or "")
        evidence = str(item.get("evidence") or "")
        if not product or product == "未知" or preference not in {"prefer", "reject"}:
            reject("product_preferences", item, "invalid_product_preference")
            continue
        if not engine.verbatim(text, evidence):
            reject("product_preferences", item, "evidence_not_verbatim")
            continue
        if preference == "reject" and intent != "reject_product":
            reject("product_preferences", item, "rejection_requires_reject_product_intent")
            continue
        product_candidates[(product, preference)] = {
            "product": product,
            "preference": preference,
            "scope": target_scope,
            "evidence": evidence,
        }
    accepted["product_preferences"].extend(product_candidates.values())

    if intent in QUESTION_INTENTS:
        for kind in UPDATE_KINDS:
            for item in accepted[kind]:
                reject(kind, item, "question_intent_disallows_state_change")
            accepted[kind] = []

    coverage_items: list[dict[str, str]] = []
    for item in raw.get("coverage_items", []) or []:
        if not isinstance(item, dict):
            reject("coverage_items", item, "not_object")
            continue
        evidence = str(item.get("evidence") or "")
        disposition = str(item.get("disposition") or "")
        reason = str(item.get("reason") or "")
        if disposition not in {"state_change", "intent_only", "context_only", "ambiguous"}:
            reject("coverage_items", item, "invalid_disposition")
            continue
        if not engine.verbatim(text, evidence):
            reject("coverage_items", item, "evidence_not_verbatim")
            continue
        coverage_items.append({"evidence": evidence, "disposition": disposition, "reason": reason})

    parse = {
        "intent": intent,
        "is_question": bool(raw.get("is_question")),
        "explicit_self_context": explicit_self_context,
        "recommendation_requested": recommendation_requested,
        "mentioned_products": mentioned_products,
        "mentioned_colors": mentioned_colors,
        "coverage_complete": bool(raw.get("coverage_complete")),
        "confidence": float(raw.get("confidence") or 0.0),
        "needs_clarification": bool(raw.get("needs_clarification")),
        "clarification_reason": str(raw.get("clarification_reason") or ""),
    }

    gate_reasons = list(validation_errors)
    if rejected:
        gate_reasons.append(f"rejected_items:{len(rejected)}")
    if parse["confidence"] < min_confidence:
        gate_reasons.append(f"low_confidence:{parse['confidence']:.3f}<{min_confidence:.3f}")
    if parse["needs_clarification"]:
        gate_reasons.append("provider_requested_clarification")
    if not parse["coverage_complete"]:
        gate_reasons.append("coverage_not_complete")
    if any(item["disposition"] == "ambiguous" for item in coverage_items):
        gate_reasons.append("ambiguous_coverage_item")

    evidence_values = [item["evidence"] for item in coverage_items]
    evidence_values.extend(
        str(item.get("evidence") or "") for kind in UPDATE_KINDS for item in accepted[kind]
    )
    source_length = len(compact(text))
    coverage_ratio = len(normalized_spans(text, evidence_values)) / source_length if source_length else 1.0
    parse["coverage_ratio"] = coverage_ratio
    if coverage_ratio < min_coverage:
        gate_reasons.append(f"coverage_ratio:{coverage_ratio:.3f}<{min_coverage:.3f}")

    gate_reasons = list(dict.fromkeys(gate_reasons))
    return Sanitized(
        parse=parse,
        accepted=accepted,
        rejected=rejected,
        coverage_items=coverage_items,
        validation_errors=validation_errors,
        gate_reasons=gate_reasons,
        gate_passed=not gate_reasons,
    )


def empty_sanitized(error: str) -> Sanitized:
    return Sanitized(
        parse={
            "intent": "other",
            "is_question": False,
            "explicit_self_context": False,
            "recommendation_requested": False,
            "mentioned_products": [],
            "mentioned_colors": [],
            "coverage_complete": False,
            "coverage_ratio": 0.0,
            "confidence": 0.0,
            "needs_clarification": True,
            "clarification_reason": error,
        },
        accepted={name: [] for name in UPDATE_KINDS},
        rejected=[],
        coverage_items=[],
        validation_errors=[error],
        gate_reasons=[error],
        gate_passed=False,
    )


def to_attempt(call: ProviderCall, sanitized: Sanitized) -> Attempt:
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
        sanitized_parse=sanitized.parse,
        accepted=sanitized.accepted,
        rejected=sanitized.rejected,
        coverage_items=sanitized.coverage_items,
        validation_errors=sanitized.validation_errors,
        gate_reasons=sanitized.gate_reasons,
        gate_passed=sanitized.gate_passed,
    )


def evaluate(spec: v4.Spec, parse: dict[str, Any], accepted: dict[str, list[dict[str, Any]]]) -> list[str]:
    case = spec.case
    failures: list[str] = []
    if parse.get("intent") != case.intent:
        failures.append(f"intent expected={case.intent} actual={parse.get('intent')}")
    if spec.recommendation is not None and bool(parse.get("recommendation_requested")) != spec.recommendation:
        failures.append(
            f"recommendation_requested expected={spec.recommendation} actual={bool(parse.get('recommendation_requested'))}"
        )
    if spec.self_context is not None and bool(parse.get("explicit_self_context")) != spec.self_context:
        failures.append(
            f"explicit_self_context expected={spec.self_context} actual={bool(parse.get('explicit_self_context'))}"
        )
    for product in case.products:
        if product not in parse.get("mentioned_products", []):
            failures.append(f"missing mentioned product: {product}")
    for color in case.colors:
        if color not in parse.get("mentioned_colors", []):
            failures.append(f"missing mentioned color: {color}")

    actual_fields = {
        (str(item.get("field")), str(item.get("value")), str(item.get("scope")))
        for item in accepted["field_updates"]
    }
    for expected in case.fields:
        if expected not in actual_fields:
            failures.append("missing field update: " + "|".join(expected))
    for forbidden in case.forbidden_fields:
        if any(item.get("field") == forbidden for item in accepted["field_updates"]):
            failures.append(f"forbidden field update accepted: {forbidden}")

    actual_priorities = {
        (str(item.get("name")), str(item.get("level")), str(item.get("scope")))
        for item in accepted["priority_updates"]
    }
    for expected in case.priorities:
        if expected not in actual_priorities:
            failures.append("missing priority update: " + "|".join(expected))

    actual_colors = {
        (str(item.get("color")), str(item.get("preference")), str(item.get("scope")))
        for item in accepted["color_preferences"]
    }
    for expected in case.color_prefs:
        if expected not in actual_colors:
            failures.append("missing color preference: " + "|".join(expected))

    actual_products = {
        (str(item.get("product")), str(item.get("preference")), str(item.get("scope")))
        for item in accepted["product_preferences"]
    }
    for expected in case.product_prefs:
        if expected not in actual_products:
            failures.append("missing product preference: " + "|".join(expected))

    if case.no_persistent and any(
        item.get("scope") == "persistent" for items in accepted.values() for item in items
    ):
        failures.append("unexpected persistent state change")
    return failures


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
    index = max(0, min(len(ordered) - 1, math.ceil(p * len(ordered)) - 1))
    return ordered[index]


def show_result(result: ModeCaseResult, verbose: bool) -> None:
    status = "PASS" if result.passed else "FAIL"
    print(
        f"[{status}] {result.mode:<22} {result.case_id:<36} "
        f"provider={result.selected_provider:<6} latency={result.latency_seconds:6.2f}s "
        f"cost=${result.estimated_cost_usd:.6f}"
    )
    for failure in result.failures:
        print("       -", failure)
    if verbose or not result.passed:
        for attempt in result.attempts:
            print(
                f"       attempt {attempt.provider}/{attempt.model}: ok={attempt.ok} "
                f"gate={attempt.gate_passed} latency={attempt.seconds:.3f}s "
                f"cost=${attempt.estimated_cost_usd:.6f}"
            )
            if attempt.error:
                print("         error:", attempt.error)
            if attempt.gate_reasons:
                print("         gate_reasons:", json.dumps(attempt.gate_reasons, ensure_ascii=False))
            if verbose:
                print("         raw_parse:", json.dumps(attempt.raw_parse, ensure_ascii=False))
                print("         sanitized_parse:", json.dumps(attempt.sanitized_parse, ensure_ascii=False))
                print("         accepted:", json.dumps(attempt.accepted, ensure_ascii=False))
                print("         coverage_items:", json.dumps(attempt.coverage_items, ensure_ascii=False))
                if attempt.rejected:
                    print("         rejected:", json.dumps(attempt.rejected, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cross-provider v5 benchmark for Qwen, OpenAI Luna/Terra, and adaptive cascades."
    )
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
    parser.add_argument("--gate-min-coverage", type=float, default=0.60)
    parser.add_argument("--luna-input-price", type=float, default=OPENAI_PRICES_PER_MTOK["luna"]["input"])
    parser.add_argument("--luna-output-price", type=float, default=OPENAI_PRICES_PER_MTOK["luna"]["output"])
    parser.add_argument("--terra-input-price", type=float, default=OPENAI_PRICES_PER_MTOK["terra"]["input"])
    parser.add_argument("--terra-output-price", type=float, default=OPENAI_PRICES_PER_MTOK["terra"]["output"])
    args = parser.parse_args()

    if args.repeat < 1:
        raise SystemExit("--repeat must be >= 1")
    if not 0 <= args.gate_min_confidence <= 1:
        raise SystemExit("--gate-min-confidence must be between 0 and 1")
    if not 0 <= args.gate_min_coverage <= 1:
        raise SystemExit("--gate-min-coverage must be between 0 and 1")

    modes = list(MODES) if args.all_modes else list(dict.fromkeys(args.mode or ["qwen_only"]))
    selected_specs = [
        spec for spec in v4.CASES if not args.category or spec.category in set(args.category)
    ]
    selected_specs = [
        spec for spec in selected_specs if not args.case_ids or spec.case.id in set(args.case_ids)
    ]
    if args.list_cases:
        for spec in selected_specs:
            print(f"{spec.case.id}\t{spec.category}\t{spec.case.text}")
        return 0
    if not selected_specs:
        raise SystemExit("No cases selected")

    required_providers = {provider for mode in modes for provider in provider_order(mode)}
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if required_providers & {"luna", "terra"} and not api_key:
        raise SystemExit(
            "OPENAI_API_KEY is not set in this terminal. The benchmark reads the key only from the process "
            "environment; it never accepts the key as a CLI argument or writes it to a report."
        )

    providers: dict[str, Any] = {}
    if "qwen" in required_providers:
        providers["qwen"] = OllamaProvider(args.ollama_url, args.qwen_model, args.timeout)
    if "luna" in required_providers:
        providers["luna"] = OpenAIProvider(
            "luna", args.openai_base_url, args.luna_model, args.timeout, api_key,
            args.luna_input_price, args.luna_output_price,
        )
    if "terra" in required_providers:
        providers["terra"] = OpenAIProvider(
            "terra", args.openai_base_url, args.terra_model, args.timeout, api_key,
            args.terra_input_price, args.terra_output_price,
        )

    print(f"Benchmark v{VERSION}")
    print("Modes:", ", ".join(modes))
    print(f"Cases: {len(selected_specs)} x repeat {args.repeat}")
    print(f"Gate: confidence>={args.gate_min_confidence:.2f}, coverage>={args.gate_min_coverage:.2f}")
    print(f"Qwen model: {args.qwen_model}")
    if required_providers & {"luna", "terra"}:
        print(f"OpenAI Luna model: {args.luna_model}")
        print(f"OpenAI Terra model: {args.terra_model}")
        print("OPENAI_API_KEY: loaded from environment (value hidden)")
    preload_seconds = None
    if "qwen" in providers:
        print("Preloading Qwen...")
        preload_seconds = providers["qwen"].preload()
        print(f"Qwen preload completed in {preload_seconds:.3f}s")
    print()

    # A provider is called once per case/repetition. All modes reuse that exact response,
    # so the comparison isolates provider and routing effects without duplicating API cost.
    call_cache: dict[tuple[int, str, str], tuple[ProviderCall, Sanitized]] = {}
    results: list[ModeCaseResult] = []
    stopped = False

    def get_call(rep: int, provider_name: str, spec: v4.Spec) -> tuple[ProviderCall, Sanitized]:
        key = (rep, provider_name, spec.case.id)
        if key not in call_cache:
            call = providers[provider_name].parse(spec.case.text, spec.case.state)
            sanitized = (
                sanitize(
                    spec.case.text,
                    call.raw_parse,
                    args.gate_min_confidence,
                    args.gate_min_coverage,
                )
                if call.ok
                else empty_sanitized(call.error)
            )
            call_cache[key] = (call, sanitized)
        return call_cache[key]

    for rep in range(1, args.repeat + 1):
        if args.repeat > 1:
            print(f"=== Repetition {rep}/{args.repeat} ===")
        for spec in selected_specs:
            for mode in modes:
                attempts: list[Attempt] = []
                selected_call: ProviderCall | None = None
                selected_sanitized: Sanitized | None = None
                order = provider_order(mode)
                for provider_name in order:
                    call, sanitized = get_call(rep, provider_name, spec)
                    attempts.append(to_attempt(call, sanitized))
                    selected_call, selected_sanitized = call, sanitized
                    if len(order) == 1 or (call.ok and sanitized.gate_passed):
                        break

                assert selected_call is not None and selected_sanitized is not None
                failures = evaluate(spec, selected_sanitized.parse, selected_sanitized.accepted)
                if not selected_call.ok:
                    failures.insert(0, f"selected provider failed: {selected_call.error}")
                result = ModeCaseResult(
                    case_id=spec.case.id,
                    category=spec.category,
                    mode=mode,
                    passed=not failures,
                    failures=failures,
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
                if args.fail_fast and not result.passed:
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

    print("=== Summary by mode ===")
    summaries: dict[str, Any] = {}
    for mode in modes:
        mode_results = by_mode.get(mode, [])
        if not mode_results:
            continue
        passed = sum(result.passed for result in mode_results)
        latencies = [result.latency_seconds for result in mode_results]
        total_cost = sum(result.estimated_cost_usd for result in mode_results)
        escalations = sum(result.escalated for result in mode_results)
        selected_counts = Counter(result.selected_provider for result in mode_results)
        category_total: dict[str, int] = defaultdict(int)
        category_passed: dict[str, int] = defaultdict(int)
        for result in mode_results:
            category_total[result.category] += 1
            category_passed[result.category] += int(result.passed)
        summary = {
            "passed": passed,
            "total": len(mode_results),
            "pass_rate": passed / len(mode_results),
            "latency": {
                "mean": statistics.mean(latencies),
                "p50": statistics.median(latencies),
                "p95": percentile(latencies, 0.95),
                "max": max(latencies),
            },
            "estimated_cost_usd": total_cost,
            "escalations": escalations,
            "escalation_rate": escalations / len(mode_results),
            "selected_provider_counts": dict(selected_counts),
            "category_summary": {
                category: {
                    "passed": category_passed[category],
                    "total": category_total[category],
                    "pass_rate": category_passed[category] / category_total[category],
                }
                for category in sorted(category_total)
            },
        }
        summaries[mode] = summary
        print(
            f"{mode:<22} {passed:>3}/{len(mode_results):<3} "
            f"({summary['pass_rate'] * 100:5.1f}%) "
            f"mean={summary['latency']['mean']:.3f}s "
            f"p95={summary['latency']['p95']:.3f}s "
            f"escalation={summary['escalation_rate'] * 100:5.1f}% "
            f"cost=${total_cost:.6f} selected={dict(selected_counts)}"
        )

    report = {
        "benchmark_version": VERSION,
        "started_at": datetime.now().astimezone().isoformat(),
        "modes": modes,
        "repeat_requested": args.repeat,
        "stopped_early": stopped,
        "models": {"qwen": args.qwen_model, "luna": args.luna_model, "terra": args.terra_model},
        "endpoints": {"ollama": args.ollama_url, "openai": args.openai_base_url},
        "gate": {
            "min_confidence": args.gate_min_confidence,
            "min_coverage": args.gate_min_coverage,
            "policy": "Schema/value/evidence/internal-consistency/coverage validation only; no case-specific phrase router is used.",
        },
        "api_key_handling": "OPENAI_API_KEY was read from the process environment and was not logged or written to this report.",
        "openai_price_assumptions_per_mtok": {
            "luna": {"input": args.luna_input_price, "output": args.luna_output_price},
            "terra": {"input": args.terra_input_price, "output": args.terra_output_price},
        },
        "cost_note": "Estimated cost uses total input/output tokens at configured standard rates and does not apply cached-input discounts.",
        "qwen_preload_seconds": preload_seconds,
        "summary_by_mode": summaries,
        "provider_call_count": Counter(call.provider for call, _ in call_cache.values()),
        "results": [asdict(result) for result in results],
    }
    # Counter is not JSON serializable as a mapping subclass on every runtime; normalize it.
    report["provider_call_count"] = dict(report["provider_call_count"])
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Report:", args.report)

    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
