"""Stage 3 parser-honesty tests: strict parsing is the default, lenient recovery is explicit.

Strict mode accepts only WriteFileAction schema output, fenced Verilog blocks,
repair-loop patch objects (only when base_code is supplied), and raw text that
is exactly one Verilog module. Everything else raises ModelResponseParseError.

Lenient mode (explicit opt-in via parser_mode="lenient") additionally recovers
documented JSON shapes: structural AST dicts and the LENIENT_KNOWN_KEYS values.
Arbitrary JSON keys are never scanned in either mode, and unicode_escape
decoding never applies outside lenient JSON-string recovery.
"""

import pytest
from mind3.core.driver import (
    _parse_model_code_response,
    LENIENT_KNOWN_KEYS,
    ModelResponseParseError,
)

# ── Strict-mode acceptance ────────────────────────────────────────────────

def test_direct_rtl():
    rtl = "module top(input a, output b);\n  assign b = a;\nendmodule"
    assert "module top" in _parse_model_code_response(rtl)

def test_fenced_rtl():
    raw = "Here is the code:\n```systemverilog\nmodule top(input a, output b);\n  assign b = a;\nendmodule\n```\nHope it helps!"
    assert "module top" in _parse_model_code_response(raw)

def test_strict_accepts_write_file_action_verbatim():
    payload = '{"action": "write_file", "path": "alu.sv", "content": "module alu(input clk); endmodule"}'
    assert _parse_model_code_response(payload) == "module alu(input clk); endmodule"

def test_strict_accepts_exact_module_with_leading_comment():
    raw = "/* { brace at start with content in comment */\nmodule tricky();\nendmodule"
    assert _parse_model_code_response(raw) == raw

# ── Strict-mode rejection (Phase 0 guarantee: no key unwrapping, no guessing) ──

def test_strict_rejects_content_key_json():
    """Historical Phase 0 guarantee: a generic 'content' key is NOT unwrapped in strict mode."""
    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response('{"content": "module fifo(); endmodule"}')

def test_strict_rejects_arbitrary_keys_holding_modules():
    """Arbitrary JSON values are never searched, even when they contain a module."""
    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response('{"notes": "module sneak(); endmodule"}')
    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response('{"synthesizable_code": "module s(); endmodule"}')

def test_strict_rejects_prose_wrapped_module():
    """A module embedded in surrounding prose is ambiguous and must be rejected."""
    prose = (
        "Here is the module:\n\n"
        "module embedded(input a);\nendmodule\n\n"
        "Let me know if you need anything else."
    )
    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response(prose)

def test_strict_does_not_decode_unicode_escapes():
    """Strict mode never applies unicode_escape decoding to extracted text."""
    raw = "```verilog\nmodule m(); // literal \\n escape stays\nendmodule\n```"
    result = _parse_model_code_response(raw)
    assert "\\n" in result

def test_strict_preserves_non_ascii_rtl():
    """Non-ASCII RTL comments survive strict parsing unchanged."""
    raw = "/* caf\u00e9 \u00fcber */\nmodule m(input a);\nendmodule"
    assert _parse_model_code_response(raw) == raw

def test_strict_is_default_without_configuration():
    """Calling the parser without parser_mode must behave as strict."""
    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response('{"content": "module fifo(); endmodule"}')
    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response('{"module_code": "module m(); endmodule"}')

def test_malformed_truncated_error():
    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response("This is not code at all.")

    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response("module top(input a; assign b = a;")

    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response('{"module": "test"}')  # missing pinout and implementation

    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response('{"status": "error", "message": "Failed"}')

    # The same inputs also fail in lenient mode: ambiguity is never guessed through.
    for garbage in (
        "This is not code at all.",
        "module top(input a; assign b = a;",
        '{"module": "test"}',
        '{"status": "error", "message": "Failed"}',
    ):
        with pytest.raises(ModelResponseParseError):
            _parse_model_code_response(garbage, parser_mode="lenient")

# ── Lenient-mode bounded recovery ─────────────────────────────────────────

def test_json_content_and_module_code():
    json1 = '{"content": "module top(input a, output b);\\n  assign b = a;\\nendmodule"}'
    assert "assign b = a;" in _parse_model_code_response(json1, parser_mode="lenient")

    json2 = '{"module_code": "module top(input a, output b);\\n  assign b = a;\\nendmodule"}'
    assert "assign b = a;" in _parse_model_code_response(json2, parser_mode="lenient")

def test_lenient_known_keys_only_cover_documented_keys():
    """Every documented lenient key recovers; undocumented keys never do."""
    for key in LENIENT_KNOWN_KEYS:
        payload = '{"%s": "module mod_%s(); endmodule"}' % (key, key)
        assert _parse_model_code_response(payload, parser_mode="lenient") == f"module mod_{key}(); endmodule"
    assert set(LENIENT_KNOWN_KEYS) == {"module_code", "verilog_code", "code", "content", "response", "rtl", "text"}

def test_lenient_rejects_undocumented_keys():
    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response('{"synthesizable_code": "module s(); endmodule"}', parser_mode="lenient")
    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response('{"notes": "module sneak(); endmodule"}', parser_mode="lenient")
    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response('{"rtl_code": "module r(); endmodule"}', parser_mode="lenient")

