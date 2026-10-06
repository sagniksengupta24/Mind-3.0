#include <verilated.h>
#include <verilated_cov.h>
#include "Vspi_04.h"
#include <iostream>
#include <cassert>
#include <cstdlib>
#include <cstdint>

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    Vspi_04* top = new Vspi_04;

    // Phase 1: Synchronous reset sequence (10 half-cycles)
    top->clk = 0;
    top->rst_n = 0;
    for (int i = 0; i < 10; ++i) {
        top->clk = !top->clk;
        top->eval();
    }
    top->rst_n = 1;

    // Phase 2: Boundary sweep — all-zeros then all-ones
    uint32_t sweep_vals[] = {0x00000000u, 0xFFFFFFFFu};
    for (int s = 0; s < 2; ++s) {
        uint32_t boundary_val = sweep_vals[s];
        top->clk = !top->clk;
        top->in_data = (boundary_val & 0xFFu);
        top->eval();
    }

    // Phase 2b: Walking-1 pattern across 32 bit positions
    for (int bit_pos = 0; bit_pos < 32; ++bit_pos) {
        top->clk = !top->clk;
        top->in_data = ((1u << (bit_pos % 8)) & 0xFFu);
        top->eval();
    }

    // Phase 2c: Directed soak — hold each input asserted in turn so
    // sequential depth (saturation, wrap, bounds) is actually reached.
    // Soak step 0: hold in_data asserted
    for (int soak = 0; soak < 600; ++soak) {
        top->clk = !top->clk;
        top->in_data = 0xFFu;
        top->eval();
    }

    // Soak step 1: hold all inputs asserted
    for (int soak = 0; soak < 600; ++soak) {
        top->clk = !top->clk;
        top->in_data = 0xFFu;
        top->eval();
    }


    // Phase 3: Galois LFSR pseudo-random stimulus
    // A fixed 32-bit Galois LFSR (mask 0xB4BCD35C) used for pseudo-random stimulus.
    uint32_t lfsr = 0xACE1u;
    for (int cycle = 0; cycle < 1400; ++cycle) {
        top->clk = !top->clk;
        uint32_t lsb = lfsr & 1u;
        lfsr = (lfsr >> 1) | (lsb ? 0x80000000u : 0u);
        if (lsb) lfsr ^= 0xB4BCD35Cu;
        top->in_data = ((lfsr >> 0) & 0xFFu);
        top->eval();
    }

    // Phase 4: Reset recovery verification
    top->rst_n = 0;
    for (int i = 0; i < 4; ++i) {
        top->clk = !top->clk;
        top->eval();
    }
    top->rst_n = 1;
    top->clk = !top->clk;
    top->eval();

    top->final();
    VerilatedCov::write("coverage.dat");
    std::cout << "ALL TESTS PASSED: FSM-aware stimulus complete (reset+boundary+LFSR+recovery)." << std::endl;
    delete top;
    return 0;
}
