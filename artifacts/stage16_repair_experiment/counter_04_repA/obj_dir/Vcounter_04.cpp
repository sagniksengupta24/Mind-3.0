// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Model implementation (design independent parts)

#include "Vcounter_04__pch.h"

//============================================================
// Constructors

Vcounter_04::Vcounter_04(VerilatedContext* _vcontextp__, const char* _vcname__)
    : VerilatedModel{*_vcontextp__}
    , vlSymsp{new Vcounter_04__Syms(contextp(), _vcname__, this)}
    , clk{vlSymsp->TOP.clk}
    , rst_n{vlSymsp->TOP.rst_n}
    , q{vlSymsp->TOP.q}
    , rootp{&(vlSymsp->TOP)}
{
    // Register model with the context
    contextp()->addModel(this);
}

Vcounter_04::Vcounter_04(const char* _vcname__)
    : Vcounter_04(Verilated::threadContextp(), _vcname__)
{
}

//============================================================
// Destructor

Vcounter_04::~Vcounter_04() {
    delete vlSymsp;
}

//============================================================
// Evaluation function

#ifdef VL_DEBUG
void Vcounter_04___024root___eval_debug_assertions(Vcounter_04___024root* vlSelf);
#endif  // VL_DEBUG
void Vcounter_04___024root___eval_static(Vcounter_04___024root* vlSelf);
void Vcounter_04___024root___eval_initial(Vcounter_04___024root* vlSelf);
void Vcounter_04___024root___eval_settle(Vcounter_04___024root* vlSelf);
void Vcounter_04___024root___eval(Vcounter_04___024root* vlSelf);

void Vcounter_04::eval_step() {
    VL_DEBUG_IF(VL_DBG_MSGF("+++++TOP Evaluate Vcounter_04::eval_step\n"); );
#ifdef VL_DEBUG
    // Debug assertions
    Vcounter_04___024root___eval_debug_assertions(&(vlSymsp->TOP));
#endif  // VL_DEBUG
    vlSymsp->__Vm_deleter.deleteAll();
    if (VL_UNLIKELY(!vlSymsp->__Vm_didInit)) {
        vlSymsp->__Vm_didInit = true;
        VL_DEBUG_IF(VL_DBG_MSGF("+ Initial\n"););
        Vcounter_04___024root___eval_static(&(vlSymsp->TOP));
        Vcounter_04___024root___eval_initial(&(vlSymsp->TOP));
        Vcounter_04___024root___eval_settle(&(vlSymsp->TOP));
    }
    VL_DEBUG_IF(VL_DBG_MSGF("+ Eval\n"););
    Vcounter_04___024root___eval(&(vlSymsp->TOP));
    // Evaluate cleanup
    Verilated::endOfEval(vlSymsp->__Vm_evalMsgQp);
}

//============================================================
// Events and timing
bool Vcounter_04::eventsPending() { return false; }

uint64_t Vcounter_04::nextTimeSlot() {
    VL_FATAL_MT(__FILE__, __LINE__, "", "%Error: No delays in the design");
    return 0;
}

//============================================================
// Utilities

const char* Vcounter_04::name() const {
    return vlSymsp->name();
}

//============================================================
// Invoke final blocks

void Vcounter_04___024root___eval_final(Vcounter_04___024root* vlSelf);

VL_ATTR_COLD void Vcounter_04::final() {
    Vcounter_04___024root___eval_final(&(vlSymsp->TOP));
}

//============================================================
// Implementations of abstract methods from VerilatedModel

const char* Vcounter_04::hierName() const { return vlSymsp->name(); }
const char* Vcounter_04::modelName() const { return "Vcounter_04"; }
unsigned Vcounter_04::threads() const { return 1; }
void Vcounter_04::prepareClone() const { contextp()->prepareClone(); }
void Vcounter_04::atClone() const {
    contextp()->threadPoolpOnClone();
}

//============================================================
// Trace configuration

VL_ATTR_COLD void Vcounter_04::trace(VerilatedVcdC* tfp, int levels, int options) {
    vl_fatal(__FILE__, __LINE__, __FILE__,"'Vcounter_04::trace()' called on model that was Verilated without --trace option");
}