def test_lenient_recovers_malformed_but_unambiguous_local_response():
    """A documented key holding an inner-fenced, double-escaped module recovers in lenient mode."""
    payload = '{"module_code": "```verilog\\nmodule inner();\\nendmodule\\n```"}'
    assert _parse_model_code_response(payload, parser_mode="lenient") == "module inner();\nendmodule"
    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response(payload)

def test_ast_json_full():
    ast_json = '''{
        "module": "alu",
        "parameters": {"WIDTH": 8},
        "pinout": [
            {"name": "clk", "direction": "input", "width": 1},
            {"name": "a", "direction": "input", "range": "[WIDTH-1:0]"},
            {"name": "b", "direction": "input", "bits": 8},
            {"name": "y", "direction": "output", "width": 8}
        ],
        "implementation": "always_comb y = a + b;"
    }'''
    res = _parse_model_code_response(ast_json, parser_mode="lenient")
    assert "module alu" in res
    assert "parameter WIDTH = 8" in res
    assert "input logic clk" in res
    assert "input logic [WIDTH-1:0] a" in res
    assert "input logic [7:0] b" in res
    assert "output logic [7:0] y" in res
    assert "always_comb y = a + b;" in res
    assert "endmodule" in res
    # AST reconstruction is lenient-only: strict mode must reject it.
    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response(ast_json)

def test_ast_json_empty_legal_body():
    ast_json = '''{
        "module": "empty_mod",
        "pinout": [{"name": "in1", "direction": "input", "width": 1}],
        "implementation": ""
    }'''
    res = _parse_model_code_response(ast_json, parser_mode="lenient")
    assert "module empty_mod" in res
    assert "endmodule" in res

def test_ast_json_dict_ports_and_structural_body():
    ast_json = '''{
        "module": "fifo_01",
        "ports": {
            "clk": {"type": "input", "width": 1},
            "data_in": {"type": "input", "width": 8},
            "data_out": {"type": "output", "width": 8}
        },
        "internal_signals": {
            "count": {"type": "reg", "width": 4}
        },
        "always_blocks": [
            {
                "trigger": "posedge clk",
                "body": "count <= count + 1;"
            }
        ],
        "assign_statements": [
            "assign data_out = data_in;"
        ]
    }'''
    res = _parse_model_code_response(ast_json, "fifo_01", parser_mode="lenient")
    assert "module fifo_01" in res
    assert "input logic clk" in res
    assert "input logic [7:0] data_in" in res
    assert "output logic [7:0] data_out" in res
    assert "reg [3:0] count;" in res
    assert "assign data_out = data_in;" in res
    assert "always @(posedge clk) begin" in res
    assert "count <= count + 1;" in res
    assert "endmodule" in res

def test_lenient_unescapes_documented_json_string_values():
    payload = '{"implementation_holder": "x"}'
    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response(payload, parser_mode="lenient")
    escaped = '{"module_code": "module m();\\n  assign x = 1;\\nendmodule"}'
    assert _parse_model_code_response(escaped, parser_mode="lenient") == "module m();\n  assign x = 1;\nendmodule"

def test_json_synthesizable_code_without_identifier_is_not_recovered():
    """'synthesizable_code' is not a documented lenient known key, so a bare
    synthesizable_code object (no module identifier, hence no AST shape) is
    rejected in both modes. Arbitrary keys are never scanned."""
    json_str = '{"synthesizable_code": "module s(); endmodule"}'
    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response(json_str)
    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response(json_str, parser_mode="lenient")

def test_json_synthesizable_code_with_label_uses_documented_ast_shape():
    """A label plus implementation alias matches the documented lenient AST shape,
    so it recovers in lenient mode only. Strict mode still rejects it."""
    json_str = '''{
        "label": "counter_04",
        "description": "8-bit counter",
        "synthesizable_code": "module counter_04(input clk, output [7:0] q);\\n  assign q = 8'h0;\\nendmodule"
    }'''
    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response(json_str, "counter_04")
    res = _parse_model_code_response(json_str, "counter_04", parser_mode="lenient")
    assert "module counter_04" in res
    assert "assign q = 8'h0;" in res
    assert "endmodule" in res

# ── Repair-loop separation ────────────────────────────────────────────────

def test_safe_patch_application_repair():
    base_rtl = "module counter_04 (\n  input [1:0] clk,\n  output reg [7:0] q\n);\n  assign q = 0;\nendmodule"
    patch_json = '''{
        "file": "counter_04.sv",
        "line": 2,
        "patch": "  input logic clk,"
    }'''
    res = _parse_model_code_response(patch_json, "counter_04", base_code=base_rtl)
    assert "module counter_04" in res
    assert "input logic clk," in res
    assert "input [1:0] clk" not in res
    assert "endmodule" in res

def test_repair_patch_requires_base_code():
    """A patch object without base_code is not initial-parse recovery: strict rejects it."""
    patch_json = '{"file": "c.sv", "line": 2, "patch": "  input logic clk,"}'
    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response(patch_json, "c")
    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response(patch_json, "c", parser_mode="lenient")

def test_invalid_parser_mode_raises():
    with pytest.raises(ValueError):
        _parse_model_code_response("module m(); endmodule", parser_mode="auto")
    with pytest.raises(ValueError):
        _parse_model_code_response("module m(); endmodule", parser_mode="OLLAMA")
