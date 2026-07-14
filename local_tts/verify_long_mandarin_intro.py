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
    "我们是一家面向家庭装修场景的木地板整体选购顾问门店，"
    "我会根据空间、家庭成员、地暖、清洁习惯、预算与审美偏好，"
    "帮助客户排除不适合的材料，比较不同方案的价值与取舍，并形成主推款和备选款。"
    "门店目前重点提供耐磨易维护家庭方案、地暖适配方案、高品质实木质感方案、经济实用方案。"
    "这次选地板，您最不愿意妥协的是哪一点：预算、耐磨、防水、脚感、环保，还是日常好清洁？"
)


def request_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def synthesize(base_url: str, voice: str, output_path: Path) -> tuple[dict[str, str], float]:
    payload = {
        "text": INTRODUCTION,
        "language": "zh",
        "voice": voice,
        # The Backend currently sends 1.0. The updated server intentionally
        # maps this legacy value to the configured Mandarin default.
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
    parser = argparse.ArgumentParser(description="Verify long Mandarin Kokoro synthesis.")
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
    clause_pause_ms = int(health.get("clause_pause_ms") or 0)
    sentence_pause_ms = int(health.get("sentence_pause_ms") or 0)

    print(json.dumps(
        {
            "server_version": health.get("version"),
            "configured_zh_speed": health.get("default_zh_speed"),
            "effective_response_speed": speed,
            "zh_max_chars_per_chunk": health.get("zh_max_chars_per_chunk"),
            "response_text_chunks": chunk_count,
            "clause_pause_ms": clause_pause_ms,
            "sentence_pause_ms": sentence_pause_ms,
            "introduction_characters": len(INTRODUCTION),
            "wav_duration_seconds": round(duration, 2),
            "output": str(output_path),
        },
        ensure_ascii=False,
        indent=2,
    ))

    if chunk_count < 2:
        print(
            "FAIL: the long Mandarin introduction was not divided into safe chunks.",
            file=sys.stderr,
        )
        return 2
    if speed >= 0.95:
        print(
            "FAIL: the effective Mandarin speed is still too close to the old 1.0 setting.",
            file=sys.stderr,
        )
        return 3
    if clause_pause_ms != 0 or sentence_pause_ms != 0:
        print(
            "FAIL: artificial punctuation pauses are still enabled.",
            file=sys.stderr,
        )
        return 4
    if duration <= 0:
        print("FAIL: the WAV file contains no playable duration.", file=sys.stderr)
        return 5

    print("PASS: long Mandarin text uses safe chunks, slower speech, and no artificial punctuation pauses.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
