// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vcounter_02.h for the primary calling header

#include "Vcounter_02__pch.h"
#include "Vcounter_02__Syms.h"
#include "Vcounter_02___024root.h"

#ifdef VL_DEBUG
VL_ATTR_COLD void Vcounter_02___024root___dump_triggers__ico(Vcounter_02___024root* vlSelf);
#endif  // VL_DEBUG

void Vcounter_02___024root___eval_triggers__ico(Vcounter_02___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_02__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_02___024root___eval_triggers__ico\n"); );
    // Body
    vlSelf->__VicoTriggered.set(0U, (IData)(vlSelf->__VicoFirstIteration));
#ifdef VL_DEBUG
    if (VL_UNLIKELY(vlSymsp->_vm_contextp__->debug())) {
        Vcounter_02___024root___dump_triggers__ico(vlSelf);
    }
#endif
}

VL_INLINE_OPT void Vcounter_02___024root___ico_sequent__TOP__0(Vcounter_02___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_02__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_02___024root___ico_sequent__TOP__0\n"); );
    // Body
    if (((IData)(vlSelf->clk) ^ (IData)(vlSelf->counter_02__DOT____Vtogcov__clk))) {
        ++(vlSymsp->__Vcoverage[0]);
        vlSelf->counter_02__DOT____Vtogcov__clk = vlSelf->clk;
    }
    if (((IData)(vlSelf->rst_n) ^ (IData)(vlSelf->counter_02__DOT____Vtogcov__rst_n))) {
        ++(vlSymsp->__Vcoverage[1]);
        vlSelf->counter_02__DOT____Vtogcov__rst_n = vlSelf->rst_n;
    }
    if (((IData)(vlSelf->en) ^ (IData)(vlSelf->counter_02__DOT____Vtogcov__en))) {
        ++(vlSymsp->__Vcoverage[2]);
        vlSelf->counter_02__DOT____Vtogcov__en = vlSelf->en;
    }
}

#ifdef VL_DEBUG
VL_ATTR_COLD void Vcounter_02___024root___dump_triggers__act(Vcounter_02___024root* vlSelf);
#endif  // VL_DEBUG

void Vcounter_02___024root___eval_triggers__act(Vcounter_02___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_02__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_02___024root___eval_triggers__act\n"); );
    // Body
    vlSelf->__VactTriggered.set(0U, (((IData)(vlSelf->clk) 
                                      & (~ (IData)(vlSelf->__Vtrigprevexpr___TOP__clk__0))) 
                                     | ((~ (IData)(vlSelf->rst_n)) 
                                        & (IData)(vlSelf->__Vtrigprevexpr___TOP__rst_n__0))));
    vlSelf->__Vtrigprevexpr___TOP__clk__0 = vlSelf->clk;
    vlSelf->__Vtrigprevexpr___TOP__rst_n__0 = vlSelf->rst_n;
#ifdef VL_DEBUG
    if (VL_UNLIKELY(vlSymsp->_vm_contextp__->debug())) {
        Vcounter_02___024root___dump_triggers__act(vlSelf);
    }
#endif
}

