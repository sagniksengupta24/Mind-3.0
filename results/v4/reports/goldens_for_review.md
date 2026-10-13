# Golden review package (UNREVIEWED — owner spot-check required)

Each design below was written from the task spec fields shown, never from model outputs.
SystemVerilog bodies are reprinted verbatim from tests/golden/.

---

## counter_04 — johnson_counter_8b

- natural_language_spec: 8-bit twisted-ring Johnson counter producing 16-phase sequences
- clock_reset_assumptions: clk rising edge; active-low synchronous rst_n
- expected_ports: [{"direction": "input", "name": "clk", "width": 1}, {"direction": "input", "name": "rst_n", "width": 1}, {"direction": "output", "name": "q", "width": 8}]
- functional_requirements: ["8-bit twisted-ring Johnson counter producing 16-phase sequences"]
- expected_properties:
  - assert property (@(posedge clk) disable iff (!rst_n) !rst_n |-> q == 8'h00);
  - assert property (@(posedge clk) disable iff (!rst_n) q[7:1] == $past(q[6:0]));
- golden file: tests/golden/counter_04.sv

```systemverilog
// UNREVIEWED golden reference RTL for dev task counter_04 (johnson_counter_8b).
// Written from the task spec only (8-bit twisted-ring Johnson counter,
// 16-phase sequences; active-low synchronous rst_n). Never from model outputs.
// Owner spot-check required before any use as ground truth.
module counter_04 (
  input  logic       clk,
  input  logic       rst_n,
  output logic [7:0] q
);
  always_ff @(posedge clk) begin
    if (!rst_n)
      q <= 8'h00;
    else
      q <= {~q[0], q[7:1]};
  end
endmodule
```

---

## arbiter_02 — fixed_priority_4req

- natural_language_spec: 4-client fixed priority arbiter granting client 0 over 1, 2, and 3
- clock_reset_assumptions: clk rising edge; active-low synchronous rst_n
- expected_ports: [{"direction": "input", "name": "clk", "width": 1}, {"direction": "input", "name": "rst_n", "width": 1}, {"direction": "input", "name": "req", "width": 4}, {"direction": "output", "name": "gnt", "width": 4}]
- functional_requirements: ["4-client fixed priority arbiter granting client 0 over 1, 2, and 3"]
- expected_properties:
  - assert property (@(posedge clk) req[0] |-> gnt[0]);
  - assert property (@(posedge clk) $onehot0(gnt));
- golden file: tests/golden/arbiter_02.sv

```systemverilog
// UNREVIEWED golden reference RTL for dev task arbiter_02 (fixed_priority_4req).
// Written from the task spec only (client 0 over 1, 2, 3). Owner spot-check required.
/* verilator lint_off UNUSEDSIGNAL */
// clk/rst_n are spec-mandated ports with no functional role in this purely
// combinational grant; file-wide unused waiver keeps -Wall builds clean.
module arbiter_02 (
  input  logic       clk,
  input  logic       rst_n,
  input  logic [3:0] req,
  output logic [3:0] gnt
);
  assign gnt[0] = req[0];
  assign gnt[1] = req[1] & ~req[0];
  assign gnt[2] = req[2] & ~req[1] & ~req[0];
  assign gnt[3] = req[3] & ~req[2] & ~req[1] & ~req[0];
endmodule
/* verilator lint_on UNUSEDSIGNAL */
```

---

## fifo_01 — sync_fifo_8x8

- natural_language_spec: 8-depth 8-bit synchronous FIFO with full, empty, and watermarks
- clock_reset_assumptions: clk rising edge; active-low synchronous rst_n
- expected_ports: [{"direction": "input", "name": "clk", "width": 1}, {"direction": "input", "name": "rst_n", "width": 1}, {"direction": "input", "name": "wr_en", "width": 1}, {"direction": "input", "name": "wr_data", "width": 8}, {"direction": "input", "name": "rd_en", "width": 1}, {"direction": "output", "name": "rd_data", "width": 8}, {"direction": "output", "name": "full", "width": 1}, {"direction": "output", "name": "empty", "width": 1}]
- functional_requirements: ["8-depth 8-bit synchronous FIFO with full, empty, and watermarks"]
- expected_properties:
  - assert property (@(posedge clk) disable iff (!rst_n) !(full && empty));
  - assert property (@(posedge clk) disable iff (!rst_n) !rst_n |-> empty == 1 && full == 0);
- golden file: tests/golden/fifo_01.sv

```systemverilog
// UNREVIEWED golden reference RTL for dev task fifo_01 (sync_fifo_8x8).
// Written from the task spec only (8-depth 8-bit synchronous FIFO with full,
// empty; active-low synchronous rst_n). Owner spot-check required.
module fifo_01 (
  input  logic       clk,
  input  logic       rst_n,
  input  logic       wr_en,
  input  logic [7:0] wr_data,
  input  logic       rd_en,
  output logic [7:0] rd_data,
  output logic       full,
  output logic       empty
);
  logic [7:0] mem [0:7];
  logic [2:0] wr_ptr, rd_ptr;
  logic [3:0] count;

  assign full  = (count == 4'd8);
  assign empty = (count == 4'd0);
  assign rd_data = mem[rd_ptr];

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      wr_ptr <= 3'd0;
      rd_ptr <= 3'd0;
      count  <= 4'd0;
    end else begin
      case ({wr_en & ~full, rd_en & ~empty})
        2'b10: begin mem[wr_ptr] <= wr_data; wr_ptr <= wr_ptr + 3'd1; count <= count + 4'd1; end
        2'b01: begin rd_ptr <= rd_ptr + 3'd1; count <= count - 4'd1; end
        2'b11: begin mem[wr_ptr] <= wr_data; wr_ptr <= wr_ptr + 3'd1; rd_ptr <= rd_ptr + 3'd1; end
        default: begin end
      endcase
    end
  end
endmodule
```

---

## fsm_heldout_04 — sdlc_bit_stuffer_fsm

- natural_language_spec: SDLC bit stuffer inserting 0 after 5 consecutive 1s on serial stream
- clock_reset_assumptions: clk rising edge; active-low synchronous rst_n
- expected_ports: [{"direction": "input", "name": "clk", "width": 1}, {"direction": "input", "name": "rst_n", "width": 1}, {"direction": "input", "name": "din", "width": 1}, {"direction": "output", "name": "dout", "width": 1}, {"direction": "output", "name": "stuffed", "width": 1}]
- functional_requirements: ["SDLC bit stuffer inserting 0 after 5 consecutive 1s on serial stream"]
- expected_properties:
  - assert property (@(posedge clk) disable iff (!rst_n) stuffed |-> dout == 0);
  - assert property (@(posedge clk) disable iff (!rst_n) !rst_n |-> !stuffed);
- golden file: tests/golden/fsm_heldout_04.sv

```systemverilog
// UNREVIEWED golden reference RTL for dev task fsm_heldout_04 (sdlc_bit_stuffer_fsm).
// Written from the task spec only (insert 0 after 5 consecutive 1s).
// Owner spot-check required.
module fsm_heldout_04 (
  input  logic clk,
  input  logic rst_n,
  input  logic din,
  output logic dout,
  output logic stuffed
);
  logic [2:0] ones;

  // Synchronous active-low reset per task clock_reset_assumptions.
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      ones    <= 3'd0;
      dout    <= 1'b0;
      stuffed <= 1'b0;
    end else if (ones == 3'd5) begin
      dout    <= 1'b0;
      stuffed <= 1'b1;
      ones    <= 3'd0;
    end else begin
      dout    <= din;
      stuffed <= 1'b0;
      ones    <= din ? ones + 3'd1 : 3'd0;
    end
  end
endmodule
```

---

## reset_02 — glitch_free_reset_mux

- natural_language_spec: Glitch-free reset multiplexer switching between test and mission resets
- clock_reset_assumptions: clk rising edge; active-low synchronous rst_n
- expected_ports: [{"direction": "input", "name": "clk", "width": 1}, {"direction": "input", "name": "rst_n", "width": 1}, {"direction": "input", "name": "in_data", "width": 8}, {"direction": "output", "name": "out_data", "width": 8}]
- functional_requirements: ["Glitch-free reset multiplexer switching between test and mission resets"]
- expected_properties:
  - assert property (@(posedge clk) disable iff (!rst_n) !rst_n |-> out_data == 0);
  - assert property (@(posedge clk) disable iff (!rst_n) out_data == out_data);
- golden file: tests/golden/reset_02.sv

```systemverilog
// UNREVIEWED golden reference RTL for dev task reset_02 (glitch_free_reset_mux).
// Written from the task spec only (registered data path cleared while reset
// is asserted; active-low synchronous rst_n). Owner spot-check required.
module reset_02 (
  input  logic       clk,
  input  logic       rst_n,
  input  logic [7:0] in_data,
  output logic [7:0] out_data
);
  always_ff @(posedge clk) begin
    if (!rst_n)
      out_data <= 8'h00;
    else
      out_data <= in_data;
  end
endmodule
```

---

## apb_01 — apb_gpio_controller

- natural_language_spec: APB 16-bit GPIO controller with direction, input, and output registers
- clock_reset_assumptions: clk rising edge; active-low synchronous rst_n
- expected_ports: [{"direction": "input", "name": "clk", "width": 1}, {"direction": "input", "name": "rst_n", "width": 1}, {"direction": "input", "name": "in_data", "width": 8}, {"direction": "input", "name": "out_data", "width": 8}]
- functional_requirements: ["APB 16-bit GPIO controller with direction, input, and output registers"]
- expected_properties:
  - assert property (@(posedge clk) disable iff (!rst_n) !rst_n |-> out_data == 0);
  - assert property (@(posedge clk) disable iff (!rst_n) out_data == out_data);
- golden file: tests/golden/apb_01.sv

```systemverilog
// UNREVIEWED golden reference RTL for dev task apb_01 (apb_gpio_controller).
// Written from the task spec only (registered GPIO loopback with reset clear).
// Owner spot-check required.
module apb_01 (
  input  logic       clk,
  input  logic       rst_n,
  input  logic [7:0] in_data,
  output logic [7:0] out_data
);
  always_ff @(posedge clk) begin
    if (!rst_n)
      out_data <= 8'h00;
    else
      out_data <= in_data;
  end
endmodule
```
