"""Intent gate: GENERAL answers directly, GENERATE takes the full pipeline.

Fail-safe default is GENERATE throughout: ambiguous input, classifier errors,
and verdict-bearing direct output must all land on the gated path.
"""
from pathlib import Path

import pytest

from mind3.core.driver import PhaseDriver
from mind3.core.intent import (
    ASK_BOUNDARY,
    CLASSIFY_OPTIONS,
    classify,
    keyword_hint,
    parse_intent,
)
from mind3.core.verifier import SiliconSignoffVerifier


def test_keyword_routes_generation_requests() -> None:
    assert keyword_hint("Write a FIFO in Verilog") == "GENERATE"
    assert keyword_hint("fix my verilog module, it latches") == "GENERATE"
    assert keyword_hint("verify this uart with sby") == "GENERATE"
    assert keyword_hint("generate an AXI arbiter, synthesizable") == "GENERATE"


def test_keyword_word_boundaries_and_general_questions() -> None:
    # "modular" must not match "module"; questions without action verbs stay out.
    assert keyword_hint("modular design principles?") is None
    assert keyword_hint("What does WIDTHEXPAND mean?") is None
    assert keyword_hint("Explain AXI handshake, quick example") is None
    assert keyword_hint("hello") is None
    assert keyword_hint("") is None


def test_parse_intent_requires_clean_single_word() -> None:
    assert parse_intent("GENERAL") == "GENERAL"
    assert parse_intent("  general\n") == "GENERAL"
    assert parse_intent("GENERATE") == "GENERATE"
    assert parse_intent("The classification is: GENERAL") == "GENERATE"
    assert parse_intent("") == "GENERATE"
    assert parse_intent("GENERAL.") == "GENERAL"


def test_classify_uses_keyword_first_without_calling_model() -> None:
    calls: list[str] = []

    def _query(messages: list[dict[str, str]], options: dict[str, object]) -> str:
        calls.append("called")
        return "GENERAL"

    assert classify("Write a FIFO in Verilog", _query) == "GENERATE"
    assert calls == []


def test_classify_falls_back_to_generate_on_model_error() -> None:
    def _boom(messages: list[dict[str, str]], options: dict[str, object]) -> str:
        raise RuntimeError("ollama down")

    assert classify("What is a FIFO?", _boom) == "GENERATE"


def test_classify_accepts_clean_general_only() -> None:
    assert classify("What is a FIFO?", lambda m, o: "GENERAL") == "GENERAL"
    assert classify("What is a FIFO?", lambda m, o: "GENERAL.") == "GENERAL"
    assert classify("What is a FIFO?", lambda m, o: "Probably GENERAL") == "GENERATE"


def test_classify_decode_is_tight() -> None:
    assert CLASSIFY_OPTIONS["num_predict"] <= 8
    assert CLASSIFY_OPTIONS["stop"] == ["\n", " "]


def test_route_intent_is_single_orchestration() -> None:
    from mind3.core import intent as intent_mod

    def _boom(messages: list[dict[str, str]], options: dict[str, object]) -> str:
        raise AssertionError("model must not be called on keyword hit")

    # Keyword hit never calls the model; model word decides otherwise.
    assert intent_mod.route_intent("Write a FIFO in Verilog", _boom) == "GENERATE"
    assert intent_mod.route_intent("What is a FIFO?", lambda m, o: "GENERAL") == "GENERAL"
    # classify() delegates to the same orchestration.
    assert intent_mod.classify("Write a FIFO in Verilog", _boom) == "GENERATE"


def _make_driver(tmp_path: Path) -> PhaseDriver:
    ws = tmp_path / "ws"
    ws.mkdir()
    return PhaseDriver(
        session_id="intent-test",
        workspace=ws,
        verifier=SiliconSignoffVerifier(top_module="t"),
    )


def test_ask_returns_text_and_writes_no_rtl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    driver = _make_driver(tmp_path)
    monkeypatch.setattr(driver, "_query_model", lambda messages: "A FIFO buffers data.")
    try:
        reply = driver.ask("What is a FIFO?")
    finally:
        driver.close()
    assert reply == "A FIFO buffers data."
    sv_files = [p for p in (tmp_path / "ws").rglob("*.sv")]
    assert sv_files == []


def test_ask_carries_capped_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    driver = _make_driver(tmp_path)
    seen: dict[str, object] = {}

    def _capture(messages: list[dict[str, str]]) -> str:
        seen["messages"] = messages
        return "An answer."

    monkeypatch.setattr(driver, "_query_model", _capture)
    try:
        history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"turn {i} " + "x" * 2000} for i in range(8)]
        driver.ask("Follow-up?", history=history)  # type: ignore[arg-type]
    finally:
        driver.close()
    messages = seen["messages"]
    assert messages[0]["role"] == "system"
    assert messages[-1] == {"role": "user", "content": "Follow-up?"}
    prior = messages[1:-1]
    assert len(prior) == 4  # last 4 only
    assert all(len(t["content"]) <= 1000 for t in prior)
    assert prior[0]["content"].startswith("turn 4")


def test_ask_rejects_verdict_tokens(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    driver = _make_driver(tmp_path)
    monkeypatch.setattr(driver, "_query_model", lambda messages: "done SILICON_VERIFIED")
    try:
        with pytest.raises(ValueError):
            driver.ask("Status?")
    finally:
        driver.close()


def test_ask_boundary_forbids_full_modules() -> None:
    assert "production synthesizable" in ASK_BOUNDARY
    assert "SILICON_VERIFIED" in ASK_BOUNDARY


def test_classify_request_falls_back_without_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    driver = _make_driver(tmp_path)

    def _boom(messages: object) -> str:
        raise RuntimeError("no network")

    monkeypatch.setattr(driver, "_query_model", _boom)
    try:
        assert driver.classify_request("Anything at all") == "GENERATE"
    finally:
        driver.close()
