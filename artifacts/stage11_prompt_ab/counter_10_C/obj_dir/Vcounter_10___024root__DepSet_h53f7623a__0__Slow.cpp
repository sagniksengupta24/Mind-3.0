// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vcounter_10.h for the primary calling header

#include "Vcounter_10__pch.h"
#include "Vcounter_10__Syms.h"
#include "Vcounter_10___024root.h"

#ifdef VL_DEBUG
VL_ATTR_COLD void Vcounter_10___024root___dump_triggers__stl(Vcounter_10___024root* vlSelf);
#endif  // VL_DEBUG

VL_ATTR_COLD void Vcounter_10___024root___eval_triggers__stl(Vcounter_10___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_10__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_10___024root___eval_triggers__stl\n"); );
    // Body
    vlSelf->__VstlTriggered.set(0U, (IData)(vlSelf->__VstlFirstIteration));
#ifdef VL_DEBUG
    if (VL_UNLIKELY(vlSymsp->_vm_contextp__->debug())) {
        Vcounter_10___024root___dump_triggers__stl(vlSelf);
    }
#endif
}

VL_ATTR_COLD void Vcounter_10___024root___stl_sequent__TOP__0(Vcounter_10___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_10__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_10___024root___stl_sequent__TOP__0\n"); );
    // Body
    if (((IData)(vlSelf->clk) ^ (IData)(vlSelf->counter_10__DOT____Vtogcov__clk))) {
        ++(vlSymsp->__Vcoverage[0]);
        vlSelf->counter_10__DOT____Vtogcov__clk = vlSelf->clk;
    }
    if (((IData)(vlSelf->rst_n) ^ (IData)(vlSelf->counter_10__DOT____Vtogcov__rst_n))) {
        ++(vlSymsp->__Vcoverage[1]);
        vlSelf->counter_10__DOT____Vtogcov__rst_n = vlSelf->rst_n;
    }
    if (((IData)(vlSelf->strobe) ^ (IData)(vlSelf->counter_10__DOT____Vtogcov__strobe))) {
        ++(vlSymsp->__Vcoverage[2]);
        vlSelf->counter_10__DOT____Vtogcov__strobe 
            = vlSelf->strobe;
    }
    if ((1U & ((IData)(vlSelf->count) ^ (IData)(vlSelf->counter_10__DOT____Vtogcov__count)))) {
        ++(vlSymsp->__Vcoverage[3]);
        vlSelf->counter_10__DOT____Vtogcov__count = 
            ((0xfeU & (IData)(vlSelf->counter_10__DOT____Vtogcov__count)) 
             | (1U & (IData)(vlSelf->count)));
    }
    if ((2U & ((IData)(vlSelf->count) ^ (IData)(vlSelf->counter_10__DOT____Vtogcov__count)))) {
        ++(vlSymsp->__Vcoverage[4]);
        vlSelf->counter_10__DOT____Vtogcov__count = 
            ((0xfdU & (IData)(vlSelf->counter_10__DOT____Vtogcov__count)) 
             | (2U & (IData)(vlSelf->count)));
    }
    if ((4U & ((IData)(vlSelf->count) ^ (IData)(vlSelf->counter_10__DOT____Vtogcov__count)))) {
        ++(vlSymsp->__Vcoverage[5]);
        vlSelf->counter_10__DOT____Vtogcov__count = 
            ((0xfbU & (IData)(vlSelf->counter_10__DOT____Vtogcov__count)) 
             | (4U & (IData)(vlSelf->count)));
    }
    if ((8U & ((IData)(vlSelf->count) ^ (IData)(vlSelf->counter_10__DOT____Vtogcov__count)))) {
        ++(vlSymsp->__Vcoverage[6]);
        vlSelf->counter_10__DOT____Vtogcov__count = 
            ((0xf7U & (IData)(vlSelf->counter_10__DOT____Vtogcov__count)) 
             | (8U & (IData)(vlSelf->count)));
    }
    if ((0x10U & ((IData)(vlSelf->count) ^ (IData)(vlSelf->counter_10__DOT____Vtogcov__count)))) {
        ++(vlSymsp->__Vcoverage[7]);
        vlSelf->counter_10__DOT____Vtogcov__count = 
            ((0xefU & (IData)(vlSelf->counter_10__DOT____Vtogcov__count)) 
             | (0x10U & (IData)(vlSelf->count)));
    }
    if ((0x20U & ((IData)(vlSelf->count) ^ (IData)(vlSelf->counter_10__DOT____Vtogcov__count)))) {
        ++(vlSymsp->__Vcoverage[8]);
        vlSelf->counter_10__DOT____Vtogcov__count = 
            ((0xdfU & (IData)(vlSelf->counter_10__DOT____Vtogcov__count)) 
             | (0x20U & (IData)(vlSelf->count)));
    }
    if ((0x40U & ((IData)(vlSelf->count) ^ (IData)(vlSelf->counter_10__DOT____Vtogcov__count)))) {
        ++(vlSymsp->__Vcoverage[9]);
        vlSelf->counter_10__DOT____Vtogcov__count = 
            ((0xbfU & (IData)(vlSelf->counter_10__DOT____Vtogcov__count)) 
             | (0x40U & (IData)(vlSelf->count)));
    }
    if ((0x80U & ((IData)(vlSelf->count) ^ (IData)(vlSelf->counter_10__DOT____Vtogcov__count)))) {
        ++(vlSymsp->__Vcoverage[10]);
        vlSelf->counter_10__DOT____Vtogcov__count = 
            ((0x7fU & (IData)(vlSelf->counter_10__DOT____Vtogcov__count)) 
             | (0x80U & (IData)(vlSelf->count)));
    }
}

