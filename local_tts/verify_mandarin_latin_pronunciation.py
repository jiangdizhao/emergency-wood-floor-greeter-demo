from __future__ import annotations

from mandarin_latin_pronunciation import transliterate_latin_for_mandarin


def main() -> None:
    cases = {
        "这款 SPC 锁扣地板达到 AC5 耐磨等级。": "这款 艾丝 批 西 锁扣地板达到 诶 西 五 耐磨等级。",
        "ENF 环保等级和 E0 等级需要看检测文件。": "伊 恩 艾弗 环保等级和 伊 零 等级需要看检测文件。",
        "AI 顾问会介绍 PVC、LVT 和 WPC 的区别。": "诶 艾 顾问会介绍 批 维 西、艾勒 维 提 和 达不溜 批 西 的区别。",
        "地板厚度是 8 mm，房间面积是 60 m2。": "地板厚度是 8 毫米，房间面积是 60 平方米。",
        "Kokoro flooring demo": "Kokoro flooring demo",
    }

    for source, expected in cases.items():
        actual, changed = transliterate_latin_for_mandarin(source)
        assert actual == expected, f"{source!r}: expected {expected!r}, got {actual!r}"
        assert changed is (source != expected)
        print(f"{source} -> {actual}")

    print("Mandarin Latin-acronym pronunciation check passed.")


if __name__ == "__main__":
    main()
