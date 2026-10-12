"""C1 replay harness: recorded/synthetic model-output shapes -> parser verdicts.

Each fixture directory under tests/fixtures/qwen_shapes/<id>/ contains:
  raw.txt   - exact model-shaped bytes fed to the parser
  meta.json - {"notes": str, "needs_base_code": bool,
               "expect": {"strict": "accept"|"reject",
                          "lenient": "accept"|"reject"}}

Parser or prompt PRs must pass offline here before any live rerun (plan C1).
Real Stage-6 raw outputs are added under the same layout with
"model_digest" set in meta.json (scrubbed of local paths, few-KB cap).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mind3.core.driver import ModelResponseParseError, _parse_model_code_response

SHAPES_DIR = Path(__file__).resolve().parent / "fixtures" / "qwen_shapes"
DUMMY_BASE = "module dut (\n  input logic clk\n);\nendmodule\n"


def _load_cases() -> list[tuple[str, str, dict]]:
    cases: list[tuple[str, str, dict]] = []
    if not SHAPES_DIR.is_dir():
        return cases
    for child in sorted(SHAPES_DIR.iterdir()):
        raw_path = child / "raw.txt"
        meta_path = child / "meta.json"
        if child.is_dir() and raw_path.is_file() and meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            cases.append((child.name, raw_path.read_text(encoding="utf-8"), meta))
    return cases


def _try_parse(raw: str, mode: str, needs_base: bool) -> str | None:
    try:
        return _parse_model_code_response(
            raw,
            default_module_name="dut",
            base_code=DUMMY_BASE if needs_base else None,
            parser_mode=mode,
        )
    except ModelResponseParseError:
        return None


@pytest.mark.parametrize("shape_id,raw,meta", _load_cases())
def test_qwen_shape_verdict(shape_id: str, raw: str, meta: dict) -> None:
    expect = meta["expect"]
    needs_base = bool(meta.get("needs_base_code", False))
    assert set(expect) == {"strict", "lenient"}, f"{shape_id}: meta must pin both modes"
    for mode in ("strict", "lenient"):
        result = _try_parse(raw, mode, needs_base)
        if expect[mode] == "accept":
            assert result is not None, f"{shape_id}: expected ACCEPT in {mode}, got reject"
            assert "endmodule" in result, f"{shape_id}: accepted text lacks endmodule"
        else:
            assert result is None, f"{shape_id}: expected REJECT in {mode}, got accept"
