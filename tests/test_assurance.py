from pathlib import Path

from mind3.core.assurance import TapeoutReadinessVerifier


def test_tapeout_readiness_fails_closed_without_receipts(tmp_path: Path) -> None:
    result = TapeoutReadinessVerifier().verify(tmp_path)

    assert result["tapeout_ready"] is False
    assert len(result["receipts"]) == 8
    assert all(not receipt["passed"] for receipt in result["receipts"])


def test_tapeout_readiness_requires_clean_external_receipts(tmp_path: Path) -> None:
    verifier = TapeoutReadinessVerifier()
    for check in verifier.policy.checks:
        report = tmp_path / check.report
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("STATUS: PASS\n", encoding="utf-8")

    assert verifier.verify(tmp_path)["tapeout_ready"] is True

    (tmp_path / verifier.policy.checks[0].report).write_text("STATUS: FAIL\n", encoding="utf-8")
    assert verifier.verify(tmp_path)["tapeout_ready"] is False
