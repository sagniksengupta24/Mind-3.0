// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design internal header
// See Vcounter_03.h for the primary calling header

#ifndef VERILATED_VCOUNTER_03___024ROOT_H_
#define VERILATED_VCOUNTER_03___024ROOT_H_  // guard

#include "verilated.h"
#include "verilated_cov.h"


class Vcounter_03__Syms;

class alignas(VL_CACHE_LINE_BYTES) Vcounter_03___024root final : public VerilatedModule {
  public:

    // DESIGN SPECIFIC STATE
    VL_IN8(clk,0,0);
    VL_IN8(rst_n,0,0);
    VL_IN8(en,0,0);
    VL_OUT8(bcd_ones,3,0);
    VL_OUT8(bcd_tens,3,0);
    VL_OUT8(carry_out,0,0);
    CData/*3:0*/ counter_03__DOT__bcd_ones_reg;
    CData/*3:0*/ counter_03__DOT__bcd_tens_reg;
    CData/*0:0*/ counter_03__DOT__carry_out_reg;
    CData/*0:0*/ counter_03__DOT____Vtogcov__clk;
    CData/*0:0*/ counter_03__DOT____Vtogcov__rst_n;
    CData/*0:0*/ counter_03__DOT____Vtogcov__en;
    CData/*3:0*/ counter_03__DOT____Vtogcov__bcd_ones;
    CData/*3:0*/ counter_03__DOT____Vtogcov__bcd_tens;
    CData/*0:0*/ counter_03__DOT____Vtogcov__carry_out;
    CData/*3:0*/ counter_03__DOT____Vtogcov__bcd_ones_reg;
    CData/*3:0*/ counter_03__DOT____Vtogcov__bcd_tens_reg;
    CData/*0:0*/ counter_03__DOT____Vtogcov__carry_out_reg;
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
    Vcounter_03__Syms* const vlSymsp;

    // CONSTRUCTORS
    Vcounter_03___024root(Vcounter_03__Syms* symsp, const char* v__name);
    ~Vcounter_03___024root();
    VL_UNCOPYABLE(Vcounter_03___024root);

    // INTERNAL METHODS
    void __Vconfigure(bool first);
    void __vlCoverInsert(uint32_t* countp, bool enable, const char* filenamep, int lineno, int column,
        const char* hierp, const char* pagep, const char* commentp, const char* linescovp);
};


#endif  // guard
