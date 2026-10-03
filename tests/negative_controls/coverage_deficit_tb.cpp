#include "Vcoverage_deficit.h"
#include "verilated.h"
#include <memory>

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    auto dut = std::make_unique<Vcoverage_deficit>();
    dut->clk = 0;
    dut->sel = 0;
    dut->a = 0;
    dut->b = 0;
    dut->eval();
    // Intentionally never drives sel=1 and never varies the data inputs.
    for (int i = 0; i < 8; ++i) {
        dut->clk = 1;
        dut->eval();
        dut->clk = 0;
        dut->eval();
    }
    return 0;
}
