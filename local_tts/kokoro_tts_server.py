from __future__ import annotations

import io
import os
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Literal

import soundfile as sf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.responses import Response


@dataclass
class KokoroRuntime:
    lock: threading.RLock
    inference_lock: threading.Lock
    en_pipeline: object | None = None
    zh_pipeline: object | None = None
    loaded_at: float | None = None
    load_error: str | None = None
    warmup_started_at: float | None = None
    warmup_completed_at: float | None = None
    warmup_cache: dict[tuple[str, str, float, str], bytes] = field(default_factory=dict)
    warmup_errors: dict[str, str] = field(default_factory=dict)


class LocalTTSRequest(BaseModel):
    text: str = Field(min_length=1)
    language: Literal["zh", "en"] = "en"
    voice: str | None = None
    speed: float = 1.0


runtime = KokoroRuntime(lock=threading.RLock(), inference_lock=threading.Lock())

DEFAULT_EN_VOICE = os.getenv("KOKORO_EN_VOICE", "af_heart")
DEFAULT_ZH_VOICE = os.getenv("KOKORO_ZH_VOICE", "zm_yunxi")
SAMPLE_RATE = int(os.getenv("KOKORO_SAMPLE_RATE", "24000"))
WARMUP_ON_START = os.getenv("KOKORO_WARMUP_ON_START", "true").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
WARMUP_TEXT_ZH = os.getenv(
    "KOKORO_WARMUP_TEXT_ZH",
    "您好，欢迎来到木地板体验区。我是您的 AI 选购顾问小木。我可以根据房间、装修风格、预算，以及地暖、宠物和日常清洁需求，为您推荐合适的地板。请问您这次主要想为哪个空间选择地板呢？",
)
WARMUP_ZH_VOICES = tuple(
    dict.fromkeys(
        [
            DEFAULT_ZH_VOICE,
            *[
                voice.strip()
                for voice in os.getenv(
                    "KOKORO_WARMUP_ZH_VOICES",
                    "zm_yunxi,zm_yunjian,zm_yunxia,zm_yunyang",
                ).split(",")
                if voice.strip()
            ],
        ]
    )
)


def _load_pipeline(language: Literal["zh", "en"]):
    with runtime.lock:
        try:
            from kokoro import KPipeline

            if language == "en":
                if runtime.en_pipeline is None:
                    runtime.en_pipeline = KPipeline(lang_code="a")
                runtime.loaded_at = runtime.loaded_at or time.time()
                runtime.load_error = None
                return runtime.en_pipeline

            if runtime.zh_pipeline is None:
                runtime.zh_pipeline = KPipeline(lang_code="z")
            runtime.loaded_at = runtime.loaded_at or time.time()
            runtime.load_error = None
            return runtime.zh_pipeline
        except Exception as exc:  # pragma: no cover - runtime environment specific
            runtime.load_error = str(exc)
            raise


def _synthesize_wav(
    text: str,
    language: Literal["zh", "en"],
    voice: str,
    speed: float,
) -> bytes:
    # Kokoro pipelines are shared by FastAPI worker threads. Serialize inference
    # so simultaneous requests cannot mutate the same pipeline state.
    with runtime.inference_lock:
        pipeline = _load_pipeline(language)
        generator = pipeline(
            text,
            voice=voice,
            speed=speed,
            split_pattern=r"\n+",
        )

        chunks = []
        for _graphemes, _phonemes, audio in generator:
            chunks.append(audio)

        if not chunks:
            raise RuntimeError("Kokoro returned no audio chunks.")

        import numpy as np

        merged = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
        buffer = io.BytesIO()
        sf.write(buffer, merged, SAMPLE_RATE, format="WAV")
        return buffer.getvalue()


