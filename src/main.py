import os
import sys

# 路径 Hack (确保能找到 Assassyn 和 src)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from assassyn.frontend import *
from assassyn.backend import elaborate, config
from assassyn import utils

# 导入所有模块
# 支持两种运行方式：
# 1. python -m src.main (推荐，使用相对导入)
# 2. python src/main.py (直接运行，使用绝对导入)
if __package__:
    # 作为包运行时使用相对导入
    from .control_signals import *
    from .fetch import Fetcher, FetcherImpl
    from .decoder import Decoder, DecoderImpl
    from .data_hazard import DataHazardUnit
    from .execution import Execution
    from .memory import MemoryAccess
    from .writeback import WriteBack
else:
    # 作为脚本运行时使用绝对导入
    from src.control_signals import *
    from src.fetch import Fetcher, FetcherImpl
    from src.decoder import Decoder, DecoderImpl
    from src.data_hazard import DataHazardUnit
    from src.execution import Execution
    from src.memory import MemoryAccess
    from src.writeback import WriteBack

# 全局工作区路径
current_path = os.path.dirname(os.path.abspath(__file__))
workspace = f"{current_path}/../.workspace/"


# 辅助模块：用于初始化 offset (参考 minor_cpu)
class MemUser(Module):
    def __init__(self):
        super().__init__(ports={})

    @module.combinational
    def build(self, rdata: RegArray):
        width = rdata.scalar_ty.bits
        rdata = rdata[0].bitcast(Int(width))
        offset_reg = RegArray(Bits(width), 1)
        offset_reg[0] = rdata.bitcast(Bits(width))
        return offset_reg


class Driver(Module):
    def __init__(self):
        super().__init__(ports={})

    @module.combinational
    def build(self, fetcher: Module, user: Module):
        init_reg = RegArray(UInt(1), 1, initializer=[1])
        # 使用 workload.init 初始化 offset
        init_cache = SRAM(width=32, depth=32, init_file=f"{workspace}/workload.init")
        init_cache.build(
            we=Bits(1)(0),
            re=init_reg[0].bitcast(Bits(1)),
            wdata=Bits(32)(0),
            addr=Bits(5)(0),
        )

        # Cycle 0: 初始化 offset
        with Condition(init_reg[0] == UInt(1)(1)):
            user.async_called()
            init_reg[0] = UInt(1)(0)

        # Cycle >0: 启动 Fetcher (点火)
        # 注意：这里我们只负责 "kickstart"，Fetcher 后续会自动流转
        # 但在 Assassyn 的刚性流水线模型中，通常需要持续驱动
        # 不过根据我们的 FetcherImpl 设计，它只要有 stall/flush 信号就会自我驱动
        # 这里为了兼容性，保留这个启动信号，或者 Fetcher 内部有自举逻辑

        return init_cache


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

        # 辅助模块 (Offset Loader)
        mem_user = MemUser()
        driver = Driver()

        # 3. 逆序构建 (Reverse Build)

        # --- Step A: WB 阶段 ---
        wb_rd = writeback.build(reg_file)

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
        init_cache = driver.build(fetcher, mem_user)
        offset_reg = mem_user.build(init_cache.dout)

        # 4. 顶层暴露 (Expose)
        # --------------------------------------------------------
        sys.expose_on_top(reg_file, kind="Output")
        sys.expose_on_top(pc_reg, kind="Output")
        # 可以暴露更多用于调试

    # 5. 生成仿真器
    print(f"Building System: {sys_name}")
    conf = config(
        verilog=False,  # 单元测试通常不需要 Verilog，集成测试可以开
        sim_threshold=1000000,
        idle_threshold=500000,
        fifo_depth=1,
    )

    simulator_path, verilog_path = elaborate(sys, **conf)

    # 编译二进制
    print("Building Simulator Binary...")
    binary_path = utils.build_simulator(simulator_path)
    print(f"Binary Built: {binary_path}")

    return sys, binary_path


# 导出构建函数
if __name__ == "__main__":
    build_cpu()
