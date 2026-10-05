// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Symbol table internal header
//
// Internal details; most calling programs do not need this header,
// unless using verilator public meta comments.

#ifndef VERILATED_VCOUNTER_05__SYMS_H_
#define VERILATED_VCOUNTER_05__SYMS_H_  // guard

#include "verilated.h"

// INCLUDE MODEL CLASS

#include "Vcounter_05.h"

// INCLUDE MODULE CLASSES
#include "Vcounter_05___024root.h"

// SYMS CLASS (contains all model state)
class alignas(VL_CACHE_LINE_BYTES)Vcounter_05__Syms final : public VerilatedSyms {
  public:
    // INTERNAL STATE
    Vcounter_05* const __Vm_modelp;
    VlDeleter __Vm_deleter;
    bool __Vm_didInit = false;

    // MODULE INSTANCE STATE
    Vcounter_05___024root          TOP;

    // COVERAGE
    uint32_t __Vcoverage[10];

    // CONSTRUCTORS
    Vcounter_05__Syms(VerilatedContext* contextp, const char* namep, Vcounter_05* modelp);
    ~Vcounter_05__Syms();

    // METHODS
    const char* name() { return TOP.name(); }
};

#endif  // guard
