// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design internal header
// See Vtop.h for the primary calling header

#ifndef VERILATED_VTOP___024ROOT_H_
#define VERILATED_VTOP___024ROOT_H_  // guard

#include "verilated.h"


class Vtop__Syms;

class alignas(VL_CACHE_LINE_BYTES) Vtop___024root final : public VerilatedModule {
  public:

    // DESIGN SPECIFIC STATE
    VL_IN8(clk,0,0);
    CData/*0:0*/ Top__DOT____Vcellinp__TriggerCounterImpl__rst_n;
    VL_IN8(rst,0,0);
    VL_OUT8(global_finish,0,0);
    CData/*0:0*/ Top__DOT__clk;
    CData/*0:0*/ Top__DOT__rst;
    CData/*0:0*/ Top__DOT__global_finish;
    CData/*0:0*/ Top__DOT___Driver_executed;
    CData/*0:0*/ Top__DOT___Driver_cnt_w_port0;
    CData/*0:0*/ Top__DOT___TriggerCounterImpl_pop_valid;
    CData/*0:0*/ Top__DOT__cnt__DOT__clk;
    CData/*0:0*/ Top__DOT__cnt__DOT__rst;
    CData/*0:0*/ Top__DOT__cnt__DOT__w_port0;
    CData/*0:0*/ Top__DOT__cnt__DOT__widx_port0;
    CData/*0:0*/ Top__DOT__TriggerCounterImpl__DOT__clk;
    CData/*0:0*/ Top__DOT__TriggerCounterImpl__DOT__rst_n;
    CData/*7:0*/ Top__DOT__TriggerCounterImpl__DOT__delta;
    CData/*0:0*/ Top__DOT__TriggerCounterImpl__DOT__delta_ready;
    CData/*0:0*/ Top__DOT__TriggerCounterImpl__DOT__pop_ready;
    CData/*0:0*/ Top__DOT__TriggerCounterImpl__DOT__pop_valid;
    CData/*7:0*/ Top__DOT__TriggerCounterImpl__DOT__count;
    CData/*7:0*/ Top__DOT__TriggerCounterImpl__DOT__temp;
    CData/*7:0*/ Top__DOT__TriggerCounterImpl__DOT__new_count;
    CData/*0:0*/ Top__DOT__Driver__DOT__clk;
    CData/*0:0*/ Top__DOT__Driver__DOT__rst;
    CData/*0:0*/ Top__DOT__Driver__DOT__trigger_counter_pop_valid;
    CData/*0:0*/ Top__DOT__Driver__DOT__executed;
    CData/*0:0*/ Top__DOT__Driver__DOT__finish;
    CData/*0:0*/ Top__DOT__Driver__DOT__cnt_w_port0;
    CData/*0:0*/ Top__DOT__Driver__DOT__cnt_widx_port0;
    CData/*0:0*/ Top__DOT__Driver__DOT__valid_Driver_cnt_rd_1;
    CData/*0:0*/ __VstlFirstIteration;
    CData/*0:0*/ __VicoFirstIteration;
    CData/*0:0*/ __Vtrigprevexpr___TOP__clk__0;
    CData/*0:0*/ __Vtrigprevexpr___TOP__Top__DOT____Vcellinp__TriggerCounterImpl__rst_n__0;
    CData/*0:0*/ __VactContinue;
    IData/*31:0*/ Top__DOT___Driver_cnt_wdata_port0;
    IData/*31:0*/ Top__DOT___cnt_rdata_port0;
    IData/*31:0*/ Top__DOT___cnt_rdata_port1;
    IData/*31:0*/ Top__DOT__cnt__DOT__wdata_port0;
    IData/*31:0*/ Top__DOT__cnt__DOT__rdata_port0;
    IData/*31:0*/ Top__DOT__cnt__DOT__rdata_port1;
    IData/*31:0*/ Top__DOT__cnt__DOT___GEN;
    IData/*31:0*/ Top__DOT__cnt__DOT___GEN_0;
    IData/*31:0*/ Top__DOT__Driver__DOT__cnt_rdata_port0;
    IData/*31:0*/ Top__DOT__Driver__DOT__cnt_rdata_port1;
    IData/*31:0*/ Top__DOT__Driver__DOT__cnt_wdata_port0;
    IData/*31:0*/ Top__DOT__Driver__DOT__expose_Driver_cnt_rd_1;
    IData/*31:0*/ __VactIterCount;
    VL_OUT64(global_cycle_count,63,0);
    QData/*63:0*/ Top__DOT__global_cycle_count;
    QData/*63:0*/ Top__DOT___GEN;
    QData/*63:0*/ Top__DOT__Driver__DOT__cycle_count;
    VlTriggerVec<1> __VstlTriggered;
    VlTriggerVec<1> __VicoTriggered;
    VlTriggerVec<2> __VactTriggered;
    VlTriggerVec<2> __VnbaTriggered;

    // INTERNAL VARIABLES
    Vtop__Syms* const vlSymsp;

    // PARAMETERS
    static constexpr QData/*63:0*/ Top__DOT__TriggerCounterImpl__DOT__WIDTH = 8ULL;

    // CONSTRUCTORS
    Vtop___024root(Vtop__Syms* symsp, const char* v__name);
    ~Vtop___024root();
    VL_UNCOPYABLE(Vtop___024root);

    // INTERNAL METHODS
    void __Vconfigure(bool first);
};


#endif  // guard
