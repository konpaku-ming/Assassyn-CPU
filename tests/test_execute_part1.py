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
        #
        # alu_func: ALU功能码 (独热码)
        # rs1_sel/rs2_sel: 数据来源选择 (独热码)
        # op1_sel/op2_sel: 操作数选择 (独热码)
        # branch_type: 分支类型 (16位独热码)
        # next_pc_addr: 预测的下一条PC地址
        # pc: 当前PC值
        # rs1_data: 寄存器数据
        # rs2_data: 寄存器数据
        # imm: 立即数
        # ex_mem_fwd: EX-MEM旁路数据
        # mem_wb_fwd: MEM-WB旁路数据
        # wb_fwd: WB旁路数据 (来自写回阶段的旁路数据)
        # expected_result: 预期的ALU结果

        vectors = [
            # --- ALU 操作测试 ---
            # Case 0: ADD 指令 (rs1 + rs2)
            (
                ALUOp.ADD,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.RS2,
                BranchType.NO_BRANCH,
                Bits(32)(0x1004),
                Bits(32)(0x1000),
                Bits(32)(10),
                Bits(32)(20),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(30),
            ),
            # Case 1: SUB 指令 (rs1 - rs2)
            (
                ALUOp.SUB,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.RS2,
                BranchType.NO_BRANCH,
                Bits(32)(0x1004),
                Bits(32)(0x1000),
                Bits(32)(20),
                Bits(32)(10),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(10),
            ),
            # Case 2: AND 指令 (rs1 & rs2)
            (
                ALUOp.AND,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.RS2,
                BranchType.NO_BRANCH,
                Bits(32)(0x1004),
                Bits(32)(0x1000),
                Bits(32)(0xF0F0F0F0),
                Bits(32)(0x0F0F0F0F),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0x00000000),
            ),
            # Case 3: OR 指令 (rs1 | rs2)
            (
                ALUOp.OR,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.RS2,
                BranchType.NO_BRANCH,
                Bits(32)(0x1004),
                Bits(32)(0x1000),
                Bits(32)(0xF0F0F0F0),
                Bits(32)(0x0F0F0F0F),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0xFFFFFFFF),
            ),
            # Case 4: SLL 指令 (rs1 << rs2[4:0])
            (
                ALUOp.SLL,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.RS2,
                BranchType.NO_BRANCH,
                Bits(32)(0x1004),
                Bits(32)(0x1000),
                Bits(32)(0x0000000F),
                Bits(32)(2),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0x0000003C),
            ),
            # Case 5: SRL 指令 (rs1 >> rs2[4:0])
            (
                ALUOp.SRL,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.RS2,
                BranchType.NO_BRANCH,
                Bits(32)(0x1004),
                Bits(32)(0x1000),
                Bits(32)(0xFFFFFFFC),
                Bits(32)(2),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0x3FFFFFFF),
            ),
            # Case 6: SRA 指令 (有符号右移)
            (
                ALUOp.SRA,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.RS2,
                BranchType.NO_BRANCH,
                Bits(32)(0x1004),
                Bits(32)(0x1000),
                Bits(32)(0xFFFFFFF0),
                Bits(32)(2),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0xFFFFFFFC),
            ),
            # Case 7: SLT 指令 (有符号比较)
            (
                ALUOp.SLT,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.RS2,
                BranchType.NO_BRANCH,
                Bits(32)(0x1004),
                Bits(32)(0x1000),
                Bits(32)(0xFFFFFFFB),
                Bits(32)(5),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(1),
            ),
            # Case 8: SLTU 指令 (无符号比较)
            (
                ALUOp.SLTU,
                Rs1Sel.RS1,
                Rs2Sel.RS2,
                Op1Sel.RS1,
                Op2Sel.RS2,
                BranchType.NO_BRANCH,
                Bits(32)(0x1004),
                Bits(32)(0x1000),
                Bits(32)(0x80000000),
                Bits(32)(5),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
                Bits(32)(0),
            ),
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
        mem_ctrl = mem_ctrl_signals.bundle(
            mem_opcode=MemOp.NONE,  # 第一部分测试不涉及内存操作
            mem_width=MemWidth.WORD,
            mem_unsigned=MemSign.UNSIGNED,
            rd_addr=dynamic_rd_addr,  # 默认写入x1寄存器
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

        # 7. 发送数据到Execution模块
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
# 2. 验证逻辑 (Python Check)
# ==============================================================================
def check(raw_output):
    print(">>> 开始验证EX模块输出（第一部分：基础ALU操作）...")

    # 预期结果列表 (必须与Driver中的vectors严格对应)
    expected_results = [
        0x0000001E,  # Case 0: ADD (10+20=30)
        0x0000000A,  # Case 1: SUB (20-10=10)
        0x00000000,  # Case 2: AND (0xF0F0F0F0 & 0x0F0F0F0F = 0x00000000)
        0xFFFFFFFF,  # Case 3: OR (0xF0F0F0F0 | 0x0F0F0F0F = 0xFFFFFFFF)
        0x0000003C,  # Case 4: SLL (0x0000000F << 2 = 0x0000003C)
        0x3FFFFFFF,  # Case 5: SRL (0xFFFFFFFC >> 2 = 0x3FFFFFFF)
        0xFFFFFFFC,  # Case 6: SRA (0xFFFFFFF0 >> 2 = 0xFFFFFFFC)
        0x00000001,  # Case 7: SLT (-5 < 5 = 1)
        0x00000000,  # Case 8: SLTU (0x80000000 < 5 = 0, 无符号比较)
    ]

    # 使用公共验证函数
    check_alu_results(raw_output, expected_results, "EX模块第一部分（基础ALU操作）")
    check_bypass_updates(raw_output, expected_results)

    print("✅ EX模块第一部分测试通过！（基础ALU操作正确）")


# ==============================================================================
# 4. 主执行入口
# ==============================================================================
if __name__ == "__main__":
    sys = SysBuilder("test_execute_module_part1")

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
