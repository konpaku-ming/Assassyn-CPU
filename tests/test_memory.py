import sys
import os

# 1. 环境路径设置 (确保能 import src)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from assassyn.frontend import *

# 导入你的设计
from src.memory import MemoryAccess
from src.writeback import WriteBack
from src.control_signals import *
from tests.common import run_test_module


# ==============================================================================
# 1. Driver 模块定义：前三行不能改，这是Assassyn的约定。
# ==============================================================================
class Driver(Module):
    def __init__(self):
        super().__init__(ports={})

    @module.combinational
    def build(
        self, dut: Module, wb_module: Module, sram_dout: Array, mem_bypass_reg: Array
    ):
        # --- 测试向量定义 ---
        # 格式: (mem_opcode, mem_width, mem_unsigned, rd_addr, alu_result, sram_data, expected_result)
        # mem_opcode: 0=NONE, 1=LOAD, 2=STORE
        # mem_width: 0=BYTE, 1=HALF, 2=WORD
        # mem_unsigned: 0=SIGNED, 1=UNSIGNED

        # 注意：mem_unsigned使用的是二进制编码而不是独热码
        # 原因：mem_unsigned只有两个可能的值（SIGNED或UNSIGNED），使用1位二进制编码更高效
        # 而mem_opcode和mem_width有多个可能的值，使用独热码便于选择逻辑的实现

        vectors = [
            # --- 基础加载测试 (修改数据以测试负数符号扩展) ---
            # Case 0: LB (加载字节，有符号) - 地址对齐 (Offset 0)
            # Input: ...F8 (1111_1000, 负数) -> 符号扩展 -> FFFFFFF8
            (1, 0, 0, 1, 0x10000000, 0x123456F8, 0xFFFFFFF8),
            # Case 1: LH (加载半字，有符号) - 地址对齐 (Offset 0)
            # Input: ...F678 (1111_..., 负数) -> 符号扩展 -> FFFFF678
            (1, 1, 0, 2, 0x10000000, 0x1234F678, 0xFFFFF678),
            # Case 2: LW (加载字) - 地址对齐
            # Input: ... (正数) -> 直接加载
            (1, 2, 0, 3, 0x10000000, 0x12345678, 0x12345678),
            # --- 无符号扩展测试 ---
            # Case 3: LBU (加载字节，无符号) - 地址对齐
            # Input: ...F8 (负数) -> 零扩展 -> 000000F8
            (1, 0, 1, 4, 0x10000000, 0x123456F8, 0x000000F8),
            # Case 4: LHU (加载半字，无符号) - 地址对齐
            # Input: ...F678 (负数) -> 零扩展 -> 0000F678
            (1, 1, 1, 5, 0x10000000, 0x1234F678, 0x0000F678),
            # --- 偏移地址测试 (Little Endian: 低地址存低位) ---
            # Case 5: LB (加载字节，有符号) - Offset 1 (取 [15:8])
            # Input: 0x1234F678 -> Byte1 is F6 (负数) -> FFFFFFF6
            (1, 0, 0, 6, 0x10000001, 0x1234F678, 0xFFFFFFF6),
            # Case 6: LB (加载字节，有符号) - Offset 2 (取 [23:16])
            # Input: 0x12F45678 -> Byte2 is F4 (负数) -> FFFFFFF4
            (1, 0, 0, 7, 0x10000002, 0x12F45678, 0xFFFFFFF4),
            # Case 7: LB (加载字节，有符号) - Offset 3 (取 [31:24])
            # Input: 0xF2345678 -> Byte3 is F2 (负数) -> FFFFFFF2
            (1, 0, 0, 8, 0x10000003, 0xF2345678, 0xFFFFFFF2),
            # Case 8: LH (加载半字，有符号) - Offset 2 (取 [31:16])
            # Input: 0xF2345678 -> Half1 is F234 (负数) -> FFFFF234
            (1, 1, 0, 9, 0x10000002, 0xF2345678, 0xFFFFF234),
            # --- 其他测试 ---
            # Case 9: 非加载指令 (ALU 运算)
            (0, 0, 0, 10, 0xABCDEF00, 0x00000000, 0xABCDEF00),
            # Case 10: 边界测试 - 最大负值 (Byte 0 = FF)
            (1, 0, 0, 11, 0x10000000, 0x000000FF, 0xFFFFFFFF),
            # Case 11: 边界测试 - 正数零扩展
            (1, 0, 1, 12, 0x10000000, 0x7F123456, 0x00000056),
            # Case 12: 写 x0 (忽略)
            (1, 2, 0, 0, 0x10000000, 0xDEADBEEF, 0xDEADBEEF),
        ]

        # --- 激励生成逻辑 ---
        # 1. 计数器：跟踪当前测试进度
        cnt = RegArray(UInt(32), 1)
        (cnt & self)[0] <= cnt[0] + UInt(32)(1)

        idx = cnt[0]

        # 2. 组合逻辑 Mux：根据 idx 选择当前的测试向量
        # 初始化默认值
        current_mem_opcode = Bits(3)(0)
        current_mem_width = Bits(3)(0)
        current_mem_unsigned = Bits(1)(0)
        current_rd_addr = Bits(5)(0)
        current_alu_result = Bits(32)(0)
        current_sram_data = Bits(32)(0)
        current_expected = Bits(32)(0)

        # 这里的循环展开会生成一棵 Mux 树
        for i, (
            mem_opcode,
            mem_width,
            mem_unsigned,
            rd_addr,
            alu_result,
            sram_data,
            expected,
        ) in enumerate(vectors):
            is_match = idx == UInt(32)(i)

            # 独热码构造：只有对应位为1，其他位为0
            if mem_opcode == 0:  # NONE
                opcode_onehot = Bits(3)(0b001)
            elif mem_opcode == 1:  # LOAD
                opcode_onehot = Bits(3)(0b010)
            else:  # STORE
                opcode_onehot = Bits(3)(0b100)
            current_mem_opcode = is_match.select(
                opcode_onehot, current_mem_opcode
            )  # 独热码

            # 独热码构造：只有对应位为1，其他位为0
            if mem_width == 0:  # BYTE
                width_onehot = Bits(3)(0b001)
            elif mem_width == 1:  # HALF
                width_onehot = Bits(3)(0b010)
            else:  # WORD
                width_onehot = Bits(3)(0b100)
            current_mem_width = is_match.select(
                width_onehot, current_mem_width
            )  # 独热码

            # 使用control_signals.py中定义的MemSign常量而不是直接使用0和1
            # 这样可以提高代码的可读性和维护性
            if mem_unsigned == 0:  # SIGNED
                mem_sign_value = MemSign.SIGNED
            else:  # UNSIGNED
                mem_sign_value = MemSign.UNSIGNED
            current_mem_unsigned = is_match.select(mem_sign_value, current_mem_unsigned)
            current_rd_addr = is_match.select(Bits(5)(rd_addr), current_rd_addr)
            current_alu_result = is_match.select(
                Bits(32)(alu_result), current_alu_result
            )
            current_sram_data = is_match.select(Bits(32)(sram_data), current_sram_data)
            current_expected = is_match.select(Bits(32)(expected), current_expected)

        # 3. 构建控制信号包
        ctrl_pkt = mem_ctrl_signals.bundle(
            mem_opcode=current_mem_opcode,
            mem_width=current_mem_width,
            mem_unsigned=current_mem_unsigned,
            rd_addr=current_rd_addr,
            halt_if=Bits(1)(0),
        )

        # 4. 模拟 SRAM 输出数据
        sram_dout[0] = current_sram_data

        # 5. 发送数据
        # 只有当 idx 在向量范围内时才发送 (valid)
        valid_test = idx < UInt(32)(len(vectors))

        with Condition(valid_test):
            # 打印 Driver 发出的请求，方便对比调试
            log(
                "Driver: idx={} mem_op={} width={} unsigned={} rd=x{} addr=0x{:x} sram=0x{:x} expected=0x{:x}",
                idx,
                current_mem_opcode,
                current_mem_width,
                current_mem_unsigned,
                current_rd_addr,
                current_alu_result,
                current_sram_data,
                current_expected,
            )

            # 建立连接 (async_called)
            call = dut.async_called(ctrl=ctrl_pkt, alu_result=current_alu_result)
            call.bind.set_fifo_depth(ctrl=1, alu_result=1)  # 设置 FIFO 深度，防止阻塞

        # [关键] 返回 cnt 和预期结果，让它们成为模块的输出
        return cnt, current_rd_addr, current_expected


