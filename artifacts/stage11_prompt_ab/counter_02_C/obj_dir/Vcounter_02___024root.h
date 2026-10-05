// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design internal header
// See Vcounter_02.h for the primary calling header

#ifndef VERILATED_VCOUNTER_02___024ROOT_H_
#define VERILATED_VCOUNTER_02___024ROOT_H_  // guard

#include "verilated.h"
#include "verilated_cov.h"


class Vcounter_02__Syms;

class alignas(VL_CACHE_LINE_BYTES) Vcounter_02___024root final : public VerilatedModule {
  public:

    // DESIGN SPECIFIC STATE
    VL_IN8(clk,0,0);
    VL_IN8(rst_n,0,0);
    VL_IN8(en,0,0);
    VL_OUT8(gray,3,0);
    CData/*3:0*/ counter_02__DOT__gray_reg;
    CData/*0:0*/ counter_02__DOT____Vtogcov__clk;
    CData/*0:0*/ counter_02__DOT____Vtogcov__rst_n;
    CData/*0:0*/ counter_02__DOT____Vtogcov__en;
    CData/*3:0*/ counter_02__DOT____Vtogcov__gray;
    CData/*3:0*/ counter_02__DOT____Vtogcov__gray_reg;
    CData/*0:0*/ __VstlFirstIteration;
    CData/*0:0*/ __VicoFirstIteration;
    CData/*0:0*/ __Vtrigprevexpr___TOP__clk__0;
    CData/*0:0*/ __Vtrigprevexpr___TOP__rst_n__0;
    CData/*0:0*/ __VactContinue;
    IData/*31:0*/ __VactIterCount;
    VlTriggerVec<1> __VstlTriggered;
    VlTriggerVec<1> __VicoTriggered;
    VlTriggerVec<1> __VactTriggered;
    VlTriggerVec<1> __VnbaTriggered;

    // INTERNAL VARIABLES
    Vcounter_02__Syms* const vlSymsp;

    // CONSTRUCTORS
    Vcounter_02___024root(Vcounter_02__Syms* symsp, const char* v__name);
    ~Vcounter_02___024root();
    VL_UNCOPYABLE(Vcounter_02___024root);

    // INTERNAL METHODS
    void __Vconfigure(bool first);
    void __vlCoverInsert(uint32_t* countp, bool enable, const char* filenamep, int lineno, int column,
        const char* hierp, const char* pagep, const char* commentp, const char* linescovp);
};


#endif  // guard
