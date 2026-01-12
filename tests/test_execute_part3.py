import sys
import os
import re

# 1. 环境路径设置 (确保能 import src)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from assassyn.frontend import *

# 导入你的设计
from src.execution import Execution
from src.control_signals import *
from tests.common import run_test_module
from tests.test_mock import (
    MockSRAM,
    MockMEM,
    MockFeedback,
    check_alu_results,
    check_bypass_updates,
)


# ==============================================================================
# 1. Driver 模块定义：前三行不能改，这是Assassyn的约定。
# ==============================================================================
class Driver(Module):
    def __init__(self):
        super().__init__(ports={})

    @module.combinational
    def build(
        self,
        dut: Module,
        ex_mem_bypass: Array,
        mem_wb_bypass: Array,
        wb_bypass: Array,
        mock_feedback: Module,
    ):
        # --- 测试向量定义 ---
        # 格式: (alu_func, rs1_sel, rs2_sel, op1_sel, op2_sel, branch_type,
        #       next_pc_addr, pc, rs1_data, rs2_data, imm, ex_mem_fwd, mem_wb_fwd, wb_fwd, expected_result)
        vectors = [
            # --- Store 指令测试 ---
            # Case 0: SW (Store Word) - 存储数据到地址0x1000
            (
                ALUOp.ADD,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.IMM,
                BranchType.NO_BRANCH,
                Bits(32)(0x1004),
                Bits(32)(0x1000),
                Bits(32)(0x1000),
                Bits(32)(0x12345678),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(50),
                Bits(32)(0x1000),
            ),  # ALU结果: 0x1000 + 0 = 0x1000 (计算地址)
            # Case 1: SW (Store Word) - 存储数据到地址0x1004
            (
                ALUOp.ADD,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.IMM,
                BranchType.NO_BRANCH,
                Bits(32)(0x1008),
                Bits(32)(0x1004),
                Bits(32)(0x1004),
                Bits(32)(0xABCDEF00),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(60),
                Bits(32)(0x1008),
            ),  # ALU结果: 0x1004 + 0 = 0x1004 (计算地址)
            # Case 2: SW (Store Word) - 存储数据到地址0x1008
            (
                ALUOp.ADD,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.IMM,
                BranchType.NO_BRANCH,
                Bits(32)(0x100C),
                Bits(32)(0x1008),
                Bits(32)(0x1008),
                Bits(32)(0x11223344),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(70),
                Bits(32)(0x100C),
            ),  # ALU结果: 0x1008 + 0 = 0x1008 (计算地址)
            # --- Load 指令测试 ---
            # Case 3: LW (Load Word) - 从地址0x1000加载数据
            (
                ALUOp.ADD,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.IMM,
                BranchType.NO_BRANCH,
                Bits(32)(0x1004),
                Bits(32)(0x1000),
                Bits(32)(0x1000),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(80),
                Bits(32)(0x1004),
            ),  # ALU结果: 0x1000 + 0 = 0x1000 (计算地址)
            # Case 4: LW (Load Word) - 从地址0x1004加载数据
            (
                ALUOp.ADD,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.IMM,
                BranchType.NO_BRANCH,
                Bits(32)(0x1008),
                Bits(32)(0x1004),
                Bits(32)(0x1004),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(90),
                Bits(32)(0x1008),
            ),  # ALU结果: 0x1004 + 0 = 0x1004 (计算地址)
            # Case 5: LW (Load Word) - 从地址0x1008加载数据
            (
                ALUOp.ADD,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.IMM,
                BranchType.NO_BRANCH,
                Bits(32)(0x100C),
                Bits(32)(0x1008),
                Bits(32)(0x1008),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(100),
                Bits(32)(0x100C),
            ),  # ALU结果: 0x1008 + 0 = 0x1008 (计算地址)
            # --- 地址对齐测试 ---
            # Case 6: SW (Store Word) - 未对齐地址访问
            (
                ALUOp.ADD,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.IMM,
                BranchType.NO_BRANCH,
                Bits(32)(0x1004),
                Bits(32)(0x1000),
                Bits(32)(0x1001),
                Bits(32)(0x55555555),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(110),
                Bits(32)(0x1004),
            ),  # ALU结果: 0x1001 + 0 = 0x1001 (计算地址)
            # Case 7: LW (Load Word) - 未对齐地址访问
            (
                ALUOp.ADD,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.IMM,
                BranchType.NO_BRANCH,
                Bits(32)(0x1004),
                Bits(32)(0x1000),
                Bits(32)(0x1003),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(120),
                Bits(32)(0x1004),
            ),  # ALU结果: 0x1003 + 0 = 0x1003 (计算地址)
            # --- 不同宽度的Store指令测试 ---
            # Case 8: SH (Store Half) - 存储半字到地址0x1010
            (
                ALUOp.ADD,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.IMM,
                BranchType.NO_BRANCH,
                Bits(32)(0x1014),
                Bits(32)(0x1010),
                Bits(32)(0x1010),
                Bits(32)(0xABCD),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(130),
                Bits(32)(0x1014),
            ),  # 地址=0x1010
            # Case 9: SB (Store Byte) - 存储字节到地址0x1011
            (
                ALUOp.ADD,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.IMM,
                BranchType.NO_BRANCH,
                Bits(32)(0x1014),
                Bits(32)(0x1010),
                Bits(32)(0x1011),
                Bits(32)(0xEF),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(140),
                Bits(32)(0x1011),
            ),  # 地址=0x1011
            # --- 不同宽度的Load指令测试 ---
            # Case 10: LH (Load Half) - 从地址0x1010加载半字（有符号）
            (
                ALUOp.ADD,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.IMM,
                BranchType.NO_BRANCH,
                Bits(32)(0x1014),
                Bits(32)(0x1010),
                Bits(32)(0x1010),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(150),
                Bits(32)(0x1010),
            ),  # 地址=0x1010
            # Case 11: LHU (Load Half Unsigned) - 从地址0x1010加载半字（无符号）
            (
                ALUOp.ADD,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.IMM,
                BranchType.NO_BRANCH,
                Bits(32)(0x1014),
                Bits(32)(0x1010),
                Bits(32)(0x1010),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(160),
                Bits(32)(0x1014),
            ),  # 地址=0x1010
            # Case 12: LB (Load Byte) - 从地址0x1011加载字节（有符号）
            (
                ALUOp.ADD,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.IMM,
                BranchType.NO_BRANCH,
                Bits(32)(0x1014),
                Bits(32)(0x1010),
                Bits(32)(0x1011),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(170),
                Bits(32)(0x1014),
            ),  # 地址=0x1011
            # Case 13: LBU (Load Byte Unsigned) - 从地址0x1011加载字节（无符号）
            (
                ALUOp.ADD,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.IMM,
                BranchType.NO_BRANCH,
                Bits(32)(0x1014),
                Bits(32)(0x1010),
                Bits(32)(0x1011),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(180),
                Bits(32)(0x1014),
            ),  # 地址=0x1011
            # --- 混合宽度测试 ---
            # Case 14: SW + SH + SB - 连续存储不同宽度的数据
            (
                ALUOp.ADD,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.IMM,
                BranchType.NO_BRANCH,
                Bits(32)(0x1020),
                Bits(32)(0x1020),
                Bits(32)(0x12345678),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(190),
                Bits(32)(0x1024),
            ),  # 地址=0x12345678
            # Case 15: 从0x1020读取字，验证之前存储的数据
            (
                ALUOp.ADD,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.IMM,
                BranchType.NO_BRANCH,
                Bits(32)(0x1024),
                Bits(32)(0x1020),
                Bits(32)(0x1020),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(200),
                Bits(32)(0x1024),
            ),  # 地址=0x1020
            # --- 半字和字节未对齐测试 ---
            # Case 16: SH (Store Half) - 未对齐地址访问
            (
                ALUOp.ADD,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.IMM,
                BranchType.NO_BRANCH,
                Bits(32)(0x1024),
                Bits(32)(0x1020),
                Bits(32)(0x1021),
                Bits(32)(0x1234),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(210),
                Bits(32)(0x1024),
            ),  # ALU结果: 0x1021 + 0 = 0x1021 (计算地址)
            # Case 17: LH (Load Half) - 未对齐地址访问
            (
                ALUOp.ADD,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.IMM,
                BranchType.NO_BRANCH,
                Bits(32)(0x1024),
                Bits(32)(0x1020),
                Bits(32)(0x1023),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(220),
                Bits(32)(0x1024),
            ),  # ALU结果: 0x1023 + 0 = 0x1023 (计算地址)
        ]

        # --- 激励生成逻辑 ---
        # 1. 计数器：跟踪当前测试进度
        cnt = RegArray(UInt(32), 1)
        (cnt & self)[0] <= cnt[0] + UInt(32)(1)

        idx = cnt[0]

        # 组合逻辑 Mux：根据 idx 选择当前的测试向量
        # 初始化默认值
        current_alu_func = Bits(16)(0)
        current_rs1_sel = Bits(4)(0)
        current_rs2_sel = Bits(4)(0)
        current_op1_sel = Bits(3)(0)
        current_op2_sel = Bits(3)(0)
        current_branch_type = Bits(16)(0)
        current_next_pc_addr = Bits(32)(0)
        current_pc = Bits(32)(0)
        current_rs1_data = Bits(32)(0)
        current_rs2_data = Bits(32)(0)
        current_imm = Bits(32)(0)
        current_ex_mem_fwd = Bits(32)(0)
        current_mem_wb_fwd = Bits(32)(0)
        current_wb_fwd = Bits(32)(0)
        current_expected = Bits(32)(0)

        # 这里的循环展开会生成一棵 Mux 树
        for i, (
            alu_func,
            rs1_sel,
            rs2_sel,
            op1_sel,
            op2_sel,
            branch_type,
            next_pc_addr,
            pc,
            rs1_data,
            rs2_data,
            imm,
            ex_mem_fwd,
            mem_wb_fwd,
            wb_fwd,
            expected,
        ) in enumerate(vectors):
            is_match = idx == UInt(32)(i)

            current_alu_func = is_match.select(alu_func, current_alu_func)
            current_rs1_sel = is_match.select(rs1_sel, current_rs1_sel)
            current_rs2_sel = is_match.select(rs2_sel, current_rs2_sel)
            current_op1_sel = is_match.select(op1_sel, current_op1_sel)
            current_op2_sel = is_match.select(op2_sel, current_op2_sel)
            current_branch_type = is_match.select(branch_type, current_branch_type)
            current_next_pc_addr = is_match.select(next_pc_addr, current_next_pc_addr)
            current_pc = is_match.select(pc, current_pc)
            current_rs1_data = is_match.select(rs1_data, current_rs1_data)
            current_rs2_data = is_match.select(rs2_data, current_rs2_data)
            current_imm = is_match.select(imm, current_imm)
            current_ex_mem_fwd = is_match.select(ex_mem_fwd, current_ex_mem_fwd)
            current_mem_wb_fwd = is_match.select(mem_wb_fwd, current_mem_wb_fwd)
            current_wb_fwd = is_match.select(wb_fwd, current_wb_fwd)
            current_expected = is_match.select(expected, current_expected)

        dynamic_rd_addr = (idx == idx).select(Bits(5)(1), Bits(5)(1))

        # 4. 构建控制信号包
        # 首先创建mem_ctrl信号
        # 根据测试用例索引设置不同的内存操作
        mem_opcode = MemOp.NONE  # 默认不进行内存操作
        mem_width = MemWidth.WORD  # 默认字访问
        mem_unsigned = MemSign.UNSIGNED  # 默认无符号扩展

        # 为Store和Load操作设置内存操作码和宽度
        with Condition(idx >= UInt(32)(0) & idx < UInt(32)(3)):  # Cases 0-2: SW操作
            mem_opcode = MemOp.STORE
            mem_width = MemWidth.WORD

        with Condition(idx >= UInt(32)(3) & idx < UInt(32)(6)):  # Cases 3-5: LW操作
            mem_opcode = MemOp.LOAD
            mem_width = MemWidth.WORD

        with Condition(
            idx >= UInt(32)(6) & idx < UInt(32)(8)
        ):  # Cases 6-7: 未对齐访问测试
            mem_opcode = MemOp.STORE if (idx == UInt(32)(6)) else MemOp.LOAD
            mem_width = MemWidth.WORD

        # 不同宽度的Store操作
        with Condition(idx == UInt(32)(8)):  # Case 8: SH操作
            mem_opcode = MemOp.STORE
            mem_width = MemWidth.HALF

        with Condition(idx == UInt(32)(9)):  # Case 9: SB操作
            mem_opcode = MemOp.STORE
            mem_width = MemWidth.BYTE

        # 不同宽度的Load操作
        with Condition(idx == UInt(32)(10)):  # Case 10: LH操作
            mem_opcode = MemOp.LOAD
            mem_width = MemWidth.HALF
            mem_unsigned = MemSign.SIGNED  # 有符号扩展

        with Condition(idx == UInt(32)(11)):  # Case 11: LHU操作
            mem_opcode = MemOp.LOAD
            mem_width = MemWidth.HALF
            mem_unsigned = MemSign.UNSIGNED  # 无符号扩展

        with Condition(idx == UInt(32)(12)):  # Case 12: LB操作
            mem_opcode = MemOp.LOAD
            mem_width = MemWidth.BYTE
            mem_unsigned = MemSign.SIGNED  # 有符号扩展

        with Condition(idx == UInt(32)(13)):  # Case 13: LBU操作
            mem_opcode = MemOp.LOAD
            mem_width = MemWidth.BYTE
            mem_unsigned = MemSign.UNSIGNED  # 无符号扩展

        # 混合宽度测试
        with Condition(idx == UInt(32)(14)):  # Case 14: SW操作
            mem_opcode = MemOp.STORE
            mem_width = MemWidth.WORD

        with Condition(idx == UInt(32)(15)):  # Case 15: LW操作
            mem_opcode = MemOp.LOAD
            mem_width = MemWidth.WORD

        # 半字和字节未对齐测试
        with Condition(idx == UInt(32)(16)):  # Case 16: SH操作
            mem_opcode = MemOp.STORE
            mem_width = MemWidth.HALF

        with Condition(idx == UInt(32)(17)):  # Case 17: LH操作
            mem_opcode = MemOp.LOAD
            mem_width = MemWidth.HALF
            mem_unsigned = MemSign.SIGNED  # 有符号扩展

        mem_ctrl = mem_ctrl_signals.bundle(
            mem_opcode=mem_opcode,
            mem_width=mem_width,
            mem_unsigned=mem_unsigned,
            rd_addr=dynamic_rd_addr,  # 默认写入x1寄存器
            halt_if=Bits(1)(0),
        )

        # 然后创建ex_ctrl信号
        ctrl_pkt = ex_ctrl_signals.bundle(
            alu_func=current_alu_func,
            rs1_sel=current_rs1_sel,
            rs2_sel=current_rs2_sel,
            op1_sel=current_op1_sel,
            op2_sel=current_op2_sel,
            branch_type=current_branch_type,
            next_pc_addr=current_next_pc_addr,
            mem_ctrl=mem_ctrl,
        )

        # 设置旁路数据
        ex_mem_bypass[0] = current_ex_mem_fwd
        mem_wb_bypass[0] = current_mem_wb_fwd
        wb_bypass[0] = current_wb_fwd

        # 发送数据到Execution模块
        # 只有当 idx 在向量范围内时才发送 (valid)
        valid_test = idx < UInt(32)(len(vectors))

        with Condition(~valid_test):
            finish()

        log(
            "Driver: idx={} alu_func={} rs1_sel={} rs2_sel={} op1_sel={} op2_sel={} branch_type={} pc=0x{:x} rs1=0x{:x} rs2=0x{:x} imm=0x{:x} ex_mem_fwd=0x{:x} mem_wb_fwd=0x{:x} wb_fwd=0x{:x} expected=0x{:x}",
            idx,
            current_alu_func,
            current_rs1_sel,
            current_rs2_sel,
            current_op1_sel,
            current_op2_sel,
            current_branch_type,
            current_pc,
            current_rs1_data,
            current_rs2_data,
            current_imm,
            current_ex_mem_fwd,
            current_mem_wb_fwd,
            current_wb_fwd,
            current_expected,
        )

        # 从寄存器读取数据并调用Execution模块
        dut.async_called(
            ctrl=ctrl_pkt,
            pc=current_pc,
            rs1_data=current_rs1_data,
            rs2_data=current_rs2_data,
            imm=current_imm,
        )

        mock_feedback.async_called()  # 触发 MockFeedback 模块

        return cnt, current_expected


