"""Deterministic mutant generator for S3 golden-mutant testing.

Reads each golden in tests/golden/, applies named textual transforms (each
pattern must occur exactly once or generation fails loudly), and writes the
mutants into tests/golden_mutants/. Every mutant is designed to violate at
least one SPECIFIED property of its task (spec-blind mutants are excluded by
rule: the dev specs cannot see them, so survival would prove nothing about
the gate). Run: python3 tests/soundness/make_mutants.py
"""

from __future__ import annotations

from pathlib import Path

GOLDEN_DIR = Path(__file__).resolve().parent.parent / "golden"
OUT_DIR = Path(__file__).resolve().parent.parent / "golden_mutants"


def _mutate(text: str, old: str, new: str) -> str:
    n = text.count(old)
    assert n == 1, f"pattern {old!r} found {n}x (need exactly 1)"
    return text.replace(old, new, 1)


def _mark(text: str, task: str, kind: str, violates: str) -> str:
    lines = text.splitlines(keepends=True)
    assert lines[0].startswith("// UNREVIEWED"), "golden header changed?"
    note = (
        f"// MUTANT {task}/{kind} (UNREVIEWED test input): violates specified "
        f"property via: {violates}. Must FAIL at some gate.\n"
    )
    return lines[0] + note + "".join(lines[1:])


