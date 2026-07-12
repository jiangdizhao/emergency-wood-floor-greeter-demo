from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_VOICES = ("am_liam", "am_michael", "am_puck", "am_onyx")
REPOSITORY_ID = "hexgrad/Kokoro-82M"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download the four Kokoro English voice tensors used by the bilingual demo."
    )
    parser.add_argument(
        "--voices",
        nargs="+",
        default=list(DEFAULT_VOICES),
        help="Kokoro voice IDs to download.",
    )
    parser.add_argument(
        "--cache-dir",
        default=None,
        help="Optional Hugging Face cache directory. Omit to use the normal user cache.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise SystemExit(
            "huggingface_hub is unavailable in this Python environment. "
            "Activate the kokoro-tts environment and install local_tts/requirements.txt first."
        ) from exc

    print(f"Python executable: {sys.executable}")
    print(f"Kokoro repository: {REPOSITORY_ID}")
    print("Voices: " + ", ".join(args.voices))
    print()

    downloaded: list[tuple[str, Path]] = []
    for voice in args.voices:
        filename = f"voices/{voice}.pt"
        print(f"Downloading {filename} ...", flush=True)
        path = Path(
            hf_hub_download(
                repo_id=REPOSITORY_ID,
                filename=filename,
                cache_dir=args.cache_dir,
            )
        )
        if not path.exists() or path.stat().st_size < 100_000:
            raise RuntimeError(f"Downloaded voice file is missing or unexpectedly small: {path}")
        downloaded.append((voice, path))
        print(f"  OK: {path} ({path.stat().st_size:,} bytes)")

    print()
    print("All requested Kokoro English voices are present in the Hugging Face cache.")
    for voice, path in downloaded:
        print(f"{voice}: {path}")


if __name__ == "__main__":
    main()