# ==============================================================================
# 2. 验证逻辑 (Python Check)
# ==============================================================================
def check(raw_output):
    print(">>> 开始验证日志...")

    # 预期发生的写入操作 (过滤掉 rd=0 的 case)
    # 预期发生的写入操作 (注意：必须与上面的 vectors 严格对应)
    expected_writes = [
        (1, 0xFFFFFFF8),  # Case 0
        (2, 0xFFFFF678),  # Case 1
        (3, 0x12345678),  # Case 2
        (4, 0x000000F8),  # Case 3
        (5, 0x0000F678),  # Case 4
        (6, 0xFFFFFFF6),  # Case 5
        (7, 0xFFFFFFF4),  # Case 6
        (8, 0xFFFFFFF2),  # Case 7
        (9, 0xFFFFF234),  # Case 8
        (10, 0xABCDEF00),  # Case 9
        (11, 0xFFFFFFFF),  # Case 10
        (12, 0x00000056),  # Case 11
        # Case 12 (x0) 被忽略，不在此列表中
    ]

    # 实际捕捉到的写入操作
    captured_writes = []
    bypass_data = []

    for line in raw_output.split("\n"):
        # 捕获 WriteBack 模块的写入操作
        if "WB: Write" in line:
            # 简单解析字符串
            # 示例行: "[100] WB: Write x5 <= 0x55555555"
            parts = line.split()
            rd = None
            data = None
            for part in parts:
                if part.startswith("x") and part[1:].isdigit():
                    rd = int(part[1:])
                if part.startswith("0x"):
                    data = int(part, 16)

            if rd is not None and data is not None:
                captured_writes.append((rd, data))
                print(f"  [捕获] WB: x{rd} <= 0x{data:08x}")

        # 捕获旁路寄存器的数据更新
        if "MEM: Bypass" in line:
            # 示例行: "[100] MEM: Bypass <= 0x12345678"
            parts = line.split()
            for part in parts:
                if part.startswith("0x"):
                    bypass_data.append(int(part, 16))
                    print(f"  [捕获] Bypass: 0x{int(part, 16):08x}")

    # --- 断言比对 ---

    # 1. 数量检查
    if len(captured_writes) != len(expected_writes):
        print(
            f"❌ 错误：预期写入 {len(expected_writes)} 次，实际写入 {len(captured_writes)} 次"
        )
        print("  可能是 x0 的写入没有被屏蔽，或者有效写入丢失。")
        assert False

    # 2. 内容检查
    for i, (exp_rd, exp_data) in enumerate(expected_writes):
        act_rd, act_data = captured_writes[i]

        if act_rd != exp_rd or act_data != exp_data:
            print(f"❌ 错误：第 {i} 次写入不匹配")
            print(f"  预期: x{exp_rd} <= 0x{exp_data:08x}")
            print(f"  实际: x{act_rd} <= 0x{act_data:08x}")
            assert False

    # 3. 旁路寄存器数据检查
    if len(bypass_data) != len(expected_writes) + 1:
        print(
            f"❌ 错误：预期旁路更新 {len(expected_writes)} 次，实际更新 {len(bypass_data)} 次"
        )
        assert False

    for i, (exp_rd, exp_data) in enumerate(expected_writes):
        if bypass_data[i] != exp_data:
            print(f"❌ 错误：第 {i} 次旁路数据不匹配")
            print(f"  预期: 0x{exp_data:08x}")
            print(f"  实际: 0x{bypass_data[i]:08x}")
            assert False

    print("✅ MemoryAccess 测试通过！(所有加载指令、非加载指令和旁路寄存器均正确)")


