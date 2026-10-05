// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Model implementation (design independent parts)

#include "Vcounter_10__pch.h"

//============================================================
// Constructors

Vcounter_10::Vcounter_10(VerilatedContext* _vcontextp__, const char* _vcname__)
    : VerilatedModel{*_vcontextp__}
    , vlSymsp{new Vcounter_10__Syms(contextp(), _vcname__, this)}
    , clk{vlSymsp->TOP.clk}
    , rst_n{vlSymsp->TOP.rst_n}
    , strobe{vlSymsp->TOP.strobe}
    , count{vlSymsp->TOP.count}
    , rootp{&(vlSymsp->TOP)}
{
    // Register model with the context
    contextp()->addModel(this);
}

Vcounter_10::Vcounter_10(const char* _vcname__)
    : Vcounter_10(Verilated::threadContextp(), _vcname__)
{
}

//============================================================
// Destructor

Vcounter_10::~Vcounter_10() {
    delete vlSymsp;
}

//============================================================
// Evaluation function

#ifdef VL_DEBUG
void Vcounter_10___024root___eval_debug_assertions(Vcounter_10___024root* vlSelf);
#endif  // VL_DEBUG
void Vcounter_10___024root___eval_static(Vcounter_10___024root* vlSelf);
void Vcounter_10___024root___eval_initial(Vcounter_10___024root* vlSelf);
void Vcounter_10___024root___eval_settle(Vcounter_10___024root* vlSelf);
void Vcounter_10___024root___eval(Vcounter_10___024root* vlSelf);

void Vcounter_10::eval_step() {
    VL_DEBUG_IF(VL_DBG_MSGF("+++++TOP Evaluate Vcounter_10::eval_step\n"); );
#ifdef VL_DEBUG
    // Debug assertions
    Vcounter_10___024root___eval_debug_assertions(&(vlSymsp->TOP));
#endif  // VL_DEBUG
    vlSymsp->__Vm_deleter.deleteAll();
    if (VL_UNLIKELY(!vlSymsp->__Vm_didInit)) {
        vlSymsp->__Vm_didInit = true;
        VL_DEBUG_IF(VL_DBG_MSGF("+ Initial\n"););
        Vcounter_10___024root___eval_static(&(vlSymsp->TOP));
        Vcounter_10___024root___eval_initial(&(vlSymsp->TOP));
        Vcounter_10___024root___eval_settle(&(vlSymsp->TOP));
    }
    VL_DEBUG_IF(VL_DBG_MSGF("+ Eval\n"););
    Vcounter_10___024root___eval(&(vlSymsp->TOP));
    // Evaluate cleanup
    Verilated::endOfEval(vlSymsp->__Vm_evalMsgQp);
}

//============================================================
// Events and timing
bool Vcounter_10::eventsPending() { return false; }

uint64_t Vcounter_10::nextTimeSlot() {
    VL_FATAL_MT(__FILE__, __LINE__, "", "%Error: No delays in the design");
    return 0;
}

//============================================================
// Utilities

const char* Vcounter_10::name() const {
    return vlSymsp->name();
}

//============================================================
// Invoke final blocks

void Vcounter_10___024root___eval_final(Vcounter_10___024root* vlSelf);

VL_ATTR_COLD void Vcounter_10::final() {
    Vcounter_10___024root___eval_final(&(vlSymsp->TOP));
}

//============================================================
// Implementations of abstract methods from VerilatedModel

const char* Vcounter_10::hierName() const { return vlSymsp->name(); }
const char* Vcounter_10::modelName() const { return "Vcounter_10"; }
unsigned Vcounter_10::threads() const { return 1; }
void Vcounter_10::prepareClone() const { contextp()->prepareClone(); }
void Vcounter_10::atClone() const {
    contextp()->threadPoolpOnClone();
}

//============================================================
// Trace configuration

VL_ATTR_COLD void Vcounter_10::trace(VerilatedVcdC* tfp, int levels, int options) {
    vl_fatal(__FILE__, __LINE__, __FILE__,"'Vcounter_10::trace()' called on model that was Verilated without --trace option");
}
