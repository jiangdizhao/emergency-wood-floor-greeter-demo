from __future__ import annotations

import io
import os
import re
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

Language = Literal["zh", "en"]


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
    language: Language = "en"
    voice: str | None = None
    speed: float | None = Field(default=None, ge=0.65, le=1.25)


runtime = KokoroRuntime(lock=threading.RLock(), inference_lock=threading.Lock())

DEFAULT_EN_VOICE = os.getenv("KOKORO_EN_VOICE", "am_liam")
DEFAULT_ZH_VOICE = os.getenv("KOKORO_ZH_VOICE", "zm_yunxi")
SAMPLE_RATE = int(os.getenv("KOKORO_SAMPLE_RATE", "24000"))

# Kokoro divides predicted duration by speed. Values below 1.0 therefore speak
# more slowly. Chinese needs a lower default than the previous hard-coded 1.0
# for a relaxed retail-consultant delivery.
DEFAULT_ZH_SPEED = float(os.getenv("KOKORO_ZH_SPEED", "0.84"))
DEFAULT_EN_SPEED = float(os.getenv("KOKORO_EN_SPEED", "0.92"))
LEGACY_SPEED_ONE_USES_DEFAULT = os.getenv(
    "KOKORO_LEGACY_SPEED_ONE_USES_DEFAULT",
    "true",
).strip().lower() not in {"0", "false", "no", "off"}

# Mandarin still needs explicit length control because the upstream pipeline can
# truncate phoneme strings above 510 symbols. Use fewer, larger chunks so the
# model's own punctuation prosody is preserved without creating many artificial
# utterance boundaries.
ZH_MAX_CHARS = max(24, int(os.getenv("KOKORO_ZH_MAX_CHARS", "88")))
EN_MAX_CHARS = max(120, int(os.getenv("KOKORO_EN_MAX_CHARS", "260")))

# No synthetic silence is inserted by default. Kokoro already models punctuation
# prosody. These optional values remain available only for controlled experiments.
CLAUSE_PAUSE_MS = max(0, int(os.getenv("KOKORO_CLAUSE_PAUSE_MS", "0")))
SENTENCE_PAUSE_MS = max(0, int(os.getenv("KOKORO_SENTENCE_PAUSE_MS", "0")))

