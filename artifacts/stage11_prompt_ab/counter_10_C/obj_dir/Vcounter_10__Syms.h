// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Symbol table internal header
//
// Internal details; most calling programs do not need this header,
// unless using verilator public meta comments.

#ifndef VERILATED_VCOUNTER_10__SYMS_H_
#define VERILATED_VCOUNTER_10__SYMS_H_  // guard

#include "verilated.h"

// INCLUDE MODEL CLASS

#include "Vcounter_10.h"

// INCLUDE MODULE CLASSES
#include "Vcounter_10___024root.h"

// SYMS CLASS (contains all model state)
class alignas(VL_CACHE_LINE_BYTES)Vcounter_10__Syms final : public VerilatedSyms {
  public:
    // INTERNAL STATE
    Vcounter_10* const __Vm_modelp;
    VlDeleter __Vm_deleter;
    bool __Vm_didInit = false;

    // MODULE INSTANCE STATE
    Vcounter_10___024root          TOP;

    // COVERAGE
    uint32_t __Vcoverage[16];

    // CONSTRUCTORS
    Vcounter_10__Syms(VerilatedContext* contextp, const char* namep, Vcounter_10* modelp);
    ~Vcounter_10__Syms();

    // METHODS
    const char* name() { return TOP.name(); }
};

#endif  // guard
