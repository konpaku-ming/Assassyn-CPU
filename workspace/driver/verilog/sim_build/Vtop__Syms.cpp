// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Symbol table implementation internals

#include "Vtop__pch.h"
#include "Vtop.h"
#include "Vtop___024root.h"

// FUNCTIONS
Vtop__Syms::~Vtop__Syms()
{

    // Tear down scope hierarchy
    __Vhier.remove(0, &__Vscope_Top);
    __Vhier.remove(&__Vscope_Top, &__Vscope_Top__Driver);
    __Vhier.remove(&__Vscope_Top, &__Vscope_Top__TriggerCounterImpl);
    __Vhier.remove(&__Vscope_Top, &__Vscope_Top__cnt);

}

Vtop__Syms::Vtop__Syms(VerilatedContext* contextp, const char* namep, Vtop* modelp)
    : VerilatedSyms{contextp}
    // Setup internal state of the Syms class
    , __Vm_modelp{modelp}
    // Setup module instances
    , TOP{this, namep}
{
        // Check resources
        Verilated::stackCheck(25);
    // Configure time unit / time precision
    _vm_contextp__->timeunit(-12);
    _vm_contextp__->timeprecision(-12);
    // Setup each module's pointers to their submodules
    // Setup each module's pointer back to symbol table (for public functions)
    TOP.__Vconfigure(true);
    // Setup scopes
    __Vscope_TOP.configure(this, name(), "TOP", "TOP", 0, VerilatedScope::SCOPE_OTHER);
    __Vscope_Top.configure(this, name(), "Top", "Top", -12, VerilatedScope::SCOPE_MODULE);
    __Vscope_Top__Driver.configure(this, name(), "Top.Driver", "Driver", -12, VerilatedScope::SCOPE_MODULE);
    __Vscope_Top__TriggerCounterImpl.configure(this, name(), "Top.TriggerCounterImpl", "TriggerCounterImpl", -12, VerilatedScope::SCOPE_MODULE);
    __Vscope_Top__cnt.configure(this, name(), "Top.cnt", "cnt", -12, VerilatedScope::SCOPE_MODULE);

    // Set up scope hierarchy
    __Vhier.add(0, &__Vscope_Top);
    __Vhier.add(&__Vscope_Top, &__Vscope_Top__Driver);
    __Vhier.add(&__Vscope_Top, &__Vscope_Top__TriggerCounterImpl);
    __Vhier.add(&__Vscope_Top, &__Vscope_Top__cnt);

    // Setup export functions
    for (int __Vfinal = 0; __Vfinal < 2; ++__Vfinal) {
        __Vscope_TOP.varInsert(__Vfinal,"clk", &(TOP.clk), false, VLVT_UINT8,VLVD_IN|VLVF_PUB_RW,0);
        __Vscope_TOP.varInsert(__Vfinal,"global_cycle_count", &(TOP.global_cycle_count), false, VLVT_UINT64,VLVD_OUT|VLVF_PUB_RW,1 ,63,0);
        __Vscope_TOP.varInsert(__Vfinal,"global_finish", &(TOP.global_finish), false, VLVT_UINT8,VLVD_OUT|VLVF_PUB_RW,0);
        __Vscope_TOP.varInsert(__Vfinal,"rst", &(TOP.rst), false, VLVT_UINT8,VLVD_IN|VLVF_PUB_RW,0);
        __Vscope_Top.varInsert(__Vfinal,"_Driver_cnt_w_port0", &(TOP.Top__DOT___Driver_cnt_w_port0), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,0);
        __Vscope_Top.varInsert(__Vfinal,"_Driver_cnt_wdata_port0", &(TOP.Top__DOT___Driver_cnt_wdata_port0), false, VLVT_UINT32,VLVD_NODIR|VLVF_PUB_RW,1 ,31,0);
        __Vscope_Top.varInsert(__Vfinal,"_Driver_executed", &(TOP.Top__DOT___Driver_executed), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,0);
        __Vscope_Top.varInsert(__Vfinal,"_GEN", &(TOP.Top__DOT___GEN), false, VLVT_UINT64,VLVD_NODIR|VLVF_PUB_RW,1 ,63,0);
        __Vscope_Top.varInsert(__Vfinal,"_TriggerCounterImpl_pop_valid", &(TOP.Top__DOT___TriggerCounterImpl_pop_valid), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,0);
        __Vscope_Top.varInsert(__Vfinal,"_cnt_rdata_port0", &(TOP.Top__DOT___cnt_rdata_port0), false, VLVT_UINT32,VLVD_NODIR|VLVF_PUB_RW,1 ,31,0);
        __Vscope_Top.varInsert(__Vfinal,"_cnt_rdata_port1", &(TOP.Top__DOT___cnt_rdata_port1), false, VLVT_UINT32,VLVD_NODIR|VLVF_PUB_RW,1 ,31,0);
        __Vscope_Top.varInsert(__Vfinal,"clk", &(TOP.Top__DOT__clk), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,0);
        __Vscope_Top.varInsert(__Vfinal,"global_cycle_count", &(TOP.Top__DOT__global_cycle_count), false, VLVT_UINT64,VLVD_NODIR|VLVF_PUB_RW,1 ,63,0);
        __Vscope_Top.varInsert(__Vfinal,"global_finish", &(TOP.Top__DOT__global_finish), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,0);
        __Vscope_Top.varInsert(__Vfinal,"rst", &(TOP.Top__DOT__rst), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,0);
        __Vscope_Top__Driver.varInsert(__Vfinal,"clk", &(TOP.Top__DOT__Driver__DOT__clk), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,0);
        __Vscope_Top__Driver.varInsert(__Vfinal,"cnt_rdata_port0", &(TOP.Top__DOT__Driver__DOT__cnt_rdata_port0), false, VLVT_UINT32,VLVD_NODIR|VLVF_PUB_RW,1 ,31,0);
        __Vscope_Top__Driver.varInsert(__Vfinal,"cnt_rdata_port1", &(TOP.Top__DOT__Driver__DOT__cnt_rdata_port1), false, VLVT_UINT32,VLVD_NODIR|VLVF_PUB_RW,1 ,31,0);
        __Vscope_Top__Driver.varInsert(__Vfinal,"cnt_w_port0", &(TOP.Top__DOT__Driver__DOT__cnt_w_port0), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,0);
        __Vscope_Top__Driver.varInsert(__Vfinal,"cnt_wdata_port0", &(TOP.Top__DOT__Driver__DOT__cnt_wdata_port0), false, VLVT_UINT32,VLVD_NODIR|VLVF_PUB_RW,1 ,31,0);
        __Vscope_Top__Driver.varInsert(__Vfinal,"cnt_widx_port0", &(TOP.Top__DOT__Driver__DOT__cnt_widx_port0), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,0);
        __Vscope_Top__Driver.varInsert(__Vfinal,"cycle_count", &(TOP.Top__DOT__Driver__DOT__cycle_count), false, VLVT_UINT64,VLVD_NODIR|VLVF_PUB_RW,1 ,63,0);
        __Vscope_Top__Driver.varInsert(__Vfinal,"executed", &(TOP.Top__DOT__Driver__DOT__executed), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,0);
        __Vscope_Top__Driver.varInsert(__Vfinal,"expose_Driver_cnt_rd_1", &(TOP.Top__DOT__Driver__DOT__expose_Driver_cnt_rd_1), false, VLVT_UINT32,VLVD_NODIR|VLVF_PUB_RW,1 ,31,0);
        __Vscope_Top__Driver.varInsert(__Vfinal,"finish", &(TOP.Top__DOT__Driver__DOT__finish), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,0);
        __Vscope_Top__Driver.varInsert(__Vfinal,"rst", &(TOP.Top__DOT__Driver__DOT__rst), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,0);
        __Vscope_Top__Driver.varInsert(__Vfinal,"trigger_counter_pop_valid", &(TOP.Top__DOT__Driver__DOT__trigger_counter_pop_valid), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,0);
        __Vscope_Top__Driver.varInsert(__Vfinal,"valid_Driver_cnt_rd_1", &(TOP.Top__DOT__Driver__DOT__valid_Driver_cnt_rd_1), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,0);
        __Vscope_Top__TriggerCounterImpl.varInsert(__Vfinal,"WIDTH", const_cast<void*>(static_cast<const void*>(&(TOP.Top__DOT__TriggerCounterImpl__DOT__WIDTH))), true, VLVT_UINT64,VLVD_NODIR|VLVF_PUB_RW,1 ,63,0);
        __Vscope_Top__TriggerCounterImpl.varInsert(__Vfinal,"clk", &(TOP.Top__DOT__TriggerCounterImpl__DOT__clk), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,0);
        __Vscope_Top__TriggerCounterImpl.varInsert(__Vfinal,"count", &(TOP.Top__DOT__TriggerCounterImpl__DOT__count), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,1 ,7,0);
        __Vscope_Top__TriggerCounterImpl.varInsert(__Vfinal,"delta", &(TOP.Top__DOT__TriggerCounterImpl__DOT__delta), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,1 ,7,0);
        __Vscope_Top__TriggerCounterImpl.varInsert(__Vfinal,"delta_ready", &(TOP.Top__DOT__TriggerCounterImpl__DOT__delta_ready), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,0);
        __Vscope_Top__TriggerCounterImpl.varInsert(__Vfinal,"new_count", &(TOP.Top__DOT__TriggerCounterImpl__DOT__new_count), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,1 ,7,0);
        __Vscope_Top__TriggerCounterImpl.varInsert(__Vfinal,"pop_ready", &(TOP.Top__DOT__TriggerCounterImpl__DOT__pop_ready), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,0);
        __Vscope_Top__TriggerCounterImpl.varInsert(__Vfinal,"pop_valid", &(TOP.Top__DOT__TriggerCounterImpl__DOT__pop_valid), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,0);
        __Vscope_Top__TriggerCounterImpl.varInsert(__Vfinal,"rst_n", &(TOP.Top__DOT__TriggerCounterImpl__DOT__rst_n), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,0);
        __Vscope_Top__TriggerCounterImpl.varInsert(__Vfinal,"temp", &(TOP.Top__DOT__TriggerCounterImpl__DOT__temp), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,1 ,7,0);
        __Vscope_Top__cnt.varInsert(__Vfinal,"_GEN", &(TOP.Top__DOT__cnt__DOT___GEN), false, VLVT_UINT32,VLVD_NODIR|VLVF_PUB_RW,1 ,31,0);
        __Vscope_Top__cnt.varInsert(__Vfinal,"_GEN_0", &(TOP.Top__DOT__cnt__DOT___GEN_0), false, VLVT_UINT32,VLVD_NODIR|VLVF_PUB_RW,1, 31,0);
        __Vscope_Top__cnt.varInsert(__Vfinal,"clk", &(TOP.Top__DOT__cnt__DOT__clk), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,0);
        __Vscope_Top__cnt.varInsert(__Vfinal,"rdata_port0", &(TOP.Top__DOT__cnt__DOT__rdata_port0), false, VLVT_UINT32,VLVD_NODIR|VLVF_PUB_RW,1 ,31,0);
        __Vscope_Top__cnt.varInsert(__Vfinal,"rdata_port1", &(TOP.Top__DOT__cnt__DOT__rdata_port1), false, VLVT_UINT32,VLVD_NODIR|VLVF_PUB_RW,1 ,31,0);
        __Vscope_Top__cnt.varInsert(__Vfinal,"rst", &(TOP.Top__DOT__cnt__DOT__rst), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,0);
        __Vscope_Top__cnt.varInsert(__Vfinal,"w_port0", &(TOP.Top__DOT__cnt__DOT__w_port0), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,0);
        __Vscope_Top__cnt.varInsert(__Vfinal,"wdata_port0", &(TOP.Top__DOT__cnt__DOT__wdata_port0), false, VLVT_UINT32,VLVD_NODIR|VLVF_PUB_RW,1 ,31,0);
        __Vscope_Top__cnt.varInsert(__Vfinal,"widx_port0", &(TOP.Top__DOT__cnt__DOT__widx_port0), false, VLVT_UINT8,VLVD_NODIR|VLVF_PUB_RW,0);
    }
}
