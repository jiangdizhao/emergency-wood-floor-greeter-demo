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
DEFAULT_ZH_SPEED = float(os.getenv("KOKORO_ZH_SPEED", "0.84"))
DEFAULT_EN_SPEED = float(os.getenv("KOKORO_EN_SPEED", "0.92"))
LEGACY_SPEED_ONE_USES_DEFAULT = os.getenv(
    "KOKORO_LEGACY_SPEED_ONE_USES_DEFAULT",
    "true",
).strip().lower() not in {"0", "false", "no", "off"}

# Keep chunks below Kokoro's long-phoneme truncation boundary, but avoid the
# previous 48-character fragmentation that sounded like separate recordings.
ZH_MAX_CHARS = max(24, int(os.getenv("KOKORO_ZH_MAX_CHARS", "88")))
EN_MAX_CHARS = max(120, int(os.getenv("KOKORO_EN_MAX_CHARS", "260")))

# Synthetic pauses remain disabled. Mandarin punctuation can still make Kokoro
# produce exaggerated pauses, so the audio-only synthesis text may neutralize
# punctuation while the visible UI text remains unchanged.
CLAUSE_PAUSE_MS = max(0, int(os.getenv("KOKORO_CLAUSE_PAUSE_MS", "0")))
SENTENCE_PAUSE_MS = max(0, int(os.getenv("KOKORO_SENTENCE_PAUSE_MS", "0")))
ZH_NEUTRALIZE_PUNCTUATION = os.getenv(
    "KOKORO_ZH_NEUTRALIZE_PUNCTUATION",
    "true",
).strip().lower() not in {"0", "false", "no", "off"}
TRIM_CHUNK_SILENCE = os.getenv(
    "KOKORO_TRIM_CHUNK_SILENCE",
    "true",
).strip().lower() not in {"0", "false", "no", "off"}
SILENCE_THRESHOLD_DB = float(os.getenv("KOKORO_SILENCE_THRESHOLD_DB", "-42"))
SILENCE_PAD_MS = max(0, int(os.getenv("KOKORO_SILENCE_PAD_MS", "8")))
CHUNK_CROSSFADE_MS = max(0, int(os.getenv("KOKORO_CHUNK_CROSSFADE_MS", "8")))

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


def _synthesis_text(chunk: str, language: Language) -> str:
    if language != "zh" or not ZH_NEUTRALIZE_PUNCTUATION:
        return chunk

    # Preserve all words and numbers while removing punctuation tokens that can
    # create long model-level pauses. Visible text is not modified.
    neutralized = re.sub(r"[，。！？；：、,.!?;:]+", " ", chunk)
    neutralized = re.sub(r"\s+", " ", neutralized).strip()
    return neutralized or chunk


def _pause_samples(graphemes: str) -> int:
    stripped = graphemes.rstrip()
    sentence_endings = ("。", "！", "？", ".", "!", "?")
    pause_ms = SENTENCE_PAUSE_MS if stripped.endswith(sentence_endings) else CLAUSE_PAUSE_MS
    return int(SAMPLE_RATE * pause_ms / 1000)


def _trim_silence(array):
    import numpy as np

    samples = np.asarray(array, dtype=np.float32).reshape(-1)
    if not TRIM_CHUNK_SILENCE or samples.size == 0:
        return samples

    peak = float(np.max(np.abs(samples)))
    if peak <= 1e-7:
        return samples

    relative_threshold = peak * (10.0 ** (SILENCE_THRESHOLD_DB / 20.0))
    threshold = max(1e-5, relative_threshold)
    active = np.flatnonzero(np.abs(samples) >= threshold)
    if active.size == 0:
        return samples

    pad = int(SAMPLE_RATE * SILENCE_PAD_MS / 1000)
    start = max(0, int(active[0]) - pad)
    end = min(samples.size, int(active[-1]) + pad + 1)
    trimmed = samples[start:end]

    # Never return an implausibly short fragment because of an aggressive
    # threshold. A spoken chunk should normally exceed 80 milliseconds.
    if trimmed.size < int(SAMPLE_RATE * 0.08):
        return samples
    return trimmed


