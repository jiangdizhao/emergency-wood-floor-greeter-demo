from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import local_llm_dialogue_benchmark as engine

VERSION = "4.0-generalization"


@dataclass(frozen=True)
class Spec:
    category: str
    case: engine.Case
    recommendation: bool | None = None
    self_context: bool | None = None
    facts_stage: str | None = None
    note: str = ""


def C(category: str, case_id: str, text: str, state: dict[str, Any], intent: str, **kwargs: Any) -> Spec:
    meta = {name: kwargs.pop(name, None) for name in ("recommendation", "self_context", "facts_stage")}
    note = kwargs.pop("note", "")
    return Spec(category, engine.Case(case_id, text, state, intent, **kwargs), **meta, note=note)


CASES = (
    C("paraphrase", "G01_colloquial_living_room", "打算铺客厅，家里两只猫，价格按经济档来，耐磨和好打理最重要。", {}, "provide_or_modify_needs",
      fields=(("room_type", "客厅", "persistent"), ("has_pets", "yes", "persistent"), ("budget", "经济", "persistent")),
      forbidden_fields=("has_children", "has_elderly", "humid_environment"), priorities=(("耐磨", "high", "persistent"), ("好清洁", "high", "persistent")),
      recommendation=False, self_context=True, facts_stage="run", note="Colloquial cats, economic budget, and 好打理 synonym."),
    C("paraphrase", "G02_study_style_budget", "主要给书房铺，价位选偏高档，喜欢北欧风。", {}, "provide_or_modify_needs",
      fields=(("room_type", "书房", "persistent"), ("budget", "偏高", "persistent"), ("style", "北欧风", "persistent")), recommendation=False, self_context=True, facts_stage="run"),
    C("paraphrase", "G03_whole_home_children_environment", "全屋都准备换，家里有小朋友，环保要放在第一位。", {}, "provide_or_modify_needs",
      fields=(("room_type", "全屋", "persistent"), ("has_children", "yes", "persistent")), forbidden_fields=("has_elderly", "has_pets"),
      priorities=(("环保", "high", "persistent"),), recommendation=False, self_context=True, facts_stage="run"),
    C("paraphrase", "G04_humid_kitchen", "南方一楼返潮比较明显，厨房这块准备铺地板。", {}, "provide_or_modify_needs",
      fields=(("room_type", "厨房", "persistent"), ("humid_environment", "yes", "persistent")), recommendation=False, self_context=True, facts_stage="run"),
    C("paraphrase", "G05_no_pets_bedroom", "卧室要用，家里不养猫也不养狗。", {}, "provide_or_modify_needs",
      fields=(("room_type", "卧室", "persistent"), ("has_pets", "no", "persistent")), forbidden_fields=("has_children", "has_elderly"), recommendation=False, self_context=True, facts_stage="run"),
    C("paraphrase", "G06_elder_room", "是给老人房用的，家中有长辈常住。", {}, "provide_or_modify_needs",
      fields=(("room_type", "老人房", "persistent"), ("has_elderly", "yes", "persistent")), recommendation=False, self_context=True, facts_stage="run"),
    C("paraphrase", "G07_floor_heating_synonym", "我家走地采暖，客厅准备重新铺。", {}, "provide_or_modify_needs",
      fields=(("room_type", "客厅", "persistent"), ("has_floor_heating", "yes", "persistent")), recommendation=False, self_context=True, facts_stage="run"),
    C("paraphrase", "G08_raise_budget_synonym", "价格可以往上提一档，脚感优先。", {"budget": "中等"}, "provide_or_modify_needs",
      fields=(("budget", "偏高", "persistent"),), priorities=(("脚感", "high", "persistent"),), recommendation=False, self_context=True, facts_stage="run"),

    C("correction_negation", "G09_room_correction_reversed", "前面我讲反了，卧室不要，是客厅。", {"room_type": "卧室"}, "provide_or_modify_needs",
      fields=(("room_type", "客厅", "persistent"),), recommendation=False, self_context=True, facts_stage="run"),
    C("correction_negation", "G10_floor_heating_correction", "地暖那项改一下，我们家其实没装。", {"has_floor_heating": "yes"}, "provide_or_modify_needs",
      fields=(("has_floor_heating", "no", "persistent"),), recommendation=False, self_context=True, facts_stage="run"),
    C("correction_negation", "G11_pet_correction", "刚才说有宠物不对，家里没养猫也没养狗。", {"has_pets": "yes"}, "provide_or_modify_needs",
      fields=(("has_pets", "no", "persistent"),), recommendation=False, self_context=True, facts_stage="run"),
    C("correction_negation", "G12_budget_downshift", "预算还是收一收，从偏高改成中等吧。", {"budget": "偏高"}, "provide_or_modify_needs",
      fields=(("budget", "中等", "persistent"),), recommendation=False, self_context=True, facts_stage="run"),
    C("correction_negation", "G13_remove_and_raise_priority", "防水不用考虑，耐磨才是第一位。", {"priorities": {"防水": "high"}}, "provide_or_modify_needs",
      priorities=(("防水", "remove", "persistent"), ("耐磨", "high", "persistent")), recommendation=False, self_context=True, facts_stage="run"),
    C("correction_negation", "G14_family_mixed_polarity", "家里没有老人，倒是有两个小孩。", {}, "provide_or_modify_needs",
      fields=(("has_elderly", "no", "persistent"), ("has_children", "yes", "persistent")), forbidden_fields=("has_pets", "has_floor_heating"), recommendation=False, self_context=True, facts_stage="run"),

    C("intent_boundary", "G15_reason_without_why_keyword", "多层实木看着也不错，怎么没把它放在首选？", {}, "ask_reason",
      products=("多层实木",), no_persistent=True, recommendation=False, self_context=False, facts_stage="skipped", note="Reason question without 为什么."),
    C("intent_boundary", "G16_comparison_without_standard_trigger", "SPC 跟多层实木到底差在哪，哪个更省心？", {}, "request_comparison",
      products=("SPC", "多层实木"), no_persistent=True, recommendation=True, self_context=False, facts_stage="run"),
    C("intent_boundary", "G17_soft_product_rejection", "SPC 就算了，给我看看别的。", {"recommended_products": ["SPC"]}, "reject_product",
      products=("SPC",), product_prefs=(("SPC", "reject", "persistent"),), recommendation=False, self_context=True, facts_stage="run"),
    C("intent_boundary", "G18_color_sentiment_rejection", "灰色看着太冷了，换成原木色吧。", {"preferred_colors": ["灰色"]}, "reject_color",
      colors=("灰色", "原木色"), color_prefs=(("灰色", "reject", "persistent"), ("原木色", "prefer", "persistent")), recommendation=False, self_context=True, facts_stage="run"),
    C("intent_boundary", "G19_product_capability_question", "多层实木能不能配地暖？", {}, "general_product_question",
      products=("多层实木",), no_persistent=True, recommendation=False, self_context=False, facts_stage="skipped"),
    C("intent_boundary", "G20_recommend_from_existing_state", "按我前面这些条件，你直接给个最合适的。", {"room_type": "客厅", "budget": "中等", "has_pets": "yes"}, "request_recommendation",
      recommendation=True, self_context=True, facts_stage="run"),

    C("scope", "G21_generic_comparison_scope", "养猫又有地暖的家庭，SPC 和多层实木怎么选？", {}, "request_comparison",
      products=("SPC", "多层实木"), fields=(("has_pets", "yes", "turn_only"), ("has_floor_heating", "yes", "turn_only")), no_persistent=True,
      recommendation=True, self_context=False, facts_stage="run"),
    C("scope", "G22_personal_comparison_scope", "我家养猫，也有地暖，SPC 和多层实木怎么选？", {}, "request_comparison",
      products=("SPC", "多层实木"), fields=(("has_pets", "yes", "persistent"), ("has_floor_heating", "yes", "persistent")), recommendation=True, self_context=True, facts_stage="run"),
    C("scope", "G23_generic_recommendation_scope", "有老人和小孩的家庭选什么地板？", {}, "request_recommendation",
      fields=(("has_elderly", "yes", "turn_only"), ("has_children", "yes", "turn_only")), no_persistent=True,
      recommendation=True, self_context=False, facts_stage="run", note="Generic recommendation conditions must not enter customer memory."),
    C("scope", "G24_personal_recommendation_scope", "我家有老人和小孩，帮我推荐一下。", {}, "request_recommendation",
      fields=(("has_elderly", "yes", "persistent"), ("has_children", "yes", "persistent")), recommendation=True, self_context=True, facts_stage="run"),

    C("asr_noise", "G25_no_punctuation", "客厅用家里有狗预算中等主要要耐磨好清洁", {}, "provide_or_modify_needs",
      fields=(("room_type", "客厅", "persistent"), ("has_pets", "yes", "persistent"), ("budget", "中等", "persistent")),
      priorities=(("耐磨", "high", "persistent"), ("好清洁", "high", "persistent")), recommendation=False, self_context=True, facts_stage="run"),
    C("asr_noise", "G26_character_spacing", "我 家 没 有 地 暖 卧 室 用", {}, "provide_or_modify_needs",
      fields=(("has_floor_heating", "no", "persistent"), ("room_type", "卧室", "persistent")), recommendation=False, self_context=True, facts_stage="run"),
    C("asr_noise", "G27_spelled_product_name", "S P C 和多层实木哪个更适合我家？", {}, "request_comparison",
      products=("SPC", "多层实木"), recommendation=True, self_context=True, facts_stage="run"),
    C("asr_noise", "G28_spaced_colors", "我不喜欢灰 色，想看原木 色。", {"preferred_colors": ["灰色"]}, "reject_color",
      colors=("灰色", "原木色"), color_prefs=(("灰色", "reject", "persistent"), ("原木色", "prefer", "persistent")), recommendation=False, self_context=True, facts_stage="run"),

    C("multi_intent", "G29_reject_and_update_preferences", "SPC 不考虑了，我更在意脚感，预算可以高一点。", {"budget": "中等", "recommended_products": ["SPC"]}, "reject_product",
      products=("SPC",), fields=(("budget", "偏高", "persistent"),), priorities=(("脚感", "high", "persistent"),),
      product_prefs=(("SPC", "reject", "persistent"),), recommendation=False, self_context=True, facts_stage="run"),
    C("multi_intent", "G30_correct_then_recommend", "不是卧室，是客厅，家里有狗，按中等预算推荐一款。", {"room_type": "卧室"}, "request_recommendation",
      fields=(("room_type", "客厅", "persistent"), ("has_pets", "yes", "persistent"), ("budget", "中等", "persistent")), recommendation=True, self_context=True, facts_stage="run"),
)

