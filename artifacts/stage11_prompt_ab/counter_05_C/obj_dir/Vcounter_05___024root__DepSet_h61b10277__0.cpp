// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vcounter_05.h for the primary calling header

#include "Vcounter_05__pch.h"
#include "Vcounter_05__Syms.h"
#include "Vcounter_05___024root.h"

#ifdef VL_DEBUG
VL_ATTR_COLD void Vcounter_05___024root___dump_triggers__ico(Vcounter_05___024root* vlSelf);
#endif  // VL_DEBUG

void Vcounter_05___024root___eval_triggers__ico(Vcounter_05___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_05__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_05___024root___eval_triggers__ico\n"); );
    // Body
    vlSelf->__VicoTriggered.set(0U, (IData)(vlSelf->__VicoFirstIteration));
#ifdef VL_DEBUG
    if (VL_UNLIKELY(vlSymsp->_vm_contextp__->debug())) {
        Vcounter_05___024root___dump_triggers__ico(vlSelf);
    }
#endif
}

VL_INLINE_OPT void Vcounter_05___024root___ico_sequent__TOP__0(Vcounter_05___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_05__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_05___024root___ico_sequent__TOP__0\n"); );
    // Body
    if (((IData)(vlSelf->clk) ^ (IData)(vlSelf->counter_05__DOT____Vtogcov__clk))) {
        ++(vlSymsp->__Vcoverage[0]);
        vlSelf->counter_05__DOT____Vtogcov__clk = vlSelf->clk;
    }
    if (((IData)(vlSelf->rst_n) ^ (IData)(vlSelf->counter_05__DOT____Vtogcov__rst_n))) {
        ++(vlSymsp->__Vcoverage[1]);
        vlSelf->counter_05__DOT____Vtogcov__rst_n = vlSelf->rst_n;
    }
    if (((IData)(vlSelf->kick) ^ (IData)(vlSelf->counter_05__DOT____Vtogcov__kick))) {
        ++(vlSymsp->__Vcoverage[2]);
        vlSelf->counter_05__DOT____Vtogcov__kick = vlSelf->kick;
    }
}

#ifdef VL_DEBUG
VL_ATTR_COLD void Vcounter_05___024root___dump_triggers__act(Vcounter_05___024root* vlSelf);
#endif  // VL_DEBUG

void Vcounter_05___024root___eval_triggers__act(Vcounter_05___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_05__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_05___024root___eval_triggers__act\n"); );
    // Body
    vlSelf->__VactTriggered.set(0U, (((IData)(vlSelf->clk) 
                                      & (~ (IData)(vlSelf->__Vtrigprevexpr___TOP__clk__0))) 
                                     | ((~ (IData)(vlSelf->rst_n)) 
                                        & (IData)(vlSelf->__Vtrigprevexpr___TOP__rst_n__0))));
    vlSelf->__Vtrigprevexpr___TOP__clk__0 = vlSelf->clk;
    vlSelf->__Vtrigprevexpr___TOP__rst_n__0 = vlSelf->rst_n;
#ifdef VL_DEBUG
    if (VL_UNLIKELY(vlSymsp->_vm_contextp__->debug())) {
        Vcounter_05___024root___dump_triggers__act(vlSelf);
    }
#endif
}

VL_INLINE_OPT void Vcounter_05___024root___nba_sequent__TOP__0(Vcounter_05___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_05__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_05___024root___nba_sequent__TOP__0\n"); );
    // Body
    ++(vlSymsp->__Vcoverage[7]);
    if (vlSelf->rst_n) {
        ++(vlSymsp->__Vcoverage[6]);
    }
    if ((1U & (~ (IData)(vlSelf->rst_n)))) {
        ++(vlSymsp->__Vcoverage[5]);
    }
    vlSelf->counter_05__DOT__fault_reg = ((IData)(vlSelf->rst_n) 
                                          && (1U & 
                                              (~ (IData)(vlSelf->kick))));
    if (((IData)(vlSelf->counter_05__DOT__fault_reg) 
         ^ (IData)(vlSelf->counter_05__DOT____Vtogcov__fault_reg))) {
        ++(vlSymsp->__Vcoverage[4]);
        vlSelf->counter_05__DOT____Vtogcov__fault_reg 
            = vlSelf->counter_05__DOT__fault_reg;
    }
    vlSelf->fault = vlSelf->counter_05__DOT__fault_reg;
    if (((IData)(vlSelf->fault) ^ (IData)(vlSelf->counter_05__DOT____Vtogcov__fault))) {
        ++(vlSymsp->__Vcoverage[3]);
        vlSelf->counter_05__DOT____Vtogcov__fault = vlSelf->fault;
    }
}