def mutants_for(task: str, golden: str) -> dict[str, tuple[str, str]]:
    """Return {kind: (mutated_text, violated_spec_property)}."""
    if task == "counter_04":
        return {
            "stuck": (
                _mark(_mutate(golden, "q <= {~q[0], q[7:1]};", "q <= 8'h00;"),
                      task, "stuck", "cover/vacuity path (no counting)"),
                "no counting behavior",
            ),
            "wrongreset": (
                _mark(_mutate(golden, "q <= 8'h00;", "q <= 8'hFF;"),
                      task, "wrongreset", "!rst_n |-> q == 8'h00"),
                "!rst_n |-> q == 8'h00",
            ),
            "offbyone": (
                _mark(_mutate(golden, "q <= {~q[0], q[7:1]};", "q <= {~q[1], q[7:1]};"),
                      task, "offbyone", "Johnson sequence (16-phase) behavior"),
                "Johnson sequence behavior",
            ),
        }
    if task == "arbiter_02":
        return {
            "stuck": (
                _mark(_mutate(golden, "assign gnt[0] = req[0];", "assign gnt[0] = 1'b0;"),
                      task, "stuck", "req[0] |-> gnt[0]"),
                "req[0] |-> gnt[0]",
            ),
            "priority": (
                _mark(_mutate(golden, "assign gnt[0] = req[0];", "assign gnt[0] = req[0] & ~req[3];"),
                      task, "priority", "req[0] |-> gnt[0] (req3 steals grant)"),
                "req[0] |-> gnt[0]",
            ),
            "double": (
                _mark(_mutate(golden, "assign gnt[1] = req[1] & ~req[0];", "assign gnt[1] = req[1];"),
                      task, "double", "$onehot0(gnt)"),
                "$onehot0(gnt)",
            ),
        }
    if task == "fifo_01":
        return {
            "noreset": (
                _mark(_mutate(
                    golden,
                    "    if (!rst_n) begin\n      wr_ptr <= 3'd0;\n      rd_ptr <= 3'd0;\n      count  <= 4'd0;\n    end else begin",
                    "    begin",
                ), task, "noreset", "!rst_n |-> empty == 1 && full == 0"),
                "!rst_n |-> empty == 1 && full == 0",
            ),
            "emptyhigh": (
                _mark(_mutate(golden, "assign empty = (count == 4'd0);", "assign empty = 1'b1;"),
                      task, "emptyhigh", "!(full && empty)"),
                "!(full && empty)",
            ),
            "fullhigh": (
                _mark(_mutate(golden, "assign full  = (count == 4'd8);", "assign full  = 1'b1;"),
                      task, "fullhigh", "!(full && empty) and reset empty/full"),
                "!(full && empty)",
            ),
            "slowreset": (
                _mark(_mutate(
                    golden,
                    "    if (!rst_n) begin\n      wr_ptr <= 3'd0;\n      rd_ptr <= 3'd0;\n      count  <= 4'd0;\n    end else begin",
                    "    if (!rst_n) begin\n      wr_ptr <= 3'd0;\n      rd_ptr <= 3'd0;\n      count  <= count;\n    end else begin",
                ), task, "slowreset", "!rst_n |-> empty == 1 && full == 0 (count never clears)"),
                "!rst_n |-> empty == 1 && full == 0",
            ),
        }
    if task == "fsm_heldout_04":
        return {
            "stuffone": (
                _mark(_mutate(golden, "dout    <= 1'b0;\n      stuffed <= 1'b1;",
                              "dout    <= 1'b1;\n      stuffed <= 1'b1;"),
                      task, "stuffone", "stuffed |-> dout == 0"),
                "stuffed |-> dout == 0",
            ),
            "nostuff": (
                _mark(_mutate(golden, "dout    <= 1'b0;\n      stuffed <= 1'b1;\n      ones    <= 3'd0;",
                              "dout    <= din;\n      stuffed <= 1'b0;\n      ones    <= 3'd0;"),
                      task, "nostuff", "vacuity path (antecedent never fires)"),
                "stuffing behavior (vacuous fail)",
            ),
            "stuffstuck": (
                _mark(_mutate(golden, "stuffed <= 1'b0;\n      ones    <= din ? ones + 3'd1 : 3'd0;",
                              "stuffed <= 1'b1;\n      ones    <= din ? ones + 3'd1 : 3'd0;"),
                      task, "stuffstuck", "stuffed |-> dout == 0"),
                "stuffed |-> dout == 0",
            ),
            "halfreset": (
                _mark(_mutate(
                    golden,
                    "    if (!rst_n) begin\n      ones    <= 3'd0;\n      dout    <= 1'b0;\n      stuffed <= 1'b0;\n    end else if",
                    "    if (!rst_n) begin\n      dout    <= 1'b0;\n      stuffed <= 1'b0;\n    end else if",
                ), task, "halfreset", "!rst_n |-> !stuffed (ones not cleared)"),
                # S3 halt ruling: under approved P5b semantics this defect is
                # invisible to every stated formal property (checked cycles
                # always have freshly-cleared stuffed). Retained as documented
                # spec-coverage evidence, excluded from the mutant exit count.
                "!rst_n |-> !stuffed",
            ),
            "noreset": (
                _mark(_mutate(
                    golden,
                    "  // Synchronous active-low reset per task clock_reset_assumptions.\n  always_ff @(posedge clk) begin\n    if (!rst_n) begin\n      ones    <= 3'd0;\n      dout    <= 1'b0;\n      stuffed <= 1'b0;\n    end else if (ones == 3'd5) begin",
                    "  // Synchronous active-low reset per task clock_reset_assumptions.\n  always_ff @(posedge clk) begin\n    if (ones == 3'd5) begin",
                ), task, "noreset", "!rst_n |-> !stuffed (reset ignored)"),
                "!rst_n |-> !stuffed",
            ),
        }
    if task in ("reset_02", "apb_01"):
        return {
            "noreset": (
                _mark(_mutate(
                    golden,
                    "    if (!rst_n)\n      out_data <= 8'h00;\n    else\n      out_data <= in_data;",
                    "    out_data <= in_data;",
                ), task, "noreset", "!rst_n |-> out_data == 0"),
                "!rst_n |-> out_data == 0",
            ),
            "wrongreset": (
                _mark(_mutate(golden, "out_data <= 8'h00;", "out_data <= 8'hFF;"),
                      task, "wrongreset", "!rst_n |-> out_data == 0"),
                "!rst_n |-> out_data == 0",
            ),
            "halfreset": (
                _mark(_mutate(
                    golden,
                    "    if (!rst_n)\n      out_data <= 8'h00;\n    else\n      out_data <= in_data;",
                    "    if (!rst_n)\n      out_data[3:0] <= 4'h0;\n    else\n      out_data <= in_data;",
                ), task, "halfreset", "!rst_n |-> out_data == 0"),
                "!rst_n |-> out_data == 0",
            ),
            "slowreset": (
                _mark(_mutate(
                    golden,
                    "  always_ff @(posedge clk) begin\n    if (!rst_n)\n      out_data <= 8'h00;\n    else\n      out_data <= in_data;\n  end\nendmodule",
                    "  logic [7:0] pipe;\n"
                    "  always_ff @(posedge clk) begin\n"
                    "    if (!rst_n) begin\n"
                    "      pipe <= 8'h00;\n"
                    "      out_data <= pipe;\n"
                    "    end else begin\n"
                    "      pipe <= in_data;\n"
                    "      out_data <= pipe;\n"
                    "    end\n"
                    "  end\nendmodule",
                ), task, "slowreset", "!rst_n |-> out_data == 0 (2-cycle reset)"),
                "!rst_n |-> out_data == 0",
            ),
        }
    raise KeyError(task)


TASKS = ["counter_04", "arbiter_02", "fifo_01", "fsm_heldout_04", "reset_02", "apb_01"]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    for task in TASKS:
        golden = (GOLDEN_DIR / f"{task}.sv").read_text(encoding="utf-8")
        for kind, (text, violates) in mutants_for(task, golden).items():
            assert text != golden, f"{task}/{kind} identical to golden"
            (OUT_DIR / f"{task}__{kind}.sv").write_text(text, encoding="utf-8")
            total += 1
            print(f"{task}__{kind}: violates [{violates}]")
    print(f"wrote {total} mutants")


if __name__ == "__main__":
    main()