ALLOWED = {
    "room_type": {"客厅", "卧室", "全屋", "厨房", "书房", "儿童房", "老人房"},
    "budget": {"经济", "中等", "偏高", "高端"},
    "has_pets": {"yes", "no"}, "has_floor_heating": {"yes", "no"},
    "has_children": {"yes", "no"}, "has_elderly": {"yes", "no"},
    "humid_environment": {"yes", "no"}, "style": None,
}


def pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(p * len(ordered)) - 1))] if ordered else 0.0


def safety(spec: Spec, result: engine.Result) -> list[str]:
    out: list[str] = []
    resolved = result.resolved_intent or {}
    if spec.recommendation is not None and bool(resolved.get("recommendation_requested")) != spec.recommendation:
        out.append(f"recommendation_requested expected={spec.recommendation} actual={bool(resolved.get('recommendation_requested'))}")
    if spec.self_context is not None and bool(resolved.get("explicit_self_context")) != spec.self_context:
        out.append(f"explicit_self_context expected={spec.self_context} actual={bool(resolved.get('explicit_self_context'))}")
    if spec.facts_stage == "run" and result.done_reasons[1] == "skipped": out.append("facts stage was unexpectedly skipped")
    if spec.facts_stage == "skipped" and result.done_reasons[1] != "skipped": out.append(f"facts stage expected=skipped actual={result.done_reasons[1]}")
    for kind, items in result.accepted.items():
        seen: dict[tuple[str, ...], tuple[str, ...]] = {}
        for item in items:
            if not engine.verbatim(spec.case.text, str(item.get("evidence") or "")): out.append(f"accepted {kind} has non-verbatim evidence: {item}")
            if item.get("scope") not in {"persistent", "turn_only"}: out.append(f"accepted {kind} has invalid scope: {item}")
            if kind == "field_updates":
                field, value = str(item.get("field") or ""), str(item.get("value") or "")
                allowed = ALLOWED.get(field, "missing")
                if allowed == "missing": out.append(f"accepted unknown field: {item}")
                elif allowed is None and not value.strip(): out.append(f"accepted empty style value: {item}")
                elif isinstance(allowed, set) and value not in allowed: out.append(f"accepted invalid field value: {item}")
                key, payload = (field,), (value, str(item.get("scope")))
            elif kind == "priority_updates":
                if item.get("name") not in engine.PRIORITIES: out.append(f"accepted unknown priority: {item}")
                if item.get("level") not in {"high", "medium", "low", "remove"}: out.append(f"accepted invalid priority level: {item}")
                key, payload = (str(item.get("name")),), (str(item.get("level")), str(item.get("scope")))
            elif kind == "color_preferences":
                if not str(item.get("color") or "").strip(): out.append(f"accepted empty color: {item}")
                key, payload = (str(item.get("color")), str(item.get("preference"))), (str(item.get("scope")),)
            else:
                if not str(item.get("product") or "").strip() or item.get("product") == "未知": out.append(f"accepted invalid product: {item}")
                key, payload = (str(item.get("product")), str(item.get("preference"))), (str(item.get("scope")),)
            if key in seen and seen[key] != payload: out.append(f"conflicting accepted updates for {kind} key={key}: {seen[key]} vs {payload}")
            seen[key] = payload
    return out


