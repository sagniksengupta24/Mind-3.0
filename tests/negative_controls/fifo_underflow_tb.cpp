#include "Vfifo_underflow.h"
#include "verilated.h"
#include <cstdio>
#include <memory>

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    auto dut = std::make_unique<Vfifo_underflow>();
    dut->clk = 0;
    dut->rst_n = 0;
    dut->wr_en = 0;
    dut->rd_en = 0;
    dut->wr_data = 0;
    dut->eval();

    // Reset sequence
    dut->clk = 1; dut->eval(); dut->clk = 0; dut->eval();
    dut->rst_n = 1;

    // FIFO is empty. Attempt illegal read when empty:
    dut->rd_en = 1;
    dut->clk = 1; dut->eval(); dut->clk = 0; dut->eval();
    dut->rd_en = 0;

    // Check count underflow: count should remain 0, but is now 7
    if (dut->empty == 0 || dut->count != 0) {
        fprintf(stderr, "ASSERTION FAILED: FIFO underflow occurred! empty=%d, count=%d (expected count=0)\n", dut->empty, dut->count);
        return 1;
    }
    return 0;
}
