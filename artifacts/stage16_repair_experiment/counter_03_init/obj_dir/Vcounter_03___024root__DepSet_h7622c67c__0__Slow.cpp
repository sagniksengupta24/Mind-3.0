// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vcounter_03.h for the primary calling header

#include "Vcounter_03__pch.h"
#include "Vcounter_03__Syms.h"
#include "Vcounter_03___024root.h"

#ifdef VL_DEBUG
VL_ATTR_COLD void Vcounter_03___024root___dump_triggers__stl(Vcounter_03___024root* vlSelf);
#endif  // VL_DEBUG

VL_ATTR_COLD void Vcounter_03___024root___eval_triggers__stl(Vcounter_03___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_03__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_03___024root___eval_triggers__stl\n"); );
    // Body
    vlSelf->__VstlTriggered.set(0U, (IData)(vlSelf->__VstlFirstIteration));
#ifdef VL_DEBUG
    if (VL_UNLIKELY(vlSymsp->_vm_contextp__->debug())) {
        Vcounter_03___024root___dump_triggers__stl(vlSelf);
    }
#endif
}

VL_ATTR_COLD void Vcounter_03___024root___stl_sequent__TOP__0(Vcounter_03___024root* vlSelf) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_03__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_03___024root___stl_sequent__TOP__0\n"); );
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
    if (((IData)(vlSelf->counter_03__DOT__carry_out_reg) 
         ^ (IData)(vlSelf->counter_03__DOT____Vtogcov__carry_out_reg))) {
        ++(vlSymsp->__Vcoverage[20]);
        vlSelf->counter_03__DOT____Vtogcov__carry_out_reg 
            = vlSelf->counter_03__DOT__carry_out_reg;
    }
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
    vlSelf->carry_out = vlSelf->counter_03__DOT__carry_out_reg;
    vlSelf->bcd_ones = vlSelf->counter_03__DOT__bcd_ones_reg;
    vlSelf->bcd_tens = vlSelf->counter_03__DOT__bcd_tens_reg;
    if (((IData)(vlSelf->carry_out) ^ (IData)(vlSelf->counter_03__DOT____Vtogcov__carry_out))) {
        ++(vlSymsp->__Vcoverage[11]);
        vlSelf->counter_03__DOT____Vtogcov__carry_out 
            = vlSelf->carry_out;
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
}

VL_ATTR_COLD void Vcounter_03___024root___configure_coverage(Vcounter_03___024root* vlSelf, bool first) {
    if (false && vlSelf) {}  // Prevent unused
    Vcounter_03__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_03___024root___configure_coverage\n"); );
    // Body
    if (false && first) {}  // Prevent unused
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[0]), first, "counter_03.sv", 2, 9, ".counter_03", "v_toggle/counter_03", "clk", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[1]), first, "counter_03.sv", 3, 9, ".counter_03", "v_toggle/counter_03", "rst_n", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[2]), first, "counter_03.sv", 4, 9, ".counter_03", "v_toggle/counter_03", "en", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[3]), first, "counter_03.sv", 5, 16, ".counter_03", "v_toggle/counter_03", "bcd_ones[0]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[4]), first, "counter_03.sv", 5, 16, ".counter_03", "v_toggle/counter_03", "bcd_ones[1]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[5]), first, "counter_03.sv", 5, 16, ".counter_03", "v_toggle/counter_03", "bcd_ones[2]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[6]), first, "counter_03.sv", 5, 16, ".counter_03", "v_toggle/counter_03", "bcd_ones[3]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[7]), first, "counter_03.sv", 6, 16, ".counter_03", "v_toggle/counter_03", "bcd_tens[0]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[8]), first, "counter_03.sv", 6, 16, ".counter_03", "v_toggle/counter_03", "bcd_tens[1]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[9]), first, "counter_03.sv", 6, 16, ".counter_03", "v_toggle/counter_03", "bcd_tens[2]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[10]), first, "counter_03.sv", 6, 16, ".counter_03", "v_toggle/counter_03", "bcd_tens[3]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[11]), first, "counter_03.sv", 7, 10, ".counter_03", "v_toggle/counter_03", "carry_out", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[12]), first, "counter_03.sv", 10, 13, ".counter_03", "v_toggle/counter_03", "bcd_ones_reg[0]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[13]), first, "counter_03.sv", 10, 13, ".counter_03", "v_toggle/counter_03", "bcd_ones_reg[1]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[14]), first, "counter_03.sv", 10, 13, ".counter_03", "v_toggle/counter_03", "bcd_ones_reg[2]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[15]), first, "counter_03.sv", 10, 13, ".counter_03", "v_toggle/counter_03", "bcd_ones_reg[3]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[16]), first, "counter_03.sv", 11, 13, ".counter_03", "v_toggle/counter_03", "bcd_tens_reg[0]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[17]), first, "counter_03.sv", 11, 13, ".counter_03", "v_toggle/counter_03", "bcd_tens_reg[1]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[18]), first, "counter_03.sv", 11, 13, ".counter_03", "v_toggle/counter_03", "bcd_tens_reg[2]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[19]), first, "counter_03.sv", 11, 13, ".counter_03", "v_toggle/counter_03", "bcd_tens_reg[3]", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[20]), first, "counter_03.sv", 12, 7, ".counter_03", "v_toggle/counter_03", "carry_out_reg", "");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[21]), first, "counter_03.sv", 22, 9, ".counter_03", "v_branch/counter_03", "if", "22-24");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[22]), first, "counter_03.sv", 22, 10, ".counter_03", "v_branch/counter_03", "else", "25-27");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[23]), first, "counter_03.sv", 20, 7, ".counter_03", "v_branch/counter_03", "if", "20-21");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[24]), first, "counter_03.sv", 20, 8, ".counter_03", "v_branch/counter_03", "else", "29-31");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[25]), first, "counter_03.sv", 19, 14, ".counter_03", "v_line/counter_03", "if", "19");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[26]), first, "counter_03.sv", 19, 15, ".counter_03", "v_line/counter_03", "else", "33-34");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[27]), first, "counter_03.sv", 15, 5, ".counter_03", "v_line/counter_03", "elsif", "15-18");
    vlSelf->__vlCoverInsert(&(vlSymsp->__Vcoverage[28]), first, "counter_03.sv", 14, 3, ".counter_03", "v_line/counter_03", "block", "14");
}
