// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Symbol table internal header
//
// Internal details; most calling programs do not need this header,
// unless using verilator public meta comments.

#ifndef VERILATED_VCOUNTER_03__SYMS_H_
#define VERILATED_VCOUNTER_03__SYMS_H_  // guard

#include "verilated.h"

// INCLUDE MODEL CLASS

#include "Vcounter_03.h"

// INCLUDE MODULE CLASSES
#include "Vcounter_03___024root.h"

// SYMS CLASS (contains all model state)
class alignas(VL_CACHE_LINE_BYTES)Vcounter_03__Syms final : public VerilatedSyms {
  public:
    // INTERNAL STATE
    Vcounter_03* const __Vm_modelp;
    VlDeleter __Vm_deleter;
    bool __Vm_didInit = false;

    // MODULE INSTANCE STATE
    Vcounter_03___024root          TOP;

    // COVERAGE
    uint32_t __Vcoverage[29];

    // CONSTRUCTORS
    Vcounter_03__Syms(VerilatedContext* contextp, const char* namep, Vcounter_03* modelp);
    ~Vcounter_03__Syms();

    // METHODS
    const char* name() { return TOP.name(); }
};

#endif  // guard
