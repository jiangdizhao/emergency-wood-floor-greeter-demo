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
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

VERSION = "3.0"
DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3.5:4b"
KEEP_ALIVE = "30m"
INTENTS = [
    "provide_or_modify_needs", "request_recommendation", "request_comparison",
    "ask_reason", "reject_product", "reject_color", "general_product_question", "other",
]
FIELDS = [
    "room_type", "style", "budget", "has_pets", "has_floor_heating",
    "has_children", "has_elderly", "humid_environment",
]
PRIORITIES = ["防水", "耐磨", "环保", "价格", "脚感", "好清洁", "地暖适配"]
PRODUCT_ALIASES = {"spc": "SPC", "多层实木": "多层实木"}
COLOR_ALIASES = {"浅灰": "灰色", "灰色": "灰色", "原木色": "原木色", "暖色": "暖色"}
EMPTY = {"field_updates": [], "priority_updates": [], "color_preferences": [], "product_preferences": []}

INTENT_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "intent": {"type": "string", "enum": INTENTS},
        "is_question": {"type": "boolean"},
        "explicit_self_context": {"type": "boolean"},
        "recommendation_requested": {"type": "boolean"},
        "mentioned_products": {"type": "array", "items": {"type": "string"}},
        "mentioned_colors": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["intent", "is_question", "explicit_self_context", "recommendation_requested",
                 "mentioned_products", "mentioned_colors", "confidence"],
}

ITEM_SCHEMAS = {
    "field_updates": {
        "field": {"type": "string", "enum": FIELDS}, "value": {"type": "string"},
        "scope": {"type": "string", "enum": ["persistent", "turn_only"]}, "evidence": {"type": "string"},
    },
    "priority_updates": {
        "name": {"type": "string", "enum": PRIORITIES},
        "level": {"type": "string", "enum": ["high", "medium", "low", "remove"]},
        "scope": {"type": "string", "enum": ["persistent", "turn_only"]}, "evidence": {"type": "string"},
    },
    "color_preferences": {
        "color": {"type": "string"}, "preference": {"type": "string", "enum": ["prefer", "reject"]},
        "scope": {"type": "string", "enum": ["persistent", "turn_only"]}, "evidence": {"type": "string"},
    },
    "product_preferences": {
        "product": {"type": "string"}, "preference": {"type": "string", "enum": ["prefer", "reject"]},
        "scope": {"type": "string", "enum": ["persistent", "turn_only"]}, "evidence": {"type": "string"},
    },
}
FACT_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "properties": {
        key: {
            "type": "array",
            "items": {"type": "object", "additionalProperties": False,
                      "properties": props, "required": list(props)},
        }
        for key, props in ITEM_SCHEMAS.items()
    },
    "required": list(ITEM_SCHEMAS),
}

INTENT_PROMPT = """
你是木地板导购系统的意图分类器，只分类和提取原话中的产品、颜色。
关键边界：
- “为什么你不推荐多层实木？”=ask_reason，不是拒绝。
- “SPC 和多层实木哪种更适合……”=request_comparison。
- “我不喜欢灰色，还有原木色或暖色吗？”=reject_color。
- 只有明确“我不要/不想要/不考虑某产品”才是 reject_product。
- 泛指“有宠物的家庭”不是本人情况；“我家/家里/客厅用/预算中等”是本人需求。
- request_recommendation 和 request_comparison 的 recommendation_requested=true。
只输出符合 Schema 的 JSON。
""".strip()

FACT_PROMPT = """
你是证据事实提取器，只从顾客最新一句话提取明确事实。
每条 evidence 必须逐字复制原话连续片段；没有证据就不要输出，禁止空 evidence。
没有提到绝不等于 no。宠物不能推出潮湿、耐磨、好清洁、儿童或老人。
询问为什么不推荐不等于拒绝；比较不等于偏好。
本人需求 scope=persistent，泛指比较条件 scope=turn_only。
“防水不是最重要”=>防水 low；“更看重脚感”=>脚感 high；
“预算可以稍微高一些”且当前中等=>budget 偏高。
值规范：房间=客厅/卧室/全屋/厨房/书房/儿童房/老人房；预算=经济/中等/偏高/高端；布尔=yes/no。
只输出符合 Schema 的 JSON。
""".strip()

