import os
import sys

# 路径 Hack (确保能找到 Assassyn 和 src)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from assassyn.frontend import *
from assassyn.backend import elaborate, config
from assassyn import utils

# 导入所有模块
from .control_signals import *
from .fetch import Fetcher, FetcherImpl
from .decoder import Decoder, DecoderImpl
from .data_hazard import DataHazardUnit
from .execution import Execution
from .memory import MemoryAccess
from .writeback import WriteBack

# 全局工作区路径
current_path = os.path.dirname(os.path.abspath(__file__))
workspace = f"{current_path}/../workloads/"


class Driver(Module):
    def __init__(self):
        super().__init__(ports={})

    @module.combinational
    def build(self, fetcher: Module):
        fetcher.async_called()


def build_cpu(depth_log=16):
    sys_name = "rv32i_cpu"
    sys = SysBuilder(sys_name)

    with sys:
        # 1. 物理资源初始化
        main_memory = SRAM(
            width=32, depth=1 << depth_log, init_file=f"{workspace}/workload_mem.exe"
        )
        icache = SRAM(
            width=32, depth=1 << depth_log, init_file=f"{workspace}/workload_ins.exe"
        )

        # 寄存器堆
        reg_file = RegArray(Bits(32), 32)

        # 全局状态寄存器
        branch_target_reg = RegArray(Bits(32), 1)
        wb_bypass_reg = RegArray(Bits(32), 1)
        ex_bypass_reg = RegArray(Bits(32), 1)
        mem_bypass_reg = RegArray(Bits(32), 1)

        # 2. 模块实例化
        fetcher = Fetcher()
        fetcher_impl = FetcherImpl()

        decoder = Decoder()
        decoder_impl = DecoderImpl()
        hazard_unit = DataHazardUnit()

        executor = Execution()
        memory_unit = MemoryAccess()
        writeback = WriteBack()

        driver = Driver()

        # 3. 逆序构建 (Reverse Build)

        # --- Step A: WB 阶段 ---
        wb_rd = writeback.build(
            reg_file=reg_file,
            wb_bypass_reg=wb_bypass_reg,
        )

        # --- Step B: MEM 阶段 ---
        mem_rd = memory_unit.build(
            wb_module=writeback,
            sram_dout=main_memory.dout,
            mem_bypass_reg=mem_bypass_reg,
        )

        # --- Step C: EX 阶段 ---
        ex_rd, ex_is_load = executor.build(
            mem_module=memory_unit,
            ex_mem_bypass=ex_bypass_reg,
            mem_wb_bypass=mem_bypass_reg,
            wb_bypass=wb_bypass_reg,
            branch_target_reg=branch_target_reg,
            dcache=main_memory,
        )

        # --- Step D: ID 阶段 (Shell) ---
        pre_pkt, rs1, rs2, use1, use2 = decoder.build(
            icache_dout=icache.dout,
            reg_file=reg_file,
        )

        # --- Step E: Hazard Unit ---
        rs1_sel, rs2_sel, stall_if = hazard_unit.build(
            rs1_idx=rs1,
            rs2_idx=rs2,
            rs1_used=use1,
            rs2_used=use2,
            ex_rd=ex_rd,
            ex_is_load=ex_is_load,
            mem_rd=mem_rd,
            wb_rd=wb_rd,
        )

        # --- Step F: ID 阶段 (Core) ---
        stall_if = decoder_impl.build(
            pre=pre_pkt,
            executor=executor,
            rs1_sel=rs1_sel,
            rs2_sel=rs2_sel,
            stall_if=stall_if,
            branch_target_reg=branch_target_reg,
        )

        # --- Step G: IF 阶段 ---
        pc_reg = fetcher.build()
        fetcher_impl.build(
            pc_reg=pc_reg,
            icache=main_memory,
            decoder=decoder,
            stall_if=stall_if,
            branch_target=branch_target_reg,
        )

        # --- Step H: 辅助驱动 ---
        driver.build(fetcher=fetcher)

    # 5. 生成仿真器
    print(f"Building System: {sys_name}")
    conf = config(
        verilog=False,  # 单元测试通常不需要 Verilog，集成测试可以开
        sim_threshold=1000000,
        idle_threshold=500000,
        fifo_depth=1,
    )

    return sys


# ==============================================================================
# 主程序入口
# ==============================================================================

if __name__ == "__main__":
    # 构建 CPU 模块
    sys_builder = build_cpu(depth_log=16)
    print(f"🚀 Compiling system: {sys_builder.name}...")

    # 配置
    print(sys_builder)
    cfg = config(verilog=False, sim_threshold=600000, idle_threshold=600000)

    # 生成源码
    simulator_path, verilog_path = elaborate(sys_builder, **cfg)

    # 编译二进制
    try:
        # build_simulator 内部会调用 cargo build，它的输出我们暂时不管
        # 只要最后 binary_path 存在就行
        binary_path = utils.build_simulator(simulator_path)
        print(f"🔨 Building binary from: {binary_path}")
    except Exception as e:
        print(f"❌ Simulator build failed: {e}")
        raise e

    # 运行模拟器，捕获输出
    print(f"🏃 Running simulation (Direct Output Mode)...")
    raw = utils.run_simulator(binary_path=binary_path)

    print(raw)
    print("🔍 Verifying output...")
