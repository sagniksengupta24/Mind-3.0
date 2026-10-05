// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vcounter_04.h for the primary calling header

#include "Vcounter_04__pch.h"
#include "Vcounter_04__Syms.h"
#include "Vcounter_04___024root.h"

#ifdef VL_DEBUG
VL_ATTR_COLD void Vcounter_04___024root___dump_triggers__ico(Vcounter_04___024root* vlSelf);
#endif  // VL_DEBUG

void Vcounter_04___024root___eval_triggers__ico(Vcounter_04___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_04__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_04___024root___eval_triggers__ico\n"); );
    // Body
    vlSelf->__VicoTriggered.set(0U, (IData)(vlSelf->__VicoFirstIteration));
#ifdef VL_DEBUG
    if (VL_UNLIKELY(vlSymsp->_vm_contextp__->debug())) {
        Vcounter_04___024root___dump_triggers__ico(vlSelf);
    }
#endif
}

VL_INLINE_OPT void Vcounter_04___024root___ico_sequent__TOP__0(Vcounter_04___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_04__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_04___024root___ico_sequent__TOP__0\n"); );
    // Body
    if (((IData)(vlSelf->clk) ^ (IData)(vlSelf->counter_04__DOT____Vtogcov__clk))) {
        ++(vlSymsp->__Vcoverage[0]);
        vlSelf->counter_04__DOT____Vtogcov__clk = vlSelf->clk;
    }
    if (((IData)(vlSelf->rst_n) ^ (IData)(vlSelf->counter_04__DOT____Vtogcov__rst_n))) {
        ++(vlSymsp->__Vcoverage[1]);
        vlSelf->counter_04__DOT____Vtogcov__rst_n = vlSelf->rst_n;
    }
}

#ifdef VL_DEBUG
VL_ATTR_COLD void Vcounter_04___024root___dump_triggers__act(Vcounter_04___024root* vlSelf);
#endif  // VL_DEBUG

void Vcounter_04___024root___eval_triggers__act(Vcounter_04___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_04__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_04___024root___eval_triggers__act\n"); );
    // Body
    vlSelf->__VactTriggered.set(0U, (((IData)(vlSelf->clk) 
                                      & (~ (IData)(vlSelf->__Vtrigprevexpr___TOP__clk__0))) 
                                     | ((~ (IData)(vlSelf->rst_n)) 
                                        & (IData)(vlSelf->__Vtrigprevexpr___TOP__rst_n__0))));
    vlSelf->__Vtrigprevexpr___TOP__clk__0 = vlSelf->clk;
    vlSelf->__Vtrigprevexpr___TOP__rst_n__0 = vlSelf->rst_n;
#ifdef VL_DEBUG
    if (VL_UNLIKELY(vlSymsp->_vm_contextp__->debug())) {
        Vcounter_04___024root___dump_triggers__act(vlSelf);
    }
#endif
}

