from __future__ import annotations

import hashlib
import json
import os

import requests
from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

router = APIRouter(tags=["realtime-asr"])

_MAX_SDP_BYTES = 256_000
_DEFAULT_MODEL = "gpt-realtime-2.1"


def _realtime_model() -> str:
    return os.getenv("OPENAI_REALTIME_MODEL", _DEFAULT_MODEL).strip() or _DEFAULT_MODEL


def _realtime_enabled() -> bool:
    value = os.getenv("OPENAI_REALTIME_ENABLED", "true").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _base_instructions() -> str:
    return """
You are the speech-understanding layer for a wood-floor retail demo.
Your only job is to listen to each complete user audio turn and return the user's final intended utterance as plain text.
Do not answer the user. Do not recommend products. Do not explain your reasoning.

Self-correction rules:
- Later explicit corrections override earlier uncertain words.
- Chinese correction signals include 不, 不是, 不对, 我是说, 应该是, and 纠正一下.
- Character explanations are authoritative. Example: 深浅的浅，灰色的灰 means 浅灰色.
- Preserve all requirements that the user did not retract.
- Use the surrounding conversation and the supplied flooring vocabulary only to resolve plausible acoustic ambiguity.
- Never invent a requirement that is not supported by the audio.
- If the audio is genuinely unintelligible or two interpretations remain equally plausible, return exactly __UNCLEAR__.
- Otherwise return only the normalized utterance, without labels, quotation marks, JSON, Markdown, or commentary.
""".strip()


def _safety_identifier(session_id: str) -> str:
    digest = hashlib.sha256(session_id.encode("utf-8", errors="ignore")).hexdigest()
    return f"woodfloor-demo-{digest[:32]}"


@router.get("/api/realtime/status")
def realtime_status() -> dict:
    configured = bool(os.getenv("OPENAI_API_KEY")) and _realtime_enabled()
    return {
        "ok": True,
        "configured": configured,
        "enabled": _realtime_enabled(),
        "model": _realtime_model(),
        "transport": "webrtc",
        "turn_mode": "push_to_talk",
        "output_modalities": ["text"],
        "api_key_present": bool(os.getenv("OPENAI_API_KEY")),
        "legacy_browser_asr_preserved": True,
    }


@router.post("/api/realtime/session")
async def create_realtime_session(request: Request, session_id: str = "demo-session-001") -> Response:
    if not _realtime_enabled():
        raise HTTPException(status_code=503, detail="GPT Realtime ASR is disabled by OPENAI_REALTIME_ENABLED.")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not set in the Backend process.")

    raw_sdp = await request.body()
    if not raw_sdp:
        raise HTTPException(status_code=400, detail="Realtime WebRTC SDP offer is empty.")
    if len(raw_sdp) > _MAX_SDP_BYTES:
        raise HTTPException(status_code=413, detail="Realtime WebRTC SDP offer is too large.")

    try:
        sdp_offer = raw_sdp.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Realtime WebRTC SDP offer must be UTF-8 text.") from exc

    session_config = {
        "type": "realtime",
        "model": _realtime_model(),
        "output_modalities": ["text"],
        "audio": {
            "input": {
                "turn_detection": None,
            }
        },
        "instructions": _base_instructions(),
    }

    multipart = {
        "sdp": (None, sdp_offer, "application/sdp"),
        "session": (None, json.dumps(session_config, ensure_ascii=False), "application/json"),
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Safety-Identifier": _safety_identifier(session_id),
    }
    timeout = float(os.getenv("OPENAI_REALTIME_CONNECT_TIMEOUT_SECONDS", "30"))

    try:
        upstream = await run_in_threadpool(
            requests.post,
            "https://api.openai.com/v1/realtime/calls",
            headers=headers,
            files=multipart,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Could not create GPT Realtime session: {exc}") from exc

    if upstream.status_code >= 400:
        detail = upstream.text[:1200]
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI Realtime session creation failed ({upstream.status_code}): {detail}",
        )

    return Response(
        content=upstream.content,
        media_type="application/sdp",
        headers={
            "Cache-Control": "no-store",
            "X-Realtime-Model": _realtime_model(),
            "X-Realtime-Turn-Mode": "push-to-talk",
        },
    )
