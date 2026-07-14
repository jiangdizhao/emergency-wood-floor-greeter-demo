from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import wave
from pathlib import Path

INTRODUCTION = (
    "您好，欢迎来到森境地板生活馆。"
    "我是小木，也是这里的高级地板选购顾问。"
    "我不会让您一开始就回答一长串问题，而是先根据您最看重的一点，"
    "拿两款有代表性的产品把差别讲清楚。"
    "比如 SPC 锁扣地板适合关注耐磨、防水和日常维护的家庭，"
    "其中部分产品的耐磨等级可以达到 AC5。"
    "门店主要有耐磨易维护、地暖适配、高品质实木质感和经济实用四条选购路线。"
    "您先告诉我最在意的是耐磨、防水、脚感、好清洁、预算还是环保，我就直接从产品讲起。"
)


def request_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def synthesize(base_url: str, voice: str, output_path: Path) -> tuple[dict[str, str], float]:
    payload = {
        "text": INTRODUCTION,
        "language": "zh",
        "voice": voice,
        "speed": 1.0,
    }
    request = urllib.request.Request(
        f"{base_url}/tts",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        audio = response.read()
        headers = {key.lower(): value for key, value in response.headers.items()}

    output_path.write_bytes(audio)
    with wave.open(str(output_path), "rb") as wav_file:
        duration = wav_file.getnframes() / float(wav_file.getframerate())
    return headers, duration


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify natural Mandarin Kokoro synthesis.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--voice", default="zm_yunxi")
    parser.add_argument("--output", default="kokoro_long_mandarin_intro.wav")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    output_path = Path(args.output).resolve()

    try:
        health = request_json(f"{base_url}/health")
        headers, duration = synthesize(base_url, args.voice, output_path)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}: {body}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Verification failed: {exc}", file=sys.stderr)
        return 1

    speed = float(headers.get("x-tts-speed", "0"))
    chunk_count = int(headers.get("x-tts-text-chunks", "0"))
    prosody_mode = headers.get("x-tts-zh-prosody-mode", "")
    latin_transliteration = headers.get("x-tts-zh-latin-transliteration", "false") == "true"
    silence_trimmed = headers.get("x-tts-silence-trimmed", "false") == "true"
    clause_pause_ms = int(health.get("clause_pause_ms") or 0)
    sentence_pause_ms = int(health.get("sentence_pause_ms") or 0)

    result = {
        "server_version": health.get("version"),
        "configured_zh_speed": health.get("default_zh_speed"),
        "configured_voice_speed": (health.get("zh_voice_speeds") or {}).get(args.voice),
        "effective_response_speed": speed,
        "zh_max_chars_per_chunk": health.get("zh_max_chars_per_chunk"),
        "response_text_chunks": chunk_count,
        "clause_pause_ms": clause_pause_ms,
        "sentence_pause_ms": sentence_pause_ms,
        "zh_prosody_mode": prosody_mode,
        "zh_latin_transliteration": latin_transliteration,
        "trim_chunk_silence": silence_trimmed,
        "silence_threshold_db": health.get("silence_threshold_db"),
        "silence_pad_ms": health.get("silence_pad_ms"),
        "chunk_crossfade_ms": health.get("chunk_crossfade_ms"),
        "introduction_characters": len(INTRODUCTION),
        "wav_duration_seconds": round(duration, 2),
        "output": str(output_path),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if chunk_count < 2:
        print("FAIL: the long Mandarin introduction was not divided into safe chunks.", file=sys.stderr)
        return 2
    if speed >= 0.95:
        print("FAIL: the effective Mandarin speed is still too close to 1.0.", file=sys.stderr)
        return 3
    if clause_pause_ms != 0 or sentence_pause_ms != 0:
        print("FAIL: synthetic punctuation pauses are still enabled.", file=sys.stderr)
        return 4
    if prosody_mode != "soft":
        print("FAIL: soft Mandarin prosody is not active.", file=sys.stderr)
        return 5
    if not latin_transliteration:
        print("FAIL: Mandarin Latin-acronym pronunciation is not active.", file=sys.stderr)
        return 6
    if not silence_trimmed:
        print("FAIL: generated chunk-edge silence trimming is not active.", file=sys.stderr)
        return 7
    if int(health.get("silence_pad_ms") or 0) < 15:
        print("FAIL: chunk trimming is too aggressive to preserve natural word endings.", file=sys.stderr)
        return 8
    if duration <= 0:
        print("FAIL: the WAV file contains no playable duration.", file=sys.stderr)
        return 9

    print(
        "PASS: Mandarin uses soft prosody, acronym pronunciation, per-voice pacing, "
        "natural edge padding and no synthetic pauses."
    )
    print("Listen specifically for SPC and AC5 in the generated WAV file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
