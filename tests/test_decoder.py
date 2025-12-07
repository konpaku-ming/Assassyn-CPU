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
from tests.test_mock import MockSinkDecoder


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
        rs1_sel: Bits(4),
        rs2_sel: Bits(4),
        stall_if: Bits(1),
        branch_target_reg: Array,
    ):
        # --- 测试向量定义 ---
        # 格式: (pc, instruction, rs1_data, rs2_data,
        #       rs1_sel, rs2_sel, stall_if, branch_target)
        vectors = [
            # R-Type指令测试
            # add x1, x2, x3 -> 0x003100b3 (funct3=0b000, funct7=0b0000000)
            (
                Bits(32)(0x00000000),
                Bits(32)(0x003100B3),
                Bits(32)(0x00000002),
                Bits(32)(0x00000003),
                Bits(4)(0x2),
                Bits(4)(0x3),
                Bits(1)(0),
                Bits(32)(0),
            ),
            # and x1, x2, x3 -> 0x003170b3 (funct3=0b111, funct7=0b0000000)
            (
                Bits(32)(0x00000004),
                Bits(32)(0x003170B3),
                Bits(32)(0x0000000F),
                Bits(32)(0x0000000A),
                Bits(4)(0x2),
                Bits(4)(0x3),
                Bits(1)(0),
                Bits(32)(0),
            ),
            # I-Type指令测试 (ALU)
            # addi x1, x2, 5 -> 0x00510113
            (
                Bits(32)(0x00000008),
                Bits(32)(0x00510113),
                Bits(32)(0x0000000A),
                Bits(32)(0x00000000),
                Bits(4)(0x2),
                Bits(4)(0x0),
                Bits(1)(0),
                Bits(32)(0),
            ),
            # I-Type指令测试 (Load)
            # lw x1, 4(x2) -> 0x00410203
            (
                Bits(32)(0x0000000C),
                Bits(32)(0x00410203),
                Bits(32)(0x00001000),
                Bits(32)(0x00000000),
                Bits(4)(0x2),
                Bits(4)(0x0),
                Bits(1)(0),
                Bits(32)(0),
            ),
            # S-Type指令测试
            # sw x1, 4(x2) -> 0x00512023
            (
                Bits(32)(0x00000010),
                Bits(32)(0x00512023),
                Bits(32)(0x00001000),
                Bits(32)(0x0000000A),
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
                Bits(32)(0x00000001),
                Bits(32)(0x00000001),
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
                Bits(32)(0x00000000),
                Bits(32)(0x00000000),
                Bits(4)(0x0),
                Bits(4)(0x0),
                Bits(1)(0),
                Bits(32)(0),
            ),
            # J-Type指令测试
            # jal x1, 0x100 -> 0x0FE000EF
            (
                Bits(32)(0x0000001C),
                Bits(32)(0x0FE000EF),
                Bits(32)(0x00000000),
                Bits(32)(0x00000000),
                Bits(4)(0x0),
                Bits(4)(0x0),
                Bits(1)(0),
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
        current_pc = Bits(32)(0)
        current_instruction = Bits(32)(0)
        current_rs1_data = Bits(32)(0)
        current_rs2_data = Bits(32)(0)
        current_rs1_sel = Bits(4)(0)
        current_rs2_sel = Bits(4)(0)
        current_stall_if = Bits(1)(0)
        current_branch_target = Bits(32)(0)

        # 这里的循环展开会生成一棵 Mux 树
        for i, (
            pc,
            instruction,
            rs1_data,
            rs2_data,
            rs1_sel,
            rs2_sel,
            stall_if,
            branch_target,
        ) in enumerate(vectors):
            is_match = idx == UInt(32)(i)

            current_pc = is_match.select(pc, current_pc)
            current_instruction = is_match.select(instruction, current_instruction)
            current_rs1_data = is_match.select(rs1_data, current_rs1_data)
            current_rs2_data = is_match.select(rs2_data, current_rs2_data)
            current_rs1_sel = is_match.select(rs1_sel, current_rs1_sel)
            current_rs2_sel = is_match.select(rs2_sel, current_rs2_sel)
            current_stall_if = is_match.select(stall_if, current_stall_if)
            current_branch_target = is_match.select(
                branch_target, current_branch_target
            )

        # 设置icache_dout和reg_file的值
        icache_dout[0] = current_instruction

        # 初始化寄存器文件
        for i in range(32):
            reg_file[i] = Bits(32)(0)

        # 根据rs1_sel和rs2_sel设置相应的寄存器值
        if current_rs1_sel < UInt(32)(32):
            reg_file[current_rs1_sel] = current_rs1_data
        if current_rs2_sel < UInt(32)(32):
            reg_file[current_rs2_sel] = current_rs2_data

        # 设置其他信号
        rs1_sel = current_rs1_sel
        rs2_sel = current_rs2_sel
        stall_if = current_stall_if
        branch_target_reg[0] = current_branch_target

        # 设置Decoder的PC输入
        dut.pc = current_pc

        # 只有当 idx 在向量范围内时才发送 (valid)
        valid_test = idx < UInt(32)(len(vectors))

        with Condition(~valid_test):
            finish()

        log(
            "Driver: idx={} pc=0x{:x} instruction=0x{:x} rs1_data=0x{:x} rs2_data=0x{:x}",
            idx,
            current_pc,
            current_instruction,
            current_rs1_data,
            current_rs2_data,
        )

        return cnt


# ==============================================================================
# 2. 验证逻辑 (Python Check)
# ==============================================================================
def check(raw_output):
    print(">>> 开始验证Decoder模块输出...")

    # 解析输出，检查Decoder是否正确解码了所有指令
    lines = raw_output.split("\n")

    # 初始化统计数据
    test_count = 0
    success_count = 0

    # 存储测试结果
    test_results = []

    # 存储Decoder输出信息
    decoder_outputs = {}

    # 第一遍解析：收集所有Driver和Decoder输出
    for line in lines:
        # 检查Driver输出
        if "Driver: idx=" in line:
            test_count += 1
            # 提取测试信息
            match = re.search(
                r"Driver: idx=(\d+) pc=(0x\w+) instruction=(0x\w+) rs1_data=(0x\w+) rs2_data=(0x\w+)",
                line,
            )
            if match:
                idx = int(match.group(1))
                pc = match.group(2)
                instruction = match.group(3)
                rs1_data = match.group(4)
                rs2_data = match.group(5)

                # 存储测试向量信息
                if idx not in decoder_outputs:
                    decoder_outputs[idx] = {
                        "driver": {
                            "idx": idx,
                            "pc": pc,
                            "instruction": instruction,
                            "rs1_data": rs1_data,
                            "rs2_data": rs2_data,
                        },
                        "decoder": None,
                    }

        # 检查Decoder输出
        if "MockSinkDecoder:" in line:
            # 尝试提取Decoder输出信息
            decoder_match = re.search(
                r"MockSinkDecoder: alu_func=(0x\w+) op1_sel=(0x\w+) op2_sel=(0x\w+) branch_type=(0x\w+) next_pc_addr=(0x\w+) mem_ctrl=\[mem_opcode=(0x\w+) mem_width=(0x\w+) mem_unsigned=(0x\w+) rd_addr=(0x\w+)\] pc=(0x\w+) rs1_data=(0x\w+) rs2_data=(0x\w+) imm=(0x\w+) rs1=(0x\w+) rs2=(0x\w+) rs1_used=(\w+) rs2_used=(\w+)",
                line,
            )
            if decoder_match:
                # 找到最近的Driver idx
                for prev_line_idx in range(
                    max(0, lines.index(line) - 10), lines.index(line)
                ):
                    prev_line = lines[prev_line_idx]
                    if "Driver: idx=" in prev_line:
                        driver_match = re.search(r"Driver: idx=(\d+)", prev_line)
                        if driver_match:
                            idx = int(driver_match.group(1))
                            if idx in decoder_outputs:
                                decoder_outputs[idx]["decoder"] = {
                                    "alu_func": decoder_match.group(1),
                                    "op1_sel": decoder_match.group(2),
                                    "op2_sel": decoder_match.group(3),
                                    "branch_type": decoder_match.group(4),
                                    "next_pc_addr": decoder_match.group(5),
                                    "mem_ctrl": {
                                        "mem_opcode": decoder_match.group(6),
                                        "mem_width": decoder_match.group(7),
                                        "mem_unsigned": decoder_match.group(8),
                                        "rd_addr": decoder_match.group(9),
                                    },
                                    "pc": decoder_match.group(10),
                                    "rs1_data": decoder_match.group(11),
                                    "rs2_data": decoder_match.group(12),
                                    "imm": decoder_match.group(13),
                                    "rs1": decoder_match.group(14),
                                    "rs2": decoder_match.group(15),
                                    "rs1_used": decoder_match.group(16),
                                    "rs2_used": decoder_match.group(17),
                                }
                            break

    # 第二遍解析：验证每个测试向量
    for idx in sorted(decoder_outputs.keys()):
        driver_info = decoder_outputs[idx]["driver"]
        decoder_info = decoder_outputs[idx]["decoder"]

        # 获取指令码
        instruction = int(driver_info["instruction"], 16)

        # 解析指令
        opcode = instruction & 0x7F  # 低7位
        funct3 = (instruction >> 12) & 0x7  # 位12-14
        funct7 = (instruction >> 25) & 0x7F  # 位25-31
        bit30 = (instruction >> 30) & 0x1  # 位30

        # 计算立即数
        imm = calculate_immediate(instruction, opcode)

        # 计算预期的控制信号
        expected_signals = get_expected_signals(opcode, funct3, funct7, bit30, imm)

        # 验证结果
        test_result = {
            "idx": idx,
            "instruction": driver_info["instruction"],
            "instruction_name": expected_signals["name"],
            "expected": expected_signals,
            "actual": decoder_info,
            "passed": False,
        }

        # 如果有Decoder输出，进行验证
        if decoder_info:
            # 验证ALU功能码
            alu_match = (
                int(decoder_info["alu_func"], 16) == expected_signals["alu_func"]
            )

            # 验证操作数选择
            op1_match = int(decoder_info["op1_sel"], 16) == expected_signals["op1_sel"]
            op2_match = int(decoder_info["op2_sel"], 16) == expected_signals["op2_sel"]

            # 验证立即数
            imm_match = int(decoder_info["imm"], 16) == expected_signals["imm"]

            # 验证PC值
            pc_match = int(decoder_info["pc"], 16) == int(driver_info["pc"], 16)

            # 验证寄存器数据
            rs1_data_match = int(decoder_info["rs1_data"], 16) == int(driver_info["rs1_data"], 16)
            rs2_data_match = int(decoder_info["rs2_data"], 16) == int(driver_info["rs2_data"], 16)

            # 验证寄存器编号
            rs1_match = int(decoder_info["rs1"], 16) == int(driver_info["rs1_sel"], 16) if driver_info["rs1_sel"] else True
            rs2_match = int(decoder_info["rs2"], 16) == int(driver_info["rs2_sel"], 16) if driver_info["rs2_sel"] else True

            # 验证寄存器使用标志
            rs1_used_match = decoder_info["rs1_used"] == "True" if int(driver_info["rs1_sel"], 16) != 0 else decoder_info["rs1_used"] == "False"
            rs2_used_match = decoder_info["rs2_used"] == "True" if int(driver_info["rs2_sel"], 16) != 0 else decoder_info["rs2_used"] == "False"

            # 整体验证
            test_result["passed"] = (alu_match and op1_match and op2_match and imm_match and
                                    pc_match and rs1_data_match and rs2_data_match and
                                    rs1_match and rs2_match and rs1_used_match and rs2_used_match)

            if test_result["passed"]:
                success_count += 1
                print(f"✅ 测试向量 {idx}: {expected_signals['name']} 指令解码成功")
            else:
                print(f"❌ 测试向量 {idx}: {expected_signals['name']} 指令解码失败")
                # 打印详细的不匹配信息
                if not alu_match:
                    print(f"  - alu_func不匹配: 预期 0x{expected_signals['alu_func']:x}, 实际 0x{int(decoder_info['alu_func'], 16):x}")
                if not op1_match:
                    print(f"  - op1_sel不匹配: 预期 0x{expected_signals['op1_sel']:x}, 实际 0x{int(decoder_info['op1_sel'], 16):x}")
                if not op2_match:
                    print(f"  - op2_sel不匹配: 预期 0x{expected_signals['op2_sel']:x}, 实际 0x{int(decoder_info['op2_sel'], 16):x}")
                if not imm_match:
                    print(f"  - imm不匹配: 预期 0x{expected_signals['imm']:x}, 实际 0x{int(decoder_info['imm'], 16):x}")
                if not pc_match:
                    print(f"  - pc不匹配: 预期 {driver_info['pc']}, 实际 {decoder_info['pc']}")
                if not rs1_data_match:
                    print(f"  - rs1_data不匹配: 预期 {driver_info['rs1_data']}, 实际 {decoder_info['rs1_data']}")
                if not rs2_data_match:
                    print(f"  - rs2_data不匹配: 预期 {driver_info['rs2_data']}, 实际 {decoder_info['rs2_data']}")
                if not rs1_match:
                    print(f"  - rs1不匹配: 预期 {driver_info['rs1_sel']}, 实际 {decoder_info['rs1']}")
                if not rs2_match:
                    print(f"  - rs2不匹配: 预期 {driver_info['rs2_sel']}, 实际 {decoder_info['rs2']}")
                if not rs1_used_match:
                    print(f"  - rs1_used不匹配: 预期 {'True' if int(driver_info['rs1_sel'], 16) != 0 else 'False'}, 实际 {decoder_info['rs1_used']}")
                if not rs2_used_match:
                    print(f"  - rs2_used不匹配: 预期 {'True' if int(driver_info['rs2_sel'], 16) != 0 else 'False'}, 实际 {decoder_info['rs2_used']}")
        else:
            print(f"❌ 测试向量 {idx}: 未找到Decoder输出")

        test_results.append(test_result)

    # 生成详细报告
    generate_test_report(test_results)

    # 检查是否所有测试向量都已执行
    if success_count >= len(decoder_outputs):
        print(f"✅ 所有 {success_count} 个测试向量执行成功！")
        print("✅ Decoder模块测试通过！")
        return True
    else:
        print(f"❌ 只有 {success_count}/{len(decoder_outputs)} 个测试向量执行成功")
        print("❌ Decoder模块测试失败！")
        return False


def calculate_immediate(instruction, opcode):
    """根据指令类型计算立即数"""
    # I-Type: [31:20] -> 12位立即数，符号扩展
    if (
        opcode == 0b0010011 or opcode == 0b0000011 or opcode == 0b1100111
    ):  # OP_I_TYPE, OP_LOAD, OP_JALR
        imm = (instruction >> 20) & 0xFFF
        # 符号扩展
        if imm & 0x800:
            imm -= 0x1000
        return imm

    # S-Type: [31:25] | [11:7] -> 12位立即数，符号扩展
    elif opcode == 0b0100011:  # OP_STORE
        imm = ((instruction >> 25) << 5) | ((instruction >> 7) & 0x1F)
        # 符号扩展
        if imm & 0x800:
            imm -= 0x1000
        return imm

    # B-Type: [31] | [7] | [30:25] | [11:8] -> 13位立即数，左移1位，符号扩展
    elif opcode == 0b1100011:  # OP_BRANCH
        imm = (
            ((instruction >> 31) << 12)
            | ((instruction >> 7) & 0x1) << 11
            | ((instruction >> 25) & 0x3F) << 5
            | ((instruction >> 8) & 0xF) << 1
        )
        # 符号扩展
        if imm & 0x1000:
            imm -= 0x2000
        return imm

    # U-Type: [31:12] -> 20位立即数，左移12位
    elif opcode == 0b0110111 or opcode == 0b0010111:  # OP_LUI, OP_AUIPC
        imm = (instruction >> 12) & 0xFFFFF
        return imm << 12

    # J-Type: [31] | [19:12] | [20] | [30:21] -> 21位立即数，左移1位，符号扩展
    elif opcode == 0b1101111:  # OP_JAL
        imm = (
            ((instruction >> 31) << 20)
            | ((instruction >> 12) & 0xFF) << 12
            | ((instruction >> 20) & 0x1) << 11
            | ((instruction >> 21) & 0x3FF) << 1
        )
        # 符号扩展
        if imm & 0x100000:
            imm -= 0x200000
        return imm

    # 默认情况
    return 0


def get_expected_signals(opcode, funct3, funct7, bit30, imm_i):
    """根据指令码获取预期的控制信号"""
    # 默认值
    result = {"name": "UNKNOWN", "alu_func": 0, "op1_sel": 0, "op2_sel": 0, "imm": 0}

    # R-Type指令
    if opcode == 0b0110011:  # OP_R_TYPE
        if funct3 == 0x0:
            if bit30 == 0:  # add
                result.update(
                    {
                        "name": "add",
                        "alu_func": 0b0000000000000001,  # ALUOp.ADD
                        "op1_sel": 0b001,  # Op1Sel.RS1
                        "op2_sel": 0b001,  # Op2Sel.RS2
                        "imm": 0,
                    }
                )
            else:  # sub
                result.update(
                    {
                        "name": "sub",
                        "alu_func": 0b0000000000000010,  # ALUOp.SUB
                        "op1_sel": 0b001,  # Op1Sel.RS1
                        "op2_sel": 0b001,  # Op2Sel.RS2
                        "imm": 0,
                    }
                )
        elif funct3 == 0x7:  # and
            result.update(
                {
                    "name": "and",
                    "alu_func": 0b0000001000000000,  # ALUOp.AND
                    "op1_sel": 0b001,  # Op1Sel.RS1
                    "op2_sel": 0b001,  # Op2Sel.RS2
                    "imm": 0,
                }
            )

    # I-Type指令 (ALU)
    elif opcode == 0b0010011:  # OP_I_TYPE
        if funct3 == 0x0:  # addi
            result.update(
                {
                    "name": "addi",
                    "alu_func": 0b0000000000000001,  # ALUOp.ADD
                    "op1_sel": 0b001,  # Op1Sel.RS1
                    "op2_sel": 0b010,  # Op2Sel.IMM
                    "imm": imm_i,
                }
            )

    # Load指令
    elif opcode == 0b0000011:  # OP_LOAD
        if funct3 == 0x2:  # lw
            result.update(
                {
                    "name": "lw",
                    "alu_func": 0b0000000000000001,  # ALUOp.ADD
                    "op1_sel": 0b001,  # Op1Sel.RS1
                    "op2_sel": 0b010,  # Op2Sel.IMM
                    "imm": imm_i,
                }
            )

    # S-Type指令
    elif opcode == 0b0100011:  # OP_STORE
        if funct3 == 0x2:  # sw
            result.update(
                {
                    "name": "sw",
                    "alu_func": 0b0000000000000001,  # ALUOp.ADD
                    "op1_sel": 0b001,  # Op1Sel.RS1
                    "op2_sel": 0b010,  # Op2Sel.IMM
                    "imm": imm_i,
                }
            )

    # B-Type指令
    elif opcode == 0b1100011:  # OP_BRANCH
        if funct3 == 0x0:  # beq
            result.update(
                {
                    "name": "beq",
                    "alu_func": 0b0000000000000010,  # ALUOp.SUB
                    "op1_sel": 0b001,  # Op1Sel.RS1
                    "op2_sel": 0b001,  # Op2Sel.RS2
                    "imm": imm_i,
                }
            )

    # U-Type指令
    elif opcode == 0b0110111:  # OP_LUI
        result.update(
            {
                "name": "lui",
                "alu_func": 0b0000000000000001,  # ALUOp.ADD
                "op1_sel": 0b100,  # Op1Sel.ZERO
                "op2_sel": 0b010,  # Op2Sel.IMM
                "imm": imm_i,
            }
        )

    # J-Type指令
    elif opcode == 0b1101111:  # OP_JAL
        result.update(
            {
                "name": "jal",
                "alu_func": 0b0000000000000001,  # ALUOp.ADD
                "op1_sel": 0b010,  # Op1Sel.PC
                "op2_sel": 0b100,  # Op2Sel.CONST_4
                "imm": imm_i,
            }
        )

    return result


def generate_test_report(test_results):
    """生成详细的测试报告"""
    print("\n" + "=" * 60)
    print("Decoder测试详细报告")
    print("=" * 60)

    # 统计各类指令的测试情况
    instruction_stats = {}

    for result in test_results:
        instr_name = result["instruction_name"]
        if instr_name not in instruction_stats:
            instruction_stats[instr_name] = {"total": 0, "passed": 0}

        instruction_stats[instr_name]["total"] += 1
        if result["passed"]:
            instruction_stats[instr_name]["passed"] += 1

    # 打印指令统计
    print("\n指令类型统计:")
    print("-" * 40)
    for instr, stats in instruction_stats.items():
        pass_rate = (
            (stats["passed"] / stats["total"]) * 100 if stats["total"] > 0 else 0
        )
        print(
            f"{instr:10} | 通过: {stats['passed']:2d}/{stats['total']:2d} | 通过率: {pass_rate:5.1f}%"
        )

    print("\n" + "=" * 60)


# ==============================================================================
# 3. 主执行入口
# ==============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("MyCPU Decoder模块测试")
    print("=" * 60)
    print("测试说明：")
    print("1. 本测试验证Decoder模块是否能正确解码RISC-V指令")
    print("2. 测试覆盖R-Type、I-Type、S-Type、B-Type、U-Type和J-Type指令")
    print("3. 验证控制信号(ALU功能码、操作数选择、立即数)的正确性")
    print("4. 在apptainer容器中运行测试:")
    print("   - source setup.sh")
    print("   - cd MyCPU")
    print("   - python tests/test_decoder.py")
    print("=" * 60)

    sys = SysBuilder("test_decoder_module")

    with sys:
        # 创建测试模块
        dut = Decoder()
        driver = Driver()
        executor = MockSinkDecoder()

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
            rs1_sel,
            rs2_sel,
            stall_if,
            branch_target_reg,
        )

        # 构建Decoder
        pre_pkt, rs1, rs2, rs1_used, rs2_used = dut.build(icache_dout, reg_file)

        # 连接Decoder输出到MockSinkDecoder
        executor.build(
            pre_pkt,
            rs1,
            rs2,
            rs1_used,
            rs2_used,
        )

    run_test_module(sys, check)
