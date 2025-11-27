// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vtop.h for the primary calling header

#include "Vtop__pch.h"
#include "Vtop___024root.h"

VL_ATTR_COLD void Vtop___024root___eval_static(Vtop___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vtop__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtop___024root___eval_static\n"); );
}

VL_ATTR_COLD void Vtop___024root___eval_initial__TOP(Vtop___024root* vlSelf);

VL_ATTR_COLD void Vtop___024root___eval_initial(Vtop___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vtop__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtop___024root___eval_initial\n"); );
    // Body
    Vtop___024root___eval_initial__TOP(vlSelf);
    vlSelf->__Vtrigprevexpr___TOP__clk__0 = vlSelf->clk;
    vlSelf->__Vtrigprevexpr___TOP__Top__DOT____Vcellinp__TriggerCounterImpl__rst_n__0 
        = vlSelf->Top__DOT____Vcellinp__TriggerCounterImpl__rst_n;
}

VL_ATTR_COLD void Vtop___024root___eval_initial__TOP(Vtop___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vtop__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtop___024root___eval_initial__TOP\n"); );
    // Body
    vlSelf->Top__DOT__global_finish = 0U;
    vlSelf->Top__DOT__Driver__DOT__finish = 0U;
    vlSelf->Top__DOT__Driver__DOT__cnt_widx_port0 = 0U;
    vlSelf->Top__DOT__cnt__DOT__widx_port0 = 0U;
    vlSelf->Top__DOT__TriggerCounterImpl__DOT__delta = 1U;
}

VL_ATTR_COLD void Vtop___024root___eval_final(Vtop___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vtop__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtop___024root___eval_final\n"); );
}

#ifdef VL_DEBUG
VL_ATTR_COLD void Vtop___024root___dump_triggers__stl(Vtop___024root* vlSelf);
#endif  // VL_DEBUG
VL_ATTR_COLD bool Vtop___024root___eval_phase__stl(Vtop___024root* vlSelf);

VL_ATTR_COLD void Vtop___024root___eval_settle(Vtop___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vtop__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtop___024root___eval_settle\n"); );
    // Init
    IData/*31:0*/ __VstlIterCount;
    CData/*0:0*/ __VstlContinue;
    // Body
    __VstlIterCount = 0U;
    vlSelf->__VstlFirstIteration = 1U;
    __VstlContinue = 1U;
    while (__VstlContinue) {
        if (VL_UNLIKELY((0x64U < __VstlIterCount))) {
#ifdef VL_DEBUG
            Vtop___024root___dump_triggers__stl(vlSelf);
#endif
            VL_FATAL_MT("/home/tomorrow_arc1/CS/assassyn/MyCPU/workspace/driver/verilog/sv/hw/Top.sv", 2, "", "Settle region did not converge.");
        }
        __VstlIterCount = ((IData)(1U) + __VstlIterCount);
        __VstlContinue = 0U;
        if (Vtop___024root___eval_phase__stl(vlSelf)) {
            __VstlContinue = 1U;
        }
        vlSelf->__VstlFirstIteration = 0U;
    }
}

#ifdef VL_DEBUG
VL_ATTR_COLD void Vtop___024root___dump_triggers__stl(Vtop___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vtop__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtop___024root___dump_triggers__stl\n"); );
    // Body
    if ((1U & (~ vlSelf->__VstlTriggered.any()))) {
        VL_DBG_MSGF("         No triggers active\n");
    }
    if ((1ULL & vlSelf->__VstlTriggered.word(0U))) {
        VL_DBG_MSGF("         'stl' region trigger index 0 is active: Internal 'stl' trigger - first iteration\n");
    }
}
#endif  // VL_DEBUG

void Vtop___024root___ico_sequent__TOP__0(Vtop___024root* vlSelf);

VL_ATTR_COLD void Vtop___024root___eval_stl(Vtop___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vtop__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtop___024root___eval_stl\n"); );
    // Body
    if ((1ULL & vlSelf->__VstlTriggered.word(0U))) {
        Vtop___024root___ico_sequent__TOP__0(vlSelf);
    }
}

VL_ATTR_COLD void Vtop___024root___eval_triggers__stl(Vtop___024root* vlSelf);