# ==============================================================================
# 3. 主执行入口
# ==============================================================================
if __name__ == "__main__":
    sys = SysBuilder("test_mem_module")

    with sys:
        reg_file = RegArray(Bits(32), 32)
        dut = MemoryAccess()
        wb_module = WriteBack()
        driver = Driver()

        # 创建 SRAM 输出端口和旁路寄存器
        sram_dout = RegArray(Bits(32), 1)
        mem_bypass_reg = RegArray(Bits(32), 1)

        # [关键] 获取 Driver 的返回值
        driver_cnt, driver_rd, driver_expected = driver.build(
            dut, wb_module, sram_dout, mem_bypass_reg
        )

        # 获取 DUT 的返回值
        mem_ctrl, _ = dut.build(wb_module, sram_dout, mem_bypass_reg)

        # 获取 WB 模块的返回值
        # 创建 wb_bypass_reg 用于 WriteBack 模块
        wb_bypass_reg = RegArray(Bits(32), 1)
        wb_rd = wb_module.build(reg_file, wb_bypass_reg)

        # [关键] 暴露 Driver 的计数器，防止被 DCE 优化掉
        sys.expose_on_top(driver_cnt, kind="Output")
        sys.expose_on_top(driver_rd, kind="Output")
        sys.expose_on_top(driver_expected, kind="Output")

        # 暴露 DUT 的输出
        sys.expose_on_top(reg_file, kind="Output")
        sys.expose_on_top(wb_rd, kind="Output")
        sys.expose_on_top(mem_bypass_reg, kind="Output")
        sys.expose_on_top(wb_bypass_reg, kind="Output")

    run_test_module(sys, check)
