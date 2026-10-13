// UNREVIEWED golden reference RTL for dev task arbiter_02 (fixed_priority_4req).
// MUTANT arbiter_02/stuck (UNREVIEWED test input): violates specified property via: req[0] |-> gnt[0]. Must FAIL at some gate.
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
  assign gnt[0] = 1'b0;
  assign gnt[1] = req[1] & ~req[0];
  assign gnt[2] = req[2] & ~req[1] & ~req[0];
  assign gnt[3] = req[3] & ~req[2] & ~req[1] & ~req[0];
endmodule
/* verilator lint_on UNUSEDSIGNAL */