VL_INLINE_OPT void Vcounter_04___024root___nba_sequent__TOP__0(Vcounter_04___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_04__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_04___024root___nba_sequent__TOP__0\n"); );
    // Body
    ++(vlSymsp->__Vcoverage[20]);
    if (vlSelf->rst_n) {
        ++(vlSymsp->__Vcoverage[19]);
        vlSelf->counter_04__DOT__q_reg = ((0xfeU & 
                                           ((IData)(vlSelf->counter_04__DOT__q_reg) 
                                            << 1U)) 
                                          | (1U & ((IData)(vlSelf->counter_04__DOT__q_reg) 
                                                   >> 7U)));
    } else {
        vlSelf->counter_04__DOT__q_reg = 0U;
    }
    if ((1U & (~ (IData)(vlSelf->rst_n)))) {
        ++(vlSymsp->__Vcoverage[18]);
    }
    if ((1U & ((IData)(vlSelf->counter_04__DOT__q_reg) 
               ^ (IData)(vlSelf->counter_04__DOT____Vtogcov__q_reg)))) {
        ++(vlSymsp->__Vcoverage[10]);
        vlSelf->counter_04__DOT____Vtogcov__q_reg = 
            ((0xfeU & (IData)(vlSelf->counter_04__DOT____Vtogcov__q_reg)) 
             | (1U & (IData)(vlSelf->counter_04__DOT__q_reg)));
    }
    if ((2U & ((IData)(vlSelf->counter_04__DOT__q_reg) 
               ^ (IData)(vlSelf->counter_04__DOT____Vtogcov__q_reg)))) {
        ++(vlSymsp->__Vcoverage[11]);
        vlSelf->counter_04__DOT____Vtogcov__q_reg = 
            ((0xfdU & (IData)(vlSelf->counter_04__DOT____Vtogcov__q_reg)) 
             | (2U & (IData)(vlSelf->counter_04__DOT__q_reg)));
    }
    if ((4U & ((IData)(vlSelf->counter_04__DOT__q_reg) 
               ^ (IData)(vlSelf->counter_04__DOT____Vtogcov__q_reg)))) {
        ++(vlSymsp->__Vcoverage[12]);
        vlSelf->counter_04__DOT____Vtogcov__q_reg = 
            ((0xfbU & (IData)(vlSelf->counter_04__DOT____Vtogcov__q_reg)) 
             | (4U & (IData)(vlSelf->counter_04__DOT__q_reg)));
    }
    if ((8U & ((IData)(vlSelf->counter_04__DOT__q_reg) 
               ^ (IData)(vlSelf->counter_04__DOT____Vtogcov__q_reg)))) {
        ++(vlSymsp->__Vcoverage[13]);
        vlSelf->counter_04__DOT____Vtogcov__q_reg = 
            ((0xf7U & (IData)(vlSelf->counter_04__DOT____Vtogcov__q_reg)) 
             | (8U & (IData)(vlSelf->counter_04__DOT__q_reg)));
    }
    if ((0x10U & ((IData)(vlSelf->counter_04__DOT__q_reg) 
                  ^ (IData)(vlSelf->counter_04__DOT____Vtogcov__q_reg)))) {
        ++(vlSymsp->__Vcoverage[14]);
        vlSelf->counter_04__DOT____Vtogcov__q_reg = 
            ((0xefU & (IData)(vlSelf->counter_04__DOT____Vtogcov__q_reg)) 
             | (0x10U & (IData)(vlSelf->counter_04__DOT__q_reg)));
    }
    if ((0x20U & ((IData)(vlSelf->counter_04__DOT__q_reg) 
                  ^ (IData)(vlSelf->counter_04__DOT____Vtogcov__q_reg)))) {
        ++(vlSymsp->__Vcoverage[15]);
        vlSelf->counter_04__DOT____Vtogcov__q_reg = 
            ((0xdfU & (IData)(vlSelf->counter_04__DOT____Vtogcov__q_reg)) 
             | (0x20U & (IData)(vlSelf->counter_04__DOT__q_reg)));
    }
    if ((0x40U & ((IData)(vlSelf->counter_04__DOT__q_reg) 
                  ^ (IData)(vlSelf->counter_04__DOT____Vtogcov__q_reg)))) {
        ++(vlSymsp->__Vcoverage[16]);
        vlSelf->counter_04__DOT____Vtogcov__q_reg = 
            ((0xbfU & (IData)(vlSelf->counter_04__DOT____Vtogcov__q_reg)) 
             | (0x40U & (IData)(vlSelf->counter_04__DOT__q_reg)));
    }
    if ((0x80U & ((IData)(vlSelf->counter_04__DOT__q_reg) 
                  ^ (IData)(vlSelf->counter_04__DOT____Vtogcov__q_reg)))) {
        ++(vlSymsp->__Vcoverage[17]);
        vlSelf->counter_04__DOT____Vtogcov__q_reg = 
            ((0x7fU & (IData)(vlSelf->counter_04__DOT____Vtogcov__q_reg)) 
             | (0x80U & (IData)(vlSelf->counter_04__DOT__q_reg)));
    }
    vlSelf->q = vlSelf->counter_04__DOT__q_reg;
    if ((1U & ((IData)(vlSelf->q) ^ (IData)(vlSelf->counter_04__DOT____Vtogcov__q)))) {
        ++(vlSymsp->__Vcoverage[2]);
        vlSelf->counter_04__DOT____Vtogcov__q = ((0xfeU 
                                                  & (IData)(vlSelf->counter_04__DOT____Vtogcov__q)) 
                                                 | (1U 
                                                    & (IData)(vlSelf->q)));
    }
    if ((2U & ((IData)(vlSelf->q) ^ (IData)(vlSelf->counter_04__DOT____Vtogcov__q)))) {
        ++(vlSymsp->__Vcoverage[3]);
        vlSelf->counter_04__DOT____Vtogcov__q = ((0xfdU 
                                                  & (IData)(vlSelf->counter_04__DOT____Vtogcov__q)) 
                                                 | (2U 
                                                    & (IData)(vlSelf->q)));
    }
    if ((4U & ((IData)(vlSelf->q) ^ (IData)(vlSelf->counter_04__DOT____Vtogcov__q)))) {
        ++(vlSymsp->__Vcoverage[4]);
        vlSelf->counter_04__DOT____Vtogcov__q = ((0xfbU 
                                                  & (IData)(vlSelf->counter_04__DOT____Vtogcov__q)) 
                                                 | (4U 
                                                    & (IData)(vlSelf->q)));
    }
    if ((8U & ((IData)(vlSelf->q) ^ (IData)(vlSelf->counter_04__DOT____Vtogcov__q)))) {
        ++(vlSymsp->__Vcoverage[5]);
        vlSelf->counter_04__DOT____Vtogcov__q = ((0xf7U 
                                                  & (IData)(vlSelf->counter_04__DOT____Vtogcov__q)) 
                                                 | (8U 
                                                    & (IData)(vlSelf->q)));
    }
    if ((0x10U & ((IData)(vlSelf->q) ^ (IData)(vlSelf->counter_04__DOT____Vtogcov__q)))) {
        ++(vlSymsp->__Vcoverage[6]);
        vlSelf->counter_04__DOT____Vtogcov__q = ((0xefU 
                                                  & (IData)(vlSelf->counter_04__DOT____Vtogcov__q)) 
                                                 | (0x10U 
                                                    & (IData)(vlSelf->q)));
    }
    if ((0x20U & ((IData)(vlSelf->q) ^ (IData)(vlSelf->counter_04__DOT____Vtogcov__q)))) {
        ++(vlSymsp->__Vcoverage[7]);
        vlSelf->counter_04__DOT____Vtogcov__q = ((0xdfU 
                                                  & (IData)(vlSelf->counter_04__DOT____Vtogcov__q)) 
                                                 | (0x20U 
                                                    & (IData)(vlSelf->q)));
    }
    if ((0x40U & ((IData)(vlSelf->q) ^ (IData)(vlSelf->counter_04__DOT____Vtogcov__q)))) {
        ++(vlSymsp->__Vcoverage[8]);
        vlSelf->counter_04__DOT____Vtogcov__q = ((0xbfU 
                                                  & (IData)(vlSelf->counter_04__DOT____Vtogcov__q)) 
                                                 | (0x40U 
                                                    & (IData)(vlSelf->q)));
    }
    if ((0x80U & ((IData)(vlSelf->q) ^ (IData)(vlSelf->counter_04__DOT____Vtogcov__q)))) {
        ++(vlSymsp->__Vcoverage[9]);
        vlSelf->counter_04__DOT____Vtogcov__q = ((0x7fU 
                                                  & (IData)(vlSelf->counter_04__DOT____Vtogcov__q)) 
                                                 | (0x80U 
                                                    & (IData)(vlSelf->q)));
    }
}
