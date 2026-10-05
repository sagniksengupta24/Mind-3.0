// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Symbol table implementation internals

#include "Vcounter_02__pch.h"
#include "Vcounter_02.h"
#include "Vcounter_02___024root.h"

// FUNCTIONS
Vcounter_02__Syms::~Vcounter_02__Syms()
{
}

Vcounter_02__Syms::Vcounter_02__Syms(VerilatedContext* contextp, const char* namep, Vcounter_02* modelp)
    : VerilatedSyms{contextp}
    // Setup internal state of the Syms class
    , __Vm_modelp{modelp}
    // Setup module instances
    , TOP{this, namep}
{
    // Configure time unit / time precision
    _vm_contextp__->timeunit(-12);
    _vm_contextp__->timeprecision(-12);
    // Setup each module's pointers to their submodules
    // Setup each module's pointer back to symbol table (for public functions)
    TOP.__Vconfigure(true);
}
