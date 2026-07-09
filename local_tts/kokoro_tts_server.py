from __future__ import annotations

import io
import os
import threading
import time
from dataclasses import dataclass
from typing import Literal

import soundfile as sf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.responses import Response


@dataclass
class KokoroRuntime:
    lock: threading.RLock
    en_pipeline: object | None = None
    zh_pipeline: object | None = None
    loaded_at: float | None = None
    load_error: str | None = None


class LocalTTSRequest(BaseModel):
    text: str = Field(min_length=1)
    language: Literal["zh", "en"] = "en"
    voice: str | None = None
    speed: float = 1.0


app = FastAPI(
    title="Local Kokoro TTS Server",
    version="0.1.0",
    description="Standalone local TTS server for the wood-floor greeter demo.",
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

runtime = KokoroRuntime(lock=threading.RLock())

DEFAULT_EN_VOICE = os.getenv("KOKORO_EN_VOICE", "af_heart")
DEFAULT_ZH_VOICE = os.getenv("KOKORO_ZH_VOICE", "zf_xiaobei")
SAMPLE_RATE = int(os.getenv("KOKORO_SAMPLE_RATE", "24000"))


def _load_pipeline(language: Literal["zh", "en"]):
    with runtime.lock:
        try:
            from kokoro import KPipeline

            if language == "en":
                if runtime.en_pipeline is None:
                    runtime.en_pipeline = KPipeline(lang_code="a")
                runtime.loaded_at = runtime.loaded_at or time.time()
                return runtime.en_pipeline

            if runtime.zh_pipeline is None:
                runtime.zh_pipeline = KPipeline(lang_code="z")
            runtime.loaded_at = runtime.loaded_at or time.time()
            return runtime.zh_pipeline
        except Exception as exc:  # pragma: no cover - runtime environment specific
            runtime.load_error = str(exc)
            raise


@app.get("/health")
def health() -> dict:
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
    }


@app.post("/tts")
def tts(request: LocalTTSRequest) -> Response:
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is empty.")

    language = request.language
    voice = request.voice or (DEFAULT_ZH_VOICE if language == "zh" else DEFAULT_EN_VOICE)

    try:
        pipeline = _load_pipeline(language)
        generator = pipeline(
            text,
            voice=voice,
            speed=request.speed,
            split_pattern=r"\n+",
        )

        chunks = []
        for _graphemes, _phonemes, audio in generator:
            chunks.append(audio)

        if not chunks:
            raise HTTPException(status_code=502, detail="Kokoro returned no audio chunks.")

        import numpy as np

        merged = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
        buffer = io.BytesIO()
        sf.write(buffer, merged, SAMPLE_RATE, format="WAV")
        buffer.seek(0)
        return Response(
            content=buffer.read(),
            media_type="audio/wav",
            headers={
                "Cache-Control": "no-store",
                "X-TTS-Provider": "kokoro-local",
                "X-TTS-Voice": voice,
                "X-TTS-Language": language,
            },
        )
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - runtime environment specific
        raise HTTPException(status_code=502, detail=f"Kokoro TTS failed: {exc}") from exc
