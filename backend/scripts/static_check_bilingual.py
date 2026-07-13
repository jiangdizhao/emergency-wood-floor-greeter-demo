from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

if sys.version_info < (3, 10):
    raise SystemExit("Bilingual static check requires Python 3.10 or newer.")

from app.llm.prompts import EN_QWEN_RENDER_SYSTEM_PROMPT, EN_RENDER_SYSTEM_PROMPT, build_render_user_prompt
from app.llm.schemas import AnswerPlan, ApprovedProductFact
from app.localization import localize_answer_plan_payload
from app.response_language import get_current_response_language, set_current_response_language


def contains_cjk(value: object) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", json.dumps(value, ensure_ascii=False)))


def main() -> None:
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version.split()[0]}")

    set_current_response_language("en")
    assert get_current_response_language() == "en"

    plan = AnswerPlan(
        response_type="recommendation",
        sales_stage="recommendation",
        sales_objective="围绕核心需求给出主推款和备选款",
        next_best_action="present_main_and_backup",
        customer_need_summary=["首要购买驱动：耐磨", "使用空间：客厅", "预算：中等"],
        products=[
            ApprovedProductFact(
                product_id="WF-SPC-001",
                name="云杉浅灰 SPC 锁扣地板",
                product_type="SPC",
                color="浅灰",
                price_range="中等",
                presentation_role="主推款",
                approved_facts=["材质：SPC", "颜色：浅灰", "耐磨等级：AC5"],
                match_reasons=["符合您把耐磨放在首位的要求", "适合客厅"],
                tradeoffs=["脚感与天然木质感通常不如实木类产品温润"],
            )
        ],
        next_question="为了判断活动条件、报价范围和铺装工作量，请问预计铺装面积大约多少平方米？",
        must_recommend_now=True,
    )

    payload = localize_answer_plan_payload(plan.model_dump(), "en")
    assert payload["response_language"] == "en"
    assert payload["products"][0]["name"] == "Light Grey Spruce SPC Click Flooring"
    assert payload["products"][0]["presentation_role"] == "main recommendation"
    assert payload["products"][0]["tradeoffs"]
    assert not contains_cjk(payload["products"])
    assert not contains_cjk(payload["customer_need_summary"])
    assert not contains_cjk(payload["next_question"])

    prompt_payload = json.loads(build_render_user_prompt(plan, response_language="en"))
    assert prompt_payload["products"][0]["name"] == "Light Grey Spruce SPC Click Flooring"
    assert "English" in EN_RENDER_SYSTEM_PROMPT
    assert "English" in EN_QWEN_RENDER_SYSTEM_PROMPT

    ui_api = (REPO_ROOT / "ui" / "src" / "api.ts").read_text(encoding="utf-8")
    ui_runtime = (REPO_ROOT / "ui" / "public" / "bilingual-ui.js").read_text(encoding="utf-8")
    ui_network = (REPO_ROOT / "ui" / "public" / "bilingual-network.js").read_text(encoding="utf-8")
    speech_patch = (REPO_ROOT / "ui" / "src" / "speechRecognitionDomainPatch.ts").read_text(encoding="utf-8")
    index_html = (REPO_ROOT / "ui" / "index.html").read_text(encoding="utf-8")

    for voice in ("am_liam", "am_michael", "am_puck", "am_onyx"):
        assert voice in ui_api
        assert voice in ui_network
    assert "response_language: language" in ui_api
    assert "language === 'en' ? 'en-US' : 'zh-CN'" in speech_patch
    assert "woodfloor-language-toggle" in ui_runtime
    assert "/bilingual-ui.js" in index_html
    assert "/bilingual-network.js" in index_html

    tts_server = (REPO_ROOT / "local_tts" / "kokoro_tts_server.py").read_text(encoding="utf-8")
    downloader = (REPO_ROOT / "local_tts" / "download_english_voices.py").read_text(encoding="utf-8")
    for voice in ("am_liam", "am_michael", "am_puck", "am_onyx"):
        assert voice in tts_server
        assert voice in downloader
    assert 'KPipeline(lang_code="a")' in tts_server
    assert "warmup_en_ready" in tts_server

    print("Bilingual UI and speech static check passed.")
    print("English AnswerPlan localization: yes")
    print("Terra and Qwen English render prompts: yes")
    print("One-click UI language selector: yes")
    print("English browser speech recognition: yes")
    print("English Kokoro voice mapping: am_liam, am_michael, am_puck, am_onyx")
    print("Bilingual Kokoro startup warm-up: yes")


if __name__ == "__main__":
    main()
