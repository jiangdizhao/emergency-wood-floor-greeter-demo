from __future__ import annotations

import re

# Kokoro's Mandarin G2P does not reliably emit phonemes for embedded Latin
# letters. Convert short technical acronyms to Mandarin letter names before the
# text reaches KPipeline(lang_code="z"). The visible UI text is not changed.
LETTER_NAMES_ZH: dict[str, str] = {
    "A": "诶",
    "B": "比",
    "C": "西",
    "D": "迪",
    "E": "伊",
    "F": "艾弗",
    "G": "吉",
    "H": "艾尺",
    "I": "艾",
    "J": "杰",
    "K": "开",
    "L": "艾勒",
    "M": "艾姆",
    "N": "恩",
    "O": "欧",
    "P": "批",
    "Q": "丘",
    "R": "阿尔",
    "S": "艾丝",
    "T": "提",
    "U": "优",
    "V": "维",
    "W": "达不溜",
    "X": "艾克斯",
    "Y": "歪",
    "Z": "兹",
}

DIGIT_NAMES_ZH: dict[str, str] = {
    "0": "零",
    "1": "一",
    "2": "二",
    "3": "三",
    "4": "四",
    "5": "五",
    "6": "六",
    "7": "七",
    "8": "八",
    "9": "九",
}

# Known flooring, indoor-air-quality and AI acronyms are accepted even when an
# LLM returns them in lowercase. Unlisted ordinary English words are preserved
# instead of being incorrectly spelled letter by letter.
KNOWN_ACRONYMS = (
    "SPC",
    "PVC",
    "LVT",
    "WPC",
    "HDF",
    "MDF",
    "OSB",
    "VOC",
    "TVOC",
    "ENF",
    "CARB",
    "FSC",
    "AC",
    "UV",
    "AI",
    "TTS",
    "LLM",
)

_KNOWN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?P<letters>"
    + "|".join(sorted((re.escape(item) for item in KNOWN_ACRONYMS), key=len, reverse=True))
    + r")(?P<digits>[0-9]{0,3})(?![A-Za-z0-9])",
    flags=re.IGNORECASE,
)
_UPPERCASE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?P<letters>[A-Z]{2,8})(?P<digits>[0-9]{0,3})(?![A-Za-z0-9])"
)
_GRADE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?P<letters>[A-Z])(?P<digits>[0-9]{1,3})(?![A-Za-z0-9])"
)
_SPACED_ACRONYM_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?P<token>(?:[A-Za-z]\s+){1,7}[A-Za-z](?:\s*[0-9]{1,3})?)(?![A-Za-z0-9])"
)


def _speak_token(letters: str, digits: str = "") -> str:
    spoken_letters = [LETTER_NAMES_ZH.get(character.upper(), character) for character in letters]
    spoken_digits = [DIGIT_NAMES_ZH.get(character, character) for character in digits]
    # Spaces help Mandarin G2P keep individual letter names intelligible without
    # adding the long punctuation pauses that were removed in the previous fix.
    return " ".join([*spoken_letters, *spoken_digits])


def _replace_match(match: re.Match[str]) -> str:
    return _speak_token(match.group("letters"), match.group("digits") or "")


def _replace_spaced_match(match: re.Match[str]) -> str:
    compact = re.sub(r"\s+", "", match.group("token"))
    letters_match = re.match(r"(?P<letters>[A-Za-z]+)(?P<digits>[0-9]*)$", compact)
    if not letters_match:
        return match.group(0)
    return _speak_token(letters_match.group("letters"), letters_match.group("digits") or "")


def transliterate_latin_for_mandarin(text: str) -> tuple[str, bool]:
    """Return Mandarin-readable speech text and whether a replacement occurred.

    Examples:
      SPC -> 艾丝 批 西
      AC5 -> 诶 西 五
      ENF -> 伊 恩 艾弗
      E0 -> 伊 零
      8 mm -> 8 毫米

    Ordinary English words such as ``Kokoro`` or ``flooring`` are left alone.
    They can later be handled by a mixed-language synthesis path if the product
    needs arbitrary English phrases rather than short technical acronyms.
    """

    output = text
    output = re.sub(r"(?i)(?<![A-Za-z])mm(?![A-Za-z])", "毫米", output)
    output = re.sub(r"(?i)(?<![A-Za-z])cm(?![A-Za-z])", "厘米", output)
    output = re.sub(r"(?i)(?<![A-Za-z])m(?:2|²)(?![A-Za-z0-9])", "平方米", output)
    output = _SPACED_ACRONYM_PATTERN.sub(_replace_spaced_match, output)
    output = _KNOWN_PATTERN.sub(_replace_match, output)
    output = _GRADE_PATTERN.sub(_replace_match, output)
    output = _UPPERCASE_PATTERN.sub(_replace_match, output)
    output = re.sub(r"[ \t]+", " ", output).strip()
    return output, output != text.strip()