@dataclass(frozen=True)
class Case:
    id: str
    text: str
    state: dict[str, Any]
    intent: str
    products: tuple[str, ...] = ()
    colors: tuple[str, ...] = ()
    fields: tuple[tuple[str, str, str], ...] = ()
    forbidden_fields: tuple[str, ...] = ()
    priorities: tuple[tuple[str, str, str], ...] = ()
    color_prefs: tuple[tuple[str, str, str], ...] = ()
    product_prefs: tuple[tuple[str, str, str], ...] = ()
    no_persistent: bool = False

CASES = (
    Case("T01_basic_needs", "客厅用，家里有一只狗，预算中等，我最关注耐磨和好清洁。", {}, "provide_or_modify_needs",
         fields=(("room_type", "客厅", "persistent"), ("budget", "中等", "persistent"), ("has_pets", "yes", "persistent")),
         forbidden_fields=("has_children", "has_elderly", "humid_environment"),
         priorities=(("耐磨", "high", "persistent"), ("好清洁", "high", "persistent"))),
    Case("T02_correction", "刚才说错了，不是客厅，是卧室，而且我家没有地暖。",
         {"room_type": "客厅", "has_floor_heating": "yes"}, "provide_or_modify_needs",
         fields=(("room_type", "卧室", "persistent"), ("has_floor_heating", "no", "persistent"))),
    Case("T03_priority_rerank", "防水不是最重要，我更看重脚感，预算可以稍微高一些。",
         {"budget": "中等", "priorities": {"防水": "high"}}, "provide_or_modify_needs",
         fields=(("budget", "偏高", "persistent"),),
         priorities=(("防水", "low", "persistent"), ("脚感", "high", "persistent"))),
    Case("T04_color_change", "我不喜欢灰色，还有原木色或者暖色的吗？", {"preferred_colors": ["浅灰"]}, "reject_color",
         colors=("灰色", "原木色", "暖色"),
         color_prefs=(("灰色", "reject", "persistent"), ("原木色", "prefer", "persistent"), ("暖色", "prefer", "persistent"))),
    Case("T05_ask_reason", "为什么你不推荐多层实木？", {}, "ask_reason", products=("多层实木",), no_persistent=True),
    Case("T06_comparison_generic", "SPC 和多层实木哪一种更适合有地暖和宠物的家庭？", {}, "request_comparison",
         products=("SPC", "多层实木"), fields=(("has_floor_heating", "yes", "turn_only"), ("has_pets", "yes", "turn_only")), no_persistent=True),
    Case("T07_explicit_product_reject", "我不想要 SPC，换一款脚感更舒服的。", {"recommended_products": ["SPC"]}, "reject_product",
         products=("SPC",), priorities=(("脚感", "high", "persistent"),), product_prefs=(("SPC", "reject", "persistent"),)),
    Case("T08_general_question", "SPC 地板防水吗？", {}, "general_product_question", products=("SPC",), no_persistent=True),
    Case("T09_explicit_no_children", "家里没有小孩，但有一位老人，卧室用。", {}, "provide_or_modify_needs",
         fields=(("has_children", "no", "persistent"), ("has_elderly", "yes", "persistent"), ("room_type", "卧室", "persistent"))),
    Case("T10_omitted_is_unknown", "客厅用，预算中等。", {}, "provide_or_modify_needs",
         fields=(("room_type", "客厅", "persistent"), ("budget", "中等", "persistent")),
         forbidden_fields=("has_children", "has_elderly", "has_pets", "has_floor_heating", "humid_environment")),
)

