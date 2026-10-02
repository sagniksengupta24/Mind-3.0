#include "Vsim_behavioral_failure.h"
#include "verilated.h"
#include <cstdio>
#include <memory>

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    auto dut = std::make_unique<Vsim_behavioral_failure>();
    dut->clk = 0;
    dut->rst_n = 0;
    dut->a = 0;
    dut->b = 0;
    dut->eval();

    // Reset
    dut->clk = 1; dut->eval(); dut->clk = 0; dut->eval();
    dut->rst_n = 1;

    // Stimulate with 10 + 20
    dut->a = 10;
    dut->b = 20;
    dut->clk = 1; dut->eval(); dut->clk = 0; dut->eval();

    // Expected: 30. Actual: 10 - 20 = 246 (0xF6 in 8-bit unsigned)
    if (dut->sum != 30) {
        fprintf(stderr, "ASSERTION FAILED: Behavioral mismatch! Expected 10 + 20 = 30, got sum=%d\n", dut->sum);
        return 1;
    }
    return 0;
}
