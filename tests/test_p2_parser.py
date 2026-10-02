"""Comprehensive P2 Parser test suite verifying all required formats and error handling."""

import pytest
from mind3.core.driver import _parse_model_code_response, ModelResponseParseError

def test_direct_rtl():
    rtl = "module top(input a, output b);\n  assign b = a;\nendmodule"
    assert "module top" in _parse_model_code_response(rtl)

def test_fenced_rtl():
    raw = "Here is the code:\n```systemverilog\nmodule top(input a, output b);\n  assign b = a;\nendmodule\n```\nHope it helps!"
    assert "module top" in _parse_model_code_response(raw)

def test_json_content_and_module_code():
    json1 = '{"content": "module top(input a, output b);\\n  assign b = a;\\nendmodule"}'
    assert "assign b = a;" in _parse_model_code_response(json1)

    json2 = '{"module_code": "module top(input a, output b);\\n  assign b = a;\\nendmodule"}'
    assert "assign b = a;" in _parse_model_code_response(json2)

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
    res = _parse_model_code_response(ast_json)
    assert "module alu" in res
    assert "parameter WIDTH = 8" in res
    assert "input logic clk" in res
    assert "input logic [WIDTH-1:0] a" in res
    assert "input logic [7:0] b" in res
    assert "output logic [7:0] y" in res
    assert "always_comb y = a + b;" in res
    assert "endmodule" in res

def test_ast_json_empty_legal_body():
    ast_json = '''{
        "module": "empty_mod",
        "pinout": [{"name": "in1", "direction": "input", "width": 1}],
        "implementation": ""
    }'''
    res = _parse_model_code_response(ast_json)
    assert "module empty_mod" in res
    assert "endmodule" in res

def test_malformed_truncated_error():
    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response("This is not code at all.")

    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response("module top(input a; assign b = a;")

    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response('{"module": "test"}')  # missing pinout and implementation

    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response('{"status": "error", "message": "Failed"}')


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
    res = _parse_model_code_response(ast_json, "fifo_01")
    assert "module fifo_01" in res
    assert "input logic clk" in res
    assert "input logic [7:0] data_in" in res
    assert "output logic [7:0] data_out" in res
    assert "reg [3:0] count;" in res
    assert "assign data_out = data_in;" in res
    assert "always @(posedge clk) begin" in res
    assert "count <= count + 1;" in res
    assert "endmodule" in res


def test_json_synthesizable_code_unwrapping():
    json_str = '''{
        "label": "counter_04",
        "description": "8-bit counter",
        "synthesizable_code": "module counter_04(input clk, output [7:0] q);\\n  assign q = 8'h0;\\nendmodule"
    }'''
    res = _parse_model_code_response(json_str, "counter_04")
    assert "module counter_04" in res
    assert "assign q = 8'h0;" in res
    assert "endmodule" in res


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


