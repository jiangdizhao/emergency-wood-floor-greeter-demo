from __future__ import annotations

import copy
import re
from typing import Any

PRODUCT_EN: dict[str, dict[str, Any]] = {
    "WF-SPC-001": {
        "name": "Light Grey Spruce SPC Click Flooring",
        "type": "SPC",
        "color": "light grey",
        "price_range": "mid-range",
        "rooms": ["living room", "bedroom", "study", "whole home"],
        "wear_level": "AC5",
        "floor_heating": True,
        "pet_friendly": True,
        "waterproof": True,
        "spec": "1220×180×5.5 mm",
        "selling_points": [
            "strong water resistance",
            "high wear resistance",
            "well suited to homes with pets and children",
        ],
    },
    "WF-WOOD-002": {
        "name": "Natural Oak Engineered Wood Flooring",
        "type": "engineered wood",
        "color": "natural oak",
        "price_range": "upper-mid range",
        "rooms": ["bedroom", "living room"],
        "wear_level": "medium-high",
        "floor_heating": True,
        "pet_friendly": False,
        "waterproof": False,
        "spec": "1900×190×15 mm",
        "selling_points": [
            "natural underfoot feel",
            "authentic wood grain",
            "well suited to warm, natural interior styles",
        ],
    },
    "WF-LAM-003": {
        "name": "Morning Mist Grey Laminate Flooring",
        "type": "laminate",
        "color": "grey tone",
        "price_range": "economy",
        "rooms": ["living room", "study", "rental property"],
        "wear_level": "AC4",
        "floor_heating": True,
        "pet_friendly": True,
        "waterproof": False,
        "spec": "1215×195×12 mm",
        "selling_points": [
            "strong value for money",
            "good wear resistance",
            "suitable for budget-conscious households",
        ],
    },
    "WF-SPC-004": {
        "name": "Dark Walnut Waterproof SPC Flooring",
        "type": "SPC",
        "color": "dark walnut",
        "price_range": "upper-mid range",
        "rooms": ["living room", "dining room", "whole home"],
        "wear_level": "AC5",
        "floor_heating": True,
        "pet_friendly": True,
        "waterproof": True,
        "spec": "1220×228×6 mm",
        "selling_points": [
            "rich dark-walnut appearance",
            "strong water and wear resistance",
            "suited to modern-luxury and contemporary Chinese interiors",
        ],
    },
    "WF-WOOD-005": {
        "name": "Warm Light Oak Three-Layer Wood Flooring",
        "type": "three-layer wood",
        "color": "light oak",
        "price_range": "premium",
        "rooms": ["bedroom", "study", "living room"],
        "wear_level": "medium-high",
        "floor_heating": True,
        "pet_friendly": False,
        "waterproof": False,
        "spec": "1860×189×15 mm",
        "selling_points": [
            "comfortable underfoot feel",
            "authentic natural wood texture",
            "creates a warm residential atmosphere",
        ],
    },
    "WF-LAM-006": {
        "name": "Cream White High-Wear Laminate Flooring",
        "type": "laminate",
        "color": "cream white",
        "price_range": "mid-range",
        "rooms": ["bedroom", "study", "children's room"],
        "wear_level": "AC4",
        "floor_heating": True,
        "pet_friendly": True,
        "waterproof": False,
        "spec": "1215×198×12 mm",
        "selling_points": [
            "bright cream-white appearance",
            "wear-resistant and easy to maintain",
            "well suited to bedrooms and children's rooms",
        ],
    },
}