def signatures(result: engine.Result, source: str) -> set[str]:
    if source == "recoveries":
        return {json.dumps([x.get("kind"), x.get("item") or {}], ensure_ascii=False, sort_keys=True) for x in result.recoveries}
    return {json.dumps([kind, item], ensure_ascii=False, sort_keys=True) for kind, items in result.accepted.items() for item in items}


def show(spec: Spec, result: engine.Result, verbose: bool) -> None:
    status = "PASS" if result.passed else "FAIL"
    resolved = result.resolved_intent or {}
    print(f"[{status}] {spec.case.id:<36} category={spec.category:<20} intent={str(resolved.get('intent') or 'unknown'):<28} route={str(resolved.get('route_source') or 'unknown'):<18} latency={float(result.seconds or 0):5.2f}s")
    for failure in result.failures: print("       -", failure)
    if verbose or not result.passed:
        print("       utterance:", spec.case.text)
        if spec.note: print("       note:", spec.note)
        for label, value in (("raw_intent", result.raw_intent), ("resolved_intent", result.resolved_intent), ("accepted", result.accepted)):
            print(f"       {label}:", json.dumps(value, ensure_ascii=False))
        if result.recoveries: print("       deterministic_recoveries:", json.dumps(result.recoveries, ensure_ascii=False))
        if result.rejections: print("       guard_rejections:", json.dumps(result.rejections, ensure_ascii=False))
        if verbose: print("       raw_facts:", json.dumps(result.raw_facts, ensure_ascii=False))


