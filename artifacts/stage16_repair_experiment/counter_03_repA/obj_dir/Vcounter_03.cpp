// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Model implementation (design independent parts)

#include "Vcounter_03__pch.h"

//============================================================
// Constructors

Vcounter_03::Vcounter_03(VerilatedContext* _vcontextp__, const char* _vcname__)
    : VerilatedModel{*_vcontextp__}
    , vlSymsp{new Vcounter_03__Syms(contextp(), _vcname__, this)}
    , clk{vlSymsp->TOP.clk}
    , rst_n{vlSymsp->TOP.rst_n}
    , en{vlSymsp->TOP.en}
    , bcd_ones{vlSymsp->TOP.bcd_ones}
    , bcd_tens{vlSymsp->TOP.bcd_tens}
    , carry_out{vlSymsp->TOP.carry_out}
    , rootp{&(vlSymsp->TOP)}
{
    // Register model with the context
    contextp()->addModel(this);
}

Vcounter_03::Vcounter_03(const char* _vcname__)
    : Vcounter_03(Verilated::threadContextp(), _vcname__)
{
}

//============================================================
// Destructor

Vcounter_03::~Vcounter_03() {
    delete vlSymsp;
}

//============================================================
// Evaluation function

#ifdef VL_DEBUG
void Vcounter_03___024root___eval_debug_assertions(Vcounter_03___024root* vlSelf);
#endif  // VL_DEBUG
void Vcounter_03___024root___eval_static(Vcounter_03___024root* vlSelf);
void Vcounter_03___024root___eval_initial(Vcounter_03___024root* vlSelf);
void Vcounter_03___024root___eval_settle(Vcounter_03___024root* vlSelf);
void Vcounter_03___024root___eval(Vcounter_03___024root* vlSelf);

void Vcounter_03::eval_step() {
    VL_DEBUG_IF(VL_DBG_MSGF("+++++TOP Evaluate Vcounter_03::eval_step\n"); );
#ifdef VL_DEBUG
    // Debug assertions
    Vcounter_03___024root___eval_debug_assertions(&(vlSymsp->TOP));
#endif  // VL_DEBUG
    vlSymsp->__Vm_deleter.deleteAll();
    if (VL_UNLIKELY(!vlSymsp->__Vm_didInit)) {
        vlSymsp->__Vm_didInit = true;
        VL_DEBUG_IF(VL_DBG_MSGF("+ Initial\n"););
        Vcounter_03___024root___eval_static(&(vlSymsp->TOP));
        Vcounter_03___024root___eval_initial(&(vlSymsp->TOP));
        Vcounter_03___024root___eval_settle(&(vlSymsp->TOP));
    }
    VL_DEBUG_IF(VL_DBG_MSGF("+ Eval\n"););
    Vcounter_03___024root___eval(&(vlSymsp->TOP));
    // Evaluate cleanup
    Verilated::endOfEval(vlSymsp->__Vm_evalMsgQp);
}

//============================================================
// Events and timing
bool Vcounter_03::eventsPending() { return false; }

uint64_t Vcounter_03::nextTimeSlot() {
    VL_FATAL_MT(__FILE__, __LINE__, "", "%Error: No delays in the design");
    return 0;
}

//============================================================
// Utilities

const char* Vcounter_03::name() const {
    return vlSymsp->name();
}

//============================================================
// Invoke final blocks

void Vcounter_03___024root___eval_final(Vcounter_03___024root* vlSelf);

VL_ATTR_COLD void Vcounter_03::final() {
    Vcounter_03___024root___eval_final(&(vlSymsp->TOP));
}

//============================================================
// Implementations of abstract methods from VerilatedModel

const char* Vcounter_03::hierName() const { return vlSymsp->name(); }
const char* Vcounter_03::modelName() const { return "Vcounter_03"; }
unsigned Vcounter_03::threads() const { return 1; }
void Vcounter_03::prepareClone() const { contextp()->prepareClone(); }
void Vcounter_03::atClone() const {
    contextp()->threadPoolpOnClone();
}

//============================================================
// Trace configuration

VL_ATTR_COLD void Vcounter_03::trace(VerilatedVcdC* tfp, int levels, int options) {
    vl_fatal(__FILE__, __LINE__, __FILE__,"'Vcounter_03::trace()' called on model that was Verilated without --trace option");
}