COLLECTION_EN: dict[str, dict[str, Any]] = {
    "easycare_family": {
        "name": "Durable Easy-Care Family Collection",
        "tagline": "Designed for pets, children and high-traffic rooms, with an emphasis on wear resistance and easy cleaning.",
        "strengths": ["high wear resistance", "straightforward daily maintenance", "suited to busy family spaces"],
        "tradeoffs": ["underfoot feel and natural timber character are usually less warm than real-wood options"],
    },
    "floor_heating_ready": {
        "name": "Underfloor-Heating Ready Collection",
        "tagline": "Selected around dimensional stability, material route and household heating requirements.",
        "strengths": ["representative products are marked as suitable for underfloor heating", "supports comparison across budget, feel and maintenance"],
        "tradeoffs": ["the heating system, subfloor condition and installation requirements still need final confirmation"],
    },
    "natural_wood_comfort": {
        "name": "Natural Wood Comfort Collection",
        "tagline": "For owner-occupied homes where natural grain, warmth and underfoot feel matter most.",
        "strengths": ["authentic timber grain", "more natural underfoot feel", "warmer interior character"],
        "tradeoffs": ["typically higher budget", "more demanding moisture control and maintenance than SPC or laminate"],
    },
    "value_practical": {
        "name": "Value and Practicality Collection",
        "tagline": "Balances wear resistance, appearance and maintenance within a tighter budget.",
        "strengths": ["strong value for money", "easy installation and maintenance", "clear style options"],
        "tradeoffs": ["some products are not the first choice where strong water resistance is essential"],
    },
    "modern_design": {
        "name": "Modern Interior Design Collection",
        "tagline": "Light grey, grey, cream and dark-walnut directions for modern, contemporary-luxury and updated Chinese interiors.",
        "strengths": ["clear colour directions", "easy coordination with modern furniture and finishes"],
        "tradeoffs": ["final colour should be checked against physical samples, lighting, walls and furniture"],
    },
}

PROMOTION_EN: dict[str, dict[str, Any]] = {
    "DEMO-SPC-60": {
        "title": "Whole-Home SPC Support Package — Demo Promotion",
        "approved_message": (
            "A demo-only whole-home SPC support package is currently listed. For selected SPC products, projects with a suggested flooring area of at least 60 square metres may be assessed for store installation-support benefits. The exact benefit and final quotation must be confirmed in writing by store staff."
        ),
        "conditions": [
            "selected demo SPC products only",
            "suggested flooring area of at least 60 square metres",
            "pricing, installation and benefits require a formal written store quotation",
        ],
        "call_to_action": "Share an approximate area and I can check whether this demo promotion appears relevant to your project.",
    },
    "DEMO-WOOD-CONSULT": {
        "title": "Natural Wood Consultation Benefit — Demo Promotion",
        "approved_message": (
            "A demo consultation benefit is listed for the natural-wood collection. It can support further discussion of samples, room coordination and installation conditions. It does not mean free installation or a fixed discount, and the final scope must be confirmed by store staff."
        ),
        "conditions": [
            "engineered or three-layer wood demo products only",
            "samples, measurement and installation advice require store confirmation",
            "does not represent free installation or a fixed discount",
        ],
        "call_to_action": "Would you prefer to confirm underfoot feel and grain first, or assess budget and maintenance first?",
    },
    "DEMO-VALUE-ROOM": {
        "title": "Room Renovation Value Package — Demo Promotion",
        "approved_message": (
            "A demo-only value package is listed for bedrooms, studies and partial renovations. Selected laminate products with a suggested area of at least 15 square metres may be assessed as a package. Damp or high-water-resistance environments still require a separate material review."
        ),
        "conditions": [
            "selected laminate demo products only",
            "suggested area of at least 15 square metres",
            "damp or high-water-resistance environments require reassessment",
        ],
        "call_to_action": "Tell me the approximate area and intended installation timing so I can judge whether this demo package is worth comparing.",
    },
}

VALUE_EN = {
    "客厅": "living room",
    "卧室": "bedroom",
    "全屋": "whole home",
    "厨房": "kitchen",
    "书房": "study",
    "儿童房": "children's room",
    "老人房": "older person's room",
    "餐厅": "dining room",
    "出租房": "rental property",
    "现代简约": "modern minimalist",
    "北欧": "Scandinavian",
    "日式": "Japanese",
    "自然风": "natural",
    "轻奢": "contemporary luxury",
    "新中式": "contemporary Chinese",
    "现代": "modern",
    "原木": "natural timber",
    "奶油风": "cream-style interior",
    "经济": "economy",
    "中等": "mid-range",
    "偏高": "upper-mid range",
    "高端": "premium",
    "浅灰": "light grey",
    "浅灰色": "light grey",
    "灰调": "grey tone",
    "深胡桃色": "dark walnut",
    "原木色": "natural oak",
    "浅橡木色": "light oak",
    "奶油白": "cream white",
    "防水": "water resistance",
    "耐磨": "wear resistance",
    "环保": "environmental documentation",
    "价格": "budget",
    "脚感": "underfoot feel",
    "好清洁": "easy cleaning",
    "宠物": "pets",
    "地暖": "underfloor heating",
    "儿童": "children",
    "老人": "older family members",
    "潮湿环境": "a humid environment",
    "新房装修": "new-home fit-out",
    "旧房翻新": "existing-home renovation",
    "局部改造": "partial renovation",
    "自住": "owner-occupied home",
    "立即": "immediately",
    "1个月内": "within one month",
    "1-3个月": "within one to three months",
    "3个月以上": "more than three months",
    "待定": "not decided yet",
    "初步了解": "early research",
    "正在比较": "comparing options",
    "准备购买": "preparing to purchase",
    "等待家人决定": "waiting for a family decision",
    "价格顾虑": "budget concern",
    "环保顾虑": "environmental-documentation concern",
    "防水顾虑": "water-resistance concern",
    "维护顾虑": "maintenance concern",
    "脚感顾虑": "underfoot-feel concern",
    "需要商量": "needs family discussion",
    "需要比较": "needs comparison",
    "颜色顾虑": "colour concern",
    "high": "high",
    "medium": "medium",
    "low": "low",
}