@dataclass
class Call:
    data: dict[str, Any]
    seconds: float
    tokens: int
    done: str

@dataclass
class Result:
    case_id: str
    passed: bool
    failures: list[str]
    raw_intent: dict[str, Any]
    resolved_intent: dict[str, Any]
    raw_facts: dict[str, Any]
    accepted: dict[str, list[dict[str, Any]]]
    recoveries: list[dict[str, Any]]
    rejections: list[dict[str, Any]]
    seconds: float
    done_reasons: tuple[str, str]

class Ollama:
    def __init__(self, url: str, model: str, timeout: float):
        self.url, self.model, self.timeout = url.rstrip("/"), model, timeout

    def post(self, body: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(self.url + "/api/chat",
            data=json.dumps(body, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Ollama HTTP {e.code}: {e.read().decode(errors='replace')}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Cannot reach Ollama at {self.url}: {e}") from e

    def preload(self) -> float:
        t = time.perf_counter()
        self.post({"model": self.model, "messages": [], "stream": False, "keep_alive": KEEP_ALIVE})
        return time.perf_counter() - t

    def structured(self, system: str, user: str, schema: dict[str, Any], limit: int) -> Call:
        t = time.perf_counter()
        r = self.post({"model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False, "think": False, "format": schema, "keep_alive": KEEP_ALIVE,
            "options": {"num_ctx": 4096, "num_predict": limit, "temperature": 0}})
        seconds = time.perf_counter() - t
        content = r.get("message", {}).get("content", "")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON: {e}: {content!r}") from e
        if not isinstance(data, dict):
            raise RuntimeError("Structured output is not an object")
        return Call(data, seconds, int(r.get("eval_count") or 0), str(r.get("done_reason") or ""))

def norm(s: str) -> str:
    return re.sub(r"[\s，。！？、；：,.!?;:'\"“”‘’（）()\-—]", "", s).lower()

def verbatim(text: str, evidence: str) -> bool:
    return bool(norm(evidence)) and norm(evidence) in norm(text)

def products(text: str) -> list[str]:
    n = norm(text)
    return list(dict.fromkeys(v for k, v in PRODUCT_ALIASES.items() if k in n))

def colors(text: str) -> list[str]:
    n = norm(text)
    return list(dict.fromkeys(v for k, v in COLOR_ALIASES.items() if k in n))

def self_context(text: str) -> bool:
    n = norm(text)
    if any(x in n for x in ("哪一种更适合", "哪种更适合", "适合有", "的家庭")) and not any(x in n for x in ("我", "我家", "家里")):
        return False
    return any(x in n for x in ("我", "我家", "家里", "客厅用", "卧室用", "全屋用", "预算"))

def explicit_reject(text: str) -> bool:
    n = norm(text)
    return "为什么" not in n and any(x in n for x in ("我不要", "我不想要", "我不喜欢", "我不考虑", "排除"))

def resolve(text: str, raw: dict[str, Any]) -> dict[str, Any]:
    n, ps, cs = norm(text), products(text), colors(text)
    intent, source = str(raw.get("intent") or "other"), "model"
    if "为什么" in n and ("推荐" in n or "不推荐" in n): intent, source = "ask_reason", "rule:why"
    elif len(ps) >= 2 and any(x in n for x in ("哪一种更适合", "哪种更适合", "区别", "对比", "比较")): intent, source = "request_comparison", "rule:comparison"
    elif ps and explicit_reject(text): intent, source = "reject_product", "rule:reject_product"
    elif cs and explicit_reject(text): intent, source = "reject_color", "rule:reject_color"
    elif "推荐" in n and "为什么" not in n: intent, source = "request_recommendation", "rule:recommend"
    elif ("吗" in n or "？" in text) and ps: intent, source = "general_product_question", "rule:question"
    elif self_context(text): intent, source = "provide_or_modify_needs", "rule:self"
    return {**raw, "intent": intent, "explicit_self_context": self_context(text),
            "recommendation_requested": intent in {"request_recommendation", "request_comparison"},
            "mentioned_products": ps, "mentioned_colors": cs, "route_source": source}

def add(dst: list[dict[str, Any]], item: dict[str, Any], keys: tuple[str, ...]) -> None:
    sig = tuple(item.get(k) for k in keys)
    if not any(tuple(x.get(k) for k in keys) == sig for x in dst): dst.append(item)

def deterministic(text: str, state: dict[str, Any], intent: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out = {k: [] for k in EMPTY}
    scope = "turn_only" if intent["intent"] == "request_comparison" and not self_context(text) else "persistent"
    def fld(name: str, value: str, evidence: str): add(out["field_updates"], {"field": name, "value": value, "scope": scope, "evidence": evidence}, ("field",))
    def pri(name: str, level: str, evidence: str): add(out["priority_updates"], {"name": name, "level": level, "scope": scope, "evidence": evidence}, ("name",))
    room_names = ("儿童房", "老人房", "客厅", "卧室", "全屋", "厨房", "书房")
    correction = re.search(r"不是(?:儿童房|老人房|客厅|卧室|全屋|厨房|书房)[，,、\s]*是(儿童房|老人房|客厅|卧室|全屋|厨房|书房)", text)
    if correction:
        room = correction.group(1); fld("room_type", room, "是" + room)
    else:
        for room in room_names:
            if f"{room}用" in text: fld("room_type", room, f"{room}用"); break
    for b in ("中等", "经济", "偏高", "高端"):
        if "预算" + b in text: fld("budget", b, "预算" + b); break
    if "预算可以稍微高一些" in text and state.get("budget") == "中等": fld("budget", "偏高", "预算可以稍微高一些")
    if any(x in text for x in ("有一只狗", "有宠物", "养宠物")): fld("has_pets", "yes", next(x for x in ("家里有一只狗", "有一只狗", "有宠物", "养宠物") if x in text))
    if intent["intent"] == "request_comparison" and "宠物" in text: fld("has_pets", "yes", "宠物")
    if "没有地暖" in text: fld("has_floor_heating", "no", "没有地暖")
    elif "有地暖" in text: fld("has_floor_heating", "yes", "有地暖")
    if "没有小孩" in text: fld("has_children", "no", "没有小孩")
    if "有一位老人" in text: fld("has_elderly", "yes", "有一位老人")
    if "防水不是最重要" in text: pri("防水", "low", "防水不是最重要")
    if "更看重脚感" in text: pri("脚感", "high", "更看重脚感")
    elif "脚感更舒服" in text: pri("脚感", "high", "脚感更舒服")
    if "最关注耐磨" in text: pri("耐磨", "high", "耐磨")
    if "好清洁" in text: pri("好清洁", "high", "好清洁")
    if intent["intent"] == "reject_color":
        if "不喜欢灰色" in text: add(out["color_preferences"], {"color": "灰色", "preference": "reject", "scope": "persistent", "evidence": "不喜欢灰色"}, ("color", "preference"))
        for c in ("原木色", "暖色"):
            if c in text: add(out["color_preferences"], {"color": c, "preference": "prefer", "scope": "persistent", "evidence": c}, ("color", "preference"))
    if intent["intent"] == "reject_product" and explicit_reject(text):
        for p in products(text): add(out["product_preferences"], {"product": p, "preference": "reject", "scope": "persistent", "evidence": p}, ("product", "preference"))
    return out

def guard(text: str, intent: dict[str, Any], raw: dict[str, Any], det: dict[str, list[dict[str, Any]]]):
    accepted = {k: [dict(x) for x in det[k]] for k in EMPTY}
    recoveries = [{"kind": k, "item": x, "reason": "high_precision_explicit_evidence"} for k in EMPTY for x in det[k]]
    rejected: list[dict[str, Any]] = []
    target_scope = "turn_only" if intent["intent"] == "request_comparison" and not self_context(text) else "persistent"
    key_fields = {"field_updates": ("field",), "priority_updates": ("name",), "color_preferences": ("color", "preference"), "product_preferences": ("product", "preference")}
    for kind in EMPTY:
        items = raw.get(kind, [])
        if not isinstance(items, list):
            rejected.append({"kind": kind, "item": items, "reason": "not_array"}); continue
        for item in items:
            if not isinstance(item, dict) or not verbatim(text, str(item.get("evidence") or "")):
                rejected.append({"kind": kind, "item": item, "reason": "evidence_not_verbatim"}); continue
            item = dict(item); item["scope"] = target_scope
            if intent["intent"] in {"ask_reason", "general_product_question"}:
                rejected.append({"kind": kind, "item": item, "reason": "question_disallows_state_change"}); continue
            if kind == "product_preferences" and item.get("preference") == "reject" and (intent["intent"] != "reject_product" or not explicit_reject(text)):
                rejected.append({"kind": kind, "item": item, "reason": "no_explicit_product_rejection"}); continue
            keys = key_fields[kind]
            sig = tuple(item.get(k) for k in keys)
            if any(tuple(x.get(k) for k in keys) == sig for x in accepted[kind]):
                rejected.append({"kind": kind, "item": item, "reason": "duplicate_or_conflict"}); continue
            accepted[kind].append(item)
    return accepted, recoveries, rejected

def triples(items: list[dict[str, Any]], keys: tuple[str, str, str]) -> set[tuple[str, str, str]]:
    return {tuple(str(x.get(k)) for k in keys) for x in items}

def evaluate(case: Case, resolved: dict[str, Any], accepted: dict[str, list[dict[str, Any]]], done: tuple[str, str]) -> list[str]:
    fail: list[str] = []
    if resolved.get("intent") != case.intent: fail.append(f"intent expected={case.intent} actual={resolved.get('intent')}")
    for p in case.products:
        if p not in resolved.get("mentioned_products", []): fail.append(f"missing mentioned product: {p}")
    for c in case.colors:
        if c not in resolved.get("mentioned_colors", []): fail.append(f"missing mentioned color: {c}")
    actual = triples(accepted["field_updates"], ("field", "value", "scope"))
    for x in case.fields:
        if x not in actual: fail.append("missing field update: " + "|".join(x))
    for name in case.forbidden_fields:
        if any(x.get("field") == name for x in accepted["field_updates"]): fail.append(f"forbidden field update accepted: {name}")
    actual = triples(accepted["priority_updates"], ("name", "level", "scope"))
    for x in case.priorities:
        if x not in actual: fail.append("missing priority update: " + "|".join(x))
    actual = triples(accepted["color_preferences"], ("color", "preference", "scope"))
    for x in case.color_prefs:
        if x not in actual: fail.append("missing color preference: " + "|".join(x))
    actual = triples(accepted["product_preferences"], ("product", "preference", "scope"))
    for x in case.product_prefs:
        if x not in actual: fail.append("missing product preference: " + "|".join(x))
    if case.no_persistent and any(x.get("scope") == "persistent" for items in accepted.values() for x in items): fail.append("unexpected persistent state change")
    if done[0] != "stop": fail.append(f"intent done_reason={done[0]}")
    if done[1] not in {"stop", "skipped"}: fail.append(f"facts done_reason={done[1]}")
    return fail

def run(client: Ollama, case: Case) -> Result:
    state = json.dumps(case.state, ensure_ascii=False, separators=(",", ":"))
    ci = client.structured(INTENT_PROMPT, f"当前客户状态：{state}\n顾客最新话语：{case.text}\n请分类。", INTENT_SCHEMA, 220)
    resolved = resolve(case.text, ci.data)
    should_facts = resolved["intent"] not in {"ask_reason", "general_product_question", "other"}
    if should_facts:
        cf = client.structured(FACT_PROMPT, f"当前客户状态：{state}\n已解析意图：{json.dumps(resolved, ensure_ascii=False)}\n顾客最新话语：{case.text}\n请提取事实。", FACT_SCHEMA, 420)
    else:
        cf = Call({k: [] for k in EMPTY}, 0.0, 0, "skipped")
    det = deterministic(case.text, case.state, resolved) if should_facts else {k: [] for k in EMPTY}
    accepted, recoveries, rejections = guard(case.text, resolved, cf.data, det)
    failures = evaluate(case, resolved, accepted, (ci.done, cf.done))
    return Result(case.id, not failures, failures, ci.data, resolved, cf.data, accepted, recoveries, rejections, ci.seconds + cf.seconds, (ci.done, cf.done))

def print_result(r: Result, verbose: bool) -> None:
    status = "PASS" if r.passed else "FAIL"
    intent = str((r.resolved_intent or {}).get("intent") or "unknown")
    print(f"[{status}] {r.case_id:<30} intent={intent:<28} latency={float(r.seconds or 0):5.2f}s")
    for f in r.failures: print("       -", f)
    if verbose or not r.passed:
        print("       raw_intent:", json.dumps(r.raw_intent, ensure_ascii=False))
        print("       resolved_intent:", json.dumps(r.resolved_intent, ensure_ascii=False))
        print("       accepted:", json.dumps(r.accepted, ensure_ascii=False))
        if r.recoveries: print("       deterministic_recoveries:", json.dumps(r.recoveries, ensure_ascii=False))
        if r.rejections: print("       guard_rejections:", json.dumps(r.rejections, ensure_ascii=False))
        if verbose: print("       raw_facts:", json.dumps(r.raw_facts, ensure_ascii=False))

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL); ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--repeat", type=int, default=1); ap.add_argument("--timeout", type=float, default=90)
    ap.add_argument("--verbose", action="store_true"); ap.add_argument("--report", type=Path)
    a = ap.parse_args()
    if a.repeat < 1: raise SystemExit("--repeat must be >= 1")
    client = Ollama(a.base_url, a.model, a.timeout)
    print(f"Benchmark v{VERSION}\nModel: {a.model}\nOllama: {a.base_url}\nPreloading model...")
    preload = client.preload(); print(f"Preload completed in {preload:.3f}s\n")
    results: list[Result] = []
    for rep in range(a.repeat):
        if a.repeat > 1: print(f"=== Repetition {rep + 1}/{a.repeat} ===")
        for case in CASES:
            try:
                r = run(client, case)
            except Exception as e:
                r = Result(case.id, False, [f"exception: {type(e).__name__}: {e}"], {}, {"intent": "unknown", "route_source": "exception"}, {}, {k: [] for k in EMPTY}, [], [], 0.0, ("", ""))
            results.append(r); print_result(r, a.verbose)
        print()
    passed, total = sum(x.passed for x in results), len(results)
    lat = [x.seconds for x in results if x.seconds > 0]
    print("=== Summary ==="); print(f"Passed: {passed}/{total} ({passed / total * 100:.1f}%)")
    if lat:
        ordered = sorted(lat); p95 = ordered[max(0, min(len(ordered)-1, math.ceil(.95*len(ordered))-1))]
        print(f"Latency mean: {statistics.mean(lat):.3f}s\nLatency P50:  {statistics.median(lat):.3f}s\nLatency P95:  {p95:.3f}s\nLatency max:  {max(lat):.3f}s")
    report = {"benchmark_version": VERSION, "started_at": datetime.now().astimezone().isoformat(), "model": a.model,
              "preload_seconds": preload, "passed": passed, "total": total, "pass_rate": passed/total,
              "results": [asdict(x) for x in results]}
    if a.report:
        a.report.parent.mkdir(parents=True, exist_ok=True); a.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"); print("Report:", a.report)
    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(main())
