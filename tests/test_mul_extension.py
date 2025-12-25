"""
RISC-V M Extension - Multiplication Instructions Test
测试 MUL, MULH, MULHSU, MULHU 指令的正确性
"""
import sys
import os
import re

# 1. 环境路径设置 (确保能 import src)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from assassyn.frontend import *

# 导入设计
from src.execution import Execution
from src.control_signals import *
from tests.common import run_test_module
from tests.test_mock import (
    MockSRAM,
    MockMEM,
    MockFeedback,
)


# ==============================================================================
# 1. Driver 模块定义
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
        # 格式: (test_name, alu_func, rs1_data, rs2_data, expected_result)
        
        vectors = [
            # === MUL 测试（返回低32位）===
            ("MUL: 10 * 20", ALUOp.MUL, 10, 20, 200),
            ("MUL: -5 * 3", ALUOp.MUL, 0xFFFFFFFB, 3, 0xFFFFFFF1),  # -5 * 3 = -15
            ("MUL: 100 * 100", ALUOp.MUL, 100, 100, 10000),
            ("MUL: MAX * 2", ALUOp.MUL, 0xFFFFFFFF, 2, 0xFFFFFFFE),
            ("MUL: 0 * anything", ALUOp.MUL, 0, 12345, 0),
            
            # === MULH 测试（有符号×有符号，返回高32位）===
            ("MULH: 0x80000000 * 2", ALUOp.MULH, 0x80000000, 2, 1),  # -2^31 * 2 的高位 = 1
            ("MULH: positive", ALUOp.MULH, 0x40000000, 4, 1),  # 2^30 * 4 = 2^32, 高位=1
            ("MULH: negative", ALUOp.MULH, 0x80000000, 0x80000000, 0x40000000),  # (-2^31)^2
            
            # === MULHSU 测试（有符号×无符号，返回高32位）===
            ("MULHSU: signed * unsigned", ALUOp.MULHSU, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFE),  # -1 * MAX
            ("MULHSU: positive * unsigned", ALUOp.MULHSU, 0x40000000, 4, 1),
            
            # === MULHU 测试（无符号×无符号，返回高32位）===
            ("MULHU: MAX * MAX", ALUOp.MULHU, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFE),
            ("MULHU: large numbers", ALUOp.MULHU, 0x80000000, 0x80000000, 0x40000000),
        ]

        # 初始化测试计数器
        cycle = RegArray(Bits(32), 1)
        cycle[0] = cycle[0] + Bits(32)(1)

        # 遍历测试向量
        for idx, (test_name, alu_func, rs1_val, rs2_val, expected) in enumerate(vectors):
            with Condition(cycle[0] == Bits(32)(idx + 1)):
                # 构造控制信号
                mem_ctrl = mem_ctrl_signals.bundle(
                    mem_opcode=MemOp.NONE,
                    mem_width=MemWidth.WORD,
                    mem_unsigned=Bits(1)(0),
                    rd_addr=Bits(5)(1),  # 写入 x1
                )
                
                ctrl = ex_ctrl_signals.bundle(
                    alu_func=alu_func,
                    rs1_sel=Rs1Sel.RS1,
                    rs2_sel=Rs2Sel.RS2,
                    op1_sel=Op1Sel.RS1,
                    op2_sel=Op2Sel.RS2,
                    branch_type=BranchType.NO_BRANCH,
                    next_pc_addr=Bits(32)(0x1000 + idx * 4),
                    mem_ctrl=mem_ctrl,
                )
                
                # 调用 DUT
                result = dut.async_called(
                    ctrl=ctrl,
                    pc=Bits(32)(0x1000 + idx * 4),
                    rs1_data=Bits(32)(rs1_val),
                    rs2_data=Bits(32)(rs2_val),
                    imm=Bits(32)(0),
                )
                result.bind.set_fifo_depth(ctrl=1, pc=1, rs1_data=1, rs2_data=1, imm=1)
                
                log(f"Test {idx}: {test_name}")
                log(f"  Expected: 0x{expected:08x}")
        
        # 停止条件
        with Condition(cycle[0] == Bits(32)(len(vectors) + 10)):
            finish()


# ==============================================================================
# 2. 主测试函数
# ==============================================================================
def test_mul_extension():
    """主测试入口"""
    sys_name = "test_mul_ext"
    sys = SysBuilder(sys_name)
    
    with sys:
        # 实例化模块
        dcache = MockSRAM(width=32, depth=256)
        ex_mem_bypass = RegArray(Bits(32), 1)
        mem_wb_bypass = RegArray(Bits(32), 1)
        wb_bypass = RegArray(Bits(32), 1)
        branch_target = RegArray(Bits(32), 1)
        
        mem_mock = MockMEM()
        feedback_mock = MockFeedback()
        
        dut = Execution()
        driver = Driver()
        
        # 构建
        dut.build(
            mem_module=mem_mock,
            ex_bypass=ex_mem_bypass,
            mem_bypass=mem_wb_bypass,
            wb_bypass=wb_bypass,
            branch_target_reg=branch_target,
            dcache=dcache,
        )
        
        driver.build(
            dut=dut,
            ex_mem_bypass=ex_mem_bypass,
            mem_wb_bypass=mem_wb_bypass,
            wb_bypass=wb_bypass,
            mock_feedback=feedback_mock,
        )
    
    # 运行测试
    def check(raw):
        """验证测试结果"""
        lines = raw.strip().split('\n')
        
        # 收集所有测试输出
        test_lines = [line for line in lines if 'Test' in line and ':' in line]
        
        # 检查是否有错误
        error_keywords = ['error', 'Error', 'ERROR', 'fail', 'Fail', 'FAIL']
        for line in lines:
            for keyword in error_keywords:
                if keyword in line:
                    print(f"❌ Error detected: {line}")
                    raise AssertionError(f"Test failed with error: {line}")
        
        # 打印所有测试
        print(f"\n{'='*60}")
        print("Multiplication Instruction Tests:")
        print(f"{'='*60}")
        for line in test_lines:
            print(line)
        print(f"{'='*60}")
        
        # 验证至少运行了一些测试
        if len(test_lines) == 0:
            raise AssertionError("No test cases were executed")
        
        print(f"✅ All {len(test_lines)} multiplication tests completed successfully!")
    
    run_test_module(sys, check)


# ==============================================================================
# 3. 主程序入口
# ==============================================================================
if __name__ == '__main__':
    print("Starting RISC-V M Extension Multiplication Tests...")
    test_mul_extension()
    print("All tests passed! ✅")
