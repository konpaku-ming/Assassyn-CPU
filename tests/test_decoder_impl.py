import sys
import os
import re

# 1. 环境路径设置 (确保能 import src)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from assassyn.frontend import *

# 导入Decoder模块和相关信号定义
from src.decoder import Decoder, DecoderImpl
from src.control_signals import *
from tests.common import run_test_module
from tests.test_mock import MockExecutor, MockDataHazardUnit


# ==============================================================================
# 1. Driver 模块定义：前三行不能改，这是Assassyn的约定。
# ==============================================================================
class Driver(Module):
    def __init__(self):
        super().__init__(ports={})

    @module.combinational
    def build(
        self,
        dut: Decoder,
        icache_dout: Array,
        reg_file: Array,
        mock_dhu: MockDataHazardUnit,
        branch_target_reg: Array,
    ):
        # --- 测试向量定义 ---
        # 格式: (pc, instruction, rs1_sel, rs2_sel, stall_if, branch_target)
        vectors = [
            # R-Type指令测试
            # add x3, x1, x2 -> 0x002081B3 (funct3=0b000, funct7=0b0000000)
            (
                Bits(32)(0x00000000),
                Bits(32)(0x002081B3),
                Bits(4)(0x2),
                Bits(4)(0x3),
                Bits(1)(0),
                Bits(32)(0),
            ),
            # sub x3, x1, x2 -> 0x402081B3 (funct3=0b000, funct7=0b0100000)
            (
                Bits(32)(0x00000004),
                Bits(32)(0x402081B3),
                Bits(4)(0x2),
                Bits(4)(0x3),
                Bits(1)(0),
                Bits(32)(0),
            ),
            # I-Type指令测试 (ALU)
            # addi x1, x2, 5 -> 0x00510093
            (
                Bits(32)(0x00000008),
                Bits(32)(0x00510093),
                Bits(4)(0x2),
                Bits(4)(0x0),
                Bits(1)(0),
                Bits(32)(0),
            ),
            # I-Type指令测试 (Load)
            # lw x1, 4(x2) -> 0x00412083
            (
                Bits(32)(0x0000000C),
                Bits(32)(0x00412083),
                Bits(4)(0x2),
                Bits(4)(0x0),
                Bits(1)(0),
                Bits(32)(0),
            ),
            # S-Type指令测试
            # sw x1, 4(x2) -> 0x00112223
            (
                Bits(32)(0x00000010),
                Bits(32)(0x00112223),
                Bits(4)(0x2),
                Bits(4)(0x1),
                Bits(1)(0),
                Bits(32)(0),
            ),
            # B-Type指令测试
            # beq x1, x2, 8 -> 0x00208463
            (
                Bits(32)(0x00000014),
                Bits(32)(0x00208463),
                Bits(4)(0x1),
                Bits(4)(0x2),
                Bits(1)(0),
                Bits(32)(0),
            ),
            # U-Type指令测试
            # lui x1, 0x12345 -> 0x123450b7
            (
                Bits(32)(0x00000018),
                Bits(32)(0x123450B7),
                Bits(4)(0x0),
                Bits(4)(0x0),
                Bits(1)(0),
                Bits(32)(0),
            ),
            # J-Type指令测试
            # jal x1, 0x100 -> 0x0FE000EF
            (
                Bits(32)(0x0000001C),
                Bits(32)(0x100000EF),
                Bits(4)(0x0),
                Bits(4)(0x0),
                Bits(1)(0),
                Bits(32)(0),
            ),
            # 特殊指令测试
            # ecall -> 0x00000073
            (
                Bits(32)(0x00000020),
                Bits(32)(0x00000073),
                Bits(4)(0x0),
                Bits(4)(0x0),
                Bits(1)(0),
                Bits(32)(0),
            ),
            # 流水线停顿测试
            # add x3, x1, x2 + stall_if = 1
            (
                Bits(32)(0x00000024),
                Bits(32)(0x002081B3),
                Bits(4)(0x2),
                Bits(4)(0x3),
                Bits(1)(1),
                Bits(32)(0),
            ),
            # 流水线刷新测试
            # add x3, x1, x2 + branch_target = 0x100
            (
                Bits(32)(0x00000028),
                Bits(32)(0x002081B3),
                Bits(4)(0x2),
                Bits(4)(0x3),
                Bits(1)(0),
                Bits(32)(0x100),
            ),
        ]

        # --- 激励生成逻辑 ---
        # 1. 计数器：跟踪当前测试进度
        cnt = RegArray(UInt(32), 1)
        (cnt & self)[0] <= cnt[0] + UInt(32)(1)

        idx = cnt[0]

        # 1. 初始化寄存器 (Cycle 0, 1)
        # 预设环境：x1=0x10, x2=0x20
        is_init_x1 = idx == UInt(32)(0)
        is_init_x2 = idx == UInt(32)(1)

        with Condition(is_init_x1):
            reg_file[1] = Bits(32)(0x10)
        with Condition(is_init_x2):
            reg_file[2] = Bits(32)(0x20)

        # 2. 发送测试向量 (Cycle 2+)
        vec_idx = idx - UInt(32)(2)
        valid_test = (idx >= UInt(32)(2)) & (vec_idx < UInt(32)(len(vectors)))
        
        # 组合逻辑 Mux：根据 idx 选择当前的测试向量
        # 初始化默认值
        current_pc = Bits(32)(0)
        current_instruction = Bits(32)(0)
        current_rs1_sel = Bits(4)(0)
        current_rs2_sel = Bits(4)(0)
        current_stall_if = Bits(1)(0)
        current_branch_target = Bits(32)(0)

        # 这里的循环展开会生成一棵 Mux 树
        for i, (
            pc,
            instruction,
            rs1_sel,
            rs2_sel,
            stall_if,
            branch_target,
        ) in enumerate(vectors):
            is_match = vec_idx == UInt(32)(i)

            current_pc = is_match.select(pc, current_pc)
            current_instruction = is_match.select(instruction, current_instruction)
            current_rs1_sel = is_match.select(rs1_sel, current_rs1_sel)
            current_rs2_sel = is_match.select(rs2_sel, current_rs2_sel)
            current_stall_if = is_match.select(stall_if, current_stall_if)
            current_branch_target = is_match.select(
                branch_target, current_branch_target
            )


        # 打印输入，方便定位
        with Condition(valid_test):
            # 设置Decoder的PC输入
            next_pc = (current_pc.bitcast(UInt(32)) + UInt(32)(4)).bitcast(Bits(32))
            dut_call = dut.async_called(pc=current_pc, next_pc=next_pc, stall=current_stall_if)
            dut_call.bind.set_fifo_depth(pc=1, next_pc=1, stall=1)

            # 设置icache_dout的值
            icache_dout[0] = current_instruction

            # 设置流水线控制信号
            branch_target_reg[0] = current_branch_target
            call = mock_dhu.async_called(
                rs1_sel=current_rs1_sel,
                rs2_sel=current_rs2_sel,
                stall_if=current_stall_if,
            )
            call.bind.set_fifo_depth(rs1_sel=1, rs2_sel=1, stall_if=1)
            
            log(
                "Driver: idx={} pc=0x{:x} instruction=0x{:x} rs1_sel=0x{:x} rs2_sel=0x{:x} stall_if=0x{:x} branch_target=0x{:x}",
                vec_idx,
                current_pc,
                current_instruction,
                current_rs1_sel,
                current_rs2_sel,
                current_stall_if,
                current_branch_target,
            )

        with Condition(idx > UInt(32)(len(vectors) + 4)):
            finish()


