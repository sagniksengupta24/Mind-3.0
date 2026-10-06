"""Regression: Gate 3 branch coverage is never fabricated from line data.

Fixtures use real Verilator coverage.dat bytes (0x01/0x02 field separators).
"""

from __future__ import annotations

from pathlib import Path

from mind3.core.verifier import parse_coverage_dat_file

SOH, STX = chr(1), chr(2)
HEADER = "# SystemC::Coverage-3"


def _line(ln: int, hits: int) -> str:
    return (
        f"C '{SOH}f{STX}mod.sv{SOH}l{STX}{ln}{SOH}n{STX}5"
        f"{SOH}page{STX}v_line/mod{SOH}o{STX}stmt{SOH}S{STX}{ln}"
        f"{SOH}h{STX}TOP.mod' {hits}"
    )


def _branch(ln: int, hits: int) -> str:
    return (
        f"C '{SOH}f{STX}mod.sv{SOH}l{STX}{ln}{SOH}n{STX}5"
        f"{SOH}page{STX}v_branch/mod{SOH}o{STX}if{SOH}S{STX}{ln}-{ln + 1}"
        f"{SOH}h{STX}TOP.mod' {hits}"
    )


def _write(tmp_path: Path, name: str, rows: list[str]) -> Path:
    path = tmp_path / name
    path.write_text(HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_line_only_coverage_leaves_branch_unavailable(tmp_path: Path) -> None:
    path = _write(tmp_path, "line_only.dat", [_line(10, 6), _line(12, 218), _line(15, 3)])
    parsed = parse_coverage_dat_file(path)
    assert parsed["line"] == 100.0
    assert parsed["branch"] is None


def test_real_branch_coverage_computed(tmp_path: Path) -> None:
    path = _write(tmp_path, "branch.dat", [_branch(20, 5), _branch(21, 0)])
    parsed = parse_coverage_dat_file(path)
    assert parsed["branch"] == 50.0


def test_branch_uses_branch_data_not_line(tmp_path: Path) -> None:
    path = _write(
        tmp_path, "mixed.dat", [_line(10, 6), _line(12, 0), _branch(20, 5), _branch(21, 0)]
    )
    parsed = parse_coverage_dat_file(path)
    assert parsed["line"] == 50.0
    assert parsed["branch"] == 50.0


def test_missing_branch_cannot_satisfy_threshold(tmp_path: Path) -> None:
    path = _write(tmp_path, "line_only2.dat", [_line(10, 6)])
    parsed = parse_coverage_dat_file(path)
    assert parsed["branch"] is None
    assert not (parsed["branch"] is not None and parsed["branch"] >= 95.0)