VL_ATTR_COLD bool Vtop___024root___eval_phase__stl(Vtop___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vtop__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtop___024root___eval_phase__stl\n"); );
    // Init
    CData/*0:0*/ __VstlExecute;
    // Body
    Vtop___024root___eval_triggers__stl(vlSelf);
    __VstlExecute = vlSelf->__VstlTriggered.any();
    if (__VstlExecute) {
        Vtop___024root___eval_stl(vlSelf);
    }
    return (__VstlExecute);
}

#ifdef VL_DEBUG
VL_ATTR_COLD void Vtop___024root___dump_triggers__ico(Vtop___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vtop__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtop___024root___dump_triggers__ico\n"); );
    // Body
    if ((1U & (~ vlSelf->__VicoTriggered.any()))) {
        VL_DBG_MSGF("         No triggers active\n");
    }
    if ((1ULL & vlSelf->__VicoTriggered.word(0U))) {
        VL_DBG_MSGF("         'ico' region trigger index 0 is active: Internal 'ico' trigger - first iteration\n");
    }
}
#endif  // VL_DEBUG

#ifdef VL_DEBUG
VL_ATTR_COLD void Vtop___024root___dump_triggers__act(Vtop___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vtop__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtop___024root___dump_triggers__act\n"); );
    // Body
    if ((1U & (~ vlSelf->__VactTriggered.any()))) {
        VL_DBG_MSGF("         No triggers active\n");
    }
    if ((1ULL & vlSelf->__VactTriggered.word(0U))) {
        VL_DBG_MSGF("         'act' region trigger index 0 is active: @(posedge clk)\n");
    }
    if ((2ULL & vlSelf->__VactTriggered.word(0U))) {
        VL_DBG_MSGF("         'act' region trigger index 1 is active: @(negedge Top.__Vcellinp__TriggerCounterImpl__rst_n or posedge clk)\n");
    }
}
#endif  // VL_DEBUG

#ifdef VL_DEBUG
VL_ATTR_COLD void Vtop___024root___dump_triggers__nba(Vtop___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vtop__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtop___024root___dump_triggers__nba\n"); );
    // Body
    if ((1U & (~ vlSelf->__VnbaTriggered.any()))) {
        VL_DBG_MSGF("         No triggers active\n");
    }
    if ((1ULL & vlSelf->__VnbaTriggered.word(0U))) {
        VL_DBG_MSGF("         'nba' region trigger index 0 is active: @(posedge clk)\n");
    }
    if ((2ULL & vlSelf->__VnbaTriggered.word(0U))) {
        VL_DBG_MSGF("         'nba' region trigger index 1 is active: @(negedge Top.__Vcellinp__TriggerCounterImpl__rst_n or posedge clk)\n");
    }
}
#endif  // VL_DEBUG