EXACT_EN = {
    "我没有完全听清。请只确认一个最重要的条件。": "I did not fully catch that. Please confirm just one most important requirement.",
    "这次选地板，您最不愿意妥协的是哪一点：预算、耐磨、防水、脚感、环保，还是日常好清洁？": "For this flooring project, which point are you least willing to compromise on: budget, wear resistance, water resistance, underfoot feel, environmental documentation, or easy cleaning?",
    "明白了您的核心关注点。请问这次主要铺在客厅、卧室还是全屋？": "Understood. Is this mainly for the living room, bedroom, or the whole home?",
    "为了不让推荐偏离实际，您的预算更接近经济、中等、偏高还是高端？": "To keep the recommendation realistic, is your budget closer to economy, mid-range, upper-mid range, or premium?",
    "在满足核心使用需求的前提下，您更喜欢现代简约、北欧原木、新中式还是其他风格？": "Once the practical requirements are covered, do you prefer modern minimalist, Scandinavian natural timber, contemporary Chinese, or another style?",
    "为了让方案更接近最终效果，您更喜欢浅灰色、原木色还是深色系？": "To narrow the visual direction, do you prefer light grey, natural timber, or a darker colour scheme?",
    "为了判断活动条件、报价范围和铺装工作量，请问预计铺装面积大约多少平方米？": "To assess promotion conditions, quotation range and installation workload, approximately how many square metres will be covered?",
    "您计划什么时候铺装：1个月内、1到3个月、3个月以上，还是时间待定？": "When do you plan to install: within one month, within one to three months, more than three months away, or not decided yet?",
    "这个性能方向您是否认可？如果认可，我再帮您把颜色和整体风格收窄。": "Does this performance direction feel right? If so, I can narrow the colour and overall style next.",
    "这个主推方向是否符合您的预期，还是有哪一点仍然让您犹豫？": "Does this main recommendation meet your expectations, or is there one point that still makes you hesitate?",
    "请告诉我大概面积，我才能确认是否达到这项演示活动的建议条件。": "Please share an approximate area so I can check whether the suggested condition for this demo promotion is met.",
    "我们可以保留核心需求，只调整一个维度重新比较。": "We can keep the core requirement fixed and change just one comparison dimension.",
    "您更希望控制总预算，还是愿意为核心性能保留一定预算空间？": "Would you rather minimise the total budget, or keep some budget available for the core performance requirement?",
    "您和家人最可能分歧的是预算、颜色、脚感，还是材料性能？": "Where are you and your family most likely to differ: budget, colour, underfoot feel, or material performance?",
    "在目前的顾虑里，哪一点如果不能解决，您就不会继续考虑这个方案？": "Which current concern would stop you from considering this option if it cannot be resolved?",
    "您可以点击页面上的“获取方案与后续联系”，自愿选择联系方式和授权范围。": "You may use the separate ‘Get My Plan and Follow-Up’ form to choose a contact method and consent scope voluntarily.",
    "下一步可以确认面积、样板、正式报价或到店安排。": "The next step can be to confirm area, samples, a formal quotation, or a store visit.",
    "用于发送本次主推与备选方案，并在您授权的范围内跟进报价、样板或到店安排。": "This is used to send the main and backup options and, within your consent, follow up on quotations, samples or a store visit.",
    "您的本次方案联系授权已经保存，我不会重复索取联系方式。门店会按您授权的用途和时间安排后续。": "Your consent for follow-up on this plan has been saved. I will not ask for your contact details again, and the store will follow up only for the purposes and timing you authorised.",
    "当前批准的演示活动中，没有一项能在现有信息下确认适用。我不会自行编造折扣或活动条件。": "None of the approved demo promotions can be confirmed as applicable from the current information. I will not invent discounts or promotion conditions.",
    "云端智能服务暂时不可用。本次不会自动切换到本地模型，请稍后重试或重新开始并选择本地隐私模式。": "The cloud intelligence service is temporarily unavailable. This session will not silently switch to the local model. Please retry later or start again in local privacy mode.",
    "本地 Qwen 服务暂时不可用。请确认 Ollama 已启动并加载 qwen3.5:4b，然后再试一次。": "The local Qwen service is temporarily unavailable. Confirm that Ollama is running with qwen3.5:4b loaded, then try again.",
    "好的，我已经记录了您刚才确认的内容。": "Understood. I have recorded the information you just confirmed.",
    "好的，我已经记录了您刚才确认的需求。": "Understood. I have recorded the requirements you just confirmed.",
}

