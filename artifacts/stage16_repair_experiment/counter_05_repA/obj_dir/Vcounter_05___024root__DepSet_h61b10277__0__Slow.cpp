// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vcounter_05.h for the primary calling header

#include "Vcounter_05__pch.h"
#include "Vcounter_05__Syms.h"
#include "Vcounter_05___024root.h"

#ifdef VL_DEBUG
VL_ATTR_COLD void Vcounter_05___024root___dump_triggers__stl(Vcounter_05___024root* vlSelf);
#endif  // VL_DEBUG

VL_ATTR_COLD void Vcounter_05___024root___eval_triggers__stl(Vcounter_05___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_05__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_05___024root___eval_triggers__stl\n"); );
    // Body
    vlSelf->__VstlTriggered.set(0U, (IData)(vlSelf->__VstlFirstIteration));
#ifdef VL_DEBUG
    if (VL_UNLIKELY(vlSymsp->_vm_contextp__->debug())) {
        Vcounter_05___024root___dump_triggers__stl(vlSelf);
    }
#endif
}

VL_ATTR_COLD void Vcounter_05___024root___stl_sequent__TOP__0(Vcounter_05___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_05__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_05___024root___stl_sequent__TOP__0\n"); );
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

VL_ATTR_COLD void Vcounter_05___024root___configure_coverage(Vcounter_05___024root* vlSelf, bool first) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_05__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_05___024root___configure_coverage\n"); );
    // Body
    if (false && first) {}  // Prevent unused
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[0]), first, "counter_05.sv", 2, 9, ".counter_05", "v_toggle/counter_05", "clk", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[1]), first, "counter_05.sv", 3, 9, ".counter_05", "v_toggle/counter_05", "rst_n", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[2]), first, "counter_05.sv", 4, 9, ".counter_05", "v_toggle/counter_05", "kick", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[3]), first, "counter_05.sv", 5, 10, ".counter_05", "v_toggle/counter_05", "fault", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[4]), first, "counter_05.sv", 8, 7, ".counter_05", "v_toggle/counter_05", "fault_reg", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[5]), first, "counter_05.sv", 14, 7, ".counter_05", "v_branch/counter_05", "if", "14-15");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[6]), first, "counter_05.sv", 14, 8, ".counter_05", "v_branch/counter_05", "else", "16-17");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[7]), first, "counter_05.sv", 11, 5, ".counter_05", "v_branch/counter_05", "if", "11-12");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[8]), first, "counter_05.sv", 11, 6, ".counter_05", "v_branch/counter_05", "else", "13");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[9]), first, "counter_05.sv", 10, 3, ".counter_05", "v_line/counter_05", "block", "10");
}
