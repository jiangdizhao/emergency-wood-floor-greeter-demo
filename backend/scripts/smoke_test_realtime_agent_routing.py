from __future__ import annotations

from pathlib import Path

from app.services.turn_router import TurnRouter


def expect(text: str, expected_route: str, language: str = "zh") -> None:
    decision = TurnRouter().route(text, language=language)
    assert decision.route == expected_route, (
        f"{text!r}: expected {expected_route}, got {decision.route}; "
        f"intent={decision.intent}, reason={decision.reason}"
    )


def main() -> None:
    expect("能否再介绍一下自己", "deterministic_direct")
    expect("你能做什么", "deterministic_direct")
    expect("谢谢", "deterministic_direct")
    expect("再说一遍", "repeat_last")
    expect("停一下", "stop_speaking")
    expect("见到你很高兴", "realtime_direct")
    expect("一百平方米有什么活动", "terra")
    expect("为什么深胡桃色 SPC 更适合我", "terra")
    expect("我改成浅灰色", "terra")
    expect("一个无法安全分类的新问题", "terra")
    expect("introduce yourself", "deterministic_direct", language="en")
    expect("can you hear me", "realtime_direct", language="en")
    expect("compare these floor products", "terra", language="en")

    backend_root = Path(__file__).resolve().parents[1]
    policy_source = (backend_root / "app" / "services" / "dialogue_policy.py").read_text(encoding="utf-8")
    assert 'turn.intent in {"provide_or_modify_needs", "other"}' not in policy_source
    assert 'turn.intent == "provide_or_modify_needs"' in policy_source
    assert 'if turn.intent == "other"' in policy_source

    sales_api_source = (backend_root / "app" / "sales_api.py").read_text(encoding="utf-8")
    assert "router.include_router(interaction_router)" in sales_api_source

    print("Realtime agent routing smoke test passed.")
    print("Direct persona/social turns bypass Terra; business and unknown turns remain guarded.")


if __name__ == "__main__":
    main()
