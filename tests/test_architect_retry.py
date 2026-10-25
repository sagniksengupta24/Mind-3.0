"""Architect contract synthesis gets one bounded retry with the schema error fed back."""
import json
from pathlib import Path

from mind3.core.driver import PhaseDriver
from mind3.core.verifier import SiliconSignoffVerifier
from sandbox_stub import StubSandbox


def _make_driver(tmp_path: Path) -> PhaseDriver:
    ws = tmp_path / "ws"
    ws.mkdir()
    return PhaseDriver(
        session_id="architect-retry-test",
        workspace=ws,
        verifier=SiliconSignoffVerifier(top_module="t"),
        sandbox=StubSandbox(),
    )


def _architect_attempts(driver: PhaseDriver) -> int:
    return sum(
        1
        for rec in driver.transcript
        if rec.event.phase.value == "MODEL_CALL"
        and rec.event.payload.get("stage") == "contract_synthesis"
    )


def test_architect_retries_once_then_gives_up(tmp_path: Path, monkeypatch) -> None:
    driver = _make_driver(tmp_path)
    monkeypatch.setattr(driver, "_query_model", lambda messages, force_json=False: "not json")
    try:
        assert driver.run_silicon_pipeline("Do a thing.") is False
        assert _architect_attempts(driver) == 2
    finally:
        driver.close()


def test_architect_retry_recovers_with_valid_contract(tmp_path: Path, monkeypatch) -> None:
    from mind3.core.types import VerificationDomain, VerificationResult

    driver = _make_driver(tmp_path)
    valid = json.dumps({
        "module_name": "t",
        "functional_spec": "A wire.",
        "ports": [
            {"name": "clk", "direction": "input"},
            {"name": "rst_n", "direction": "input"},
            {"name": "a", "direction": "input"},
            {"name": "y", "direction": "output"},
        ],
    })
    calls = {"n": 0}

    def _flaky(messages: object, force_json: bool = False) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return "not json"
        if force_json:
            return valid
        return "module t(input logic clk, input logic rst_n, input logic a, output logic y); assign y = a; endmodule"

    def _fake_verify(workspace: object, sandbox: object) -> VerificationResult:
        return VerificationResult(passed=True, domain=VerificationDomain.RTL, exit_code=0, silicon_verified=True)

    monkeypatch.setattr(driver, "_query_model", _flaky)
    monkeypatch.setattr(driver.verifier, "verify", _fake_verify)
    try:
        assert driver.run_silicon_pipeline("Do a thing.") is True
        assert _architect_attempts(driver) == 2
        assert calls["n"] == 3  # 2 architect calls + 1 RTL call, no repair needed
    finally:
        driver.close()


def test_always_dead_endpoint_returns_false_bounded(tmp_path: Path, monkeypatch) -> None:
    driver = _make_driver(tmp_path)
    calls = {"n": 0}

    def _dead(messages: object, force_json: bool = False) -> str:
        calls["n"] += 1
        raise RuntimeError("endpoint dead")

    monkeypatch.setattr(driver, "_query_model", _dead)
    try:
        # Architect stage retries once, then rolls back: no EDA, no hang.
        assert driver.run_silicon_pipeline("Do a thing.") is False
        assert calls["n"] == 2
    finally:
        driver.close()


def test_architect_consistency_rejection_gets_one_retry(tmp_path: Path, monkeypatch) -> None:
    from mind3.core.types import VerificationDomain, VerificationResult

    driver = _make_driver(tmp_path)
    bad_template = json.dumps({
        "module_name": "t",
        "functional_spec": "A wire.",
        "ports": [{"name": "a", "direction": "input"}, {"name": "y", "direction": "output"}],
        "formal_properties": [{
            "name": "req_implies_gnt",
            "kind": "same_cycle_implication",
            "clock": "clk",
            "antecedent": "req",
            "consequent": "gnt",
        }],
    })
    good = json.dumps({
        "module_name": "t",
        "functional_spec": "A wire.",
        "ports": [{"name": "a", "direction": "input"}, {"name": "y", "direction": "output"}],
        "formal_properties": [{
            "name": "holds",
            "kind": "same_cycle_implication",
            "clock": None,
            "antecedent": "a",
            "consequent": "y",
        }],
    })
    calls = {"n": 0}

    def _flaky(messages: object, force_json: bool = False) -> str:
        calls["n"] += 1
        if force_json:
            return bad_template if calls["n"] == 1 else good
        return "module t(input logic a, output logic y); assign y = a; endmodule"

    def _fake_verify(workspace: object, sandbox: object):
        from mind3.core.types import VerificationDomain, VerificationResult
        return VerificationResult(passed=True, domain=VerificationDomain.RTL, exit_code=0, silicon_verified=True)

    monkeypatch.setattr(driver, "_query_model", _flaky)
    monkeypatch.setattr(driver.verifier, "verify", _fake_verify)
    try:
        # Template junk (req/gnt) rejected once, clean contract accepted.
        assert driver.run_silicon_pipeline("Do a thing.") is True
        assert _architect_attempts(driver) == 2
    finally:
        driver.close()


def test_architect_prompt_pins_temporal_honesty() -> None:
    from mind3.core.contracts import ContractSynthesizer

    system = ContractSynthesizer.build_prompt("Do a thing.")["system"]
    assert "next_cycle_implication" in system
    assert "same_cycle_implication is only valid for purely combinational paths" in system


def test_contract_override_path_sets_violations_list(tmp_path: Path, monkeypatch) -> None:
    """Benchmark path (contract_override) must not hit unbound contract_violations."""
    from mind3.core.contracts import InterfaceContract
    from mind3.core.types import VerificationDomain, VerificationResult

    driver = _make_driver(tmp_path)
    override = InterfaceContract(
        module_name="t",
        functional_spec="A wire.",
        ports=[
            {"name": "a", "direction": "input"},
            {"name": "y", "direction": "output"},
        ],
    )
    monkeypatch.setattr(
        driver, "_query_model",
        lambda messages, force_json=False: "module t(input logic a, output logic y); assign y = a; endmodule",
    )
    monkeypatch.setattr(
        driver.verifier, "verify",
        lambda ws, sb: VerificationResult(passed=True, domain=VerificationDomain.RTL, exit_code=0, silicon_verified=True),
    )
    try:
        assert driver.run_silicon_pipeline("Do a thing.", contract_override=override) is True
    finally:
        driver.close()


def test_dead_model_endpoint_cannot_spin_forever(tmp_path: Path, monkeypatch) -> None:
    import json as _json

    driver = _make_driver(tmp_path)
    valid = _json.dumps({
        "module_name": "t",
        "functional_spec": "A wire.",
        "ports": [{"name": "a", "direction": "input"}, {"name": "y", "direction": "output"}],
    })
    calls = {"n": 0}

    def _dies_after_contract(messages: object, force_json: bool = False) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return valid
        raise RuntimeError("endpoint dead")

    monkeypatch.setattr(driver, "_query_model", _dies_after_contract)
    try:
        # Pre-fix this looped forever: model-call failures never advanced any
        # budget. Now it must roll back after 3 consecutive failures.
        assert driver.run_silicon_pipeline("Do a thing.") is False
        # 1 contract + 1 initial RTL attempt + 3 failed repair calls, then stop.
        assert calls["n"] == 5
    finally:
        driver.close()
