from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from typing import Any

import requests

from ..localization import localize_direct_message
from ..models import CustomerProfile
from ..response_language import get_current_response_language
from .prompts import (
    EN_QWEN_RENDER_SYSTEM_PROMPT,
    EN_RENDER_SYSTEM_PROMPT,
    PARSE_SYSTEM_PROMPT,
    QWEN_RENDER_SYSTEM_PROMPT,
    RENDER_SYSTEM_PROMPT,
    build_parse_user_prompt,
    build_render_user_prompt,
)
from .schemas import AnswerPlan, DialogueProviderName, SemanticTurn, SEMANTIC_TURN_JSON_SCHEMA


class DialogueProviderError(RuntimeError):
    pass


def _remove_trailing_question(text: str) -> str:
    """Remove a final question sentence from a normal product-led response."""

    cleaned = text.strip()
    if not cleaned.endswith(("?", "？")):
        return cleaned

    # Remove only the final sentence, preserving the product explanation before it.
    match = re.search(r"(?:^|(?<=[。！？.!?]))[^。！？.!?]*[?？]\s*$", cleaned)
    if match:
        cleaned = cleaned[: match.start()].strip()
    return cleaned.rstrip("。.!！?？ ")


def _finalize_sales_answer(text: str, answer_plan: AnswerPlan, language: str) -> str:
    """Backend guard against renderers restarting the questionnaire.

    Prompts guide the model, but a smaller local model can still append the
    AnswerPlan's legacy next_question. Normal recommendation and comparison turns
    must end with a low-pressure statement instead of another forced question.
    """

    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if answer_plan.response_type not in {"recommendation", "comparison"}:
        return cleaned

    statement = (
        "You can first consider these two directions. Whenever you are ready, share any one detail such as the room, budget, colour, area or timing, and I will refine the options without restarting a questionnaire."
        if language == "en"
        else "您可以先感受这两个方向，想继续时再告诉我空间、预算、颜色、面积或时间中的任意一项，我会直接收窄方案，不会重新开始一轮问卷。"
    )

    without_question = _remove_trailing_question(cleaned)
    if not without_question:
        return statement
    if without_question.endswith(("。", ".", "!", "！")):
        return without_question + statement
    return without_question + (" " if language == "en" else "。") + statement


class DialogueLLMProvider(ABC):
    provider_name: DialogueProviderName
    display_name: str

    @abstractmethod
    def parse_turn(
        self,
        *,
        user_text: str,
        current_profile: CustomerProfile,
        dialogue_context: dict[str, Any] | None = None,
    ) -> SemanticTurn:
        raise NotImplementedError

    @abstractmethod
    def render_answer(self, *, answer_plan: AnswerPlan) -> str:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> dict[str, Any]:
        raise NotImplementedError


class TerraDialogueProvider(DialogueLLMProvider):
    provider_name: DialogueProviderName = "terra"
    display_name = "Cloud Intelligence · Terra"

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = os.getenv("OPENAI_DIALOGUE_MODEL", os.getenv("OPENAI_PARSE_MODEL", "gpt-5.6-terra"))
        self.parse_timeout = float(os.getenv("OPENAI_PARSE_TIMEOUT_SECONDS", "12"))
        self.render_timeout = float(os.getenv("OPENAI_RENDER_TIMEOUT_SECONDS", "15"))

    def _post(self, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if not self.api_key:
            raise DialogueProviderError("OPENAI_API_KEY is not configured for Terra mode")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json; charset=utf-8",
        }
        project_id = os.getenv("OPENAI_PROJECT_ID", "").strip()
        organization_id = os.getenv("OPENAI_ORG_ID", "").strip()
        if project_id:
            headers["OpenAI-Project"] = project_id
        if organization_id:
            headers["OpenAI-Organization"] = organization_id
        try:
            response = requests.post(
                f"{self.base_url}/responses",
                headers=headers,
                json=payload,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            raise DialogueProviderError(f"OpenAI request failed: {exc}") from exc
        if response.status_code >= 400:
            raise DialogueProviderError(f"OpenAI HTTP {response.status_code}: {response.text[:500]}")
        try:
            return response.json()
        except ValueError as exc:
            raise DialogueProviderError("OpenAI returned invalid JSON") from exc

    @staticmethod
    def _output_text(response: dict[str, Any]) -> str:
        direct = response.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
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
                    raise DialogueProviderError("OpenAI refused the dialogue request")
        text = "".join(parts).strip()
        if not text:
            raise DialogueProviderError(f"OpenAI response contained no output text; status={response.get('status')}")
        return text

    def parse_turn(
        self,
        *,
        user_text: str,
        current_profile: CustomerProfile,
        dialogue_context: dict[str, Any] | None = None,
    ) -> SemanticTurn:
        payload = {
            "model": self.model,
            "input": [
                {"role": "system", "content": PARSE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_parse_user_prompt(
                        user_text,
                        current_profile.model_dump(),
                        dialogue_context,
                    ),
                },
            ],
            "reasoning": {"effort": "none"},
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "flooring_semantic_turn",
                    "strict": True,
                    "schema": SEMANTIC_TURN_JSON_SCHEMA,
                }
            },
            "max_output_tokens": 800,
            "store": False,
        }
        raw = self._output_text(self._post(payload, self.parse_timeout))
        try:
            return SemanticTurn.model_validate_json(raw)
        except Exception as exc:
            raise DialogueProviderError(f"Terra semantic output failed validation: {exc}") from exc

    def render_answer(self, *, answer_plan: AnswerPlan) -> str:
        language = get_current_response_language()
        if answer_plan.direct_message and answer_plan.response_type in {
            "clarification",
            "service_unavailable",
        }:
            return localize_direct_message(answer_plan.direct_message, language) or answer_plan.direct_message
        system_prompt = EN_RENDER_SYSTEM_PROMPT if language == "en" else RENDER_SYSTEM_PROMPT
        payload = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": build_render_user_prompt(answer_plan, response_language=language),
                },
            ],
            "reasoning": {"effort": "none"},
            "max_output_tokens": 420 if language == "en" else 360,
            "store": False,
        }
        rendered = self._output_text(self._post(payload, self.render_timeout))
        return _finalize_sales_answer(rendered, answer_plan, language)

    def health(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "display_name": self.display_name,
            "configured": bool(self.api_key),
            "available": bool(self.api_key),
            "model": self.model,
            "privacy": "minimal turn context is sent to OpenAI; product catalog and session files remain local",
        }


