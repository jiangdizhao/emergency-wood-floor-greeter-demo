from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ContactPIIDetection:
    detected: bool
    categories: tuple[str, ...] = ()


class ContactPIIGuard:
    """Detects likely contact PII before Terra or Qwen receives user text.

    This is intentionally conservative for phone, email and explicit WeChat/name
    disclosures. Flooring measurements such as `80平` are not blocked because the
    digit threshold is seven characters.
    """

    EMAIL_PATTERN = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+", re.IGNORECASE)
    PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?\d[\s()\-]*){7,18}(?!\d)")
    CHINESE_DIGIT_PATTERN = re.compile(r"[零〇一二两三四五六七八九幺]{7,18}")
    WECHAT_PATTERN = re.compile(
        r"(?:微信|微信号|wechat|wx)\s*(?:是|为|:|：)?\s*[A-Za-z0-9_\-\.\u4e00-\u9fff]{2,60}",
        re.IGNORECASE,
    )
    NAME_PATTERN = re.compile(r"(?:我叫|我的名字是|姓名是|称呼我)[\u4e00-\u9fffA-Za-z·\s]{2,30}")

    def detect(self, text: str) -> ContactPIIDetection:
        value = str(text or "").strip()
        categories: list[str] = []
        if self.EMAIL_PATTERN.search(value):
            categories.append("email")
        if self.PHONE_PATTERN.search(value) or self.CHINESE_DIGIT_PATTERN.search(value):
            categories.append("phone")
        if self.WECHAT_PATTERN.search(value):
            categories.append("wechat")
        if self.NAME_PATTERN.search(value):
            categories.append("name")
        return ContactPIIDetection(
            detected=bool(categories),
            categories=tuple(dict.fromkeys(categories)),
        )

    @staticmethod
    def customer_message() -> str:
        return (
            "为了保护您的隐私，请不要在聊天或语音中直接发送姓名、手机号、微信号或邮箱。"
            "刚才的敏感内容不会发送给 Terra 或 Qwen，也不会按原文写入对话历史。"
            "当页面出现“获取方案与后续联系”按钮后，请使用独立表单选择联系方式和授权范围。"
        )
