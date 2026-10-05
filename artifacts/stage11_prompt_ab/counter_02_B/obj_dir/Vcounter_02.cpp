// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Model implementation (design independent parts)

#include "Vcounter_02__pch.h"

//============================================================
// Constructors

Vcounter_02::Vcounter_02(VerilatedContext* _vcontextp__, const char* _vcname__)
    : VerilatedModel{*_vcontextp__}
    , vlSymsp{new Vcounter_02__Syms(contextp(), _vcname__, this)}
    , clk{vlSymsp->TOP.clk}
    , rst_n{vlSymsp->TOP.rst_n}
    , en{vlSymsp->TOP.en}
    , gray{vlSymsp->TOP.gray}
    , rootp{&(vlSymsp->TOP)}
{
    // Register model with the context
    contextp()->addModel(this);
}

Vcounter_02::Vcounter_02(const char* _vcname__)
    : Vcounter_02(Verilated::threadContextp(), _vcname__)
{
}

//============================================================
// Destructor

Vcounter_02::~Vcounter_02() {
    delete vlSymsp;
}

//============================================================
// Evaluation function

#ifdef VL_DEBUG
void Vcounter_02___024root___eval_debug_assertions(Vcounter_02___024root* vlSelf);
#endif  // VL_DEBUG
void Vcounter_02___024root___eval_static(Vcounter_02___024root* vlSelf);
void Vcounter_02___024root___eval_initial(Vcounter_02___024root* vlSelf);
void Vcounter_02___024root___eval_settle(Vcounter_02___024root* vlSelf);
void Vcounter_02___024root___eval(Vcounter_02___024root* vlSelf);

void Vcounter_02::eval_step() {
    VL_DEBUG_IF(VL_DBG_MSGF("+++++TOP Evaluate Vcounter_02::eval_step\n"); );
#ifdef VL_DEBUG
    // Debug assertions
    Vcounter_02___024root___eval_debug_assertions(&(vlSymsp->TOP));
#endif  // VL_DEBUG
    vlSymsp->__Vm_deleter.deleteAll();
    if (VL_UNLIKELY(!vlSymsp->__Vm_didInit)) {
        vlSymsp->__Vm_didInit = true;
        VL_DEBUG_IF(VL_DBG_MSGF("+ Initial\n"););
        Vcounter_02___024root___eval_static(&(vlSymsp->TOP));
        Vcounter_02___024root___eval_initial(&(vlSymsp->TOP));
        Vcounter_02___024root___eval_settle(&(vlSymsp->TOP));
    }
    VL_DEBUG_IF(VL_DBG_MSGF("+ Eval\n"););
    Vcounter_02___024root___eval(&(vlSymsp->TOP));
    // Evaluate cleanup
    Verilated::endOfEval(vlSymsp->__Vm_evalMsgQp);
}

//============================================================
// Events and timing
bool Vcounter_02::eventsPending() { return false; }

uint64_t Vcounter_02::nextTimeSlot() {
    VL_FATAL_MT(__FILE__, __LINE__, "", "%Error: No delays in the design");
    return 0;
}

//============================================================
// Utilities

const char* Vcounter_02::name() const {
    return vlSymsp->name();
}

//============================================================
// Invoke final blocks

void Vcounter_02___024root___eval_final(Vcounter_02___024root* vlSelf);

VL_ATTR_COLD void Vcounter_02::final() {
    Vcounter_02___024root___eval_final(&(vlSymsp->TOP));
}

//============================================================
// Implementations of abstract methods from VerilatedModel

const char* Vcounter_02::hierName() const { return vlSymsp->name(); }
const char* Vcounter_02::modelName() const { return "Vcounter_02"; }
unsigned Vcounter_02::threads() const { return 1; }
void Vcounter_02::prepareClone() const { contextp()->prepareClone(); }
void Vcounter_02::atClone() const {
    contextp()->threadPoolpOnClone();
}

//============================================================
// Trace configuration

VL_ATTR_COLD void Vcounter_02::trace(VerilatedVcdC* tfp, int levels, int options) {
    vl_fatal(__FILE__, __LINE__, __FILE__,"'Vcounter_02::trace()' called on model that was Verilated without --trace option");
}
