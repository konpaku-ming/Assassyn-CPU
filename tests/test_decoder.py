import sys
import os
import re

# 1. 环境路径设置 (确保能 import src)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from assassyn.frontend import *

# 导入Decoder模块和相关信号定义
from src.decoder import Decoder
from src.control_signals import *
from tests.common import run_test_module
from tests.test_mock import MockDecoderShell


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
        icache_dout: Array,
        reg_file: Array,
    ):

        # 向量格式: (Instruction, PC)
        # 注意：这里只负责发输入，预期输出写在 check 函数里
        vectors = [
            (Bits(32)(0x002081B3), Bits(32)(0x1000)),  # 0: ADD x3, x1, x2
            (Bits(32)(0x00508193), Bits(32)(0x1004)),  # 1: ADDI x3, x1, 5
            (Bits(32)(0x0040A183), Bits(32)(0x1008)),  # 2: LW x3, 4(x1)
            (Bits(32)(0x0080A423), Bits(32)(0x100C)),  # 3: SW x2, 8(x1)
            (Bits(32)(0x00208463), Bits(32)(0x1010)),  # 4: BEQ x1, x2, 8
            (Bits(32)(0x0FE001EF), Bits(32)(0x1014)),  # 5: JAL x3, 0x100
            (Bits(32)(0x123451B7), Bits(32)(0x1018)),  # 6: LUI x3, 0x12345
        ]

        cnt = RegArray(UInt(32), 1, initializer=[0])
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

        curr_inst = Bits(32)(0)
        curr_pc = Bits(32)(0)

        for i, v in enumerate(vectors):
            match_if = vec_idx == UInt(32)(i)
            curr_inst = match_if.select(v[0], curr_inst)
            curr_pc = match_if.select(v[1], curr_pc)

        with Condition(valid_test):
            icache_dout[0] = curr_inst
            dut.async_called(pc=curr_pc)
            # 打印输入，方便定位
            log("Driver Input: Test[{}] Inst=0x{:x}", vec_idx, curr_inst)

        with Condition(idx > UInt(32)(len(vectors) + 4)):
            finish()


# ==============================================================================
# 2. 验证逻辑 (Python Check)
# ==============================================================================
C_ADD = 1
C_SUB = 2
C_SLL = 4
C_SLT = 8
C_SLTU = 16
C_XOR = 32
C_SRL = 64
C_SRA = 128
C_OR = 256
C_AND = 512

C_RS1 = 1
C_PC = 2
C_ZERO = 4
C_RS2 = 1
C_IMM = 2
C_4 = 4

M_NONE = 1
M_LOAD = 2
M_STORE = 4
M_W = 4

B_NONE = 1
B_BEQ = 2
B_JAL = 128
B_JALR = 256


