// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vcounter_03.h for the primary calling header

#include "Vcounter_03__pch.h"
#include "Vcounter_03__Syms.h"
#include "Vcounter_03___024root.h"

#ifdef VL_DEBUG
VL_ATTR_COLD void Vcounter_03___024root___dump_triggers__ico(Vcounter_03___024root* vlSelf);
#endif  // VL_DEBUG

void Vcounter_03___024root___eval_triggers__ico(Vcounter_03___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_03__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_03___024root___eval_triggers__ico\n"); );
    // Body
    vlSelf->__VicoTriggered.set(0U, (IData)(vlSelf->__VicoFirstIteration));
#ifdef VL_DEBUG
    if (VL_UNLIKELY(vlSymsp->_vm_contextp__->debug())) {
        Vcounter_03___024root___dump_triggers__ico(vlSelf);
    }
#endif
}

VL_INLINE_OPT void Vcounter_03___024root___ico_sequent__TOP__0(Vcounter_03___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_03__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_03___024root___ico_sequent__TOP__0\n"); );
    // Body
    if (((IData)(vlSelf->clk) ^ (IData)(vlSelf->counter_03__DOT____Vtogcov__clk))) {
        ++(vlSymsp->__Vcoverage[0]);
        vlSelf->counter_03__DOT____Vtogcov__clk = vlSelf->clk;
    }
    if (((IData)(vlSelf->rst_n) ^ (IData)(vlSelf->counter_03__DOT____Vtogcov__rst_n))) {
        ++(vlSymsp->__Vcoverage[1]);
        vlSelf->counter_03__DOT____Vtogcov__rst_n = vlSelf->rst_n;
    }
    if (((IData)(vlSelf->en) ^ (IData)(vlSelf->counter_03__DOT____Vtogcov__en))) {
        ++(vlSymsp->__Vcoverage[2]);
        vlSelf->counter_03__DOT____Vtogcov__en = vlSelf->en;
    }
}

#ifdef VL_DEBUG
VL_ATTR_COLD void Vcounter_03___024root___dump_triggers__act(Vcounter_03___024root* vlSelf);
#endif  // VL_DEBUG

void Vcounter_03___024root___eval_triggers__act(Vcounter_03___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_03__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_03___024root___eval_triggers__act\n"); );
    // Body
    vlSelf->__VactTriggered.set(0U, (((IData)(vlSelf->clk) 
                                      & (~ (IData)(vlSelf->__Vtrigprevexpr___TOP__clk__0))) 
                                     | ((~ (IData)(vlSelf->rst_n)) 
                                        & (IData)(vlSelf->__Vtrigprevexpr___TOP__rst_n__0))));
    vlSelf->__Vtrigprevexpr___TOP__clk__0 = vlSelf->clk;
    vlSelf->__Vtrigprevexpr___TOP__rst_n__0 = vlSelf->rst_n;
#ifdef VL_DEBUG
    if (VL_UNLIKELY(vlSymsp->_vm_contextp__->debug())) {
        Vcounter_03___024root___dump_triggers__act(vlSelf);
    }
#endif
}

