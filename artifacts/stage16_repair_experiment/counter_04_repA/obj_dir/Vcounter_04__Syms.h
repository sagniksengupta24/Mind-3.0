// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Symbol table internal header
//
// Internal details; most calling programs do not need this header,
// unless using verilator public meta comments.

#ifndef VERILATED_VCOUNTER_04__SYMS_H_
#define VERILATED_VCOUNTER_04__SYMS_H_  // guard

#include "verilated.h"

// INCLUDE MODEL CLASS

#include "Vcounter_04.h"

// INCLUDE MODULE CLASSES
#include "Vcounter_04___024root.h"

// SYMS CLASS (contains all model state)
class alignas(VL_CACHE_LINE_BYTES)Vcounter_04__Syms final : public VerilatedSyms {
  public:
    // INTERNAL STATE
    Vcounter_04* const __Vm_modelp;
    VlDeleter __Vm_deleter;
    bool __Vm_didInit = false;

    // MODULE INSTANCE STATE
    Vcounter_04___024root          TOP;

    // COVERAGE
    uint32_t __Vcoverage[21];

    // CONSTRUCTORS
    Vcounter_04__Syms(VerilatedContext* contextp, const char* namep, Vcounter_04* modelp);
    ~Vcounter_04__Syms();

    // METHODS
    const char* name() { return TOP.name(); }
};

#endif  // guard