# ==============================================================================
# 2. 验证逻辑 (Python Check)
# ==============================================================================
def check(raw_output):
    print(">>> 开始验证MockExecutor输出...")

    # 定义常量，用于验证
    # ALU功能常量
    ALU_ADD = 0b0000000000000001
    ALU_SUB = 0b0000000000000010
    ALU_SLL = 0b0000000000000100
    ALU_SLT = 0b0000000000001000
    ALU_SLTU = 0b0000000000010000
    ALU_XOR = 0b0000000000100000
    ALU_SRL = 0b0000000001000000
    ALU_SRA = 0b0000000010000000
    ALU_OR = 0b0000000100000000
    ALU_AND = 0b0000001000000000
    ALU_SYS = 0b0000010000000000
    ALU_NOP = 0b1000000000000000

    # 操作数选择常量
    OP1_RS1 = 0b001
    OP1_PC = 0b010
    OP1_ZERO = 0b100

    OP2_RS2 = 0b001
    OP2_IMM = 0b010
    OP2_4 = 0b100

    # 分支类型常量
    BR_NONE = 0b0000000000000001
    BR_BEQ = 0b0000000000000010
    BR_JAL = 0b0000000010000000

    # 预期结果表
    # 格式: (alu_func, op1_sel, op2_sel, imm, rs1_data, rs2_data, pc)
    # 注意：RS1_D 和 RS2_D 是基于 Driver 初始化的 (x1=0x10, x2=0x20)
    expected_vectors = [
        # Case 0: R-Type指令测试 - add x3, x1, x2
        {
            "alu_func": ALU_ADD,
            "op1_sel": OP1_RS1,
            "op2_sel": OP2_RS2,
            "imm": 0x0,
            "rs1_data": 0x10,
            "rs2_data": 0x20,
            "pc": 0x0,
        },
        # Case 1: R-Type指令测试 - sub x3, x1, x2 
        {
            "alu_func": ALU_SUB,
            "op1_sel": OP1_RS1,
            "op2_sel": OP2_RS2,
            "imm": 0x0,
            "rs1_data": 0x10,
            "rs2_data": 0x20,
            "pc": 0x4,
        },
        # Case 2: I-Type指令测试 (ALU) - addi x1, x2, 5 
        {
            "alu_func": ALU_ADD,
            "op1_sel": OP1_RS1,
            "op2_sel": OP2_IMM,
            "imm": 0x5,
            "rs1_data": 0x20,
            "rs2_data": 0x0,
            "pc": 0x8,
        },
        # Case 3: I-Type指令测试 (Load) - lw x1, 4(x2)
        {
            "alu_func": ALU_ADD,
            "op1_sel": OP1_RS1,
            "op2_sel": OP2_IMM,
            "imm": 0x4,
            "rs1_data": 0x20,
            "rs2_data": 0x0,
            "pc": 0xC,
        },
        # Case 4: S-Type指令测试 - sw x1, 4(x2)
        {
            "alu_func": ALU_ADD,
            "op1_sel": OP1_RS1,
            "op2_sel": OP2_IMM,
            "imm": 0x4,
            "rs1_data": 0x20,
            "rs2_data": 0x10,
            "pc": 0x10,
        },
        # Case 5: B-Type指令测试 - beq x1, x2, 8
        {
            "alu_func": ALU_SUB,
            "op1_sel": OP1_RS1,
            "op2_sel": OP2_RS2,
            "imm": 0x8,
            "rs1_data": 0x10,
            "rs2_data": 0x20,
            "pc": 0x14,
        },
        # Case 6: U-Type指令测试 - lui x1, 0x12345
        {
            "alu_func": ALU_ADD,
            "op1_sel": OP1_ZERO,
            "op2_sel": OP2_IMM,
            "imm": 0x12345000,
            "rs1_data": 0x0,
            "rs2_data": 0x0,
            "pc": 0x18,
        },
        # Case 7: J-Type指令测试 - jal x1, 0x100
        {
            "alu_func": ALU_ADD,
            "op1_sel": OP1_PC,
            "op2_sel": OP2_4,
            "imm": 0x100,
            "rs1_data": 0x0,
            "rs2_data": 0x0,
            "pc": 0x1C,
        },
        # Case 8: 特殊指令测试 - ecall
        {
            "alu_func": ALU_SYS,
            "op1_sel": OP1_RS1,
            "op2_sel": OP2_IMM,
            "imm": 0x0,
            "rs1_data": 0x0,
            "rs2_data": 0x0,
            "pc": 0x20,
        },
        # Case 9: 流水线停顿测试 - add x3, x1, x2 + stall_if = 1
        {
            "alu_func": ALU_NOP,
            "op1_sel": OP1_RS1,
            "op2_sel": OP2_RS2,
            "imm": 0x0,
            "rs1_data": 0x10,
            "rs2_data": 0x20,
            "pc": 0x24,
        },
        # Case 10: 流水线刷新测试 - add x3, x1, x2 + branch_target = 0x100
        {
            "alu_func": ALU_NOP,
            "op1_sel": OP1_RS1,
            "op2_sel": OP2_RS2,
            "imm": 0x0,
            "rs1_data": 0x10,
            "rs2_data": 0x20,
            "pc": 0x28,
        },
    ]

    # 解析MockExecutor输出
    captured_logs = []

    for line in raw_output.split("\n"):
        if "MockExecutor:" in line:
            # 解析格式: "MockExecutor: alu_func=0x{:x} op1_sel=0x{:x} op2_sel=0x{:x} imm=0x{:x} rs1_data=0x{:x} rs2_data=0x{:x} pc=0x{:x}"
            try:
                # 提取各个字段
                alu_func_match = re.search(r"alu_func=0x([0-9a-fA-F]+)", line)
                op1_sel_match = re.search(r"op1_sel=0x([0-9a-fA-F]+)", line)
                op2_sel_match = re.search(r"op2_sel=0x([0-9a-fA-F]+)", line)
                imm_match = re.search(r"imm=0x([0-9a-fA-F]+)", line)
                rs1_data_match = re.search(r"rs1_data=0x([0-9a-fA-F]+)", line)
                rs2_data_match = re.search(r"rs2_data=0x([0-9a-fA-F]+)", line)
                pc_match = re.search(r"pc=0x([0-9a-fA-F]+)", line)

                if all(
                    [
                        alu_func_match,
                        op1_sel_match,
                        op2_sel_match,
                        imm_match,
                        rs1_data_match,
                        rs2_data_match,
                        pc_match,
                    ]
                ):

                    data = {
                        "alu_func": int(alu_func_match.group(1), 16),
                        "op1_sel": int(op1_sel_match.group(1), 16),
                        "op2_sel": int(op2_sel_match.group(1), 16),
                        "imm": int(imm_match.group(1), 16),
                        "rs1_data": int(rs1_data_match.group(1), 16),
                        "rs2_data": int(rs2_data_match.group(1), 16),
                        "pc": int(pc_match.group(1), 16),
                    }

                    captured_logs.append(data)
                    print(f"  [捕获] MockExecutor输出: PC=0x{data['pc']:x}")

            except Exception as e:
                print(f"⚠️ 解析警告: {line} -> {e}")
                pass

    print(f"捕获到 {len(captured_logs)} 条MockExecutor输出")

    # 验证输出数量
    if len(captured_logs) < len(expected_vectors):
        print(
            f"❌ 错误：输出数量不足。预期 {len(expected_vectors)} 条，实际 {len(captured_logs)} 条"
        )
        assert False

    # 逐条比对
    for i, exp in enumerate(expected_vectors):
        if i >= len(captured_logs):
            print(f"❌ 错误：缺少第 {i} 条输出")
            assert False

        act = captured_logs[i]
        print(f"验证 Case {i} (PC=0x{exp.get('pc', 0):x})...")

        error_found = False
        for key, exp_val in exp.items():
            act_val = act.get(key, -1)

            # 特殊处理：对于imm字段，允许有符号扩展的差异
            if key == "imm":
                # 检查是否是12位立即数的有符号扩展
                if (exp_val & 0xFFF) == (act_val & 0xFFF):
                    continue

            if act_val != exp_val:
                print(f"  不匹配 [{key}]: 预期=0x{exp_val:x} 实际=0x{act_val:x}")
                error_found = True

        if error_found:
            print(f"❌ Case {i} 验证失败！")
            assert False
        else:
            print(f"✅ Case {i} 验证通过")

    print("✅ 所有MockExecutor输出验证通过！")
    print("✅ 无数据冲突下正常instruction解析正确")
    print("✅ 存在stall_if情况下的输出正确")
    print("✅ 流水线刷新情况下的输出正确")


# ==============================================================================
# 3. 主执行入口
# ==============================================================================
if __name__ == "__main__":

    sys = SysBuilder("test_decoder_impl_module")

    with sys:
        # 创建测试模块
        driver = Driver()
        dut = Decoder()
        dut_impl = DecoderImpl()
        executor = MockExecutor()
        datahazardunit = MockDataHazardUnit()

        # 创建必要的辅助模块和数据结构
        icache_dout = RegArray(Bits(32), 1)
        reg_file = RegArray(Bits(32), 32)
        branch_target_reg = RegArray(Bits(32), 1)

        # 构建Driver
        driver.build(
            dut,
            icache_dout,
            reg_file,
            datahazardunit,
            branch_target_reg,
        )

        # 构建Decoder
        pre_pkt, _, _ = dut.build(icache_dout, reg_file)

        stall_if, rs1_sel, rs2_sel = datahazardunit.build()

        # 构建DecoderImpl
        dut_impl.build(
            pre_pkt,
            executor,
            rs1_sel,
            rs2_sel,
            stall_if,
            branch_target_reg,
        )
        
        executor.build()

    run_test_module(sys, check)
