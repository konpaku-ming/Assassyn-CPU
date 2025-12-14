import os
import shutil

from assassyn.frontend import *
from assassyn.backend import elaborate, config
from assassyn import utils

# 导入所有模块
from control_signals import *
from fetch import Fetcher, FetcherImpl
from decoder import Decoder, DecoderImpl
from data_hazard import DataHazardUnit
from execution import Execution
from memory import MemoryAccess
from writeback import WriteBack

# 全局工作区路径
current_path = os.path.dirname(os.path.abspath(__file__))
workspace = os.path.join(current_path, ".workspace")


def convert_bin_to_hex(bin_path, hex_path):
    """
    将二进制文件转换为 hex 文本格式
    每行一个 32 位字 (8 个十六进制字符, 小写, 无 0x 前缀)
    
    参数:
        bin_path: 输入的二进制文件路径
        hex_path: 输出的 hex 文本文件路径
    """
    with open(bin_path, 'rb') as f_in, open(hex_path, 'w') as f_out:
        while True:
            # 每次读取 4 字节 (32 位)
            chunk = f_in.read(4)
            if not chunk:
                break
            
            # 如果不足 4 字节，补 0
            if len(chunk) < 4:
                chunk = chunk + b'\x00' * (4 - len(chunk))
            
            # 转换为小端序的 32 位整数，然后转为 8 位十六进制字符串
            word = int.from_bytes(chunk, byteorder='little')
            f_out.write(f"{word:08x}\n")


# 复制文件进入当前目录下指定路径（沙盒）
def load_test_case(case_name, source_subdir="main_test"):
    # =========================================================
    # 1. 路径计算 (使用绝对路径解决 Apptainer/挂载问题)
    # =========================================================

    # 获取当前脚本 (src/main.py) 的绝对路径
    current_file_path = os.path.abspath(__file__)
    # 获取 src 目录
    src_dir = os.path.dirname(current_file_path)
    # 获取项目根目录 (假设 src 的上一级是项目根目录)
    project_root = os.path.dirname(src_dir)

    # 构造源文件目录: .../Assassyn-CPU/main_test
    source_dir = os.path.join(project_root, source_subdir)

    # 构造沙盒目录: .../Assassyn-CPU/src/.workspace
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
    # 3. 文件转换 (从 .bin 到 .exe/.data)
    # =========================================================

    # 定义源文件名 (二进制文件)
    src_text_bin = os.path.join(source_dir, f"{case_name}_text.bin")
    src_data_bin = os.path.join(source_dir, f"{case_name}_data.bin")

    # 定义目标文件名 (硬件写死的固定名字)
    dst_ins = os.path.join(workspace_dir, f"workload.exe")
    dst_mem = os.path.join(workspace_dir, f"workload.data")

    # --- 转换指令文件 (.bin -> .exe) -> icache ---
    if os.path.exists(src_text_bin):
        convert_bin_to_hex(src_text_bin, dst_ins)
        print(f"  -> Converted Instruction: {case_name}_text.bin ==> workload.exe")
    else:
        # 如果找不到源文件，抛出错误（因为指令文件是必须的）
        raise FileNotFoundError(f"Test case not found: {src_text_bin}")

    # --- 转换数据文件 (.bin -> .data) -> dcache ---
    if os.path.exists(src_data_bin):
        # 检查文件是否为空
        if os.path.getsize(src_data_bin) > 0:
            convert_bin_to_hex(src_data_bin, dst_mem)
            print(f"  -> Converted Memory Data: {case_name}_data.bin ==> workload.data")
        else:
            # 如果数据文件为空，创建一个空的 hex 文件
            with open(dst_mem, "w") as f:
                pass
            print(f"  -> Data file is empty, created empty: workload.data")
    else:
        # 如果没有数据文件（有些简单测试不需要），创建一个空文件防止报错
        with open(dst_mem, "w") as f:
            pass
        print(f"  -> No .data found, created empty: workload.data")


class Driver(Module):
    def __init__(self):
        super().__init__(ports={})

    @module.combinational
    def build(self, fetcher: Module):
        fetcher.async_called()


def build_cpu(depth_log=16):
    sys_name = "rv32i_cpu"
    sys = SysBuilder(sys_name)

    data_path = os.path.join(workspace, f"workload.data")
    ins_path = os.path.join(workspace, f"workload.exe")
    print(f"[*] Data Path: {data_path}")
    print(f"[*] Ins Path: {ins_path}")

    with sys:
        # 1. 物理资源初始化
        dcache = SRAM(width=32, depth=1 << depth_log, init_file=data_path)
        dcache.name = "dcache"
        icache = SRAM(width=32, depth=1 << depth_log, init_file=ins_path)
        icache.name = "icache"

        # 寄存器堆
        # 初始化 SP (x2) 指向栈顶
        # RAM 大小: 2^depth_log 字节，栈顶在最高地址
        STACK_TOP = (1 << depth_log) - 4  # 栈顶地址（字对齐）
        reg_init = [0] * 32
        reg_init[2] = STACK_TOP  # x2 = sp，初始化为栈顶
        reg_file = RegArray(Bits(32), 32, initializer=reg_init)

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

        # 3. 逆序构建

        # --- Step A: WB 阶段 ---
        wb_rd = writeback.build(
            reg_file=reg_file,
            wb_bypass_reg=wb_bypass_reg,
        )

        # --- Step B: MEM 阶段 ---
        mem_rd = memory_unit.build(
            wb_module=writeback,
            sram_dout=dcache.dout,
            mem_bypass_reg=mem_bypass_reg,
        )

        # --- Step C: EX 阶段 ---
        ex_rd, ex_is_load = executor.build(
            mem_module=memory_unit,
            ex_mem_bypass=ex_bypass_reg,
            mem_wb_bypass=mem_bypass_reg,
            wb_bypass=wb_bypass_reg,
            branch_target_reg=branch_target_reg,
            dcache=dcache,
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
        decoder_impl.build(
            pre=pre_pkt,
            executor=executor,
            rs1_sel=rs1_sel,
            rs2_sel=rs2_sel,
            stall_if=stall_if,
            branch_target_reg=branch_target_reg,
        )

        # --- Step G: IF 阶段 ---
        pc_reg, last_pc_reg = fetcher.build()
        fetcher_impl.build(
            pc_reg=pc_reg,
            last_pc_reg=last_pc_reg,
            icache=icache,
            decoder=decoder,
            stall_if=stall_if,
            branch_target=branch_target_reg,
        )

        # --- Step H: 辅助驱动 ---
        driver.build(fetcher=fetcher)

    return sys


# ==============================================================================
# 主程序入口
# ==============================================================================

if __name__ == "__main__":
    # 构建 CPU 模块
    load_test_case("0to100")
    sys_builder = build_cpu(depth_log=16)
    print(f"🚀 Compiling system: {sys_builder.name}...")

    # 配置
    cfg = config(
        verilog=False,
        sim_threshold=600000,
        resource_base="",
        idle_threshold=600000,
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
    print(f"🏃 Running simulation (Direct Output Mode)...")
    raw = utils.run_simulator(binary_path=binary_path)

    print(raw)
    print("🔍 Verifying output...")