# ==============================================================================
# 3. 验证逻辑 (Python Check)
# ==============================================================================
def check(raw_output):
    print(">>> 开始验证EX模块输出（第三部分：内存操作测试）...")

    # 预期结果列表 (必须与Driver中的vectors严格对应)
    # 根据用户反馈，SRAM在EX阶段只输入目标地址，无论读写都在下周期进行，只有MEM阶段能看到，所以预期输出是地址而非结果
    expected_results = [
        0x00001000,  # Case 0: SW (rs1=0x1000 + imm=0) = 0x1000
        0x00001004,  # Case 1: SW (rs1=0x1004 + imm=0) = 0x1004
        0x00001008,  # Case 2: SW (rs1=0x1008 + imm=0) = 0x1008
        0x00001000,  # Case 3: LW (rs1=0x1000 + imm=0) = 0x1000
        0x00001004,  # Case 4: LW (rs1=0x1004 + imm=0) = 0x1004
        0x00001008,  # Case 5: LW (rs1=0x1008 + imm=0) = 0x1008
        0x00001001,  # Case 6: SW (rs1=0x1001 + imm=0) = 0x1001
        0x00001003,  # Case 7: LW (rs1=0x1003 + imm=0) = 0x1003
        0x00001010,  # Case 8: SH (rs1=0x1010 + imm=0) = 0x1010
        0x00001011,  # Case 9: LH (rs1=0x1011 + imm=0) = 0x1011
        0x00001010,  # Case 10: LHU (rs1=0x1010 + imm=0) = 0x1010
        0x00001010,  # Case 11: LB (rs1=0x1010 + imm=0) = 0x1010
        0x00001011,  # Case 12: SW (rs1=0x1011 + imm=0) = 0x1011
        0x00001011,  # Case 13: LBU (rs1=0x1011 + imm=0) = 0x1011
        0x12345678,  # Case 14: SH (rs1=0x12345678 + imm=0) = 0x12345678
        0x00001020,  # Case 15: LW (rs1=0x1020 + imm=0) = 0x1020
        0x00001021,  # Case 16: SH (rs1=0x1021 + imm=0) = 0x1021
        0x00001023,  # Case 17: LH (rs1=0x1023 + imm=0) = 0x1023
    ]

    # 使用公共验证函数
    check_alu_results(raw_output, expected_results, "EX模块第三部分（内存操作测试）")
    check_bypass_updates(raw_output, expected_results)

    print("✅ EX模块第三部分测试通过！（内存操作均正确）")


