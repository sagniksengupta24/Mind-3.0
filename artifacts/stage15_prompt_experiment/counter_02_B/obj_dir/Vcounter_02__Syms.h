// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Symbol table internal header
//
// Internal details; most calling programs do not need this header,
// unless using verilator public meta comments.

#ifndef VERILATED_VCOUNTER_02__SYMS_H_
#define VERILATED_VCOUNTER_02__SYMS_H_  // guard

#include "verilated.h"

// INCLUDE MODEL CLASS

#include "Vcounter_02.h"

// INCLUDE MODULE CLASSES
#include "Vcounter_02___024root.h"

// SYMS CLASS (contains all model state)
class alignas(VL_CACHE_LINE_BYTES)Vcounter_02__Syms final : public VerilatedSyms {
  public:
    // INTERNAL STATE
    Vcounter_02* const __Vm_modelp;
    VlDeleter __Vm_deleter;
    bool __Vm_didInit = false;

    // MODULE INSTANCE STATE
    Vcounter_02___024root          TOP;

    // COVERAGE
    uint32_t __Vcoverage[15];

    // CONSTRUCTORS
    Vcounter_02__Syms(VerilatedContext* contextp, const char* namep, Vcounter_02* modelp);
    ~Vcounter_02__Syms();

    // METHODS
    const char* name() { return TOP.name(); }
};

#endif  // guard
