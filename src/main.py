import os
import shutil
from importlib.util import find_spec

from assassyn.frontend import *
from assassyn.backend import elaborate, config
from assassyn import utils

# 导入所有模块
from .control_signals import *
from .fetch import Fetcher, FetcherImpl
from .decoder import Decoder, DecoderImpl
from .hazard_unit import HazardUnit
from .execution import Execution
from .memory import MemoryAccess, SingleMemory
from .writeback import WriteBack
from .btb import BTB, BTBImpl
from .tournament_predictor import TournamentPredictor, TournamentPredictorImpl

# 全局工作区路径
current_path = os.path.dirname(os.path.abspath(__file__))
workspace = os.path.join(current_path, ".workspace")


# 复制文件进入当前目录下指定路径（沙盒）
def load_test_case(case_name, source_subdir="workloads"):
    # =========================================================
    # 1. 路径计算 (使用绝对路径解决 Apptainer/挂载问题)
    # =========================================================

    # 获取当前脚本 (src/main.py) 的绝对路径
    current_file_path = os.path.abspath(__file__)
    # 获取 src 目录
    src_dir = os.path.dirname(current_file_path)
    # 获取项目根目录 (假设 src 的上一级是项目根目录)
    project_root = os.path.dirname(src_dir)

    # 构造源文件目录: .../MyCPU/workloads
    source_dir = os.path.join(project_root, source_subdir)

    # 构造沙盒目录: .../MyCPU/src/workspace
    workspace_dir = os.path.join(src_dir, ".workspace")

    print(f"[*] Source Dir: {source_dir}")
    print(f"[*] Workspace : {workspace_dir}")

    # =========================================================
    # 2. 环境清理 (沙盒重置)
    # =========================================================
    if os.path.exists(workspace_dir):
        shutil.rmtree(workspace_dir)  # 暴力删除旧目录
    os.makedirs(workspace_dir)  # 重建空目录

    # =========================================================
    # 3. 文件搬运 (Copy & Rename)
    # =========================================================

    # 定义源文件名
    src_exe = os.path.join(source_dir, f"{case_name}.exe")

    # 定义目标文件名
    dst_RAM = os.path.join(workspace_dir, f"workload.exe")

    # --- 复制 RAM 文件 (.exe) -> cache ---
    if os.path.exists(src_exe):
        shutil.copy(src_exe, dst_RAM)
        print(f"  -> Copied Instruction: {case_name}.exe ==> workload.exe")
    else:
        # 如果找不到源文件，抛出错误（因为指令文件是必须的）
        raise FileNotFoundError(f"Test case not found: {src_exe}")


class Driver(Module):
    def __init__(self):
        super().__init__(ports={})

    @module.combinational
    def build(self, fetcher: Module):
        fetcher.async_called()