VL_ATTR_COLD void Vcounter_10___024root___configure_coverage(Vcounter_10___024root* vlSelf, bool first) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_10__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_10___024root___configure_coverage\n"); );
    // Body
    if (false && first) {}  // Prevent unused
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[0]), first, "counter_10.sv", 2, 9, ".counter_10", "v_toggle/counter_10", "clk", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[1]), first, "counter_10.sv", 3, 9, ".counter_10", "v_toggle/counter_10", "rst_n", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[2]), first, "counter_10.sv", 4, 9, ".counter_10", "v_toggle/counter_10", "strobe", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[3]), first, "counter_10.sv", 5, 20, ".counter_10", "v_toggle/counter_10", "count[0]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[4]), first, "counter_10.sv", 5, 20, ".counter_10", "v_toggle/counter_10", "count[1]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[5]), first, "counter_10.sv", 5, 20, ".counter_10", "v_toggle/counter_10", "count[2]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[6]), first, "counter_10.sv", 5, 20, ".counter_10", "v_toggle/counter_10", "count[3]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[7]), first, "counter_10.sv", 5, 20, ".counter_10", "v_toggle/counter_10", "count[4]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[8]), first, "counter_10.sv", 5, 20, ".counter_10", "v_toggle/counter_10", "count[5]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[9]), first, "counter_10.sv", 5, 20, ".counter_10", "v_toggle/counter_10", "count[6]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[10]), first, "counter_10.sv", 5, 20, ".counter_10", "v_toggle/counter_10", "count[7]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[11]), first, "counter_10.sv", 11, 7, ".counter_10", "v_branch/counter_10", "if", "11-12");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[12]), first, "counter_10.sv", 11, 8, ".counter_10", "v_branch/counter_10", "else", "13-14");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[13]), first, "counter_10.sv", 8, 5, ".counter_10", "v_branch/counter_10", "if", "8-9");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[14]), first, "counter_10.sv", 8, 6, ".counter_10", "v_branch/counter_10", "else", "10");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[15]), first, "counter_10.sv", 7, 3, ".counter_10", "v_line/counter_10", "block", "7");
}
