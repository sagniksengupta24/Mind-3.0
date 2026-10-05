// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vcounter_04.h for the primary calling header

#include "Vcounter_04__pch.h"
#include "Vcounter_04__Syms.h"
#include "Vcounter_04___024root.h"

#ifdef VL_DEBUG
VL_ATTR_COLD void Vcounter_04___024root___dump_triggers__stl(Vcounter_04___024root* vlSelf);
#endif  // VL_DEBUG

VL_ATTR_COLD void Vcounter_04___024root___eval_triggers__stl(Vcounter_04___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_04__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_04___024root___eval_triggers__stl\n"); );
    // Body
    vlSelf->__VstlTriggered.set(0U, (IData)(vlSelf->__VstlFirstIteration));
#ifdef VL_DEBUG
    if (VL_UNLIKELY(vlSymsp->_vm_contextp__->debug())) {
        Vcounter_04___024root___dump_triggers__stl(vlSelf);
    }
#endif
}

VL_ATTR_COLD void Vcounter_04___024root___stl_sequent__TOP__0(Vcounter_04___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_04__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_04___024root___stl_sequent__TOP__0\n"); );
    // Body
    if (((IData)(vlSelf->clk) ^ (IData)(vlSelf->counter_04__DOT____Vtogcov__clk))) {
        ++(vlSymsp->__Vcoverage[0]);
        vlSelf->counter_04__DOT____Vtogcov__clk = vlSelf->clk;
    }
    if (((IData)(vlSelf->rst_n) ^ (IData)(vlSelf->counter_04__DOT____Vtogcov__rst_n))) {
        ++(vlSymsp->__Vcoverage[1]);
        vlSelf->counter_04__DOT____Vtogcov__rst_n = vlSelf->rst_n;
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

VL_ATTR_COLD void Vcounter_04___024root___configure_coverage(Vcounter_04___024root* vlSelf, bool first) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_04__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_04___024root___configure_coverage\n"); );
    // Body
    if (false && first) {}  // Prevent unused
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[0]), first, "counter_04.sv", 2, 9, ".counter_04", "v_toggle/counter_04", "clk", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[1]), first, "counter_04.sv", 3, 9, ".counter_04", "v_toggle/counter_04", "rst_n", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[2]), first, "counter_04.sv", 4, 16, ".counter_04", "v_toggle/counter_04", "q[0]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[3]), first, "counter_04.sv", 4, 16, ".counter_04", "v_toggle/counter_04", "q[1]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[4]), first, "counter_04.sv", 4, 16, ".counter_04", "v_toggle/counter_04", "q[2]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[5]), first, "counter_04.sv", 4, 16, ".counter_04", "v_toggle/counter_04", "q[3]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[6]), first, "counter_04.sv", 4, 16, ".counter_04", "v_toggle/counter_04", "q[4]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[7]), first, "counter_04.sv", 4, 16, ".counter_04", "v_toggle/counter_04", "q[5]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[8]), first, "counter_04.sv", 4, 16, ".counter_04", "v_toggle/counter_04", "q[6]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[9]), first, "counter_04.sv", 4, 16, ".counter_04", "v_toggle/counter_04", "q[7]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[10]), first, "counter_04.sv", 7, 13, ".counter_04", "v_toggle/counter_04", "q_reg[0]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[11]), first, "counter_04.sv", 7, 13, ".counter_04", "v_toggle/counter_04", "q_reg[1]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[12]), first, "counter_04.sv", 7, 13, ".counter_04", "v_toggle/counter_04", "q_reg[2]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[13]), first, "counter_04.sv", 7, 13, ".counter_04", "v_toggle/counter_04", "q_reg[3]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[14]), first, "counter_04.sv", 7, 13, ".counter_04", "v_toggle/counter_04", "q_reg[4]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[15]), first, "counter_04.sv", 7, 13, ".counter_04", "v_toggle/counter_04", "q_reg[5]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[16]), first, "counter_04.sv", 7, 13, ".counter_04", "v_toggle/counter_04", "q_reg[6]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[17]), first, "counter_04.sv", 7, 13, ".counter_04", "v_toggle/counter_04", "q_reg[7]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[18]), first, "counter_04.sv", 10, 5, ".counter_04", "v_branch/counter_04", "if", "10-11");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[19]), first, "counter_04.sv", 10, 6, ".counter_04", "v_branch/counter_04", "else", "12-13");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[20]), first, "counter_04.sv", 9, 3, ".counter_04", "v_line/counter_04", "block", "9");
}