VL_INLINE_OPT void Vcounter_02___024root___nba_sequent__TOP__0(Vcounter_02___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_02__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_02___024root___nba_sequent__TOP__0\n"); );
    // Body
    ++(vlSymsp->__Vcoverage[14]);
    if ((1U & (~ (IData)(vlSelf->rst_n)))) {
        ++(vlSymsp->__Vcoverage[13]);
    }
    if (vlSelf->rst_n) {
        if (vlSelf->en) {
            ++(vlSymsp->__Vcoverage[11]);
            vlSelf->counter_02__DOT__gray_reg = ((0xeU 
                                                  & ((IData)(vlSelf->counter_02__DOT__gray_reg) 
                                                     << 1U)) 
                                                 | (1U 
                                                    & ((IData)(vlSelf->counter_02__DOT__gray_reg) 
                                                       >> 3U)));
        }
        if ((1U & (~ (IData)(vlSelf->en)))) {
            ++(vlSymsp->__Vcoverage[12]);
        }
    } else {
        vlSelf->counter_02__DOT__gray_reg = 0U;
    }
    if ((1U & ((IData)(vlSelf->counter_02__DOT__gray_reg) 
               ^ (IData)(vlSelf->counter_02__DOT____Vtogcov__gray_reg)))) {
        ++(vlSymsp->__Vcoverage[7]);
        vlSelf->counter_02__DOT____Vtogcov__gray_reg 
            = ((0xeU & (IData)(vlSelf->counter_02__DOT____Vtogcov__gray_reg)) 
               | (1U & (IData)(vlSelf->counter_02__DOT__gray_reg)));
    }
    if ((2U & ((IData)(vlSelf->counter_02__DOT__gray_reg) 
               ^ (IData)(vlSelf->counter_02__DOT____Vtogcov__gray_reg)))) {
        ++(vlSymsp->__Vcoverage[8]);
        vlSelf->counter_02__DOT____Vtogcov__gray_reg 
            = ((0xdU & (IData)(vlSelf->counter_02__DOT____Vtogcov__gray_reg)) 
               | (2U & (IData)(vlSelf->counter_02__DOT__gray_reg)));
    }
    if ((4U & ((IData)(vlSelf->counter_02__DOT__gray_reg) 
               ^ (IData)(vlSelf->counter_02__DOT____Vtogcov__gray_reg)))) {
        ++(vlSymsp->__Vcoverage[9]);
        vlSelf->counter_02__DOT____Vtogcov__gray_reg 
            = ((0xbU & (IData)(vlSelf->counter_02__DOT____Vtogcov__gray_reg)) 
               | (4U & (IData)(vlSelf->counter_02__DOT__gray_reg)));
    }
    if ((8U & ((IData)(vlSelf->counter_02__DOT__gray_reg) 
               ^ (IData)(vlSelf->counter_02__DOT____Vtogcov__gray_reg)))) {
        ++(vlSymsp->__Vcoverage[10]);
        vlSelf->counter_02__DOT____Vtogcov__gray_reg 
            = ((7U & (IData)(vlSelf->counter_02__DOT____Vtogcov__gray_reg)) 
               | (8U & (IData)(vlSelf->counter_02__DOT__gray_reg)));
    }
    vlSelf->gray = vlSelf->counter_02__DOT__gray_reg;
    if ((1U & ((IData)(vlSelf->gray) ^ (IData)(vlSelf->counter_02__DOT____Vtogcov__gray)))) {
        ++(vlSymsp->__Vcoverage[3]);
        vlSelf->counter_02__DOT____Vtogcov__gray = 
            ((0xeU & (IData)(vlSelf->counter_02__DOT____Vtogcov__gray)) 
             | (1U & (IData)(vlSelf->gray)));
    }
    if ((2U & ((IData)(vlSelf->gray) ^ (IData)(vlSelf->counter_02__DOT____Vtogcov__gray)))) {
        ++(vlSymsp->__Vcoverage[4]);
        vlSelf->counter_02__DOT____Vtogcov__gray = 
            ((0xdU & (IData)(vlSelf->counter_02__DOT____Vtogcov__gray)) 
             | (2U & (IData)(vlSelf->gray)));
    }
    if ((4U & ((IData)(vlSelf->gray) ^ (IData)(vlSelf->counter_02__DOT____Vtogcov__gray)))) {
        ++(vlSymsp->__Vcoverage[5]);
        vlSelf->counter_02__DOT____Vtogcov__gray = 
            ((0xbU & (IData)(vlSelf->counter_02__DOT____Vtogcov__gray)) 
             | (4U & (IData)(vlSelf->gray)));
    }
    if ((8U & ((IData)(vlSelf->gray) ^ (IData)(vlSelf->counter_02__DOT____Vtogcov__gray)))) {
        ++(vlSymsp->__Vcoverage[6]);
        vlSelf->counter_02__DOT____Vtogcov__gray = 
            ((7U & (IData)(vlSelf->counter_02__DOT____Vtogcov__gray)) 
             | (8U & (IData)(vlSelf->gray)));
    }
}