WARMUP_ON_START = os.getenv("KOKORO_WARMUP_ON_START", "true").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
WARMUP_TEXT_ZH = os.getenv(
    "KOKORO_WARMUP_TEXT_ZH",
    "您好，欢迎来到木地板体验区。我是您的 AI 选购顾问小木。",
)
WARMUP_TEXT_EN = os.getenv(
    "KOKORO_WARMUP_TEXT_EN",
    "Hello, welcome to the wood flooring experience area. I am your AI flooring consultant, Xiao Mu.",
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
WARMUP_EN_VOICES = tuple(
    dict.fromkeys(
        [
            DEFAULT_EN_VOICE,
            *[
                voice.strip()
                for voice in os.getenv(
                    "KOKORO_WARMUP_EN_VOICES",
                    "am_liam,am_michael,am_puck,am_onyx",
                ).split(",")
                if voice.strip()
            ],
        ]
    )
)


def _default_speed(language: Language) -> float:
    return DEFAULT_ZH_SPEED if language == "zh" else DEFAULT_EN_SPEED


def _resolve_speed(language: Language, requested_speed: float | None) -> float:
    if requested_speed is None:
        return _default_speed(language)
    # The current Backend sends 1.0 as a legacy constant. Treat that legacy
    # value as "use the language default" so this server-side fix is backwards
    # compatible without requiring the Backend and TTS server to update in lockstep.
    if LEGACY_SPEED_ONE_USES_DEFAULT and abs(requested_speed - 1.0) < 1e-9:
        return _default_speed(language)
    return requested_speed


def _find_safe_cut(text: str, limit: int, language: Language) -> int:
    if len(text) <= limit:
        return len(text)

    break_chars = "。！？!?；;，、：,: \t" if language == "zh" else ".!?;,: \t"
    minimum = max(1, int(limit * 0.55))
    for index in range(limit, minimum - 1, -1):
        if text[index - 1] in break_chars:
            return index
    return limit


def _split_text_for_kokoro(text: str, language: Language) -> list[str]:
    normalized = re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n").replace("\r", "\n")).strip()
    if not normalized:
        return []

    limit = ZH_MAX_CHARS if language == "zh" else EN_MAX_CHARS
    # Prefer complete sentences as units. Commas and colons are used only as a
    # fallback cut point when one sentence would otherwise exceed the safe limit.
    boundary_chars = "。！？!?；;\n" if language == "zh" else ".!?;\n"
    units: list[str] = []
    buffer: list[str] = []

    for character in normalized:
        buffer.append(character)
        if character in boundary_chars:
            unit = "".join(buffer).strip()
            if unit:
                units.append(unit)
            buffer = []
    if buffer:
        unit = "".join(buffer).strip()
        if unit:
            units.append(unit)

    chunks: list[str] = []
    current = ""
    joiner = "" if language == "zh" else " "

    def flush_current() -> None:
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for unit in units:
        remaining = unit
        while len(remaining) > limit:
            flush_current()
            cut = _find_safe_cut(remaining, limit, language)
            piece = remaining[:cut].strip()
            if piece:
                chunks.append(piece)
            remaining = remaining[cut:].strip()

        if not remaining:
            continue
        candidate = remaining if not current else current + joiner + remaining
        if len(candidate) <= limit:
            current = candidate
        else:
            flush_current()
            current = remaining

    flush_current()
    return chunks


def _pause_samples(graphemes: str) -> int:
    stripped = graphemes.rstrip()
    sentence_endings = ("。", "！", "？", ".", "!", "?")
    pause_ms = SENTENCE_PAUSE_MS if stripped.endswith(sentence_endings) else CLAUSE_PAUSE_MS
    return int(SAMPLE_RATE * pause_ms / 1000)


def _load_pipeline(language: Language):
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
    language: Language,
    voice: str,
    speed: float,
) -> bytes:
    # Kokoro pipelines are shared by FastAPI worker threads. Serialize inference
    # so simultaneous requests cannot mutate the same pipeline state.
    with runtime.inference_lock:
        pipeline = _load_pipeline(language)
        text_chunks = _split_text_for_kokoro(text, language)
        if not text_chunks:
            raise RuntimeError("Text produced no Kokoro chunks.")

        print(
            f"Kokoro synth language={language} voice={voice} speed={speed:.2f} "
            f"characters={len(text)} text_chunks={len(text_chunks)}",
            flush=True,
        )

        # A list bypasses the upstream regex splitter. This matters for Mandarin:
        # upstream currently splits non-English text on ASCII punctuation and may
        # truncate a >510-symbol phoneme sequence even when Chinese punctuation is present.
        generator = pipeline(
            text_chunks,
            voice=voice,
            speed=speed,
            split_pattern=None,
        )

        generated_chunks: list[tuple[str, object]] = []
        for graphemes, _phonemes, audio in generator:
            if audio is not None:
                generated_chunks.append((str(graphemes), audio))

        if not generated_chunks:
            raise RuntimeError("Kokoro returned no audio chunks.")

        import numpy as np

        merged_parts = []
        for index, (graphemes, audio) in enumerate(generated_chunks):
            if hasattr(audio, "detach"):
                array = audio.detach().cpu().numpy()
            else:
                array = np.asarray(audio)
            array = np.asarray(array, dtype=np.float32).reshape(-1)
            merged_parts.append(array)

            # Normally zero because artificial pauses are disabled. Keeping this
            # branch configurable makes A/B testing possible without another code change.
            if index < len(generated_chunks) - 1:
                pause_length = _pause_samples(graphemes)
                if pause_length > 0:
                    merged_parts.append(np.zeros(pause_length, dtype=np.float32))

        merged = np.concatenate(merged_parts)
        buffer = io.BytesIO()
        sf.write(buffer, merged, SAMPLE_RATE, format="WAV")
        return buffer.getvalue()


def _warmup_voice_group(*, language: Language, voices: tuple[str, ...], text: str) -> None:
    label = "English" if language == "en" else "Mandarin"
    speed = _default_speed(language)
    text = text.strip()
    print(
        f"Warming up Kokoro {label} voices at speed {speed:.2f}: " + ", ".join(voices),
        flush=True,
    )

    for voice in voices:
        started = time.perf_counter()
        cache_key = (language, voice, speed, text)
        error_key = f"{language}:{voice}"
        try:
            audio = _synthesize_wav(text=text, language=language, voice=voice, speed=speed)
            elapsed = time.perf_counter() - started
            with runtime.lock:
                runtime.warmup_cache[cache_key] = audio
                runtime.warmup_errors.pop(error_key, None)
            print(
                f"Kokoro {label} voice '{voice}' warm-up completed in {elapsed:.2f}s; "
                f"welcome audio cached ({len(audio)} bytes).",
                flush=True,
            )
        except Exception as exc:  # pragma: no cover - runtime environment specific
            elapsed = time.perf_counter() - started
            with runtime.lock:
                runtime.warmup_errors[error_key] = str(exc)
            print(
                f"Kokoro {label} voice '{voice}' warm-up failed after {elapsed:.2f}s: {exc}",
                flush=True,
            )


