"""Regression: RTL generation must not request JSON from the model.

The strict parser consumes textual RTL (fenced/single-module Verilog or a
documented action form). Forcing ``"format": "json"`` on those calls makes the
model emit AST-shaped dicts that no parser mode accepts, so generation and
repair request plain text while contract synthesis keeps JSON.
"""

from __future__ import annotations

from pathlib import Path

from mind3.core.driver import (
    ModelResponseParseError,
    PhaseDriver,
    _parse_model_code_response,
)


class _StubVerifier:
    pass


class _SandboxStub:
    pass


class _RecordingClient:
    def __init__(self, content: str) -> None:
        self.payloads: list[dict] = []
        self._content = content

    def post(self, endpoint: str, json: dict | None = None, **kwargs):  # noqa: A002
        self.payloads.append(dict(json or {}))

        class _Resp:
            def __init__(self, text: str) -> None:
                self._text = text

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"message": {"content": self._text}}

        return _Resp(self._content)


def _driver(tmp_path: Path, content: str) -> tuple[PhaseDriver, _RecordingClient]:
    client = _RecordingClient(content)
    driver = PhaseDriver(
        session_id="rtl-format",
        workspace=tmp_path,
        verifier=_StubVerifier(),  # type: ignore[arg-type]
        sandbox=_SandboxStub(),  # type: ignore[arg-type]
        model="qwen2.5-coder:7b",
        provider="ollama",
    )
    driver.client = client  # type: ignore[assignment]
    return driver, client


def test_generation_path_omits_json_constraint(tmp_path: Path) -> None:
    driver, client = _driver(tmp_path, "module m; endmodule")
    driver._query_model([{"role": "user", "content": "hi"}], response_format="text")
    assert len(client.payloads) == 1
    assert "format" not in client.payloads[0]
    assert client.payloads[0]["model"] == "qwen2.5-coder:7b"


def test_default_path_keeps_json_constraint(tmp_path: Path) -> None:
    driver, client = _driver(tmp_path, "{}")
    driver._query_model([{"role": "user", "content": "hi"}])
    assert client.payloads[0].get("format") == "json"


def test_fenced_systemverilog_parses_strict() -> None:
    fenced = (
        "```systemverilog\n"
        "module counter_01 (input clk, input rst_n, output [7:0] count);\n"
        "  always @(posedge clk or negedge rst_n) begin\n"
        "    if (!rst_n) count <= 8'h00;\n"
        "    else count <= count + 1'b1;\n"
        "  end\n"
        "endmodule\n"
        "```"
    )
    code = _parse_model_code_response(fenced, default_module_name="counter_01", parser_mode="strict")
    assert "module counter_01" in code
    assert "endmodule" in code


def test_lossy_ast_dict_still_rejected_strict() -> None:
    ast_like = (
        '{"module": "counter_01", "sequential": '
        '[{"always": {"body": [{"assign": {"lhs": "count", "rhs": 80}}]}}]}'
    )
    try:
        _parse_model_code_response(ast_like, default_module_name="counter_01", parser_mode="strict")
    except ModelResponseParseError:
        return
    raise AssertionError("strict parser must stay fail-closed on AST-shaped dicts")


def test_repair_hint_cdc_names_crossings() -> None:
    from mind3.core.driver import _repair_strategy_hint

    hint = _repair_strategy_hint(
        "CDC_VIOLATION",
        {"cdc_violations": ["CDC-001 error f.sv unsynchronized crossing clk_a → clk_b"]},
        False,
    )
    assert "synchronizer" in hint
    assert "clk_a" in hint
    assert "Do not change port names" in hint


def test_repair_hint_formal_points_at_evidence() -> None:
    from mind3.core.driver import _repair_strategy_hint

    hint = _repair_strategy_hint("FORMAL_INVARIANT_BREACH", {}, False)
    assert "counterexample" in hint
    assert "do not alter the property" in hint


def test_repair_hint_repeated_demands_different_fix() -> None:
    from mind3.core.driver import _repair_strategy_hint

    hint = _repair_strategy_hint("COVERAGE_DEFICIT", {}, True)
    assert "do not " in hint.lower() and "repeat the same edit" in hint


def test_repair_hint_empty_for_unknown() -> None:
    from mind3.core.driver import _repair_strategy_hint

    assert _repair_strategy_hint("SOME_OTHER", {}, False) == ""
