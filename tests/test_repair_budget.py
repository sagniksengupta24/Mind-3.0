from mind3.core.driver import REPAIR_MAX_CHANGED_LINE_RATIO, _repair_diff_stats, _rtl_identity_hash
from sandbox_stub import StubSandbox


def test_successful_parses_do_not_consume_parse_budget(monkeypatch, tmp_path) -> None:
    """Parse budget counts failures only: parseable-but-failing repairs must
    receive the full stage budget (3 compile EDA turns here), and the terminal
    category must be the real failure, not RESPONSE_PARSE_FAILURE."""
    import tempfile
    from pathlib import Path as _Path

    from mind3.core.contracts import contract_from_benchmark_record
    from mind3.core.driver import PhaseDriver
    from mind3.core.types import PhaseEnum
    from mind3.core.verifier import SiliconSignoffVerifier

    contract = contract_from_benchmark_record(
        {
            "task_id": "arbiter_02",
            "natural_language_spec": "4-client fixed priority arbiter",
            "expected_ports": [
                {"name": "clk", "direction": "input", "width": 1},
                {"name": "rst_n", "direction": "input", "width": 1},
                {"name": "req", "direction": "input", "width": 4},
                {"name": "gnt", "direction": "output", "width": 4},
            ],
            "clock_reset_assumptions": "clk rising edge; active-low synchronous rst_n",
            "functional_requirements": ["4-client fixed priority arbiter"],
            "expected_properties": [
                "assert property (@(posedge clk) req[0] |-> gnt[0]);",
                "assert property (@(posedge clk) $onehot0(gnt));",
            ],
            "verification_requirements": [],
            "parameters": {},
        }
    )
    rtl = (
        "module arbiter_02 (\n"
        "  input  logic clk,\n"
        "  input  logic rst_n,\n"
        "  input  logic [3:0] req,\n"
        "  output logic [3:0] gnt\n"
        ");\n"
        "  always_ff @(posedge clk or negedge rst_n) begin\n"
        "    if (!rst_n) gnt <= 4'b0;\n"
        "    else gnt <= req;\n"
        "  end\n"
        "endmodule\n"
    )
    ws = tmp_path / "ws"
    ws.mkdir()
    verifier = SiliconSignoffVerifier(top_module="arbiter_02", contract=contract)
    driver = PhaseDriver(
        session_id="parse-budget-test",
        workspace=ws,
        verifier=verifier,
        max_repairs=3,
        model="qwen2.5-coder:7b",
        provider="ollama",
        sandbox=StubSandbox(),
    )
    monkeypatch.setattr(driver, "_query_model", lambda messages, **kwargs: rtl)
    try:
        ok = driver.run_silicon_pipeline("build arbiter", contract_override=contract)
    finally:
        driver.close()
    assert ok is False
    # No parse failure ever occurred: budget untouched.
    assert driver._parse_attempts == 0
    # Full compile stage budget spent on real EDA-loop turns.
    assert driver._stage_repair_attempts["compile"] == 3
    finishes = [r for r in driver.transcript if r.phase == PhaseEnum.REPAIR_OR_FINISH]
    assert finishes
    terminal = finishes[-1].event.payload
    assert terminal.get("status") == "ROLLED_BACK"
    assert terminal.get("failure_category") == "CLOCK_RESET_ERROR"


def test_repair_diff_stats_is_deterministic() -> None:
    before = "module x;\n  assign y = a;\nendmodule\n"
    after = "module x;\n  assign y = b;\nendmodule\n"
    stats = _repair_diff_stats(before, after)
    assert stats["changed_lines"] == 2
    assert stats["before_lines"] == 3
    assert stats["after_lines"] == 3
    assert stats["changed_line_ratio"] == 2 / 3
    assert REPAIR_MAX_CHANGED_LINE_RATIO < 1.0


def test_rtl_identity_hash_ignores_only_line_endings_and_trailing_whitespace() -> None:
    source = "module x;\r\n  assign y = a;   \r\nendmodule\r\n"
    equivalent_formatting = "module x;\n  assign y = a;\nendmodule"
    changed_behavior = "module x;\n  assign y = ~a;\nendmodule"

    assert _rtl_identity_hash(source) == _rtl_identity_hash(equivalent_formatting)
    assert _rtl_identity_hash(source) != _rtl_identity_hash(changed_behavior)