def build_cpu(depth_log, enable_branch_prediction=True):
    """
    构建 CPU 系统。
    
    Args:
        depth_log: SRAM 深度的对数 (depth = 2^depth_log)
        enable_branch_prediction: 分支预测开关
            - True: 使用 BTB + Tournament Predictor 进行分支预测
            - False: 默认 PC+4，不使用分支预测
    """
    sys_name = "rv32i_cpu"
    sys = SysBuilder(sys_name)

    RAM_path = os.path.join(workspace, f"workload.exe")
    print(f"[*] Ins Path: {RAM_path}")
    print(f"[*] Branch Prediction: {'Enabled (BTB + Tournament Predictor)' if enable_branch_prediction else 'Disabled (PC+4)'}")

    with sys:
        # 1. 物理资源初始化
        cache = SRAM(width=32, depth=1 << depth_log, init_file=RAM_path)
        cache.name = "cache"

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

        # BTB and Tournament Predictor (conditional based on enable_branch_prediction)
        if enable_branch_prediction:
            # BTB for branch prediction
            btb = BTB(num_entries=64, index_bits=6)
            btb_impl = BTBImpl(num_entries=64, index_bits=6)

            # Tournament Predictor for branch direction prediction
            tp = TournamentPredictor(num_entries=64, index_bits=6, history_bits=6)
            tp_impl = TournamentPredictorImpl(num_entries=64, index_bits=6, history_bits=6)
        else:
            btb = None
            btb_impl = None
            tp = None
            tp_impl = None

        decoder = Decoder()
        decoder_impl = DecoderImpl()
        hazard_unit = HazardUnit()

        executor = Execution()
        memory_unit = MemoryAccess()
        memory_single = SingleMemory()
        writeback = WriteBack()

        driver = Driver()

        # 3. 逆序构建

        # --- Step 0: BTB 和 Tournament Predictor 构建（仅在开关打开时） ---
        if enable_branch_prediction:
            btb_valid, btb_tags, btb_targets = btb.build()
            tp_bimodal, tp_gshare, tp_ghr, tp_selector = tp.build()
        else:
            btb_valid, btb_tags, btb_targets = None, None, None
            tp_bimodal, tp_gshare, tp_ghr, tp_selector = None, None, None, None

        # --- Step A: WB 阶段 ---
        wb_rd = writeback.build(
            reg_file=reg_file,
            wb_bypass_reg=wb_bypass_reg,
        )

        # --- Step B: MEM 阶段 ---
        mem_rd, mem_is_store = memory_unit.build(
            wb_module=writeback,
            sram_dout=cache.dout,
            mem_bypass_reg=mem_bypass_reg,
        )

        # --- Step C: EX 阶段 ---
        ex_rd, ex_addr, ex_is_load, ex_is_store, ex_width, ex_rs2, ex_mul_busy, ex_div_busy = executor.build(
            mem_module=memory_unit,
            ex_bypass=ex_bypass_reg,
            mem_bypass=mem_bypass_reg,
            wb_bypass=wb_bypass_reg,
            branch_target_reg=branch_target_reg,
            btb_impl=btb_impl,
            btb_valid=btb_valid,
            btb_tags=btb_tags,
            btb_targets=btb_targets,
            tp_impl=tp_impl,
            tp_bimodal=tp_bimodal,
            tp_gshare=tp_gshare,
            tp_ghr=tp_ghr,
            tp_selector=tp_selector,
        )

        # --- Step D: ID 阶段 (Shell) ---
        pre_pkt, rs1, rs2 = decoder.build(
            icache_dout=cache.dout,
            reg_file=reg_file,
        )

        # --- Step E: Hazard Unit ---
        rs1_sel, rs2_sel, stall_if = hazard_unit.build(
            rs1_idx=rs1,
            rs2_idx=rs2,
            ex_rd=ex_rd,
            ex_is_load=ex_is_load,
            ex_is_store=ex_is_store,
            ex_mul_busy=ex_mul_busy,
            ex_div_busy=ex_div_busy,
            mem_is_store=mem_is_store,
            mem_rd=mem_rd,
            wb_rd=wb_rd,
        )

        # --- Step F: ID 阶段 (Core) ---
        decoder_impl.build(
            pre=pre_pkt,
            executor=executor,
            rs1_sel=rs1_sel,
            rs2_sel=rs2_sel,
            stall_if=stall_if,
            branch_target_reg=branch_target_reg,
        )

        # --- Step G: IF 阶段 ---
        pc_reg, pc_addr, last_pc_reg = fetcher.build()
        current_pc = fetcher_impl.build(
            pc_reg=pc_reg,
            pc_addr=pc_addr,
            last_pc_reg=last_pc_reg,
            decoder=decoder,
            stall_if=stall_if,
            branch_target=branch_target_reg,
            btb_impl=btb_impl,
            btb_valid=btb_valid,
            btb_tags=btb_tags,
            btb_targets=btb_targets,
            tp_impl=tp_impl,
            tp_bimodal=tp_bimodal,
            tp_gshare=tp_gshare,
            tp_ghr=tp_ghr,
            tp_selector=tp_selector,
        )

        # --- Step H: SRAM 驱动 ---
        memory_single.build(
            if_addr=current_pc,
            mem_addr=ex_addr,
            re=ex_is_load,
            we=ex_is_store,
            wdata=ex_rs2,
            width=ex_width,
            sram=cache,
        )

        # --- Step I: 辅助驱动 ---
        driver.build(fetcher=fetcher)

        """RegArray exposing"""
        sys.expose_on_top(reg_file, kind="Output")

    return sys


# ==============================================================================
# 主程序入口
# ==============================================================================

if __name__ == "__main__":
    # 构建 CPU 模块
    # enable_branch_prediction=True: 使用 BTB + Tournament Predictor
    # enable_branch_prediction=False: 默认 PC+4，不使用分支预测
    load_test_case("vvadd")
    sys_builder = build_cpu(depth_log=16, enable_branch_prediction=True)

    circ_path = os.path.join(workspace, f"circ.txt")
    with open(circ_path, "w") as f:
        print(sys_builder, file=f)

    print(f"🚀 Compiling system: {sys_builder.name}...")

    # 配置
    cfg = config(
        verilog=True,
        sim_threshold=1000000,
        resource_base="",
        idle_threshold=1000000,
    )

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
    print(f"🏃 Running simulation...")
    print(simulator_path)
    print(verilog_path)
    raw = utils.run_simulator(binary_path=binary_path)
    log_path = os.path.join(workspace, f"raw.log")
    with open(log_path, "w") as f:
        print(raw, file=f)

    # 运行verilog模拟器，捕获输出
    if find_spec("cocotb.runner") is None:
        print("⚠️ Skipping cocotb Verilator run because cocotb is not installed. Install with `pip install cocotb` to enable.")
    else:
        print(f"🏃 Running simulation(verilog)...")
        raw = utils.run_verilator(verilog_path)
        log_path = os.path.join(workspace, f"verilog_raw.log")
        with open(log_path, "w") as f:
            print(raw, file=f)

    print("Done.")