TRADEOFF_EN = {
    "脚感与天然木质感通常不如实木类产品温润": "underfoot feel and natural timber character are usually less warm than real-wood options",
    "最终铺装仍需确认地暖系统、基层条件和安装要求": "the heating system, subfloor condition and installation requirements still need final confirmation",
    "预算通常更高": "the budget is usually higher",
    "防潮和日常维护要求高于 SPC 与强化类产品": "moisture control and daily maintenance are more demanding than for SPC or laminate",
    "部分产品不适合作为高防水场景的首选": "some products are not the first choice where strong water resistance is essential",
    "最终颜色应结合门店样板、采光和墙面家具共同确认": "final colour should be checked against physical samples, lighting, walls and furniture",
    "当前演示产品数据未提供可核验的环保认证或检测信息，不能据此作环保承诺": "the demo product data does not include verifiable environmental certificates or test reports, so no environmental claim can be made",
}

OBJECTION_EN = {
    "价格顾虑是合理的；我们应比较主推款解决的核心风险，以及备选款能节省预算时牺牲了什么。": "Your budget concern is reasonable. We should compare the core risk addressed by the main option with what the backup option gives up in exchange for a lower budget.",
    "环保问题必须以可核验的检测或认证资料为准；当前演示数据不足以支持额外环保承诺。": "Environmental claims must rely on verifiable test reports or certification. The current demo data is not sufficient for any additional environmental promise.",
    "防水标记只能说明当前产品资料中的能力方向，最终仍需确认铺装边界、接缝和使用环境。": "The water-resistance flag only indicates the direction supported by the current product data. Edges, joints and the real use environment still need confirmation.",
    "维护成本应结合水渍、宠物、清洁频率和材料脚感一起判断，不能只看一个参数。": "Maintenance should be judged together with spills, pets, cleaning frequency and underfoot feel, not from one parameter alone.",
    "脚感与耐磨、防水和预算往往存在取舍，可以保留核心性能后再比较实木类备选。": "Underfoot feel often trades off against wear resistance, water resistance and budget. We can preserve the core requirement and then compare a real-wood alternative.",
    "可以先保留主推款与备选款的差异摘要，方便您和家人围绕同一组标准讨论。": "We can keep a concise comparison of the main and backup options so your family can discuss the same set of criteria.",
    "比较时应固定空间和核心需求，只改变材质或预算一个变量，避免被无关参数干扰。": "For a useful comparison, keep the room and core requirement fixed and change only one variable, such as material or budget.",
    "颜色必须结合采光、墙面和家具确认；当前建议只用于收窄方向，不能替代现场样板。": "Colour must be checked against lighting, walls and furniture. The current recommendation only narrows the direction and cannot replace physical samples.",
}


def contains_cjk(text: str | None) -> bool:
    return bool(text and re.search(r"[\u4e00-\u9fff]", text))