def _warmup_chinese_voices() -> None:
    if not WARMUP_ON_START:
        print("Kokoro startup warm-up is disabled.", flush=True)
        return

    language: Literal["zh", "en"] = "zh"
    speed = 1.0
    text = WARMUP_TEXT_ZH.strip()

    with runtime.lock:
        runtime.warmup_started_at = time.time()
        runtime.warmup_completed_at = None
        runtime.warmup_cache.clear()
        runtime.warmup_errors.clear()

    print(
        "Warming up Kokoro Mandarin voices: " + ", ".join(WARMUP_ZH_VOICES),
        flush=True,
    )
    total_started = time.perf_counter()

    for voice in WARMUP_ZH_VOICES:
        started = time.perf_counter()
        cache_key = (language, voice, speed, text)
        try:
            audio = _synthesize_wav(text=text, language=language, voice=voice, speed=speed)
            elapsed = time.perf_counter() - started
            with runtime.lock:
                runtime.warmup_cache[cache_key] = audio
            print(
                f"Kokoro voice '{voice}' warm-up completed in {elapsed:.2f}s; "
                f"welcome audio cached ({len(audio)} bytes).",
                flush=True,
            )
        except Exception as exc:  # pragma: no cover - runtime environment specific
            elapsed = time.perf_counter() - started
            with runtime.lock:
                runtime.warmup_errors[voice] = str(exc)
            # Continue warming the remaining voices. The main backend still has
            # OpenAI/browser fallbacks if one local voice is unavailable.
            print(f"Kokoro voice '{voice}' warm-up failed after {elapsed:.2f}s: {exc}", flush=True)

    with runtime.lock:
        runtime.warmup_completed_at = time.time()
        cached_count = len(runtime.warmup_cache)
        error_count = len(runtime.warmup_errors)

    total_elapsed = time.perf_counter() - total_started
    print(
        f"Kokoro Mandarin warm-up finished in {total_elapsed:.2f}s; "
        f"cached={cached_count}, errors={error_count}.",
        flush=True,
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Finish loading and caching all four selectable Mandarin voices before
    # Uvicorn reports the service as ready. Customer-facing voice changes then
    # avoid first-use model/voice latency.
    _warmup_chinese_voices()
    yield


app = FastAPI(
    title="Local Kokoro TTS Server",
    version="0.3.0",
    description="Standalone local TTS server for the wood-floor greeter demo.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    with runtime.lock:
        warmup_elapsed_seconds = None
        if runtime.warmup_started_at is not None and runtime.warmup_completed_at is not None:
            warmup_elapsed_seconds = round(
                runtime.warmup_completed_at - runtime.warmup_started_at,
                3,
            )

        cached_voices = sorted({cache_key[1] for cache_key in runtime.warmup_cache})
        warmup_error = (
            "; ".join(f"{voice}: {message}" for voice, message in runtime.warmup_errors.items())
            or None
        )
        return {
            "ok": True,
            "engine": "kokoro",
            "loaded_en": runtime.en_pipeline is not None,
            "loaded_zh": runtime.zh_pipeline is not None,
            "loaded_at": runtime.loaded_at,
            "load_error": runtime.load_error,
            "default_en_voice": DEFAULT_EN_VOICE,
            "default_zh_voice": DEFAULT_ZH_VOICE,
            "sample_rate": SAMPLE_RATE,
            "warmup_enabled": WARMUP_ON_START,
            "warmup_ready": all(voice in cached_voices for voice in WARMUP_ZH_VOICES),
            "warmup_voice": DEFAULT_ZH_VOICE,
            "warmup_voices": list(WARMUP_ZH_VOICES),
            "warmup_cached_voices": cached_voices,
            "warmup_started_at": runtime.warmup_started_at,
            "warmup_completed_at": runtime.warmup_completed_at,
            "warmup_elapsed_seconds": warmup_elapsed_seconds,
            "warmup_error": warmup_error,
            "warmup_errors": dict(runtime.warmup_errors),
        }


def _audio_response(audio: bytes, language: str, voice: str, cache_status: str) -> Response:
    return Response(
        content=audio,
        media_type="audio/wav",
        headers={
            "Cache-Control": "no-store",
            "X-TTS-Provider": "kokoro-local",
            "X-TTS-Voice": voice,
            "X-TTS-Language": language,
            "X-TTS-Cache": cache_status,
        },
    )


@app.post("/tts")
def tts(request: LocalTTSRequest) -> Response:
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is empty.")

    language = request.language
    voice = request.voice or (DEFAULT_ZH_VOICE if language == "zh" else DEFAULT_EN_VOICE)
    cache_key = (language, voice, request.speed, text)

    with runtime.lock:
        cached_audio = runtime.warmup_cache.get(cache_key)
    if cached_audio is not None:
        return _audio_response(
            audio=cached_audio,
            language=language,
            voice=voice,
            cache_status="warmup-hit",
        )

    try:
        audio = _synthesize_wav(
            text=text,
            language=language,
            voice=voice,
            speed=request.speed,
        )
        return _audio_response(
            audio=audio,
            language=language,
            voice=voice,
            cache_status="miss",
        )
    except Exception as exc:  # pragma: no cover - runtime environment specific
        raise HTTPException(status_code=502, detail=f"Kokoro TTS failed: {exc}") from exc