VL_ATTR_COLD void Vtop___024root___ctor_var_reset(Vtop___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vtop__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vtop___024root___ctor_var_reset\n"); );
    // Body
    vlSelf->clk = VL_RAND_RESET_I(1);
    vlSelf->rst = VL_RAND_RESET_I(1);
    vlSelf->global_cycle_count = VL_RAND_RESET_Q(64);
    vlSelf->global_finish = VL_RAND_RESET_I(1);
    vlSelf->Top__DOT__clk = VL_RAND_RESET_I(1);
    vlSelf->Top__DOT__rst = VL_RAND_RESET_I(1);
    vlSelf->Top__DOT__global_cycle_count = VL_RAND_RESET_Q(64);
    vlSelf->Top__DOT__global_finish = VL_RAND_RESET_I(1);
    vlSelf->Top__DOT___Driver_executed = VL_RAND_RESET_I(1);
    vlSelf->Top__DOT___Driver_cnt_w_port0 = VL_RAND_RESET_I(1);
    vlSelf->Top__DOT___Driver_cnt_wdata_port0 = VL_RAND_RESET_I(32);
    vlSelf->Top__DOT___TriggerCounterImpl_pop_valid = VL_RAND_RESET_I(1);
    vlSelf->Top__DOT___cnt_rdata_port0 = VL_RAND_RESET_I(32);
    vlSelf->Top__DOT___cnt_rdata_port1 = VL_RAND_RESET_I(32);
    vlSelf->Top__DOT___GEN = VL_RAND_RESET_Q(64);
    vlSelf->Top__DOT____Vcellinp__TriggerCounterImpl__rst_n = VL_RAND_RESET_I(1);
    vlSelf->Top__DOT__cnt__DOT__clk = VL_RAND_RESET_I(1);
    vlSelf->Top__DOT__cnt__DOT__rst = VL_RAND_RESET_I(1);
    vlSelf->Top__DOT__cnt__DOT__w_port0 = VL_RAND_RESET_I(1);
    vlSelf->Top__DOT__cnt__DOT__widx_port0 = VL_RAND_RESET_I(1);
    vlSelf->Top__DOT__cnt__DOT__wdata_port0 = VL_RAND_RESET_I(32);
    vlSelf->Top__DOT__cnt__DOT__rdata_port0 = VL_RAND_RESET_I(32);
    vlSelf->Top__DOT__cnt__DOT__rdata_port1 = VL_RAND_RESET_I(32);
    vlSelf->Top__DOT__cnt__DOT___GEN = VL_RAND_RESET_I(32);
    vlSelf->Top__DOT__cnt__DOT___GEN_0 = VL_RAND_RESET_I(32);
    vlSelf->Top__DOT__TriggerCounterImpl__DOT__clk = VL_RAND_RESET_I(1);
    vlSelf->Top__DOT__TriggerCounterImpl__DOT__rst_n = VL_RAND_RESET_I(1);
    vlSelf->Top__DOT__TriggerCounterImpl__DOT__delta = VL_RAND_RESET_I(8);
    vlSelf->Top__DOT__TriggerCounterImpl__DOT__delta_ready = VL_RAND_RESET_I(1);
    vlSelf->Top__DOT__TriggerCounterImpl__DOT__pop_ready = VL_RAND_RESET_I(1);
    vlSelf->Top__DOT__TriggerCounterImpl__DOT__pop_valid = VL_RAND_RESET_I(1);
    vlSelf->Top__DOT__TriggerCounterImpl__DOT__count = VL_RAND_RESET_I(8);
    vlSelf->Top__DOT__TriggerCounterImpl__DOT__temp = VL_RAND_RESET_I(8);
    vlSelf->Top__DOT__TriggerCounterImpl__DOT__new_count = VL_RAND_RESET_I(8);
    vlSelf->Top__DOT__Driver__DOT__clk = VL_RAND_RESET_I(1);
    vlSelf->Top__DOT__Driver__DOT__rst = VL_RAND_RESET_I(1);
    vlSelf->Top__DOT__Driver__DOT__cycle_count = VL_RAND_RESET_Q(64);
    vlSelf->Top__DOT__Driver__DOT__trigger_counter_pop_valid = VL_RAND_RESET_I(1);
    vlSelf->Top__DOT__Driver__DOT__cnt_rdata_port0 = VL_RAND_RESET_I(32);
    vlSelf->Top__DOT__Driver__DOT__cnt_rdata_port1 = VL_RAND_RESET_I(32);
    vlSelf->Top__DOT__Driver__DOT__executed = VL_RAND_RESET_I(1);
    vlSelf->Top__DOT__Driver__DOT__finish = VL_RAND_RESET_I(1);
    vlSelf->Top__DOT__Driver__DOT__cnt_w_port0 = VL_RAND_RESET_I(1);
    vlSelf->Top__DOT__Driver__DOT__cnt_wdata_port0 = VL_RAND_RESET_I(32);
    vlSelf->Top__DOT__Driver__DOT__cnt_widx_port0 = VL_RAND_RESET_I(1);
    vlSelf->Top__DOT__Driver__DOT__expose_Driver_cnt_rd_1 = VL_RAND_RESET_I(32);
    vlSelf->Top__DOT__Driver__DOT__valid_Driver_cnt_rd_1 = VL_RAND_RESET_I(1);
    vlSelf->__Vtrigprevexpr___TOP__clk__0 = VL_RAND_RESET_I(1);
    vlSelf->__Vtrigprevexpr___TOP__Top__DOT____Vcellinp__TriggerCounterImpl__rst_n__0 = VL_RAND_RESET_I(1);
}
