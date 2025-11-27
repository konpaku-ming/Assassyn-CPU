
import os
import glob
from pathlib import Path

import cocotb
from cocotb.triggers import Timer
from cocotb.runner import get_runner



@cocotb.test()
async def test_tb(dut):

    dut.clk.value = 1
    dut.rst.value = 1
    await Timer(500, units="ns")
    dut.clk.value = 0
    dut.rst.value = 0
    await Timer(500, units="ns")
    for cycle in range(100):
        dut.clk.value = 1
        await Timer(500, units="ns")
        dut.clk.value = 0
        await Timer(500, units="ns")
        # log('cnt: {}', cnt_rd_1) // meta cond (1:b1)
        #@ line /home/tomorrow_arc1/CS/assassyn/MyCPU/main.py:85: log('cnt: {}', cnt_rd_1) // meta cond (1:b1)
        if ( dut.Driver.valid_Driver_cnt_rd_1.value ):
            print(f"@line:85 Cycle @{float(dut.global_cycle_count.value):.2f}: [Driver]             cnt: {int(dut.Driver.expose_Driver_cnt_rd_1.value)}")
        if dut.global_finish.value == 1:
            break



def runner():
    sim = 'verilator'
    path = Path('./sv/hw')
    with open(path / 'filelist.f', 'r') as f:
        srcs = [path / i.strip() for i in f.readlines()]
    sram_blackbox_files = glob.glob('sram_blackbox_*.sv')
    srcs = srcs + sram_blackbox_files
    srcs = srcs + ['fifo.sv', 'trigger_counter.sv']
    runner = get_runner(sim)
    runner.build(sources=srcs, hdl_toplevel='Top', always=True)
    runner.test(hdl_toplevel='Top', test_module='tb')

if __name__ == "__main__":
    runner()