def value_en(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return VALUE_EN.get(value, value)


def translate_text(text: str | None, *, fallback: str = "") -> str | None:
    if text is None:
        return None
    stripped = str(text).strip()
    if not stripped:
        return stripped
    if stripped in EXACT_EN:
        return EXACT_EN[stripped]
    if stripped in TRADEOFF_EN:
        return TRADEOFF_EN[stripped]
    if stripped in OBJECTION_EN:
        return OBJECTION_EN[stripped]

    for product_id, info in PRODUCT_EN.items():
        chinese_names = {
            "WF-SPC-001": "云杉浅灰 SPC 锁扣地板",
            "WF-WOOD-002": "原木橡木多层实木地板",
            "WF-LAM-003": "晨雾灰强化复合地板",
            "WF-SPC-004": "深胡桃防水 SPC 地板",
            "WF-WOOD-005": "温润浅橡三层实木地板",
            "WF-LAM-006": "奶油白高耐磨强化地板",
        }
        stripped = stripped.replace(chinese_names[product_id], info["name"])

    prefix_rules = [
        (r"^首要购买驱动：(.+)$", "Primary purchase driver: {}"),
        (r"^项目类型：(.+)$", "Project type: {}"),
        (r"^使用空间：(.+)$", "Room: {}"),
        (r"^预计面积：(.+)$", "Estimated area: {}"),
        (r"^计划铺装：(.+)$", "Planned installation: {}"),
        (r"^决策阶段：(.+)$", "Decision stage: {}"),
        (r"^风格：(.+)$", "Style: {}"),
        (r"^预算：(.+)$", "Budget: {}"),
        (r"^颜色偏好：(.+)$", "Colour preference: {}"),
        (r"^当前顾虑：(.+)$", "Current concerns: {}"),
    ]
    for pattern, template in prefix_rules:
        match = re.match(pattern, stripped)
        if match:
            values = [VALUE_EN.get(part, part) for part in re.split(r"[、/；]", match.group(1))]
            return template.format(", ".join(values))

    match = re.match(r"^有(.+)需求$", stripped)
    if match:
        return f"Needs support for {VALUE_EN.get(match.group(1), match.group(1))}"
    match = re.match(r"^无(.+)需求$", stripped)
    if match:
        return f"No requirement for {VALUE_EN.get(match.group(1), match.group(1))}"
    match = re.match(r"^(.+)优先级：(high|medium|low)$", stripped)
    if match:
        return f"{VALUE_EN.get(match.group(1), match.group(1))} priority: {match.group(2)}"
    match = re.match(r"^适合(.+)$", stripped)
    if match:
        return f"suited to the {VALUE_EN.get(match.group(1), match.group(1))}"
    match = re.match(r"^符合(.+)预算$", stripped)
    if match:
        return f"fits a {VALUE_EN.get(match.group(1), match.group(1))} budget"

    replacements = {
        "符合宠物家庭需求": "fits a household with pets",
        "支持地暖": "supports underfloor heating",
        "适合关注防水的环境": "suited to an environment where water resistance matters",
        "符合耐磨优先要求": "fits a wear-resistance-first requirement",
        "符合脚感优先要求": "fits an underfoot-feel-first requirement",
        "日常维护相对容易": "relatively easy to maintain day to day",
        "符合颜色偏好": "matches the colour preference",
        "符合您把防水放在首位的要求": "matches your water-resistance-first requirement",
        "符合您把耐磨放在首位的要求": "matches your wear-resistance-first requirement",
        "符合您优先控制预算的要求": "matches your priority to control the budget",
        "符合您把脚感放在首位的要求": "matches your underfoot-feel-first requirement",
        "符合您把日常好清洁放在首位的要求": "matches your easy-cleaning-first requirement",
        "产品资料中包含与环保相关的批准信息": "the approved product information includes relevant environmental documentation",
    }
    if stripped in replacements:
        return replacements[stripped]

    if stripped.startswith("明白了，我已经抓住您关于"):
        return "Understood. I have recorded the key points you confirmed."
    if stripped.startswith("好的，我已经记录并整理为："):
        body = stripped.removeprefix("好的，我已经记录并整理为：").rstrip("。")
        translated_parts = [translate_text(part, fallback="") or "" for part in body.split("；")]
        translated_parts = [part for part in translated_parts if part]
        return "Understood. I have recorded: " + "; ".join(translated_parts) + "."

    if contains_cjk(stripped):
        return fallback or "Understood. I have recorded the information you confirmed."
    return stripped


def localize_answer_plan_payload(payload: dict[str, Any], language: str) -> dict[str, Any]:
    if language != "en":
        return payload

    output = copy.deepcopy(payload)
    output["response_language"] = "en"
    output["sales_objective"] = translate_text(
        output.get("sales_objective"),
        fallback="Respond accurately and move the consultation to one clear next step.",
    )
    output["company_highlights"] = [
        translate_text(item, fallback="The store uses scenario-based flooring selection and explains trade-offs clearly.")
        for item in output.get("company_highlights", [])
    ]
    output["customer_need_summary"] = [
        translate_text(item, fallback="Confirmed customer requirement")
        for item in output.get("customer_need_summary", [])
    ]
    output["constraints"] = [
        "Use only approved products, collections, promotions, matching reasons and trade-offs.",
        "Do not change the products or main/backup roles selected by the backend.",
        "Do not invent prices, stock, discounts, warranties, certifications, case studies or installation dates.",
        "Contact details must be collected only through the separate consent form.",
        "Keep consultation follow-up consent separate from long-term marketing consent.",
    ]
    output["objection_response"] = [
        translate_text(item, fallback="Acknowledge the concern, explain the trade-off and propose one verifiable next step.")
        for item in output.get("objection_response", [])
    ]

    localized_products: list[dict[str, Any]] = []
    for product in output.get("products", []):
        item = dict(product)
        info = PRODUCT_EN.get(str(item.get("product_id") or ""))
        if info:
            item.update(
                {
                    "name": info["name"],
                    "product_type": info["type"],
                    "color": info["color"],
                    "price_range": info["price_range"],
                    "presentation_role": {
                        "主推款": "main recommendation",
                        "备选款": "backup option",
                        "对比款": "comparison option",
                    }.get(str(item.get("presentation_role")), str(item.get("presentation_role") or "option")),
                    "approved_facts": [
                        f"Material: {info['type']}",
                        f"Colour: {info['color']}",
                        f"Price range: {info['price_range']}",
                        "Suitable rooms: " + ", ".join(info["rooms"]),
                        f"Wear rating: {info['wear_level']}",
                        "Underfloor heating: " + ("supported" if info["floor_heating"] else "not marked as supported"),
                        "Pet friendly: " + ("yes" if info["pet_friendly"] else "no"),
                        "Water resistance flag: " + ("yes" if info["waterproof"] else "no"),
                        f"Dimensions: {info['spec']}",
                        *info["selling_points"],
                    ],
                    "match_reasons": [
                        translate_text(reason, fallback="matches a confirmed customer requirement")
                        for reason in item.get("match_reasons", [])
                    ],
                    "tradeoffs": [
                        translate_text(reason, fallback="the final choice still requires balancing performance, feel, maintenance and budget")
                        for reason in item.get("tradeoffs", [])
                    ],
                }
            )
        localized_products.append(item)
    output["products"] = localized_products

    localized_collections: list[dict[str, Any]] = []
    for collection in output.get("featured_collections", []):
        item = dict(collection)
        info = COLLECTION_EN.get(str(item.get("collection_id") or ""))
        if info:
            item.update(info)
        localized_collections.append(item)
    output["featured_collections"] = localized_collections

    localized_promotions: list[dict[str, Any]] = []
    for promotion in output.get("approved_promotions", []):
        item = dict(promotion)
        info = PROMOTION_EN.get(str(item.get("promotion_id") or ""))
        if info:
            item.update(info)
        localized_promotions.append(item)
    output["approved_promotions"] = localized_promotions

    for key, fallback in {
        "call_to_action": "Choose one practical next step: confirm the area, review samples, request a formal quotation, or arrange a store visit.",
        "contact_request_reason": "This is used only to send this plan and follow up within the consent you choose.",
        "next_question": "Which one point would you like to confirm next?",
        "direct_message": "Understood. I have recorded the information you confirmed.",
    }.items():
        if output.get(key):
            output[key] = translate_text(str(output[key]), fallback=fallback)

    return output


def localize_direct_message(text: str | None, language: str) -> str | None:
    if language != "en":
        return text
    return translate_text(text, fallback="Understood. I have recorded the information you confirmed.")
