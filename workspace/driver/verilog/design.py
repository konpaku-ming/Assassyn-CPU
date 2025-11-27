from pycde import Input, Output, Module, System, Clock, Reset,dim
from pycde import generator, modparams
from pycde.constructs import Reg, Array, Mux,Wire
from pycde.types import Bits, SInt, UInt
from pycde.signals import Struct, BitsSignal
from pycde.dialects import comb,sv
from functools import reduce
from operator import or_, and_, add
from assassyn.pycde_wrapper import FIFO, TriggerCounter, build_register_file

cnt = build_register_file(
    'cnt',
    UInt(32),
    1,
    num_write_ports=1,
    num_read_ports=2,
    addr_width=1,
    include_read_index=False,
)

class Driver(Module):
    clk = Clock()
    rst = Reset()
    executed = Output(Bits(1))
    cycle_count = Input(UInt(64))
    finish = Output(Bits(1))
    trigger_counter_pop_valid = Input(Bits(1))
    cnt_rdata_port0 = Input(UInt(32))
    cnt_rdata_port1 = Input(UInt(32))
    cnt_w_port0 = Output(Bits(1))
    cnt_wdata_port0 = Output(UInt(32))
    cnt_widx_port0 = Output(Bits(1))
    expose_Driver_cnt_rd_1 = Output(UInt(32))
    valid_Driver_cnt_rd_1 = Output(Bits(1))

    @generator
    def construct(self):
        # cnt_rd = cnt[(0:u1)]
        #/home/tomorrow_arc1/CS/assassyn/MyCPU/main.py:79
        cnt_rd = self.cnt_rdata_port0
        # v = cnt_rd + (1:u32)
        #/home/tomorrow_arc1/CS/assassyn/MyCPU/main.py:79
        v = ((cnt_rd + UInt(32)(1)).as_uint(32))
        # cnt[(0:u1)] <= v /* Driver */ // meta cond (1:b1)
        #/home/tomorrow_arc1/CS/assassyn/MyCPU/main.py:82
        # cnt_rd_1 = cnt[(0:u1)]
        #/home/tomorrow_arc1/CS/assassyn/MyCPU/main.py:85
        cnt_rd_1 = self.cnt_rdata_port1
        # log('cnt: {}', cnt_rd_1) // meta cond (1:b1)
        #/home/tomorrow_arc1/CS/assassyn/MyCPU/main.py:85

        executed_wire = reduce(and_, [self.trigger_counter_pop_valid], Bits(1)(1))
        self.finish = Bits(1)(0)
        self.cnt_w_port0 = executed_wire & (Bits(1)(1))
        self.cnt_wdata_port0 = v
        self.cnt_widx_port0 = UInt(1)(0).as_bits()
        # Expose: cnt_rd_1 = cnt[(0:u1)]
        self.expose_Driver_cnt_rd_1 = cnt_rd_1
        self.valid_Driver_cnt_rd_1 = executed_wire & (Bits(1)(1))
        self.executed = executed_wire

class Top(Module):
    clk = Clock()
    rst = Reset()
    global_cycle_count = Output(UInt(64))
    global_finish = Output(Bits(1))

    @generator
    def construct(self):
        
# --- Global Cycle Counter ---
        # A free-running counter for testbench control
        cycle_count = Reg(UInt(64), clk=self.clk, rst=self.rst, rst_value=0)
        cycle_count.assign( (cycle_count + UInt(64)(1)).as_bits()[0:64].as_uint() )
        self.global_cycle_count = cycle_count
        # --- Wires for FIFOs, Triggers, and Arrays ---
        # Wires for Driver's TriggerCounter
        Driver_trigger_counter_delta = Wire(Bits(8))
        Driver_trigger_counter_delta_ready = Wire(Bits(1))
        Driver_trigger_counter_pop_valid = Wire(Bits(1))
        Driver_trigger_counter_pop_ready = Wire(Bits(1))
        # Multi-port array cnt with 1 write ports and 2 read ports
        aw_cnt_w_port0 = Wire(Bits(1))
        aw_cnt_wdata_port0 = Wire(UInt(32))
        aw_cnt_widx_port0 = Wire(Bits(1))
        aw_cnt_rdata_port0 = Wire(UInt(32))
        aw_cnt_rdata_port1 = Wire(UInt(32))
        array_writer_cnt = cnt(clk=self.clk, rst=self.rst, w_port0=aw_cnt_w_port0, wdata_port0=aw_cnt_wdata_port0, widx_port0=aw_cnt_widx_port0)
        aw_cnt_rdata_port0.assign(array_writer_cnt.rdata_port0)
        aw_cnt_rdata_port1.assign(array_writer_cnt.rdata_port1)
        
# --- Hardware Instantiations ---
        Driver_trigger_counter_inst = TriggerCounter(WIDTH=8)(clk=self.clk, rst_n=~self.rst, delta=Driver_trigger_counter_delta, pop_ready=Driver_trigger_counter_pop_ready)
        Driver_trigger_counter_delta_ready.assign(Driver_trigger_counter_inst.delta_ready)
        Driver_trigger_counter_pop_valid.assign(Driver_trigger_counter_inst.pop_valid)
        
# --- Module Instantiations and Connections ---
        # Instantiation for Driver
        inst_Driver = Driver(clk=self.clk, rst=self.rst, cycle_count=cycle_count, trigger_counter_pop_valid=Driver_trigger_counter_pop_valid, cnt_rdata_port0=aw_cnt_rdata_port0, cnt_rdata_port1=aw_cnt_rdata_port1)
        
# --- Module Connections ---
        # Connections for Driver
        Driver_trigger_counter_pop_ready.assign(inst_Driver.executed)
        
# --- Global Finish Signal Collection ---
        self.global_finish = Bits(1)(0)
        
# --- Array Write-Back Connections ---
        # Connections for array cnt
        aw_cnt_w_port0.assign(inst_Driver.cnt_w_port0)
        aw_cnt_wdata_port0.assign(inst_Driver.cnt_wdata_port0)
        aw_cnt_widx_port0.assign(Bits(1)(0))
        
# --- Trigger Counter Delta Connections ---
        Driver_trigger_counter_delta.assign(Bits(8)(1))

system = System([Top], name="Top", output_directory="sv")
system.compile()