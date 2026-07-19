from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

RouteName = Literal[
    "deterministic_direct",
    "realtime_direct",
    "terra",
    "repeat_last",
    "stop_speaking",
]


@dataclass(frozen=True)
class TurnRoute:
    route: RouteName
    intent: str
    reason: str
    answer: str | None = None
    realtime_instruction: str | None = None


class TurnRouter:
    """Conservative route guard for the voice-agent front door.

    Realtime may understand and speak, but this backend guard decides whether a
    turn is safe to answer without the sales/knowledge pipeline. Unknown turns
    intentionally go to Terra so product facts and mutable customer state remain
    under the existing deterministic validation layer.
    """

    _BUSINESS_WORDS = (
        "地板",
        "spc",
        "实木",
        "强化",
        "复合",
        "产品",
        "价格",
        "报价",
        "预算",
        "面积",
        "平方",
        "活动",
        "优惠",
        "促销",
        "折扣",
        "耐磨",
        "防水",
        "地暖",
        "脚感",
        "环保",
        "颜色",
        "浅灰",
        "深灰",
        "胡桃",
        "原木",
        "推荐",
        "比较",
        "对比",
        "为什么",
        "适合",
        "安装",
        "铺装",
        "宠物",
        "客厅",
        "卧室",
        "全屋",
        "floor",
        "flooring",
        "price",
        "budget",
        "square",
        "promotion",
        "discount",
        "waterproof",
        "wear",
        "heating",
        "colour",
        "color",
        "recommend",
        "compare",
        "installation",
    )

    _SELF_INTRO = (
        r"(?:再|重新)?(?:自我)?介绍(?:一下)?(?:你自己|自己)?",
        r"你是谁",
        r"你叫什么",
        r"what(?:'s| is) your name",
        r"who are you",
        r"introduce yourself",
    )
    _CAPABILITIES = (
        r"你能做什么",
        r"你会做什么",
        r"你可以帮我什么",
        r"有什么功能",
        r"what can you do",
        r"how can you help",
    )
    _GREETING = (
        r"^(你好|您好|嗨|哈[喽啰]|早上好|下午好|晚上好)[！!。.]?$",
        r"^(hello|hi|hey|good morning|good afternoon|good evening)[!.]?$",
    )
    _THANKS = (
        r"^(谢谢|多谢|感谢|好的谢谢|明白了谢谢)[！!。.]?$",
        r"^(thanks|thank you|got it,? thanks)[!.]?$",
    )
    _REPEAT = (
        r"再说一遍",
        r"重复(?:一下)?",
        r"刚才说了什么",
        r"say that again",
        r"repeat (?:that|your answer)",
    )
    _STOP = (
        r"^(停|停止|停一下|别说了|不用讲了|暂停)[！!。.]?$",
        r"^(stop|pause|be quiet)[!.]?$",
    )
    _HELP = (
        r"怎么使用",
        r"怎么操作",
        r"我该怎么开始",
        r"how do i use this",
        r"how do i start",
    )
    _SMALLTALK = (
        r"见到你很高兴",
        r"你说话.*(?:自然|真人)",
        r"这里.*(?:吵|嘈杂).*(?:听清|听见)",
        r"nice to meet you",
        r"you sound (?:natural|human)",
        r"can you hear me",
    )

    def route(self, text: str, language: str = "zh") -> TurnRoute:
        normalized = self._normalize(text)
        lowered = normalized.lower()

        if self._matches(lowered, self._STOP):
            return TurnRoute(
                route="stop_speaking",
                intent="cancel_or_stop",
                reason="explicit stop command",
                answer="好的，我停下了。" if language != "en" else "Okay, I have stopped.",
            )

        if self._matches(lowered, self._REPEAT):
            return TurnRoute(
                route="repeat_last",
                intent="repeat_request",
                reason="explicit repeat request",
            )

        if self._matches(lowered, self._SELF_INTRO):
            return TurnRoute(
                route="deterministic_direct",
                intent="self_introduction",
                reason="canonical persona request",
                answer=self._self_intro(language),
            )

        if self._matches(lowered, self._CAPABILITIES):
            return TurnRoute(
                route="deterministic_direct",
                intent="capability_question",
                reason="canonical capability request",
                answer=self._capabilities(language),
            )

        if self._matches(lowered, self._GREETING):
            return TurnRoute(
                route="deterministic_direct",
                intent="greeting",
                reason="simple greeting",
                answer=(
                    "您好，我是小木。您可以直接告诉我最在意的空间、预算或使用需求。"
                    if language != "en"
                    else "Hello, I am Xiao Mu. Tell me the room, budget, or practical requirement that matters most to you."
                ),
            )

        if self._matches(lowered, self._THANKS):
            return TurnRoute(
                route="deterministic_direct",
                intent="thanks",
                reason="simple thanks",
                answer="不客气，有需要您可以继续问我。" if language != "en" else "You are welcome. Ask me anything else when you are ready.",
            )

        if self._matches(lowered, self._HELP):
            return TurnRoute(
                route="deterministic_direct",
                intent="help_request",
                reason="canonical interaction help",
                answer=(
                    "按下“点击说话”，看到正在聆听后说完整句话，再点击“停止说话”。您也可以直接在输入框里打字。"
                    if language != "en"
                    else "Press the talk button, wait until listening starts, say the complete sentence, and then press stop. You can also type in the text box."
                ),
            )

        if self._contains_business_signal(lowered):
            return TurnRoute(
                route="terra",
                intent="business_or_reasoning",
                reason="business facts, recommendation, mutable preference, or reasoning required",
            )

        if self._matches(lowered, self._SMALLTALK):
            return TurnRoute(
                route="realtime_direct",
                intent="smalltalk",
                reason="safe social turn with no business-state mutation",
                realtime_instruction=(
                    "请以小木的身份自然回答，最多两句。不要推荐产品，不要声称价格、活动、库存或执行结果，也不要修改客户偏好。"
                    if language != "en"
                    else "Reply naturally as Xiao Mu in no more than two sentences. Do not recommend products, claim prices, promotions, stock, or completed actions, and do not modify customer preferences."
                ),
            )

        return TurnRoute(
            route="terra",
            intent="unknown_requires_guarded_reasoning",
            reason="unknown turns default to the guarded Terra pipeline",
        )

    @classmethod
    def _contains_business_signal(cls, text: str) -> bool:
        return any(word in text for word in cls._BUSINESS_WORDS)

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

    @staticmethod
    def _matches(text: str, patterns: tuple[str, ...]) -> bool:
        return any(re.search(pattern, text, flags=re.IGNORECASE) is not None for pattern in patterns)

    @staticmethod
    def _self_intro(language: str) -> str:
        if language == "en":
            return (
                "I am Xiao Mu, the smart flooring consultant at Senjing Flooring Living Gallery. "
                "I can help you compare materials, narrow a main option and a backup, and explain the practical trade-offs for your home."
            )
        return (
            "我是小木，森境地板生活馆的智能选购顾问。"
            "我可以根据您的空间、预算和实际使用需求，帮您筛选主推款与备选款，并说明每种选择的优点和取舍。"
        )

    @staticmethod
    def _capabilities(language: str) -> str:
        if language == "en":
            return (
                "I can understand spoken questions, compare flooring materials and products, remember the requirements you confirm, "
                "and explain recommendations, promotions, and next steps. I will ask before any action that needs your consent."
            )
        return (
            "我可以听懂您的语音问题，比较地板材质和产品，记录您明确确认的需求，并解释推荐理由、活动条件和下一步安排。"
            "需要您授权的操作，我会先征求您的同意。"
        )
