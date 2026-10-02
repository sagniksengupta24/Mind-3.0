#include "Vfifo_overflow.h"
#include "verilated.h"
#include <cstdio>
#include <memory>

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    auto dut = std::make_unique<Vfifo_overflow>();
    dut->clk = 0;
    dut->rst_n = 0;
    dut->wr_en = 0;
    dut->rd_en = 0;
    dut->wr_data = 0;
    dut->eval();

    // Reset sequence
    dut->clk = 1; dut->eval(); dut->clk = 0; dut->eval();
    dut->rst_n = 1;

    // Fill FIFO with 4 elements
    for (int i = 0; i < 4; ++i) {
        dut->wr_en = 1;
        dut->wr_data = 0xA0 + i;
        dut->clk = 1; dut->eval(); dut->clk = 0; dut->eval();
    }

    // Try to write 5th element into full FIFO
    dut->wr_en = 1;
    dut->wr_data = 0xFF;
    dut->clk = 1; dut->eval(); dut->clk = 0; dut->eval();
    dut->wr_en = 0;

    // Read back first element: should be 0xA0, but was overwritten or count corrupted
    dut->rd_en = 1;
    dut->clk = 1; dut->eval(); dut->clk = 0; dut->eval();

    if (dut->rd_data != 0xA0) {
        fprintf(stderr, "ASSERTION FAILED: FIFO overflow corrupts unread data (expected 0xA0, got 0x%02X)\n", dut->rd_data);
        return 1;
    }
    if (dut->count > 4) {
        fprintf(stderr, "ASSERTION FAILED: FIFO overflow count corrupted (count = %d > 4)\n", dut->count);
        return 1;
    }
    return 0;
}