def _merge_chunks(chunks):
    import numpy as np

    if not chunks:
        raise RuntimeError("Kokoro returned no audio chunks.")
    merged = np.asarray(chunks[0], dtype=np.float32).reshape(-1)
    crossfade = int(SAMPLE_RATE * CHUNK_CROSSFADE_MS / 1000)

    for next_chunk in chunks[1:]:
        next_array = np.asarray(next_chunk, dtype=np.float32).reshape(-1)
        overlap = min(crossfade, merged.size, next_array.size)
        if overlap <= 0:
            merged = np.concatenate([merged, next_array])
            continue

        fade_out = np.linspace(1.0, 0.0, overlap, endpoint=False, dtype=np.float32)
        fade_in = np.linspace(0.0, 1.0, overlap, endpoint=False, dtype=np.float32)
        bridge = merged[-overlap:] * fade_out + next_array[:overlap] * fade_in
        merged = np.concatenate([merged[:-overlap], bridge, next_array[overlap:]])

    return merged


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
    with runtime.inference_lock:
        pipeline = _load_pipeline(language)
        source_chunks = _split_text_for_kokoro(text, language)
        if not source_chunks:
            raise RuntimeError("Text produced no Kokoro chunks.")
        synthesis_chunks = [_synthesis_text(chunk, language) for chunk in source_chunks]

        print(
            f"Kokoro synth language={language} voice={voice} speed={speed:.2f} "
            f"characters={len(text)} text_chunks={len(source_chunks)} "
            f"punctuation_neutralized={language == 'zh' and ZH_NEUTRALIZE_PUNCTUATION}",
            flush=True,
        )

        generator = pipeline(
            synthesis_chunks,
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

        processed = []
        for index, (graphemes, audio) in enumerate(generated_chunks):
            if hasattr(audio, "detach"):
                array = audio.detach().cpu().numpy()
            else:
                array = np.asarray(audio)
            array = _trim_silence(array)
            processed.append(array)

            pause_length = _pause_samples(graphemes)
            if index < len(generated_chunks) - 1 and pause_length > 0:
                processed.append(np.zeros(pause_length, dtype=np.float32))

        merged = _merge_chunks(processed)
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
    _warmup_selectable_voices()
    yield


app = FastAPI(
    title="Local Kokoro TTS Server",
    version="0.6.0",
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
            warmup_elapsed_seconds = round(runtime.warmup_completed_at - runtime.warmup_started_at, 3)

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
            "zh_punctuation_neutralized": ZH_NEUTRALIZE_PUNCTUATION,
            "trim_chunk_silence": TRIM_CHUNK_SILENCE,
            "silence_threshold_db": SILENCE_THRESHOLD_DB,
            "silence_pad_ms": SILENCE_PAD_MS,
            "chunk_crossfade_ms": CHUNK_CROSSFADE_MS,
            "sample_rate": SAMPLE_RATE,
            "warmup_enabled": WARMUP_ON_START,
            "warmup_ready": zh_ready and en_ready,
            "warmup_zh_ready": zh_ready,
            "warmup_en_ready": en_ready,
            "warmup_zh_voices": list(WARMUP_ZH_VOICES),
            "warmup_en_voices": list(WARMUP_EN_VOICES),
            "warmup_zh_cached_voices": cached_by_language["zh"],
            "warmup_en_cached_voices": cached_by_language["en"],
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
            "X-TTS-Punctuation-Neutralized": str(language == "zh" and ZH_NEUTRALIZE_PUNCTUATION).lower(),
            "X-TTS-Silence-Trimmed": str(TRIM_CHUNK_SILENCE).lower(),
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