VL_INLINE_OPT void Vcounter_03___024root___nba_sequent__TOP__0(Vcounter_03___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_03__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_03___024root___nba_sequent__TOP__0\n"); );
    // Init
    CData/*3:0*/ __Vdly__counter_03__DOT__bcd_ones_reg;
    __Vdly__counter_03__DOT__bcd_ones_reg = 0;
    CData/*3:0*/ __Vdly__counter_03__DOT__bcd_tens_reg;
    __Vdly__counter_03__DOT__bcd_tens_reg = 0;
    // Body
    ++(vlSymsp->__Vcoverage[28]);
    if ((1U & (~ (IData)(vlSelf->rst_n)))) {
        ++(vlSymsp->__Vcoverage[27]);
    }
    __Vdly__counter_03__DOT__bcd_tens_reg = vlSelf->counter_03__DOT__bcd_tens_reg;
    __Vdly__counter_03__DOT__bcd_ones_reg = vlSelf->counter_03__DOT__bcd_ones_reg;
    if (vlSelf->rst_n) {
        if (vlSelf->en) {
            ++(vlSymsp->__Vcoverage[25]);
            if ((9U == (IData)(vlSelf->counter_03__DOT__bcd_ones_reg))) {
                ++(vlSymsp->__Vcoverage[23]);
                if ((9U == (IData)(vlSelf->counter_03__DOT__bcd_tens_reg))) {
                    ++(vlSymsp->__Vcoverage[21]);
                    __Vdly__counter_03__DOT__bcd_tens_reg = 0U;
                    vlSelf->counter_03__DOT__carry_out_reg = 1U;
                } else {
                    __Vdly__counter_03__DOT__bcd_tens_reg 
                        = (0xfU & ((IData)(1U) + (IData)(vlSelf->counter_03__DOT__bcd_tens_reg)));
                    vlSelf->counter_03__DOT__carry_out_reg = 0U;
                }
                if ((9U != (IData)(vlSelf->counter_03__DOT__bcd_tens_reg))) {
                    ++(vlSymsp->__Vcoverage[22]);
                }
                __Vdly__counter_03__DOT__bcd_ones_reg = 0U;
            } else {
                __Vdly__counter_03__DOT__bcd_ones_reg 
                    = (0xfU & ((IData)(1U) + (IData)(vlSelf->counter_03__DOT__bcd_ones_reg)));
                vlSelf->counter_03__DOT__carry_out_reg = 0U;
            }
            if ((9U != (IData)(vlSelf->counter_03__DOT__bcd_ones_reg))) {
                ++(vlSymsp->__Vcoverage[24]);
            }
        } else {
            vlSelf->counter_03__DOT__carry_out_reg = 0U;
        }
        if ((1U & (~ (IData)(vlSelf->en)))) {
            ++(vlSymsp->__Vcoverage[26]);
        }
    } else {
        __Vdly__counter_03__DOT__bcd_tens_reg = 0U;
        __Vdly__counter_03__DOT__bcd_ones_reg = 0U;
        vlSelf->counter_03__DOT__carry_out_reg = 0U;
    }
    vlSelf->counter_03__DOT__bcd_tens_reg = __Vdly__counter_03__DOT__bcd_tens_reg;
    vlSelf->counter_03__DOT__bcd_ones_reg = __Vdly__counter_03__DOT__bcd_ones_reg;
    if (((IData)(vlSelf->counter_03__DOT__carry_out_reg) 
         ^ (IData)(vlSelf->counter_03__DOT____Vtogcov__carry_out_reg))) {
        ++(vlSymsp->__Vcoverage[20]);
        vlSelf->counter_03__DOT____Vtogcov__carry_out_reg 
            = vlSelf->counter_03__DOT__carry_out_reg;
    }
    vlSelf->carry_out = vlSelf->counter_03__DOT__carry_out_reg;
    if ((1U & ((IData)(vlSelf->counter_03__DOT__bcd_tens_reg) 
               ^ (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_tens_reg)))) {
        ++(vlSymsp->__Vcoverage[16]);
        vlSelf->counter_03__DOT____Vtogcov__bcd_tens_reg 
            = ((0xeU & (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_tens_reg)) 
               | (1U & (IData)(vlSelf->counter_03__DOT__bcd_tens_reg)));
    }
    if ((2U & ((IData)(vlSelf->counter_03__DOT__bcd_tens_reg) 
               ^ (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_tens_reg)))) {
        ++(vlSymsp->__Vcoverage[17]);
        vlSelf->counter_03__DOT____Vtogcov__bcd_tens_reg 
            = ((0xdU & (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_tens_reg)) 
               | (2U & (IData)(vlSelf->counter_03__DOT__bcd_tens_reg)));
    }
    if ((4U & ((IData)(vlSelf->counter_03__DOT__bcd_tens_reg) 
               ^ (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_tens_reg)))) {
        ++(vlSymsp->__Vcoverage[18]);
        vlSelf->counter_03__DOT____Vtogcov__bcd_tens_reg 
            = ((0xbU & (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_tens_reg)) 
               | (4U & (IData)(vlSelf->counter_03__DOT__bcd_tens_reg)));
    }
    if ((8U & ((IData)(vlSelf->counter_03__DOT__bcd_tens_reg) 
               ^ (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_tens_reg)))) {
        ++(vlSymsp->__Vcoverage[19]);
        vlSelf->counter_03__DOT____Vtogcov__bcd_tens_reg 
            = ((7U & (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_tens_reg)) 
               | (8U & (IData)(vlSelf->counter_03__DOT__bcd_tens_reg)));
    }
    vlSelf->bcd_tens = vlSelf->counter_03__DOT__bcd_tens_reg;
    if ((1U & ((IData)(vlSelf->counter_03__DOT__bcd_ones_reg) 
               ^ (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_ones_reg)))) {
        ++(vlSymsp->__Vcoverage[12]);
        vlSelf->counter_03__DOT____Vtogcov__bcd_ones_reg 
            = ((0xeU & (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_ones_reg)) 
               | (1U & (IData)(vlSelf->counter_03__DOT__bcd_ones_reg)));
    }
    if ((2U & ((IData)(vlSelf->counter_03__DOT__bcd_ones_reg) 
               ^ (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_ones_reg)))) {
        ++(vlSymsp->__Vcoverage[13]);
        vlSelf->counter_03__DOT____Vtogcov__bcd_ones_reg 
            = ((0xdU & (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_ones_reg)) 
               | (2U & (IData)(vlSelf->counter_03__DOT__bcd_ones_reg)));
    }
    if ((4U & ((IData)(vlSelf->counter_03__DOT__bcd_ones_reg) 
               ^ (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_ones_reg)))) {
        ++(vlSymsp->__Vcoverage[14]);
        vlSelf->counter_03__DOT____Vtogcov__bcd_ones_reg 
            = ((0xbU & (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_ones_reg)) 
               | (4U & (IData)(vlSelf->counter_03__DOT__bcd_ones_reg)));
    }
    if ((8U & ((IData)(vlSelf->counter_03__DOT__bcd_ones_reg) 
               ^ (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_ones_reg)))) {
        ++(vlSymsp->__Vcoverage[15]);
        vlSelf->counter_03__DOT____Vtogcov__bcd_ones_reg 
            = ((7U & (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_ones_reg)) 
               | (8U & (IData)(vlSelf->counter_03__DOT__bcd_ones_reg)));
    }
    vlSelf->bcd_ones = vlSelf->counter_03__DOT__bcd_ones_reg;
    if (((IData)(vlSelf->carry_out) ^ (IData)(vlSelf->counter_03__DOT____Vtogcov__carry_out))) {
        ++(vlSymsp->__Vcoverage[11]);
        vlSelf->counter_03__DOT____Vtogcov__carry_out 
            = vlSelf->carry_out;
    }
    if ((1U & ((IData)(vlSelf->bcd_tens) ^ (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_tens)))) {
        ++(vlSymsp->__Vcoverage[7]);
        vlSelf->counter_03__DOT____Vtogcov__bcd_tens 
            = ((0xeU & (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_tens)) 
               | (1U & (IData)(vlSelf->bcd_tens)));
    }
    if ((2U & ((IData)(vlSelf->bcd_tens) ^ (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_tens)))) {
        ++(vlSymsp->__Vcoverage[8]);
        vlSelf->counter_03__DOT____Vtogcov__bcd_tens 
            = ((0xdU & (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_tens)) 
               | (2U & (IData)(vlSelf->bcd_tens)));
    }
    if ((4U & ((IData)(vlSelf->bcd_tens) ^ (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_tens)))) {
        ++(vlSymsp->__Vcoverage[9]);
        vlSelf->counter_03__DOT____Vtogcov__bcd_tens 
            = ((0xbU & (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_tens)) 
               | (4U & (IData)(vlSelf->bcd_tens)));
    }
    if ((8U & ((IData)(vlSelf->bcd_tens) ^ (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_tens)))) {
        ++(vlSymsp->__Vcoverage[10]);
        vlSelf->counter_03__DOT____Vtogcov__bcd_tens 
            = ((7U & (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_tens)) 
               | (8U & (IData)(vlSelf->bcd_tens)));
    }
    if ((1U & ((IData)(vlSelf->bcd_ones) ^ (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_ones)))) {
        ++(vlSymsp->__Vcoverage[3]);
        vlSelf->counter_03__DOT____Vtogcov__bcd_ones 
            = ((0xeU & (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_ones)) 
               | (1U & (IData)(vlSelf->bcd_ones)));
    }
    if ((2U & ((IData)(vlSelf->bcd_ones) ^ (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_ones)))) {
        ++(vlSymsp->__Vcoverage[4]);
        vlSelf->counter_03__DOT____Vtogcov__bcd_ones 
            = ((0xdU & (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_ones)) 
               | (2U & (IData)(vlSelf->bcd_ones)));
    }
    if ((4U & ((IData)(vlSelf->bcd_ones) ^ (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_ones)))) {
        ++(vlSymsp->__Vcoverage[5]);
        vlSelf->counter_03__DOT____Vtogcov__bcd_ones 
            = ((0xbU & (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_ones)) 
               | (4U & (IData)(vlSelf->bcd_ones)));
    }
    if ((8U & ((IData)(vlSelf->bcd_ones) ^ (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_ones)))) {
        ++(vlSymsp->__Vcoverage[6]);
        vlSelf->counter_03__DOT____Vtogcov__bcd_ones 
            = ((7U & (IData)(vlSelf->counter_03__DOT____Vtogcov__bcd_ones)) 
               | (8U & (IData)(vlSelf->bcd_ones)));
    }
}