# ==============================================================================
# 4. 主执行入口
# ==============================================================================
if __name__ == "__main__":
    sys = SysBuilder("test_execute_module_part3")

    with sys:
        # 创建测试模块
        dut = Execution()
        driver = Driver()

        # 创建Mock模块
        mock_sram = MockSRAM()
        mock_feedback = MockFeedback()
        mock_mem_module = MockMEM()

        # 创建旁路寄存器和分支目标寄存器
        ex_mem_bypass = RegArray(Bits(32), 1)
        mem_wb_bypass = RegArray(Bits(32), 1)
        wb_bypass = RegArray(Bits(32), 1)
        branch_target_reg = RegArray(Bits(32), 1)

        # [关键] 获取 Driver 的返回值
        driver.build(
            dut,
            ex_mem_bypass,
            mem_wb_bypass,
            wb_bypass,
            mock_feedback,
        )

        # 调用Execution模块，传入所有必要的参数
        dut.build(
            mem_module=mock_mem_module,
            ex_mem_bypass=ex_mem_bypass,
            mem_wb_bypass=mem_wb_bypass,
            wb_bypass=wb_bypass,
            branch_target_reg=branch_target_reg,
            dcache=mock_sram,
        )

        # 调用MockFeedback模块，检查旁路寄存器和分支目标寄存器的值
        mock_feedback.build(branch_target_reg, ex_mem_bypass)

    run_test_module(sys, check)
