"""Generates the 10 canonical benchmark task definitions for Step 1."""
from __future__ import annotations

import json
from pathlib import Path

TASKS_DIR = Path("/home/mind/Desktop/AI/Mind-3.0/benchmarks/mind_baseline/tasks")
TASKS_DIR.mkdir(parents=True, exist_ok=True)

tasks = [
    # ── 1. Priority Encoder ───────────────────────────────────────────────
    {
        "task_id": "priority_encoder",
        "task_name": "8-to-3 Priority Encoder",
        "category": "Basic combinational/sequential logic",
        "module_name": "priority_encoder",
        "functional_spec": (
            "Implement a synthesizable 8-to-3 priority encoder in SystemVerilog.\n"
            "Ports:\n"
            "  input  wire [7:0] in\n"
            "  output reg  [2:0] out\n"
            "  output reg        valid\n"
            "Behavior:\n"
            "  The module inspects the 8-bit input 'in'. Bit 7 has the highest priority and bit 0 has the lowest priority.\n"
            "  'out' must encode the index of the highest-order '1' bit present in 'in'.\n"
            "  'valid' must be 1 whenever at least one bit of 'in' is 1.\n"
            "  If 'in' is all zeros (8'b00000000), 'valid' must be 0 and 'out' must be 3'b000.\n"
            "  The design must be purely combinational with zero inferred latches."
        ),
        "interface": {
            "ports": [
                {"name": "in", "direction": "input", "width": 8},
                {"name": "out", "direction": "output", "width": 3},
                {"name": "valid", "direction": "output", "width": 1}
            ]
        },
        "clock_reset_assumptions": "Pure combinational logic; no clock or reset required.",
        "expected_behavior": "out matches MSB index of in; valid is high iff in != 0.",
        "verification_strategy": "Exhaustive 256-vector simulation + Yosys latch check + SymbiYosys BMC.",
        "testbench_code": """`timescale 1ns/1ps
module tb_priority_encoder;
    reg [7:0] in;
    wire [2:0] out;
    wire valid;
    priority_encoder dut (.in(in), .out(out), .valid(valid));

    integer i;
    reg exp_valid;
    reg [2:0] exp_out;

    initial begin
        for (i = 0; i < 256; i = i + 1) begin
            in = i[7:0];
            #5;
            exp_valid = (in != 0);
            exp_out = 3'd0;
            if (in[7]) exp_out = 3'd7;
            else if (in[6]) exp_out = 3'd6;
            else if (in[5]) exp_out = 3'd5;
            else if (in[4]) exp_out = 3'd4;
            else if (in[3]) exp_out = 3'd3;
            else if (in[2]) exp_out = 3'd2;
            else if (in[1]) exp_out = 3'd1;
            else if (in[0]) exp_out = 3'd0;

            if (valid !== exp_valid || out !== exp_out) begin
                $display("FAIL: in=%b got valid=%b out=%b expected valid=%b out=%b",
                         in, valid, out, exp_valid, exp_out);
                $fatal(1);
            end
        end
        $display("ALL_TESTS_PASSED");
        $finish;
    end
endmodule
""",
        "sva_code": """module priority_encoder_formal(
    input wire [7:0] in
);
    wire [2:0] out;
    wire valid;
    priority_encoder dut (.in(in), .out(out), .valid(valid));

    always @(*) begin
        if (in == 8'b0) begin
            assert(!valid);
            assert(out == 3'b000);
        end else begin
            assert(valid);
        end
        if (in[7]) assert(out == 3'd7);
        else if (in[6]) assert(out == 3'd6);
        else if (in[5]) assert(out == 3'd5);
        else if (in[4]) assert(out == 3'd4);
        else if (in[3]) assert(out == 3'd3);
        else if (in[2]) assert(out == 3'd2);
        else if (in[1]) assert(out == 3'd1);
        else if (in[0]) assert(out == 3'd0);
    end
endmodule
""",
        "generation_prompt": (
            "Write a synthesizable 8-to-3 priority encoder in SystemVerilog.\n"
            "Module name: priority_encoder\n"
            "Ports:\n"
            "  input  wire [7:0] in,\n"
            "  output reg  [2:0] out,\n"
            "  output reg        valid\n"
            "Requirements:\n"
            "- Bit 7 has highest priority, bit 0 lowest priority.\n"
            "- 'out' encodes the index of the highest 1-bit.\n"
            "- 'valid' is 1 if any bit in 'in' is 1, otherwise 0.\n"
            "- When in == 8'b0, out must be 3'b000 and valid must be 1'b0.\n"
            "- Must be synthesizable with zero latches.\n"
            "Output only SystemVerilog code inside ```systemverilog ... ```."
        ),
        "repair_policy": "Maximum 3 repair turns; inject raw compiler/simulator diagnostics into prompt.",
        "timeout": 60
    },

    # ── 2. Gray Counter ───────────────────────────────────────────────────
    {
        "task_id": "gray_counter",
        "task_name": "4-bit Gray Code Counter",
        "category": "Basic combinational/sequential logic",
        "module_name": "gray_counter",
        "functional_spec": (
            "Implement a synthesizable 4-bit synchronous Gray code counter in SystemVerilog.\n"
            "Ports:\n"
            "  input  wire       clk\n"
            "  input  wire       rst_n\n"
            "  input  wire       enable\n"
            "  output reg  [3:0] gray_out\n"
            "Behavior:\n"
            "  Active-low synchronous or asynchronous reset 'rst_n' resets 'gray_out' to 4'b0000.\n"
            "  On each rising edge of 'clk', if 'enable' is high, the counter transitions to the next Gray code in the standard 16-state sequence:\n"
            "  0000 -> 0001 -> 0011 -> 0010 -> 0110 -> 0111 -> 0101 -> 0100 -> 1100 -> 1101 -> 1111 -> 1110 -> 1010 -> 1011 -> 1001 -> 1000 -> 0000.\n"
            "  If 'enable' is low, 'gray_out' holds its current value.\n"
            "  Exactly one bit must change on each count transition."
        ),
        "interface": {
            "ports": [
                {"name": "clk", "direction": "input", "width": 1},
                {"name": "rst_n", "direction": "input", "width": 1},
                {"name": "enable", "direction": "input", "width": 1},
                {"name": "gray_out", "direction": "output", "width": 4}
            ]
        },
        "clock_reset_assumptions": "Clock clk; active-low reset rst_n.",
        "expected_behavior": "gray_out advances by 1 Hamming distance per enabled clock cycle across 16 states.",
        "verification_strategy": "Cycle simulation through 32 cycles + Hamming distance check + SBY BMC.",
        "testbench_code": """`timescale 1ns/1ps
module tb_gray_counter;
    reg clk;
    reg rst_n;
    reg enable;
    wire [3:0] gray_out;

    gray_counter dut (
        .clk(clk),
        .rst_n(rst_n),
        .enable(enable),
        .gray_out(gray_out)
    );

    always #5 clk = ~clk;

    reg [3:0] seq [0:15];
    integer i, step;

    initial begin
        seq[0]=4'b0000; seq[1]=4'b0001; seq[2]=4'b0011; seq[3]=4'b0010;
        seq[4]=4'b0110; seq[5]=4'b0111; seq[6]=4'b0101; seq[7]=4'b0100;
        seq[8]=4'b1100; seq[9]=4'b1101; seq[10]=4'b1111; seq[11]=4'b1110;
        seq[12]=4'b1010; seq[13]=4'b1011; seq[14]=4'b1001; seq[15]=4'b1000;

        clk = 0;
        rst_n = 0;
        enable = 0;
        #20;
        rst_n = 1;
        #10;
        if (gray_out !== 4'b0000) begin
            $display("FAIL: Reset did not clear gray_out, got %b", gray_out);
            $fatal(1);
        end

        // Check hold when enable=0
        #20;
        if (gray_out !== 4'b0000) begin
            $display("FAIL: Counter changed while enable=0, got %b", gray_out);
            $fatal(1);
        end

        // Count through 32 cycles (2 full sequences)
        enable = 1;
        for (step = 0; step < 32; step = step + 1) begin
            @(posedge clk);
            #1;
            if (gray_out !== seq[(step + 1) % 16]) begin
                $display("FAIL: At step %0d, expected %b, got %b",
                         step, seq[(step + 1) % 16], gray_out);
                $fatal(1);
            end
        end

        $display("ALL_TESTS_PASSED");
        $finish;
    end
endmodule
""",
        "sva_code": """module gray_counter_formal(
    input wire clk,
    input wire rst_n,
    input wire enable
);
    wire [3:0] gray_out;
    gray_counter dut (.clk(clk), .rst_n(rst_n), .enable(enable), .gray_out(gray_out));

    always @(posedge clk) begin
        if (!rst_n) begin
            assert(gray_out == 4'b0000);
        end else if ($past(!rst_n)) begin
            assert(gray_out == 4'b0000);
        end else if ($past(enable)) begin
            assert($onehot(gray_out ^ $past(gray_out)));
        end else begin
            assert(gray_out == $past(gray_out));
        end
    end
endmodule
""",
        "generation_prompt": (
            "Write a synthesizable 4-bit synchronous Gray code counter in SystemVerilog.\n"
            "Module name: gray_counter\n"
            "Ports:\n"
            "  input  wire       clk,\n"
            "  input  wire       rst_n,\n"
            "  input  wire       enable,\n"
            "  output reg  [3:0] gray_out\n"
            "Requirements:\n"
            "- Active-low reset 'rst_n' clears 'gray_out' to 4'b0000.\n"
            "- When enable is 1 on rising clock, advances through the 16-step Gray code sequence.\n"
            "- Sequence: 0000, 0001, 0011, 0010, 0110, 0111, 0101, 0100, 1100, 1101, 1111, 1110, 1010, 1011, 1001, 1000, wrap to 0000.\n"
            "- When enable is 0, holds value.\n"
            "Output only SystemVerilog code inside ```systemverilog ... ```."
        ),
        "repair_policy": "Maximum 3 repair turns; inject raw compiler/simulator diagnostics into prompt.",
        "timeout": 60
    },

    # ── 3. Signed Multiplier ──────────────────────────────────────────────
    {
        "task_id": "signed_multiplier",
        "task_name": "8-bit Signed Multiplier",
        "category": "Arithmetic",
        "module_name": "signed_multiplier",
        "functional_spec": (
            "Implement a synthesizable 8-bit signed two's complement multiplier in SystemVerilog.\n"
            "Ports:\n"
            "  input  wire signed [7:0]  a\n"
            "  input  wire signed [7:0]  b\n"
            "  output wire signed [15:0] p\n"
            "Behavior:\n"
            "  Computes the 16-bit signed two's complement product p = a * b.\n"
            "  Must correctly handle full signed range from -128 to +127.\n"
            "  Corner cases: -128 * -128 = 16384 (16'h4000), -128 * 127 = -16256, 127 * 127 = 16129, 0 * x = 0.\n"
            "  Pure combinational implementation."
        ),
        "interface": {
            "ports": [
                {"name": "a", "direction": "input", "width": 8},
                {"name": "b", "direction": "input", "width": 8},
                {"name": "p", "direction": "output", "width": 16}
            ]
        },
        "clock_reset_assumptions": "Combinational logic; no clock or reset.",
        "expected_behavior": "p equals signed two's complement product of a and b across full dynamic range.",
        "verification_strategy": "Exhaustive corner cases + 500 random vectors + SBY formal equivalence.",
        "testbench_code": """`timescale 1ns/1ps
module tb_signed_multiplier;
    reg signed [7:0] a;
    reg signed [7:0] b;
    wire signed [15:0] p;

    signed_multiplier dut (.a(a), .b(b), .p(p));

    integer i, j;
    reg signed [15:0] exp_p;

    initial begin
        // Corner cases
        reg signed [7:0] test_vals [0:7];
        test_vals[0] = -128; test_vals[1] = -127; test_vals[2] = -1;
        test_vals[3] = 0;    test_vals[4] = 1;    test_vals[5] = 2;
        test_vals[6] = 126;  test_vals[7] = 127;

        for (i = 0; i < 8; i = i + 1) begin
            for (j = 0; j < 8; j = j + 1) begin
                a = test_vals[i];
                b = test_vals[j];
                #5;
                exp_p = a * b;
                if (p !== exp_p) begin
                    $display("FAIL: %0d * %0d: got %0d, expected %0d", a, b, p, exp_p);
                    $fatal(1);
                end
            end
        end

        // Random tests
        for (i = 0; i < 500; i = i + 1) begin
            a = $random;
            b = $random;
            #5;
            exp_p = a * b;
            if (p !== exp_p) begin
                $display("FAIL: Random test %0d: %0d * %0d got %0d, exp %0d", i, a, b, p, exp_p);
                $fatal(1);
            end
        end

        $display("ALL_TESTS_PASSED");
        $finish;
    end
endmodule
""",
        "sva_code": """module signed_multiplier_formal(
    input wire signed [7:0] a,
    input wire signed [7:0] b
);
    wire signed [15:0] p;
    signed_multiplier dut (.a(a), .b(b), .p(p));

    always @(*) begin
        assert(p == a * b);
    end
endmodule
""",
        "generation_prompt": (
            "Write a synthesizable 8-bit signed two's complement multiplier in SystemVerilog.\n"
            "Module name: signed_multiplier\n"
            "Ports:\n"
            "  input  wire signed [7:0]  a,\n"
            "  input  wire signed [7:0]  b,\n"
            "  output wire signed [15:0] p\n"
            "Requirements:\n"
            "- Computes the signed product p = a * b.\n"
            "- Full signed two's complement support (-128 to +127).\n"
            "- Combinational logic, zero latches.\n"
            "Output only SystemVerilog code inside ```systemverilog ... ```."
        ),
        "repair_policy": "Maximum 3 repair turns; inject raw compiler/simulator diagnostics into prompt.",
        "timeout": 60
    },

    # ── 4. Pipelined Adder ────────────────────────────────────────────────
    {
        "task_id": "pipelined_adder",
        "task_name": "32-bit Pipelined Adder (2 Stages)",
        "category": "Arithmetic",
        "module_name": "pipelined_adder",
        "functional_spec": (
            "Implement a synthesizable 32-bit 2-stage pipelined adder in SystemVerilog.\n"
            "Ports:\n"
            "  input  wire        clk\n"
            "  input  wire        rst_n\n"
            "  input  wire        valid_in\n"
            "  input  wire [31:0] a\n"
            "  input  wire [31:0] b\n"
            "  output reg  [31:0] sum\n"
            "  output reg         carry_out\n"
            "  output reg         valid_out\n"
            "Behavior:\n"
            "  Stage 1: Adds lower 16 bits {c1, sum_lo} = a[15:0] + b[15:0], registers upper halves a[31:16], b[31:16], c1, sum_lo, and propagates valid_in.\n"
            "  Stage 2: Adds upper 16 bits with carry {carry_out, sum[31:16]} = a_hi + b_hi + c1, registers sum[15:0] = sum_lo, and outputs valid_out.\n"
            "  Latency from valid_in to valid_out is exactly 2 clock cycles.\n"
            "  Active-low synchronous or asynchronous reset 'rst_n' clears all pipeline registers, clearing sum, carry_out, and valid_out."
        ),
        "interface": {
            "ports": [
                {"name": "clk", "direction": "input", "width": 1},
                {"name": "rst_n", "direction": "input", "width": 1},
                {"name": "valid_in", "direction": "input", "width": 1},
                {"name": "a", "direction": "input", "width": 32},
                {"name": "b", "direction": "input", "width": 32},
                {"name": "sum", "direction": "output", "width": 32},
                {"name": "carry_out", "direction": "output", "width": 1},
                {"name": "valid_out", "direction": "output", "width": 1}
            ]
        },
        "clock_reset_assumptions": "Clock clk; active-low reset rst_n.",
        "expected_behavior": "sum and carry_out produce a + b with 2-cycle fixed latency and valid_out tracking.",
        "verification_strategy": "Cycle simulation with carry across stage boundary + back-to-back additions + SBY BMC.",
        "testbench_code": """`timescale 1ns/1ps
module tb_pipelined_adder;
    reg clk;
    reg rst_n;
    reg valid_in;
    reg [31:0] a;
    reg [31:0] b;
    wire [31:0] sum;
    wire carry_out;
    wire valid_out;

    pipelined_adder dut (
        .clk(clk),
        .rst_n(rst_n),
        .valid_in(valid_in),
        .a(a),
        .b(b),
        .sum(sum),
        .carry_out(carry_out),
        .valid_out(valid_out)
    );

    always #5 clk = ~clk;

    reg [31:0] exp_a [0:99];
    reg [31:0] exp_b [0:99];
    reg [32:0] exp_res [0:99];
    integer i;

    initial begin
        clk = 0;
        rst_n = 0;
        valid_in = 0;
        a = 0;
        b = 0;
        #20;
        rst_n = 1;
        #10;

        for (i = 0; i < 50; i = i + 1) begin
            @(posedge clk);
            valid_in = 1;
            if (i == 0) begin
                a = 32'h0000_FFFF; b = 32'h0000_0001;
            end else if (i == 1) begin
                a = 32'hFFFF_FFFF; b = 32'h0000_0001;
            end else begin
                a = $random; b = $random;
            end
            exp_a[i] = a;
            exp_b[i] = b;
            exp_res[i] = {1'b0, a} + {1'b0, b};
        end

        @(posedge clk);
        valid_in = 0;

        for (i = 0; i < 50; i = i + 1) begin
            @(posedge clk);
            #1;
            if (i >= 1) begin
                integer chk;
                chk = i - 1;
                if (valid_out !== 1'b1) begin
                    $display("FAIL: valid_out not asserted for item %0d", chk);
                    $fatal(1);
                end
                if ({carry_out, sum} !== exp_res[chk]) begin
                    $display("FAIL: %0h + %0h: got {c,s}=%0h, expected %0h",
                             exp_a[chk], exp_b[chk], {carry_out, sum}, exp_res[chk]);
                    $fatal(1);
                end
            end
        end

        $display("ALL_TESTS_PASSED");
        $finish;
    end
endmodule
""",
        "sva_code": """module pipelined_adder_formal(
    input wire clk,
    input wire rst_n,
    input wire valid_in,
    input wire [31:0] a,
    input wire [31:0] b
);
    wire [31:0] sum;
    wire carry_out;
    wire valid_out;

    pipelined_adder dut (
        .clk(clk),
        .rst_n(rst_n),
        .valid_in(valid_in),
        .a(a),
        .b(b),
        .sum(sum),
        .carry_out(carry_out),
        .valid_out(valid_out)
    );

    reg [32:0] expected_sum_d1;
    reg [32:0] expected_sum_d2;
    reg v_d1, v_d2;

    always @(posedge clk) begin
        if (!rst_n) begin
            v_d1 <= 0;
            v_d2 <= 0;
        end else begin
            v_d1 <= valid_in;
            v_d2 <= v_d1;
            expected_sum_d1 <= {1'b0, a} + {1'b0, b};
            expected_sum_d2 <= expected_sum_d1;
            if (v_d2) begin
                assert(valid_out == 1'b1);
                assert({carry_out, sum} == expected_sum_d2);
            end
        end
    end
endmodule
""",
        "generation_prompt": (
            "Write a synthesizable 32-bit 2-stage pipelined adder in SystemVerilog.\n"
            "Module name: pipelined_adder\n"
            "Ports:\n"
            "  input  wire        clk,\n"
            "  input  wire        rst_n,\n"
            "  input  wire        valid_in,\n"
            "  input  wire [31:0] a,\n"
            "  input  wire [31:0] b,\n"
            "  output reg  [31:0] sum,\n"
            "  output reg         carry_out,\n"
            "  output reg         valid_out\n"
            "Requirements:\n"
            "- 2 pipeline stages: Stage 1 sums lower 16 bits with carry out; Stage 2 sums upper 16 bits with carry.\n"
            "- Exact 2-cycle latency from valid_in to valid_out.\n"
            "- Active-low reset rst_n clears all pipeline registers.\n"
            "Output only SystemVerilog code inside ```systemverilog ... ```."
        ),
        "repair_policy": "Maximum 3 repair turns; inject raw compiler/simulator diagnostics into prompt.",
        "timeout": 60
    },

    # ── 5. Traffic Light Controller ───────────────────────────────────────
    {
        "task_id": "traffic_light_controller",
        "task_name": "Traffic Light Controller FSM",
        "category": "FSM/control",
        "module_name": "traffic_light_controller",
        "functional_spec": (
            "Implement a synthesizable traffic light controller FSM in SystemVerilog.\n"
            "Ports:\n"
            "  input  wire       clk\n"
            "  input  wire       rst_n\n"
            "  input  wire       car_side\n"
            "  output reg  [1:0] light_main\n"
            "  output reg  [1:0] light_side\n"
            "Light Encoding:\n"
            "  2'b00: RED\n"
            "  2'b01: YELLOW\n"
            "  2'b10: GREEN\n"
            "FSM Specification:\n"
            "  State S_MAIN_GREEN (0): Main is GREEN (2'b10), Side is RED (2'b00). Must stay at least 4 cycles. If car_side=1 after 4 cycles, transition to S_MAIN_YELLOW.\n"
            "  State S_MAIN_YELLOW (1): Main is YELLOW (2'b01), Side is RED (2'b00). Stays exactly 2 cycles, then transitions to S_SIDE_GREEN.\n"
            "  State S_SIDE_GREEN (2): Main is RED (2'b00), Side is GREEN (2'b10). Stays for 4 cycles (or transitions early after min 2 cycles if car_side=0), then transitions to S_SIDE_YELLOW.\n"
            "  State S_SIDE_YELLOW (3): Main is RED (2'b00), Side is YELLOW (2'b01). Stays exactly 2 cycles, then transitions to S_MAIN_GREEN.\n"
            "  Safety Invariant: light_main and light_side must NEVER both be GREEN or YELLOW simultaneously. When one is GREEN or YELLOW, the other MUST be RED."
        ),
        "interface": {
            "ports": [
                {"name": "clk", "direction": "input", "width": 1},
                {"name": "rst_n", "direction": "input", "width": 1},
                {"name": "car_side", "direction": "input", "width": 1},
                {"name": "light_main", "direction": "output", "width": 2},
                {"name": "light_side", "direction": "output", "width": 2}
            ]
        },
        "clock_reset_assumptions": "Clock clk; active-low reset rst_n.",
        "expected_behavior": "FSM sequences lights without collision; respects minimum green/yellow timers.",
        "verification_strategy": "Cycle simulation through multiple sensor scenarios + SBY BMC mutual exclusion check.",
        "testbench_code": """`timescale 1ns/1ps
module tb_traffic_light_controller;
    reg clk;
    reg rst_n;
    reg car_side;
    wire [1:0] light_main;
    wire [1:0] light_side;

    traffic_light_controller dut (
        .clk(clk),
        .rst_n(rst_n),
        .car_side(car_side),
        .light_main(light_main),
        .light_side(light_side)
    );

    always #5 clk = ~clk;

    integer cycle;

    always @(posedge clk) begin
        if (rst_n) begin
            if (light_main != 2'b00 && light_side != 2'b00) begin
                $display("FAIL: Mutual exclusion breached: main=%b, side=%b at cycle %0d",
                         light_main, light_side, cycle);
                $fatal(1);
            end
        end
    end

    initial begin
        clk = 0;
        rst_n = 0;
        car_side = 0;
        cycle = 0;
        #20;
        rst_n = 1;

        for (cycle = 0; cycle < 10; cycle = cycle + 1) begin
            @(posedge clk);
            #1;
            if (light_main !== 2'b10 || light_side !== 2'b00) begin
                $display("FAIL: Expected Main GREEN, Side RED with no car, got main=%b, side=%b",
                         light_main, light_side);
                $fatal(1);
            end
        end

        car_side = 1;
        while (light_main == 2'b10) @(posedge clk);
        #1;
        if (light_main !== 2'b01 || light_side !== 2'b00) begin
            $display("FAIL: Expected Main YELLOW, Side RED, got main=%b, side=%b", light_main, light_side);
            $fatal(1);
        end

        while (light_main == 2'b01) @(posedge clk);
        #1;
        if (light_main !== 2'b00 || light_side !== 2'b10) begin
            $display("FAIL: Expected Main RED, Side GREEN, got main=%b, side=%b", light_main, light_side);
            $fatal(1);
        end

        while (light_side == 2'b10) @(posedge clk);
        #1;
        if (light_main !== 2'b00 || light_side !== 2'b01) begin
            $display("FAIL: Expected Main RED, Side YELLOW, got main=%b, side=%b", light_main, light_side);
            $fatal(1);
        end

        while (light_side == 2'b01) @(posedge clk);
        #1;
        if (light_main !== 2'b10 || light_side !== 2'b00) begin
            $display("FAIL: Expected return to Main GREEN, got main=%b, side=%b", light_main, light_side);
            $fatal(1);
        end

        $display("ALL_TESTS_PASSED");
        $finish;
    end
endmodule
""",
        "sva_code": """module traffic_light_controller_formal(
    input wire clk,
    input wire rst_n,
    input wire car_side
);
    wire [1:0] light_main;
    wire [1:0] light_side;

    traffic_light_controller dut (
        .clk(clk),
        .rst_n(rst_n),
        .car_side(car_side),
        .light_main(light_main),
        .light_side(light_side)
    );

    always @(posedge clk) begin
        if (rst_n) begin
            assert(!(light_main != 2'b00 && light_side != 2'b00));
        end
    end
endmodule
""",
        "generation_prompt": (
            "Write a synthesizable traffic light controller FSM in SystemVerilog.\n"
            "Module name: traffic_light_controller\n"
            "Ports:\n"
            "  input  wire       clk,\n"
            "  input  wire       rst_n,\n"
            "  input  wire       car_side,\n"
            "  output reg  [1:0] light_main,\n"
            "  output reg  [1:0] light_side\n"
            "Light encodings: 2'b00=RED, 2'b01=YELLOW, 2'b10=GREEN.\n"
            "States:\n"
            "1. S_MAIN_GREEN: Main=GREEN, Side=RED. Minimum 4 cycles. If car_side=1 after 4 cycles, goto S_MAIN_YELLOW.\n"
            "2. S_MAIN_YELLOW: Main=YELLOW, Side=RED. Exactly 2 cycles. Then goto S_SIDE_GREEN.\n"
            "3. S_SIDE_GREEN: Main=RED, Side=GREEN. Stays 4 cycles (or exits if car_side=0 after 2 cycles). Then goto S_SIDE_YELLOW.\n"
            "4. S_SIDE_YELLOW: Main=RED, Side=YELLOW. Exactly 2 cycles. Then goto S_MAIN_GREEN.\n"
            "Safety rule: light_main and light_side must NEVER both be non-red simultaneously!\n"
            "Output only SystemVerilog code inside ```systemverilog ... ```."
        ),
        "repair_policy": "Maximum 3 repair turns; inject raw compiler/simulator diagnostics into prompt.",
        "timeout": 60
    },

    # ── 6. Packet Frame Parser ────────────────────────────────────────────
    {
        "task_id": "packet_frame_parser",
        "task_name": "Packet Frame Parser FSM",
        "category": "FSM/control",
        "module_name": "packet_frame_parser",
        "functional_spec": (
            "Implement a synthesizable packet frame parser FSM in SystemVerilog.\n"
            "Ports:\n"
            "  input  wire       clk\n"
            "  input  wire       rst_n\n"
            "  input  wire       valid_in\n"
            "  input  wire [7:0] data_in\n"
            "  output reg        frame_valid\n"
            "  output reg  [7:0] payload_byte\n"
            "  output reg        payload_valid\n"
            "  output reg        frame_error\n"
            "Frame Protocol:\n"
            "  1. Start of Frame (SOF): 8'hA5\n"
            "  2. Length byte (L): 1 to 8 (valid payload length)\n"
            "  3. Payload bytes: Exactly L bytes. On each payload byte when valid_in=1, emit payload_byte = data_in and payload_valid = 1.\n"
            "  4. End of Frame (EOF): 8'h5A immediately following the last payload byte. When EOF matches, assert frame_valid=1 for 1 cycle.\n"
            "  Error Handling:\n"
            "  - In IDLE: any valid_in != 8'hA5 asserts frame_error=1 for 1 cycle.\n"
            "  - In LENGTH: if data_in == 0 or data_in > 8, asserts frame_error=1 and returns to IDLE.\n"
            "  - In EOF: if data_in != 8'h5A, asserts frame_error=1 and returns to IDLE."
        ),
        "interface": {
            "ports": [
                {"name": "clk", "direction": "input", "width": 1},
                {"name": "rst_n", "direction": "input", "width": 1},
                {"name": "valid_in", "direction": "input", "width": 1},
                {"name": "data_in", "direction": "input", "width": 8},
                {"name": "frame_valid", "direction": "output", "width": 1},
                {"name": "payload_byte", "direction": "output", "width": 8},
                {"name": "payload_valid", "direction": "output", "width": 1},
                {"name": "frame_error", "direction": "output", "width": 1}
            ]
        },
        "clock_reset_assumptions": "Clock clk; active-low reset rst_n.",
        "expected_behavior": "Extracts payload bytes and emits frame_valid on correct EOF; flags errors on invalid bytes.",
        "verification_strategy": "Cycle simulation with valid packets, invalid SOF, corrupt EOF, variable lengths + SBY BMC.",
        "testbench_code": """`timescale 1ns/1ps
module tb_packet_frame_parser;
    reg clk;
    reg rst_n;
    reg valid_in;
    reg [7:0] data_in;
    wire frame_valid;
    wire [7:0] payload_byte;
    wire payload_valid;
    wire frame_error;

    packet_frame_parser dut (
        .clk(clk),
        .rst_n(rst_n),
        .valid_in(valid_in),
        .data_in(data_in),
        .frame_valid(frame_valid),
        .payload_byte(payload_byte),
        .payload_valid(payload_valid),
        .frame_error(frame_error)
    );

    always #5 clk = ~clk;

    task send_byte(input [7:0] b);
        begin
            @(posedge clk);
            valid_in = 1;
            data_in = b;
            @(posedge clk);
            valid_in = 0;
            data_in = 0;
        end
    endtask

    integer received_payloads;
    reg [7:0] rx_buf [0:15];

    always @(posedge clk) begin
        if (payload_valid) begin
            rx_buf[received_payloads] <= payload_byte;
            received_payloads <= received_payloads + 1;
        end
    end

    initial begin
        clk = 0;
        rst_n = 0;
        valid_in = 0;
        data_in = 0;
        received_payloads = 0;
        #20;
        rst_n = 1;
        #10;

        send_byte(8'hA5);
        send_byte(8'h03);
        send_byte(8'h11);
        send_byte(8'h22);
        send_byte(8'h33);
        send_byte(8'h5A);
        #1;
        if (!frame_valid) begin
            $display("FAIL: Test 1: frame_valid not asserted on valid EOF");
            $fatal(1);
        end
        if (received_payloads !== 3 || rx_buf[0] !== 8'h11 || rx_buf[1] !== 8'h22 || rx_buf[2] !== 8'h33) begin
            $display("FAIL: Test 1: incorrect payload received");
            $fatal(1);
        end

        send_byte(8'hFF);
        #1;
        if (!frame_error) begin
            $display("FAIL: Test 2: frame_error not asserted on invalid SOF");
            $fatal(1);
        end

        send_byte(8'hA5);
        send_byte(8'h02);
        send_byte(8'hAA);
        send_byte(8'hBB);
        send_byte(8'hEE);
        #1;
        if (!frame_error) begin
            $display("FAIL: Test 3: frame_error not asserted on corrupt EOF");
            $fatal(1);
        end

        $display("ALL_TESTS_PASSED");
        $finish;
    end
endmodule
""",
        "sva_code": """module packet_frame_parser_formal(
    input wire clk,
    input wire rst_n,
    input wire valid_in,
    input wire [7:0] data_in
);
    wire frame_valid;
    wire [7:0] payload_byte;
    wire payload_valid;
    wire frame_error;

    packet_frame_parser dut (
        .clk(clk),
        .rst_n(rst_n),
        .valid_in(valid_in),
        .data_in(data_in),
        .frame_valid(frame_valid),
        .payload_byte(payload_byte),
        .payload_valid(payload_valid),
        .frame_error(frame_error)
    );

    always @(posedge clk) begin
        if (!rst_n) begin
            assert(!frame_valid);
            assert(!payload_valid);
            assert(!frame_error);
        end
    end
endmodule
""",
        "generation_prompt": (
            "Write a synthesizable packet frame parser FSM in SystemVerilog.\n"
            "Module name: packet_frame_parser\n"
            "Ports:\n"
            "  input  wire       clk,\n"
            "  input  wire       rst_n,\n"
            "  input  wire       valid_in,\n"
            "  input  wire [7:0] data_in,\n"
            "  output reg        frame_valid,\n"
            "  output reg  [7:0] payload_byte,\n"
            "  output reg        payload_valid,\n"
            "  output reg        frame_error\n"
            "Protocol:\n"
            "- SOF: 8'hA5\n"
            "- LEN: 1 to 8 bytes\n"
            "- PAYLOAD: LEN bytes (emit on payload_byte with payload_valid=1)\n"
            "- EOF: 8'h5A (assert frame_valid=1 for 1 cycle)\n"
            "- Error: if invalid byte, assert frame_error=1 for 1 cycle and reset to IDLE.\n"
            "Output only SystemVerilog code inside ```systemverilog ... ```."
        ),
        "repair_policy": "Maximum 3 repair turns; inject raw compiler/simulator diagnostics into prompt.",
        "timeout": 60
    },

    # ── 7. Synchronous FIFO ───────────────────────────────────────────────
    {
        "task_id": "sync_fifo",
        "task_name": "Synchronous FIFO with Full/Empty Flags",
        "category": "Memory/interface",
        "module_name": "sync_fifo",
        "functional_spec": (
            "Implement a synthesizable synchronous circular FIFO in SystemVerilog.\n"
            "Parameters:\n"
            "  DATA_WIDTH = 8\n"
            "  DEPTH = 8\n"
            "Ports:\n"
            "  input  wire                  clk\n"
            "  input  wire                  rst_n\n"
            "  input  wire                  wr_en\n"
            "  input  wire [DATA_WIDTH-1:0] wr_data\n"
            "  input  wire                  rd_en\n"
            "  output reg  [DATA_WIDTH-1:0] rd_data\n"
            "  output wire                  full\n"
            "  output wire                  empty\n"
            "  output wire [3:0]            count\n"
            "Behavior:\n"
            "  Reset rst_n=0 clears count to 0, empty=1, full=0.\n"
            "  Write: when wr_en && !full, write wr_data into memory and increment count.\n"
            "  Read: when rd_en && !empty, read oldest data into rd_data and decrement count.\n"
            "  Simultaneous read and write when not empty and not full: writes new data, reads oldest data, count remains unchanged.\n"
            "  When full, ignore writes unless a valid read occurs simultaneously.\n"
            "  When empty, ignore reads."
        ),
        "interface": {
            "ports": [
                {"name": "clk", "direction": "input", "width": 1},
                {"name": "rst_n", "direction": "input", "width": 1},
                {"name": "wr_en", "direction": "input", "width": 1},
                {"name": "wr_data", "direction": "input", "width": 8},
                {"name": "rd_en", "direction": "input", "width": 1},
                {"name": "rd_data", "direction": "output", "width": 8},
                {"name": "full", "direction": "output", "width": 1},
                {"name": "empty", "direction": "output", "width": 1},
                {"name": "count", "direction": "output", "width": 4}
            ]
        },
        "clock_reset_assumptions": "Clock clk; active-low reset rst_n.",
        "expected_behavior": "Strict first-in-first-out delivery, accurate full/empty generation, overflow/underflow protection.",
        "verification_strategy": "Cycle simulation: fill to full, overflow attempt, drain to empty, underflow attempt, simultaneous rw + SBY BMC.",
        "testbench_code": """`timescale 1ns/1ps
module tb_sync_fifo;
    reg clk;
    reg rst_n;
    reg wr_en;
    reg [7:0] wr_data;
    reg rd_en;
    wire [7:0] rd_data;
    wire full;
    wire empty;
    wire [3:0] count;

    sync_fifo dut (
        .clk(clk),
        .rst_n(rst_n),
        .wr_en(wr_en),
        .wr_data(wr_data),
        .rd_en(rd_en),
        .rd_data(rd_data),
        .full(full),
        .empty(empty),
        .count(count)
    );

    always #5 clk = ~clk;

    integer i;

    initial begin
        clk = 0;
        rst_n = 0;
        wr_en = 0;
        rd_en = 0;
        wr_data = 0;
        #20;
        rst_n = 1;
        #10;

        if (!empty || full || count !== 0) begin
            $display("FAIL: FIFO not empty on reset");
            $fatal(1);
        end

        for (i = 0; i < 8; i = i + 1) begin
            @(posedge clk);
            wr_en = 1;
            wr_data = 8'h10 + i;
        end
        @(posedge clk);
        wr_en = 0;
        #1;
        if (!full || empty || count !== 8) begin
            $display("FAIL: FIFO not full after 8 writes: full=%b empty=%b count=%0d", full, empty, count);
            $fatal(1);
        end

        @(posedge clk);
        wr_en = 1;
        wr_data = 8'hFF;
        @(posedge clk);
        wr_en = 0;
        #1;
        if (count !== 8) begin
            $display("FAIL: Overflow write modified count: %0d", count);
            $fatal(1);
        end

        for (i = 0; i < 8; i = i + 1) begin
            @(posedge clk);
            rd_en = 1;
            @(posedge clk);
            rd_en = 0;
            #1;
            if (rd_data !== (8'h10 + i)) begin
                $display("FAIL: Read mismatch at %0d: got %h expected %h", i, rd_data, 8'h10 + i);
                $fatal(1);
            end
        end

        if (!empty || full || count !== 0) begin
            $display("FAIL: FIFO not empty after 8 reads");
            $fatal(1);
        end

        $display("ALL_TESTS_PASSED");
        $finish;
    end
endmodule
""",
        "sva_code": """module sync_fifo_formal(
    input wire clk,
    input wire rst_n,
    input wire wr_en,
    input wire [7:0] wr_data,
    input wire rd_en
);
    wire [7:0] rd_data;
    wire full, empty;
    wire [3:0] count;

    sync_fifo dut (
        .clk(clk),
        .rst_n(rst_n),
        .wr_en(wr_en),
        .wr_data(wr_data),
        .rd_en(rd_en),
        .rd_data(rd_data),
        .full(full),
        .empty(empty),
        .count(count)
    );

    always @(posedge clk) begin
        if (rst_n) begin
            assert(empty == (count == 0));
            assert(full == (count == 8));
            assert(!(full && empty));
            assert(count <= 8);
        end
    end
endmodule
""",
        "generation_prompt": (
            "Write a synthesizable synchronous circular FIFO in SystemVerilog.\n"
            "Module name: sync_fifo\n"
            "Parameters: DATA_WIDTH = 8, DEPTH = 8\n"
            "Ports:\n"
            "  input  wire                  clk,\n"
            "  input  wire                  rst_n,\n"
            "  input  wire                  wr_en,\n"
            "  input  wire [DATA_WIDTH-1:0] wr_data,\n"
            "  input  wire                  rd_en,\n"
            "  output reg  [DATA_WIDTH-1:0] rd_data,\n"
            "  output wire                  full,\n"
            "  output wire                  empty,\n"
            "  output wire [3:0]            count\n"
            "Requirements:\n"
            "- Circular pointer or counter implementation.\n"
            "- empty = (count == 0), full = (count == DEPTH).\n"
            "- Ignore writes when full, ignore reads when empty.\n"
            "- Support simultaneous read and write.\n"
            "Output only SystemVerilog code inside ```systemverilog ... ```."
        ),
        "repair_policy": "Maximum 3 repair turns; inject raw compiler/simulator diagnostics into prompt.",
        "timeout": 60
    },

    # ── 8. SPI Master Controller ──────────────────────────────────────────
    {
        "task_id": "spi_master",
        "task_name": "SPI Master Controller (Mode 0)",
        "category": "Memory/interface",
        "module_name": "spi_master",
        "functional_spec": (
            "Implement a synthesizable SPI Master controller in SystemVerilog (Mode 0: CPOL=0, CPHA=0).\n"
            "Ports:\n"
            "  input  wire       clk\n"
            "  input  wire       rst_n\n"
            "  input  wire       start\n"
            "  input  wire [7:0] tx_data\n"
            "  input  wire       miso\n"
            "  output reg  [7:0] rx_data\n"
            "  output reg        busy\n"
            "  output reg        done\n"
            "  output reg        sclk\n"
            "  output reg        cs_n\n"
            "  output reg        mosi\n"
            "Behavior:\n"
            "  Mode 0: sclk is idle low (CPOL=0). Data shifted out MSB first on falling edges (or before first rising edge), sampled on rising edges (CPHA=0).\n"
            "  When idle, cs_n=1, sclk=0, busy=0, done=0, mosi=0.\n"
            "  On 'start' when !busy, asserts busy=1, drops cs_n=0, and begins transmitting the 8 bits of tx_data.\n"
            "  Divides system clk by at least 2 or 4 to generate sclk pulses.\n"
            "  After shifting 8 bits and sampling 8 bits from miso into rx_data, cs_n returns high, busy goes low, and done pulses high for 1 cycle."
        ),
        "interface": {
            "ports": [
                {"name": "clk", "direction": "input", "width": 1},
                {"name": "rst_n", "direction": "input", "width": 1},
                {"name": "start", "direction": "input", "width": 1},
                {"name": "tx_data", "direction": "input", "width": 8},
                {"name": "miso", "direction": "input", "width": 1},
                {"name": "rx_data", "direction": "output", "width": 8},
                {"name": "busy", "direction": "output", "width": 1},
                {"name": "done", "direction": "output", "width": 1},
                {"name": "sclk", "direction": "output", "width": 1},
                {"name": "cs_n", "direction": "output", "width": 1},
                {"name": "mosi", "direction": "output", "width": 1}
            ]
        },
        "clock_reset_assumptions": "Clock clk; active-low reset rst_n.",
        "expected_behavior": "Transmits 8-bit word MSB-first in Mode 0; generates 8 sclk pulses; asserts done.",
        "verification_strategy": "Cycle simulation with loopback miso = ~mosi; checks 8 sclk edges and byte latching + SBY BMC.",
        "testbench_code": """`timescale 1ns/1ps
module tb_spi_master;
    reg clk;
    reg rst_n;
    reg start;
    reg [7:0] tx_data;
    wire miso;
    wire [7:0] rx_data;
    wire busy;
    wire done;
    wire sclk;
    wire cs_n;
    wire mosi;

    assign miso = ~mosi;

    spi_master dut (
        .clk(clk),
        .rst_n(rst_n),
        .start(start),
        .tx_data(tx_data),
        .miso(miso),
        .rx_data(rx_data),
        .busy(busy),
        .done(done),
        .sclk(sclk),
        .cs_n(cs_n),
        .mosi(mosi)
    );

    always #5 clk = ~clk;

    initial begin
        clk = 0;
        rst_n = 0;
        start = 0;
        tx_data = 0;
        #20;
        rst_n = 1;
        #10;

        if (busy || cs_n !== 1 || sclk !== 0) begin
            $display("FAIL: SPI Master not idle on reset: busy=%b cs_n=%b sclk=%b", busy, cs_n, sclk);
            $fatal(1);
        end

        @(posedge clk);
        start = 1;
        tx_data = 8'hA5;
        @(posedge clk);
        start = 0;

        while (!done) @(posedge clk);
        #1;
        if (rx_data !== 8'h5A) begin
            $display("FAIL: rx_data mismatch: got %h, expected %h", rx_data, 8'h5A);
            $fatal(1);
        end
        if (cs_n !== 1) begin
            $display("FAIL: cs_n did not return high after transfer");
            $fatal(1);
        end

        $display("ALL_TESTS_PASSED");
        $finish;
    end
endmodule
""",
        "sva_code": """module spi_master_formal(
    input wire clk,
    input wire rst_n,
    input wire start,
    input wire [7:0] tx_data,
    input wire miso
);
    wire [7:0] rx_data;
    wire busy, done, sclk, cs_n, mosi;

    spi_master dut (
        .clk(clk),
        .rst_n(rst_n),
        .start(start),
        .tx_data(tx_data),
        .miso(miso),
        .rx_data(rx_data),
        .busy(busy),
        .done(done),
        .sclk(sclk),
        .cs_n(cs_n),
        .mosi(mosi)
    );

    always @(posedge clk) begin
        if (rst_n) begin
            if (!busy) begin
                assert(cs_n == 1'b1);
                assert(sclk == 1'b0);
            end
        end
    end
endmodule
""",
        "generation_prompt": (
            "Write a synthesizable SPI Master controller in SystemVerilog (Mode 0: CPOL=0, CPHA=0).\n"
            "Module name: spi_master\n"
            "Ports:\n"
            "  input  wire       clk,\n"
            "  input  wire       rst_n,\n"
            "  input  wire       start,\n"
            "  input  wire [7:0] tx_data,\n"
            "  input  wire       miso,\n"
            "  output reg  [7:0] rx_data,\n"
            "  output reg        busy,\n"
            "  output reg        done,\n"
            "  output reg        sclk,\n"
            "  output reg        cs_n,\n"
            "  output reg        mosi\n"
            "Requirements:\n"
            "- Mode 0: sclk is idle low (CPOL=0), shift on falling edge, sample on rising edge (CPHA=0).\n"
            "- Divides clk by 2 or 4 to produce sclk.\n"
            "- On 'start', lowers cs_n=0, raises busy=1, transmits 8 bits MSB first, samples miso into rx_data.\n"
            "- When done, raises cs_n=1, lowers busy=0, pulses done=1 for 1 cycle.\n"
            "Output only SystemVerilog code inside ```systemverilog ... ```."
        ),
        "repair_policy": "Maximum 3 repair turns; inject raw compiler/simulator diagnostics into prompt.",
        "timeout": 60
    },

    # ── 9. Two-Phase Handshake ────────────────────────────────────────────
    {
        "task_id": "two_phase_handshake",
        "task_name": "Two-Phase Valid/Ready Skid Buffer",
        "category": "Multi-clock/handshake",
        "module_name": "two_phase_handshake",
        "functional_spec": (
            "Implement a synthesizable valid/ready skid buffer pipeline register in SystemVerilog.\n"
            "Ports:\n"
            "  input  wire       clk\n"
            "  input  wire       rst_n\n"
            "  input  wire       s_valid\n"
            "  output wire       s_ready\n"
            "  input  wire [7:0] s_data\n"
            "  output reg        m_valid\n"
            "  input  wire       m_ready\n"
            "  output reg  [7:0] m_data\n"
            "Behavior:\n"
            "  Provides a 2-deep skid buffer decoupling upstream s_ready from downstream m_ready (zero combinational path between m_ready and s_ready).\n"
            "  When downstream is ready (m_ready=1), achieves full 1 beat/cycle throughput.\n"
            "  When downstream is stalled (m_ready=0), can absorb up to 2 items without losing data before dropping s_ready=0.\n"
            "  Maintains strict FIFO data ordering.\n"
            "  Active-low reset rst_n clears valid flags."
        ),
        "interface": {
            "ports": [
                {"name": "clk", "direction": "input", "width": 1},
                {"name": "rst_n", "direction": "input", "width": 1},
                {"name": "s_valid", "direction": "input", "width": 1},
                {"name": "s_ready", "direction": "output", "width": 1},
                {"name": "s_data", "direction": "input", "width": 8},
                {"name": "m_valid", "direction": "output", "width": 1},
                {"name": "m_ready", "direction": "input", "width": 1},
                {"name": "m_data", "direction": "output", "width": 8}
            ]
        },
        "clock_reset_assumptions": "Clock clk; active-low reset rst_n.",
        "expected_behavior": "Zero-bubble throughput when ready; buffers stall beats without drop or combinational feedback.",
        "verification_strategy": "Cycle simulation with burst data and random backpressure + SBY BMC handshake safety.",
        "testbench_code": """`timescale 1ns/1ps
module tb_two_phase_handshake;
    reg clk;
    reg rst_n;
    reg s_valid;
    wire s_ready;
    reg [7:0] s_data;
    wire m_valid;
    reg m_ready;
    wire [7:0] m_data;

    two_phase_handshake dut (
        .clk(clk),
        .rst_n(rst_n),
        .s_valid(s_valid),
        .s_ready(s_ready),
        .s_data(s_data),
        .m_valid(m_valid),
        .m_ready(m_ready),
        .m_data(m_data)
    );

    always #5 clk = ~clk;

    reg [7:0] sent_data [0:99];
    reg [7:0] recv_data [0:99];
    integer send_idx, recv_idx;

    always @(posedge clk) begin
        if (rst_n) begin
            if (m_valid && m_ready) begin
                recv_data[recv_idx] <= m_data;
                recv_idx <= recv_idx + 1;
            end
        end
    end

    initial begin
        clk = 0;
        rst_n = 0;
        s_valid = 0;
        s_data = 0;
        m_ready = 1;
        send_idx = 0;
        recv_idx = 0;
        #20;
        rst_n = 1;
        #10;

        while (send_idx < 50) begin
            @(posedge clk);
            s_valid = $random % 2;
            s_data = send_idx + 8'h20;
            m_ready = $random % 2;
            if (s_valid && s_ready) begin
                sent_data[send_idx] = s_data;
                send_idx = send_idx + 1;
            end
        end

        @(posedge clk);
        s_valid = 0;
        m_ready = 1;
        while (recv_idx < send_idx) @(posedge clk);

        #1;
        for (integer i = 0; i < 50; i = i + 1) begin
            if (sent_data[i] !== recv_data[i]) begin
                $display("FAIL: Data mismatch at %0d: sent %h, got %h", i, sent_data[i], recv_data[i]);
                $fatal(1);
            end
        end

        $display("ALL_TESTS_PASSED");
        $finish;
    end
endmodule
""",
        "sva_code": """module two_phase_handshake_formal(
    input wire clk,
    input wire rst_n,
    input wire s_valid,
    input wire [7:0] s_data,
    input wire m_ready
);
    wire s_ready, m_valid;
    wire [7:0] m_data;

    two_phase_handshake dut (
        .clk(clk),
        .rst_n(rst_n),
        .s_valid(s_valid),
        .s_ready(s_ready),
        .s_data(s_data),
        .m_valid(m_valid),
        .m_ready(m_ready),
        .m_data(m_data)
    );

    always @(posedge clk) begin
        if (rst_n) begin
            if ($past(m_valid) && !$past(m_ready)) begin
                assert(m_valid);
                assert(m_data == $past(m_data));
            end
        end
    end
endmodule
""",
        "generation_prompt": (
            "Write a synthesizable valid/ready skid buffer pipeline register in SystemVerilog.\n"
            "Module name: two_phase_handshake\n"
            "Ports:\n"
            "  input  wire       clk,\n"
            "  input  wire       rst_n,\n"
            "  input  wire       s_valid,\n"
            "  output wire       s_ready,\n"
            "  input  wire [7:0] s_data,\n"
            "  output reg        m_valid,\n"
            "  input  wire       m_ready,\n"
            "  output reg  [7:0] m_data\n"
            "Requirements:\n"
            "- Skid buffer holding up to 2 elements.\n"
            "- Cuts combinational path between m_ready and s_ready (registered output).\n"
            "- Full throughput (1 beat/cycle) when m_ready is high.\n"
            "- Absorbs beats during downstream stall without data drop or duplication.\n"
            "Output only SystemVerilog code inside ```systemverilog ... ```."
        ),
        "repair_policy": "Maximum 3 repair turns; inject raw compiler/simulator diagnostics into prompt.",
        "timeout": 60
    },

    # ── 10. CDC Handshake ─────────────────────────────────────────────────
    {
        "task_id": "cdc_handshake",
        "task_name": "Clock-Domain-Crossing Pulse Handshake",
        "category": "Multi-clock/handshake",
        "module_name": "cdc_handshake",
        "functional_spec": (
            "Implement a synthesizable clock-domain-crossing (CDC) pulse synchronizer in SystemVerilog.\n"
            "Ports:\n"
            "  input  wire clk_src\n"
            "  input  wire rst_src_n\n"
            "  input  wire pulse_in_src\n"
            "  output reg  busy_src\n"
            "  input  wire clk_dst\n"
            "  input  wire rst_dst_n\n"
            "  output reg  pulse_out_dst\n"
            "Behavior:\n"
            "  Safely transfers a 1-cycle pulse from the 'clk_src' domain to the asynchronous 'clk_dst' domain.\n"
            "  When 'pulse_in_src' pulses high for 1 cycle while !busy_src, 'busy_src' asserts high and an internal toggle bit is flipped in the source domain.\n"
            "  The toggle bit is synchronized into 'clk_dst' using a 2-stage flip-flop synchronizer.\n"
            "  An edge detector in 'clk_dst' generates a single-cycle 'pulse_out_dst' on the destination clock.\n"
            "  The synchronized destination toggle is synchronized back to 'clk_src' via a second 2-stage flip-flop synchronizer to clear 'busy_src' when complete.\n"
            "  Guarantees no metastability, no missed pulses, and exactly one pulse emitted per trigger across any clock frequency ratio."
        ),
        "interface": {
            "ports": [
                {"name": "clk_src", "direction": "input", "width": 1},
                {"name": "rst_src_n", "direction": "input", "width": 1},
                {"name": "pulse_in_src", "direction": "input", "width": 1},
                {"name": "busy_src", "direction": "output", "width": 1},
                {"name": "clk_dst", "direction": "input", "width": 1},
                {"name": "rst_dst_n", "direction": "input", "width": 1},
                {"name": "pulse_out_dst", "direction": "output", "width": 1}
            ]
        },
        "clock_reset_assumptions": "Independent asynchronous clocks clk_src and clk_dst; separate resets.",
        "expected_behavior": "1-cycle pulse in src generates exactly 1 pulse in dst; busy flag guards multi-cycle handshake.",
        "verification_strategy": "Cycle simulation with fast-to-slow and slow-to-fast clock ratios + Yosys CDC analysis.",
        "testbench_code": """`timescale 1ns/1ps
module tb_cdc_handshake;
    reg clk_src;
    reg rst_src_n;
    reg pulse_in_src;
    wire busy_src;

    reg clk_dst;
    reg rst_dst_n;
    wire pulse_out_dst;

    cdc_handshake dut (
        .clk_src(clk_src),
        .rst_src_n(rst_src_n),
        .pulse_in_src(pulse_in_src),
        .busy_src(busy_src),
        .clk_dst(clk_dst),
        .rst_dst_n(rst_dst_n),
        .pulse_out_dst(pulse_out_dst)
    );

    always #10 clk_src = ~clk_src;
    always #35 clk_dst = ~clk_dst;

    integer dst_pulse_count;
    always @(posedge clk_dst) begin
        if (rst_dst_n && pulse_out_dst) begin
            dst_pulse_count <= dst_pulse_count + 1;
        end
    end

    initial begin
        clk_src = 0;
        rst_src_n = 0;
        pulse_in_src = 0;
        clk_dst = 0;
        rst_dst_n = 0;
        dst_pulse_count = 0;
        #50;
        rst_src_n = 1;
        rst_dst_n = 1;
        #100;

        for (integer p = 0; p < 5; p = p + 1) begin
            @(posedge clk_src);
            pulse_in_src = 1;
            @(posedge clk_src);
            pulse_in_src = 0;

            while (busy_src) @(posedge clk_src);
            #100;
        end

        #200;
        if (dst_pulse_count !== 5) begin
            $display("FAIL: Expected exactly 5 destination pulses, got %0d", dst_pulse_count);
            $fatal(1);
        end

        $display("ALL_TESTS_PASSED");
        $finish;
    end
endmodule
""",
        "sva_code": """module cdc_handshake_formal(
    input wire clk_src,
    input wire rst_src_n,
    input wire pulse_in_src,
    input wire clk_dst,
    input wire rst_dst_n
);
    wire busy_src, pulse_out_dst;

    cdc_handshake dut (
        .clk_src(clk_src),
        .rst_src_n(rst_src_n),
        .pulse_in_src(pulse_in_src),
        .busy_src(busy_src),
        .clk_dst(clk_dst),
        .rst_dst_n(rst_dst_n),
        .pulse_out_dst(pulse_out_dst)
    );

    always @(posedge clk_src) begin
        if (!rst_src_n) begin
            assert(!busy_src);
        end
    end
endmodule
""",
        "generation_prompt": (
            "Write a synthesizable clock-domain-crossing (CDC) pulse synchronizer in SystemVerilog.\n"
            "Module name: cdc_handshake\n"
            "Ports:\n"
            "  input  wire clk_src,\n"
            "  input  wire rst_src_n,\n"
            "  input  wire pulse_in_src,\n"
            "  output reg  busy_src,\n"
            "  input  wire clk_dst,\n"
            "  input  wire rst_dst_n,\n"
            "  output reg  pulse_out_dst\n"
            "Requirements:\n"
            "- When pulse_in_src is high and !busy_src, asserts busy_src=1 and toggles internal src toggle bit.\n"
            "- Synchronizes toggle into clk_dst via a 2-stage flip-flop synchronizer.\n"
            "- Detects edge in clk_dst and emits a 1-cycle pulse on pulse_out_dst.\n"
            "- Synchronizes dst toggle back to clk_src via another 2-stage flip-flop synchronizer to clear busy_src=0.\n"
            "- Must be clean for asynchronous clocks with zero metastability.\n"
            "Output only SystemVerilog code inside ```systemverilog ... ```."
        ),
        "repair_policy": "Maximum 3 repair turns; inject raw compiler/simulator diagnostics into prompt.",
        "timeout": 60
    }
]

for t in tasks:
    path = TASKS_DIR / f"{t['task_id']}.json"
    with open(path, "w") as f:
        json.dump(t, f, indent=2)
    print(f"Wrote task definition: {path}")

print(f"Successfully generated all {len(tasks)} benchmark tasks.")
