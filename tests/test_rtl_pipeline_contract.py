import json
from pathlib import Path
from mind3.core.contracts import (
    VerificationFailureEvidence,
    VerificationRepairer,
    contract_from_benchmark_record,
    validate_rtl_against_contract,
    validate_contract_consistency,
)


def _record() -> dict:
    return {
        "task_id": "fifo_unit",
        "natural_language_spec": "Synchronous FIFO with reset.",
        "expected_ports": [
            {"name": "clk", "direction": "input", "width": 1},
            {"name": "rst_n", "direction": "input", "width": 1},
            {"name": "wr_en", "direction": "input", "width": 1},
            {"name": "wr_data", "direction": "input", "width": 8},
            {"name": "rd_en", "direction": "input", "width": 1},
            {"name": "rd_data", "direction": "output", "width": 8},
        ],
        "clock_reset_assumptions": "clk rising edge; active-low synchronous rst_n",
        "functional_requirements": ["Writes are accepted on wr_en and reads on rd_en."],
        "expected_properties": ["assert property (@(posedge clk) disable iff (!rst_n) rd_data == rd_data);"],
        "verification_requirements": ["bounded FIFO safety"],
        "parameters": {},
    }


def test_benchmark_contract_is_deterministic_and_exact() -> None:
    contract = contract_from_benchmark_record(_record())
    assert contract.module_name == "fifo_unit"
    assert [(p.name, p.direction.value, p.width) for p in contract.ports] == [
        ("clk", "input", 1),
        ("rst_n", "input", 1),
        ("wr_en", "input", 1),
        ("wr_data", "input", 8),
        ("rd_en", "input", 1),
        ("rd_data", "output", 8),
    ]
    assert contract.clock is not None and contract.clock.name == "clk"
    assert contract.reset is not None and contract.reset.name == "rst_n" and contract.reset.synchronous is True


def test_contract_rejects_interface_drift_before_eda() -> None:
    contract = contract_from_benchmark_record(_record())
    bad_rtl = "module fifo_unit(input clk, input rst_n, input wr_en, input [7:0] wr_data, input rd_en, output [7:0] wrong); assign wrong = wr_data; endmodule\n"
    violations = validate_rtl_against_contract(contract, bad_rtl)
    assert violations
    assert any(v["category"] == "INTERFACE_ERROR" for v in violations)
    assert all("reference" not in json.dumps(v).lower() for v in violations)


def test_structured_repair_prompt_contains_bound_evidence() -> None:
    contract = contract_from_benchmark_record(_record())
    bad_rtl = "module fifo_unit(input clk, input rst_n, input wr_en, input [7:0] wr_data, input rd_en, output [7:0] wrong); assign wrong = wr_data; endmodule\n"
    evidence = VerificationFailureEvidence(
        gate="Gate 1",
        category="TYPE_WIDTH_ERROR",
        stage="compile",
        tool="verilator",
        error="width mismatch",
        file="fifo_unit.sv",
        line=12,
        column=9,
        source_context="wr_data[7:0]",
        contract=contract.model_dump(mode="json"),
        attempt=1,
        repair_history=["TYPE_WIDTH_ERROR"],
    )
    prompt = VerificationRepairer.build_prompt(contract, bad_rtl, evidence)
    assert "Do not change the module interface" in prompt["system"]
    assert "Do not weaken verification" in prompt["system"]
    assert "verilator" in prompt["user"]
    assert '"line": 12' in prompt["user"]
    assert "Immutable contract" in prompt["user"]


def test_contract_json_is_json_serializable() -> None:
    contract = contract_from_benchmark_record(_record())
    dumped = contract.model_dump(mode="json")
    assert json.loads(json.dumps(dumped))["module_name"] == "fifo_unit"


def test_inconsistent_heldout_contract_is_blocked_before_generation():
    record = next(
        json.loads(line)
        for line in Path('benchmarks/heldout/tasks.jsonl').read_text(encoding='utf-8').splitlines()
        if json.loads(line)['task_id'] == 'arbiter_02'
    )
    contract = contract_from_benchmark_record(record)
    violations = validate_contract_consistency(contract)
    assert violations
    assert all(v['category'] == 'SPECIFICATION_ERROR' for v in violations)


def test_model_usage_accounting_is_explicitly_known_or_unknown(monkeypatch):
    from mind3.core.driver import PhaseDriver
    monkeypatch.delenv('MIND_COST_PER_MILLION_INPUT_USD', raising=False)
    monkeypatch.delenv('MIND_COST_PER_MILLION_OUTPUT_USD', raising=False)
    driver = object.__new__(PhaseDriver)
    driver.total_prompt_tokens = 0
    driver.total_completion_tokens = 0
    driver.model_usage_known = False
    driver.model_cost_usd = 0.0
    driver.model_cost_known = False
    driver._record_model_usage(100, 40)
    assert driver.total_tokens == 140
    assert driver.model_usage_known is True
    assert driver.model_cost_known is False


def test_phase_driver_initializes_usage_counters_before_pipeline():
    from mind3.core.driver import PhaseDriver

    class _SandboxStub:
        pass

    driver = PhaseDriver(
        session_id="usage_init",
        workspace=Path("/tmp/mind3_usage_init"),
        verifier=object(),
        sandbox=_SandboxStub(),
    )
    try:
        assert driver.total_prompt_tokens == 0
        assert driver.total_completion_tokens == 0
        assert driver.total_tokens == 0
        assert driver.model_usage_known is False
        assert driver.model_cost_usd == 0.0
        assert driver.model_cost_known is False
    finally:
        driver.close()
