// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vcounter_02.h for the primary calling header

#include "Vcounter_02__pch.h"
#include "Vcounter_02__Syms.h"
#include "Vcounter_02___024root.h"

#ifdef VL_DEBUG
VL_ATTR_COLD void Vcounter_02___024root___dump_triggers__stl(Vcounter_02___024root* vlSelf);
#endif  // VL_DEBUG

VL_ATTR_COLD void Vcounter_02___024root___eval_triggers__stl(Vcounter_02___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_02__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_02___024root___eval_triggers__stl\n"); );
    // Body
    vlSelf->__VstlTriggered.set(0U, (IData)(vlSelf->__VstlFirstIteration));
#ifdef VL_DEBUG
    if (VL_UNLIKELY(vlSymsp->_vm_contextp__->debug())) {
        Vcounter_02___024root___dump_triggers__stl(vlSelf);
    }
#endif
}

VL_ATTR_COLD void Vcounter_02___024root___stl_sequent__TOP__0(Vcounter_02___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_02__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_02___024root___stl_sequent__TOP__0\n"); );
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

VL_ATTR_COLD void Vcounter_02___024root___configure_coverage(Vcounter_02___024root* vlSelf, bool first) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_02__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_02___024root___configure_coverage\n"); );
    // Body
    if (false && first) {}  // Prevent unused
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[0]), first, "counter_02.sv", 2, 9, ".counter_02", "v_toggle/counter_02", "clk", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[1]), first, "counter_02.sv", 3, 9, ".counter_02", "v_toggle/counter_02", "rst_n", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[2]), first, "counter_02.sv", 4, 9, ".counter_02", "v_toggle/counter_02", "en", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[3]), first, "counter_02.sv", 5, 16, ".counter_02", "v_toggle/counter_02", "gray[0]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[4]), first, "counter_02.sv", 5, 16, ".counter_02", "v_toggle/counter_02", "gray[1]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[5]), first, "counter_02.sv", 5, 16, ".counter_02", "v_toggle/counter_02", "gray[2]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[6]), first, "counter_02.sv", 5, 16, ".counter_02", "v_toggle/counter_02", "gray[3]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[7]), first, "counter_02.sv", 8, 13, ".counter_02", "v_toggle/counter_02", "gray_reg[0]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[8]), first, "counter_02.sv", 8, 13, ".counter_02", "v_toggle/counter_02", "gray_reg[1]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[9]), first, "counter_02.sv", 8, 13, ".counter_02", "v_toggle/counter_02", "gray_reg[2]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[10]), first, "counter_02.sv", 8, 13, ".counter_02", "v_toggle/counter_02", "gray_reg[3]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[11]), first, "counter_02.sv", 13, 14, ".counter_02", "v_branch/counter_02", "if", "13-14");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[12]), first, "counter_02.sv", 13, 15, ".counter_02", "v_branch/counter_02", "else", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[13]), first, "counter_02.sv", 11, 5, ".counter_02", "v_line/counter_02", "elsif", "11-12");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[14]), first, "counter_02.sv", 10, 3, ".counter_02", "v_line/counter_02", "block", "10");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[15]), first, "counter_02.sv", 20, 18, ".counter_02", "v_line/counter_02", "block", "20,22-23");
}
