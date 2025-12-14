import os
import shutil
import struct

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


def bin_to_hex_words(input_path, output_path, word_size=4):
    """
    Convert binary file to hex text format (one word per line) for SRAM initialization.
    
    Args:
        input_path: Path to input binary file
        output_path: Path to output hex text file
        word_size: Number of bytes per word (default: 4 for 32-bit)
    """
    with open(input_path, 'rb') as f:
        data = f.read()
    
    # Pad to word_size boundary
    if len(data) % word_size != 0:
        padding = word_size - (len(data) % word_size)
        data += b'\x00' * padding
    
    # Convert to words (little-endian)
    words = []
    for i in range(0, len(data), word_size):
        word_bytes = data[i:i+word_size]
        # Unpack as little-endian unsigned 32-bit integer
        word_value = struct.unpack('<I', word_bytes)[0]
        words.append(word_value)
    
    # Write to output file (one hex word per line, 8 hex digits)
    with open(output_path, 'w') as f:
        for word in words:
            f.write(f'{word:08x}\n')
    
    print(f"  -> Converted {os.path.basename(input_path)} -> {os.path.basename(output_path)}")
    print(f"     (Input: {len(data)} bytes, Output: {len(words)} words)")


def prepare_workload_files(case_name):
    """
    Convert binary files from main_test/ to hex format in workloads/
    
    Args:
        case_name: Name of the test case (e.g., "my0to100")
    """
    # Get project root directory
    current_file_path = os.path.abspath(__file__)
    src_dir = os.path.dirname(current_file_path)
    project_root = os.path.dirname(src_dir)
    
    # Define paths
    main_test_dir = os.path.join(project_root, "main_test")
    workloads_dir = os.path.join(project_root, "workloads")
    
    # Create workloads directory if it doesn't exist
    os.makedirs(workloads_dir, exist_ok=True)
    
    # Source binary files
    text_bin = os.path.join(main_test_dir, f"{case_name}_text.bin")
    data_bin = os.path.join(main_test_dir, f"{case_name}_data.bin")
    
    # Target hex files
    exe_file = os.path.join(workloads_dir, f"{case_name}.exe")
    data_file = os.path.join(workloads_dir, f"{case_name}.data")
    
    print(f"[*] Preparing workload files for: {case_name}")
    
    # Convert instruction binary to .exe
    if os.path.exists(text_bin):
        bin_to_hex_words(text_bin, exe_file)
    else:
        raise FileNotFoundError(f"Instruction binary not found: {text_bin}")
    
    # Convert data binary to .data
    if os.path.exists(data_bin):
        bin_to_hex_words(data_bin, data_file)
    else:
        # Create empty data file if no data segment
        with open(data_file, 'w') as f:
            pass
        print(f"  -> No data binary found, created empty: {os.path.basename(data_file)}")


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

    # 定义源文件名 (假设源文件叫 0to100.exe 和 0to100.data)
    src_exe = os.path.join(source_dir, f"{case_name}.exe")
    src_data = os.path.join(source_dir, f"{case_name}.data")

    # 定义目标文件名 (硬件写死的固定名字)
    # 根据你之前的 build_cpu 代码，硬件找的是 workload.exe 和 workload.data
    dst_ins = os.path.join(workspace_dir, f"workload.exe")
    dst_mem = os.path.join(workspace_dir, f"workload.data")

    # --- 复制指令文件 (.exe) -> icache ---
    if os.path.exists(src_exe):
        shutil.copy(src_exe, dst_ins)
        print(f"  -> Copied Instruction: {case_name}.exe ==> workload_ins.exe")
    else:
        # 如果找不到源文件，抛出错误（因为指令文件是必须的）
        raise FileNotFoundError(f"Test case not found: {src_exe}")

    # --- 复制数据文件 (.data) -> dcache ---
    if os.path.exists(src_data):
        shutil.copy(src_data, dst_mem)
        print(f"  -> Copied Memory Data: {case_name}.data ==> workload_mem.exe")
    else:
        # 如果没有数据文件（有些简单测试不需要），创建一个空文件防止报错
        with open(dst_mem, "w") as f:
            pass
        print(f"  -> No .data found, created empty: workload_mem.exe")


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
        # Initialize register file with stack pointer (x2/sp) set to a valid stack base
        # Stack grows downward from 0x10000 (top of 64K word address space)
        # x2 = sp (stack pointer) = 0x10000 * 4 = 0x40000 (byte address)
        reg_init = [0] * 32
        reg_init[2] = 0x40000  # Set sp (x2) to stack base at 256KB
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
    # 准备工作负载文件 (从 main_test/ 的二进制文件转换到 workloads/)
    prepare_workload_files("my0to100")
    
    # 构建 CPU 模块
    load_test_case("my0to100")
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