class QwenDialogueProvider(DialogueLLMProvider):
    provider_name: DialogueProviderName = "qwen"
    display_name = "Private Local AI · Qwen 3.5"

    def __init__(self) -> None:
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        self.model = os.getenv("OLLAMA_DIALOGUE_MODEL", os.getenv("OLLAMA_CHAT_MODEL", "qwen3.5:4b"))
        self.parse_timeout = float(os.getenv("OLLAMA_PARSE_TIMEOUT_SECONDS", "20"))
        self.render_timeout = float(os.getenv("OLLAMA_RENDER_TIMEOUT_SECONDS", "15"))
        self.keep_alive = os.getenv("OLLAMA_KEEP_ALIVE", "30m")

    def _chat(self, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            raise DialogueProviderError(f"Ollama request failed: {exc}") from exc
        if response.status_code >= 400:
            raise DialogueProviderError(f"Ollama HTTP {response.status_code}: {response.text[:500]}")
        try:
            return response.json()
        except ValueError as exc:
            raise DialogueProviderError("Ollama returned invalid JSON") from exc

    def parse_turn(
        self,
        *,
        user_text: str,
        current_profile: CustomerProfile,
        dialogue_context: dict[str, Any] | None = None,
    ) -> SemanticTurn:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": PARSE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_parse_user_prompt(
                        user_text,
                        current_profile.model_dump(),
                        dialogue_context,
                    ),
                },
            ],
            "stream": False,
            "think": False,
            "format": SEMANTIC_TURN_JSON_SCHEMA,
            "keep_alive": self.keep_alive,
            "options": {
                "num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "4096")),
                "num_predict": int(os.getenv("OLLAMA_PARSE_MAX_TOKENS", "500")),
                "temperature": 0,
            },
        }
        response = self._chat(payload, self.parse_timeout)
        content = str(response.get("message", {}).get("content") or "").strip()
        if not content:
            raise DialogueProviderError("Qwen returned an empty semantic response")
        try:
            return SemanticTurn.model_validate_json(content)
        except Exception as exc:
            raise DialogueProviderError(f"Qwen semantic output failed validation: {exc}") from exc

    def render_answer(self, *, answer_plan: AnswerPlan) -> str:
        language = get_current_response_language()
        if answer_plan.direct_message and answer_plan.response_type in {
            "clarification",
            "service_unavailable",
        }:
            return localize_direct_message(answer_plan.direct_message, language) or answer_plan.direct_message
        system_prompt = EN_QWEN_RENDER_SYSTEM_PROMPT if language == "en" else QWEN_RENDER_SYSTEM_PROMPT
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": build_render_user_prompt(answer_plan, response_language=language),
                },
            ],
            "stream": False,
            "think": False,
            "keep_alive": self.keep_alive,
            "options": {
                "num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "4096")),
                "num_predict": int(os.getenv("OLLAMA_RENDER_MAX_TOKENS", "260" if language == "en" else "220")),
                "temperature": 0.2,
            },
        }
        response = self._chat(payload, self.render_timeout)
        content = str(response.get("message", {}).get("content") or "").strip()
        if not content:
            raise DialogueProviderError("Qwen returned an empty customer answer")
        return _finalize_sales_answer(content, answer_plan, language)

    def health(self) -> dict[str, Any]:
        available = False
        model_present = False
        error: str | None = None
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=1.5)
            available = response.ok
            if response.ok:
                names = {
                    str(item.get("name") or item.get("model") or "")
                    for item in response.json().get("models", [])
                    if isinstance(item, dict)
                }
                model_present = self.model in names or any(name.startswith(self.model + ":") for name in names)
        except Exception as exc:
            error = str(exc)
        return {
            "provider": self.provider_name,
            "display_name": self.display_name,
            "configured": True,
            "available": available,
            "model": self.model,
            "model_present": model_present,
            "base_url": self.base_url,
            "privacy": "all LLM inference stays on this PC",
            "error": error,
        }


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[DialogueProviderName, DialogueLLMProvider] = {
            "terra": TerraDialogueProvider(),
            "qwen": QwenDialogueProvider(),
        }

    def get(self, mode: DialogueProviderName) -> DialogueLLMProvider:
        try:
            return self._providers[mode]
        except KeyError as exc:
            raise DialogueProviderError(f"Unsupported dialogue provider: {mode}") from exc

    def status(self) -> dict[str, dict[str, Any]]:
        return {name: provider.health() for name, provider in self._providers.items()}