def _warmup_selectable_voices() -> None:
    if not WARMUP_ON_START:
        print("Kokoro startup warm-up is disabled.", flush=True)
        return

    with runtime.lock:
        runtime.warmup_started_at = time.time()
        runtime.warmup_completed_at = None
        runtime.warmup_cache.clear()
        runtime.warmup_errors.clear()

    total_started = time.perf_counter()
    _warmup_voice_group(language="zh", voices=WARMUP_ZH_VOICES, text=WARMUP_TEXT_ZH)
    _warmup_voice_group(language="en", voices=WARMUP_EN_VOICES, text=WARMUP_TEXT_EN)

    with runtime.lock:
        runtime.warmup_completed_at = time.time()
        cached_count = len(runtime.warmup_cache)
        error_count = len(runtime.warmup_errors)

    total_elapsed = time.perf_counter() - total_started
    print(
        f"Kokoro bilingual warm-up finished in {total_elapsed:.2f}s; "
        f"cached={cached_count}, errors={error_count}.",
        flush=True,
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Complete loading and caching before Uvicorn reports readiness. This avoids
    # first-use latency after the customer changes either language or voice.
    _warmup_selectable_voices()
    yield


app = FastAPI(
    title="Local Kokoro TTS Server",
    version="0.5.1",
    description="Standalone bilingual local TTS server for the wood-floor greeter demo.",
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

        cached_by_language = {
            language: sorted(
                {
                    cache_key[1]
                    for cache_key in runtime.warmup_cache
                    if cache_key[0] == language
                }
            )
            for language in ("zh", "en")
        }
        zh_ready = all(voice in cached_by_language["zh"] for voice in WARMUP_ZH_VOICES)
        en_ready = all(voice in cached_by_language["en"] for voice in WARMUP_EN_VOICES)
        warmup_error = (
            "; ".join(f"{voice}: {message}" for voice, message in runtime.warmup_errors.items())
            or None
        )
        return {
            "ok": True,
            "engine": "kokoro",
            "version": app.version,
            "loaded_en": runtime.en_pipeline is not None,
            "loaded_zh": runtime.zh_pipeline is not None,
            "loaded_at": runtime.loaded_at,
            "load_error": runtime.load_error,
            "default_en_voice": DEFAULT_EN_VOICE,
            "default_zh_voice": DEFAULT_ZH_VOICE,
            "default_en_speed": DEFAULT_EN_SPEED,
            "default_zh_speed": DEFAULT_ZH_SPEED,
            "legacy_speed_one_uses_default": LEGACY_SPEED_ONE_USES_DEFAULT,
            "zh_max_chars_per_chunk": ZH_MAX_CHARS,
            "en_max_chars_per_chunk": EN_MAX_CHARS,
            "clause_pause_ms": CLAUSE_PAUSE_MS,
            "sentence_pause_ms": SENTENCE_PAUSE_MS,
            "sample_rate": SAMPLE_RATE,
            "warmup_enabled": WARMUP_ON_START,
            "warmup_ready": zh_ready and en_ready,
            "warmup_zh_ready": zh_ready,
            "warmup_en_ready": en_ready,
            "warmup_zh_voices": list(WARMUP_ZH_VOICES),
            "warmup_en_voices": list(WARMUP_EN_VOICES),
            "warmup_zh_cached_voices": cached_by_language["zh"],
            "warmup_en_cached_voices": cached_by_language["en"],
            # Backward-compatible fields retained for existing checks.
            "warmup_voice": DEFAULT_ZH_VOICE,
            "warmup_voices": list(WARMUP_ZH_VOICES),
            "warmup_cached_voices": cached_by_language["zh"],
            "warmup_started_at": runtime.warmup_started_at,
            "warmup_completed_at": runtime.warmup_completed_at,
            "warmup_elapsed_seconds": warmup_elapsed_seconds,
            "warmup_error": warmup_error,
            "warmup_errors": dict(runtime.warmup_errors),
        }


def _audio_response(
    audio: bytes,
    language: str,
    voice: str,
    speed: float,
    text_chunk_count: int,
    cache_status: str,
) -> Response:
    return Response(
        content=audio,
        media_type="audio/wav",
        headers={
            "Cache-Control": "no-store",
            "X-TTS-Provider": "kokoro-local",
            "X-TTS-Voice": voice,
            "X-TTS-Language": language,
            "X-TTS-Speed": f"{speed:.2f}",
            "X-TTS-Text-Chunks": str(text_chunk_count),
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
    speed = _resolve_speed(language, request.speed)
    text_chunk_count = len(_split_text_for_kokoro(text, language))
    cache_key = (language, voice, speed, text)

    with runtime.lock:
        cached_audio = runtime.warmup_cache.get(cache_key)
    if cached_audio is not None:
        return _audio_response(
            audio=cached_audio,
            language=language,
            voice=voice,
            speed=speed,
            text_chunk_count=text_chunk_count,
            cache_status="warmup-hit",
        )

    try:
        audio = _synthesize_wav(
            text=text,
            language=language,
            voice=voice,
            speed=speed,
        )
        return _audio_response(
            audio=audio,
            language=language,
            voice=voice,
            speed=speed,
            text_chunk_count=text_chunk_count,
            cache_status="miss",
        )
    except Exception as exc:  # pragma: no cover - runtime environment specific
        raise HTTPException(status_code=502, detail=f"Kokoro TTS failed: {exc}") from exc