def check(raw_output):
    print(">>> 开始对拍验证...")

    # [核心] 硬编码的预期结果表 (The Truth Vectors)
    # 格式对应 Log 中的字段顺序
    # ALU, OP1, OP2, BR, NXT_PC, | M_OP, M_W, M_U, RD | PC, RS1_D, RS2_D, IMM
    # 注意：RS1_D 和 RS2_D 是基于 Driver 初始化的 (x1=0x10, x2=0x20)

    expected_vectors = [
        # Case 0: ADD x3, x1, x2 (PC=1000)
        {
            "alu_func": C_ADD,
            "op1_sel": C_RS1,
            "op2_sel": C_RS2,
            "branch_type": B_NONE,
            "mem_opcode": M_NONE,
            "rd_addr": 3,
            "pc": 0x1000,
            "rs1_data": 0x10,
            "rs2_data": 0x20,
            "imm": 0,
        },
        # Case 1: ADDI x3, x1, 5 (PC=1004)
        {
            "alu_func": C_ADD,
            "op1_sel": C_RS1,
            "op2_sel": C_IMM,
            "branch_type": B_NONE,
            "mem_opcode": M_NONE,
            "rd_addr": 3,
            "pc": 0x1004,
            "rs1_data": 0x10,
            "rs2_data": 0,
            "imm": 5,
        },
        # Case 2: LW x3, 4(x1) (PC=1008)
        {
            "alu_func": C_ADD,
            "op1_sel": C_RS1,
            "op2_sel": C_IMM,
            "branch_type": B_NONE,
            "mem_opcode": M_LOAD,
            "mem_width": M_W,
            "rd_addr": 3,
            "pc": 0x1008,
            "rs1_data": 0x10,
            "rs2_data": 0,
            "imm": 4,
        },
        # Case 3: SW x2, 8(x1) (PC=100C)
        {
            "alu_func": C_ADD,
            "op1_sel": C_RS1,
            "op2_sel": C_IMM,
            "branch_type": B_NONE,
            "mem_opcode": M_STORE,
            "mem_width": M_W,
            "rd_addr": 0,  # Store 不写回
            "pc": 0x100C,
            "rs1_data": 0x10,
            "rs2_data": 0x20,
            "imm": 8,
        },
        # Case 4: BEQ x1, x2, 8 (PC=1010)
        {
            "alu_func": C_SUB,
            "op1_sel": C_RS1,
            "op2_sel": C_RS2,
            "branch_type": B_BEQ,
            "mem_opcode": M_NONE,
            "rd_addr": 0,  # Branch 不写回
            "pc": 0x1010,
            "rs1_data": 0x10,
            "rs2_data": 0x20,
            "imm": 8,
        },
        # Case 5: JAL x3, 0x100 (PC=1014)
        {
            "alu_func": C_ADD,
            "op1_sel": C_PC,
            "op2_sel": C_4,
            "branch_type": B_JAL,
            "mem_opcode": M_NONE,
            "rd_addr": 3,
            "pc": 0x1014,
            "rs1_data": 0,
            "rs2_data": 0,
            "imm": 0x100,
        },
        # Case 6: LUI x3, 0x12345 (PC=1018)
        {
            "alu_func": C_ADD,
            "op1_sel": C_ZERO,
            "op2_sel": C_IMM,
            "branch_type": B_NONE,
            "mem_opcode": M_NONE,
            "rd_addr": 3,
            "pc": 0x1018,
            "rs1_data": 0,
            "rs2_data": 0,
            "imm": 0x12345000,
        },
    ]

    captured_logs = []

    # 1. 抓取日志
    for line in raw_output.split("\n"):
        if "Output of the Decoder:" in line:
            # 简单粗暴的字符串处理：移除前缀，移除括号，替换等号为空格
            # 变成 key val key val ... 列表
            clean_line = line.split("Output of the Decoder:")[1]
            clean_line = (
                clean_line.replace("[", " ").replace("]", " ").replace("=", " ")
            )
            tokens = clean_line.split()

            data = {}
            # 遍历 tokens, 偶数索引是 key, 奇数索引是 value
            for k, v in zip(tokens[0::2], tokens[1::2]):
                # 处理 bool True/False
                if v == "True":
                    v = 1
                elif v == "False":
                    v = 0
                else:
                    v = int(v, 16)
                data[k] = v

            captured_logs.append(data)

    print(f"Captured {len(captured_logs)} outputs.")

    # 2. 逐条比对
    if len(captured_logs) < len(expected_vectors):
        print("❌ 错误：输出数量不足")
        assert False

    for i, exp in enumerate(expected_vectors):
        act = captured_logs[i]
        print(f"Checking Case {i} (PC=0x{exp.get('pc', 0):x})...")

        error_found = False
        for key, exp_val in exp.items():
            act_val = act.get(key, -1)
            # 允许位宽掩码差异 (比如 1 vs 0x1)
            if act_val != exp_val:
                print(f"  Mismatch [{key}]: Exp=0x{exp_val:x} Act=0x{act_val:x}")
                error_found = True

        if error_found:
            print(f"❌ Case {i} Failed!")
            assert False
        else:
            print(f"✅ Case {i} Passed")

    print("✅ 所有 Decoder 测试通过！")


# ==============================================================================
# 3. 主执行入口
# ==============================================================================
if __name__ == "__main__":

    sys = SysBuilder("test_decoder_module")

    with sys:
        # 创建测试模块
        dut = Decoder()
        driver = Driver()
        output = MockDecoderShell()

        # 创建必要的辅助模块和数据结构
        icache_dout = RegArray(Bits(32), 1)
        reg_file = RegArray(Bits(32), 32)  # 32个寄存器

        rs1_sel = Bits(4)(0)
        rs2_sel = Bits(4)(0)
        stall_if = Bits(1)(0)
        branch_target_reg = RegArray(Bits(32), 1)

        # 构建Driver
        driver.build(
            dut,
            icache_dout,
            reg_file,
        )

        # 构建Decoder
        pre_pkt, rs1, rs2, rs1_used, rs2_used = dut.build(icache_dout, reg_file)

        output.build(pre_pkt, rs1, rs2, rs1_used, rs2_used)

    run_test_module(sys, check)
