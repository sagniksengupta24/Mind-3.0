#include "Voff_by_one_counter.h"
#include "verilated.h"
#include <cstdio>
#include <memory>

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    auto dut = std::make_unique<Voff_by_one_counter>();
    dut->clk = 0;
    dut->rst_n = 0;
    dut->eval();

    // Reset
    dut->clk = 1; dut->eval(); dut->clk = 0; dut->eval();
    dut->rst_n = 1;

    for (int cycle = 0; cycle < 20; ++cycle) {
        dut->clk = 1; dut->eval(); dut->clk = 0; dut->eval();
        if (dut->val > 9) {
            fprintf(stderr, "ASSERTION FAILED: off-by-one counter exceeded maximum value 9 (got val=%d)\n", dut->val);
            return 1;
        }
    }
    return 0;
}