def main() -> int:
    ap = argparse.ArgumentParser(description="v4 holdout/generalization suite; reuses the unchanged v3 engine.")
    ap.add_argument("--model", default=engine.DEFAULT_MODEL); ap.add_argument("--base-url", default=engine.DEFAULT_BASE_URL)
    ap.add_argument("--repeat", type=int, default=1); ap.add_argument("--timeout", type=float, default=90.0)
    ap.add_argument("--category", action="append"); ap.add_argument("--case", action="append", dest="case_ids")
    ap.add_argument("--list-cases", action="store_true"); ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--fail-fast", action="store_true"); ap.add_argument("--report", type=Path)
    a = ap.parse_args()
    if a.repeat < 1: raise SystemExit("--repeat must be >= 1")
    selected = [x for x in CASES if not a.category or x.category in set(a.category)]
    selected = [x for x in selected if not a.case_ids or x.case.id in set(a.case_ids)]
    if a.list_cases:
        for x in selected: print(f"{x.case.id}\t{x.category}\t{x.case.text}")
        return 0
    if not selected: raise SystemExit("No cases selected")

    client = engine.Ollama(a.base_url, a.model, a.timeout)
    print(f"Benchmark v{VERSION}\nEngine v{engine.VERSION}\nModel: {a.model}\nOllama: {a.base_url}\nCases: {len(selected)} x repeat {a.repeat}\nPreloading model...")
    preload = client.preload(); print(f"Preload completed in {preload:.3f}s\n")
    records: list[dict[str, Any]] = []; stopped = False
    for rep in range(1, a.repeat + 1):
        if a.repeat > 1: print(f"=== Repetition {rep}/{a.repeat} ===")
        for spec in selected:
            try:
                result = engine.run(client, spec.case)
                result.failures.extend(safety(spec, result)); result.passed = not result.failures
            except Exception as exc:
                result = engine.Result(spec.case.id, False, [f"exception: {type(exc).__name__}: {exc}"], {}, {"intent": "unknown", "route_source": "exception"}, {}, {k: [] for k in engine.EMPTY}, [], [], 0.0, ("", ""))
            show(spec, result, a.verbose)
            records.append({"repetition": rep, "category": spec.category, "utterance": spec.case.text, "note": spec.note,
                            "expected": {"intent": spec.case.intent, "recommendation_requested": spec.recommendation, "explicit_self_context": spec.self_context,
                                         "facts_stage": spec.facts_stage, "fields": spec.case.fields, "priorities": spec.case.priorities,
                                         "color_preferences": spec.case.color_prefs, "product_preferences": spec.case.product_prefs},
                            "result": asdict(result)})
            if a.fail_fast and not result.passed: stopped = True; break
        print()
        if stopped: break

    results = [r["result"] for r in records]; total = len(results); passed = sum(bool(r["passed"]) for r in results)
    lat = [float(r["seconds"]) for r in results if float(r["seconds"]) > 0]
    cat_total: dict[str, int] = defaultdict(int); cat_pass: dict[str, int] = defaultdict(int); routes: Counter[str] = Counter()
    raw_ok = recoveries = accepted = model_only = 0
    for record in records:
        result = record["result"]; cat = record["category"]; cat_total[cat] += 1; cat_pass[cat] += int(bool(result["passed"]))
        routes[str(result.get("resolved_intent", {}).get("route_source") or "unknown")] += 1
        raw_ok += int(result.get("raw_intent", {}).get("intent") == record["expected"]["intent"])
        typed = engine.Result(**result); rset, aset = signatures(typed, "recoveries"), signatures(typed, "accepted")
        recoveries += len(rset); accepted += len(aset); model_only += len(aset - rset)

    print("=== Summary ==="); print(f"Passed: {passed}/{total} ({passed / total * 100:.1f}%)")
    print(f"Raw intent accuracy: {raw_ok}/{total} ({raw_ok / total * 100:.1f}%)")
    print(f"Accepted facts: {accepted}; deterministic recoveries: {recoveries}; model-only accepted: {model_only}")
    if lat:
        print(f"Latency mean: {statistics.mean(lat):.3f}s\nLatency P50:  {statistics.median(lat):.3f}s\nLatency P95:  {pct(lat, .95):.3f}s\nLatency max:  {max(lat):.3f}s")
    print("Category pass rates:")
    for cat in sorted(cat_total): print(f"  {cat:<20} {cat_pass[cat]}/{cat_total[cat]} ({cat_pass[cat] / cat_total[cat] * 100:.1f}%)")
    print("Route sources:")
    for route, count in routes.most_common(): print(f"  {route:<24} {count}")

    report = {"benchmark_version": VERSION, "engine_version": engine.VERSION,
              "holdout_policy": "The v4 runner imports the v3 engine without changing its prompts, schemas, resolver, deterministic rules, or guard.",
              "started_at": datetime.now().astimezone().isoformat(), "model": a.model, "base_url": a.base_url, "preload_seconds": preload,
              "repeat_requested": a.repeat, "stopped_early": stopped, "passed": passed, "total": total, "pass_rate": passed / total if total else 0,
              "raw_intent_accuracy": raw_ok / total if total else 0,
              "accepted_fact_metrics": {"accepted_items": accepted, "deterministic_recovery_items": recoveries, "model_only_accepted_items": model_only},
              "latency": {"mean": statistics.mean(lat) if lat else None, "p50": statistics.median(lat) if lat else None, "p95": pct(lat, .95) if lat else None, "max": max(lat) if lat else None},
              "category_summary": {cat: {"passed": cat_pass[cat], "total": cat_total[cat], "pass_rate": cat_pass[cat] / cat_total[cat]} for cat in sorted(cat_total)},
              "route_sources": dict(routes), "records": records}
    if a.report:
        a.report.parent.mkdir(parents=True, exist_ok=True); a.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"); print("Report:", a.report)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
