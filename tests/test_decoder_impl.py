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
            # sub x1, x2, x3 -> 0x403100b3 (funct3=0b000, funct7=0b0100000)
            (
                Bits(32)(0x00000004),
                Bits(32)(0x403100B3),
                Bits(32)(0x00000005),
                Bits(32)(0x00000003),
                Bits(4)(0x2),
                Bits(4)(0x3),
                Bits(1)(0),
                Bits(32)(0),
            ),
            # I-Type指令测试 (ALU)
            # addi x1, x2, 5 -> 0x00510113
            (
                Bits(32)(0x00000028),
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
                Bits(32)(0x0000004C),
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
                Bits(32)(0x00000060),
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
                Bits(32)(0x0000006C),
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
                Bits(32)(0x00000084),
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
                Bits(32)(0x0000008C),
                Bits(32)(0x0FE000EF),
                Bits(32)(0x00000000),
                Bits(32)(0x00000000),
                Bits(4)(0x0),
                Bits(4)(0x0),
                Bits(1)(0),
                Bits(32)(0),
            ),
            # 特殊指令测试
            # ecall -> 0x00000073
            (
                Bits(32)(0x00000094),
                Bits(32)(0x00000073),
                Bits(32)(0x00000000),
                Bits(32)(0x00000000),
                Bits(4)(0x0),
                Bits(4)(0x0),
                Bits(1)(0),
                Bits(32)(0),
            ),
            # 流水线停顿测试
            # add x1, x2, x3 + stall_if = 1
            (
                Bits(32)(0x00000098),
                Bits(32)(0x003100B3),
                Bits(32)(0x00000002),
                Bits(32)(0x00000003),
                Bits(4)(0x2),
                Bits(4)(0x3),
                Bits(1)(1),
                Bits(32)(0),
            ),
            # 流水线刷新测试
            # add x1, x2, x3 + branch_target = 0x100
            (
                Bits(32)(0x0000009C),
                Bits(32)(0x003100B3),
                Bits(32)(0x00000002),
                Bits(32)(0x00000003),
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

        # 设置Decoder的PC输入
        dut_call = dut.async_called(pc=current_pc)
        dut_call.bind.set_fifo_depth(pc=1)

        # 设置icache_dout和reg_file的值
        icache_dout[0] = current_instruction

        # 写入寄存器文件，要求索引在[0,31]范围内
        reg_file[current_rs1_sel] = current_rs1_data
        reg_file[current_rs2_sel] = current_rs2_data

        # 设置流水线控制信号
        branch_target_reg[0] = current_branch_target
        call = mock_dhu.async_called(
            rs1_sel=current_rs1_sel,
            rs2_sel=current_rs2_sel,
            stall_if=current_stall_if,
        )
        call.bind.set_fifo_depth(rs1_sel=1, rs2_sel=1, stall_if=1)

        # 只有当 idx 在向量范围内时才发送 (valid)
        valid_test = idx < UInt(32)(len(vectors))

        log(
            "Driver: idx={} pc=0x{:x} instruction=0x{:x} rs1_data=0x{:x} rs2_data=0x{:x} rs1_sel=0x{:x} rs2_sel=0x{:x} stall_if=0x{:x} branch_target=0x{:x}",
            idx,
            current_pc,
            current_instruction,
            current_rs1_data,
            current_rs2_data,
            current_rs1_sel,
            current_rs2_sel,
            current_stall_if,
            current_branch_target,
        )


# ==============================================================================
# 2. 验证逻辑 (Python Check)
# ==============================================================================
def check(raw_output):
    print(">>> 开始验证DecoderImpl模块输出...")

    # 解析输出，检查DecoderImpl是否正确处理了流水线控制信号
    lines = raw_output.split("\n")

    # 初始化统计数据
    test_count = 0
    success_count = 0

    # 存储测试结果
    test_results = []

    # 存储DecoderImpl输出信息
    decoder_impl_outputs = {}

    # 第一遍解析：收集所有Driver和DecoderImpl输出
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

                # 提取stall_if和branch_target信息
                stall_if = "0"
                branch_target = "0x0"
                for next_line in lines[lines.index(line) + 1 : lines.index(line) + 5]:
                    if "stall_if=0x" in next_line:
                        stall_if_match = re.search(r"stall_if=(0x\w+)", next_line)
                        if stall_if_match:
                            stall_if = stall_if_match.group(1)
                    if "branch_target=0x" in next_line:
                        target_match = re.search(r"branch_target=(0x\w+)", next_line)
                        if target_match:
                            branch_target = target_match.group(1)

                # 存储测试向量信息
                if idx not in decoder_impl_outputs:
                    decoder_impl_outputs[idx] = {
                        "driver": {
                            "idx": idx,
                            "pc": pc,
                            "instruction": instruction,
                            "rs1_data": rs1_data,
                            "rs2_data": rs2_data,
                            "stall_if": stall_if,
                            "branch_target": branch_target,
                        },
                        "decoder_impl": None,
                    }

        # 检查DecoderImpl输出
        if "ID_Impl:" in line:
            # 尝试提取DecoderImpl输出信息
            impl_match = re.search(
                r"ID_Impl:.*?flush_if=(\w+).*?nop_if=(\w+).*?final_rd=(0x\w+)", line
            )
            if impl_match:
                # 找到最近的Driver idx
                for prev_line_idx in range(
                    max(0, lines.index(line) - 10), lines.index(line)
                ):
                    prev_line = lines[prev_line_idx]
                    if "Driver: idx=" in prev_line:
                        driver_match = re.search(r"Driver: idx=(\d+)", prev_line)
                        if driver_match:
                            idx = int(driver_match.group(1))
                            if idx in decoder_impl_outputs:
                                decoder_impl_outputs[idx]["decoder_impl"] = {
                                    "flush_if": impl_match.group(1),
                                    "nop_if": impl_match.group(2),
                                    "final_rd": impl_match.group(3),
                                }
                            break

    # 第二遍解析：验证每个测试向量
    for idx in sorted(decoder_impl_outputs.keys()):
        driver_info = decoder_impl_outputs[idx]["driver"]
        decoder_impl_info = decoder_impl_outputs[idx]["decoder_impl"]

        # 验证结果
        test_result = {
            "idx": idx,
            "instruction": driver_info["instruction"],
            "expected": {
                "flush_if": (
                    "True" if int(driver_info["branch_target"], 16) != 0 else "False"
                ),
                "nop_if": (
                    "True"
                    if (
                        int(driver_info["branch_target"], 16) != 0
                        or int(driver_info["stall_if"], 16) != 0
                    )
                    else "False"
                ),
                "final_rd": (
                    "0x0"
                    if (
                        int(driver_info["branch_target"], 16) != 0
                        or int(driver_info["stall_if"], 16) != 0
                    )
                    else "0x1"
                ),
            },
            "actual": decoder_impl_info,
            "passed": False,
        }

        # 如果有DecoderImpl输出，进行验证
        if decoder_impl_info:
            # 验证flush_if
            flush_if_match = (
                decoder_impl_info["flush_if"] == test_result["expected"]["flush_if"]
            )

            # 验证nop_if
            nop_if_match = (
                decoder_impl_info["nop_if"] == test_result["expected"]["nop_if"]
            )

            # 验证final_rd
            final_rd_match = (
                decoder_impl_info["final_rd"] == test_result["expected"]["final_rd"]
            )

            # 整体验证
            test_result["passed"] = flush_if_match and nop_if_match and final_rd_match
            test_result["details"] = {
                "flush_if_match": flush_if_match,
                "nop_if_match": nop_if_match,
                "final_rd_match": final_rd_match,
            }

            if test_result["passed"]:
                success_count += 1
                print(f"✅ 测试向量 {idx}: DecoderImpl流水线控制信号处理成功")
            else:
                print(f"❌ 测试向量 {idx}: DecoderImpl流水线控制信号处理失败")
                if not flush_if_match:
                    print(
                        f"   flush_if不匹配: 预期 {test_result['expected']['flush_if']}, 实际 {decoder_impl_info['flush_if']}"
                    )
                if not nop_if_match:
                    print(
                        f"   nop_if不匹配: 预期 {test_result['expected']['nop_if']}, 实际 {decoder_impl_info['nop_if']}"
                    )
                if not final_rd_match:
                    print(
                        f"   final_rd不匹配: 预期 {test_result['expected']['final_rd']}, 实际 {decoder_impl_info['final_rd']}"
                    )
        else:
            print(f"❌ 测试向量 {idx}: 未找到DecoderImpl输出")

        test_results.append(test_result)

    # 生成详细报告
    generate_test_report(test_results)

    # 检查是否所有测试向量都已执行
    if success_count >= len(decoder_impl_outputs):
        print(f"✅ 所有 {success_count} 个测试向量执行成功！")
        print("✅ DecoderImpl模块测试通过！")
        return True
    else:
        print(f"❌ 只有 {success_count}/{len(decoder_impl_outputs)} 个测试向量执行成功")
        print("❌ DecoderImpl模块测试失败！")
        return False


def generate_test_report(test_results):
    """生成详细的测试报告"""
    print("\n" + "=" * 80)
    print("DecoderImpl测试详细报告")
    print("=" * 80)

    # 统计各类指令的测试情况
    instruction_stats = {}
    failed_tests = []

    for result in test_results:
        # 根据指令码确定指令类型
        instruction = int(result["instruction"], 16)
        opcode = instruction & 0x7F

        if opcode == 0b0110011:
            instr_name = "R-Type"
        elif opcode == 0b0010011:
            instr_name = "I-Type(ALU)"
        elif opcode == 0b0000011:
            instr_name = "I-Type(Load)"
        elif opcode == 0b0100011:
            instr_name = "S-Type"
        elif opcode == 0b1100011:
            instr_name = "B-Type"
        elif opcode == 0b0110111:
            instr_name = "U-Type(LUI)"
        elif opcode == 0b0010111:
            instr_name = "U-Type(AUIPC)"
        elif opcode == 0b1101111:
            instr_name = "J-Type(JAL)"
        elif opcode == 0b1100111:
            instr_name = "J-Type(JALR)"
        elif opcode == 0b1110011:
            instr_name = "SYSTEM"
        else:
            instr_name = "UNKNOWN"

        # 添加流水线控制信息
        if int(result["expected"]["flush_if"]) or int(result["expected"]["nop_if"]):
            instr_name += "(Pipeline)"

        if instr_name not in instruction_stats:
            instruction_stats[instr_name] = {"total": 0, "passed": 0}

        instruction_stats[instr_name]["total"] += 1
        if result["passed"]:
            instruction_stats[instr_name]["passed"] += 1
        else:
            failed_tests.append(result)

    # 打印指令统计
    print("\n指令类型统计:")
    print("-" * 60)
    for instr, stats in instruction_stats.items():
        pass_rate = (
            (stats["passed"] / stats["total"]) * 100 if stats["total"] > 0 else 0
        )
        print(
            f"{instr:20} | 通过: {stats['passed']:2d}/{stats['total']:2d} | 通过率: {pass_rate:5.1f}%"
        )

    # 打印失败的测试用例
    if failed_tests:
        print("\n失败的测试用例:")
        print("-" * 60)
        for test in failed_tests:
            print(f"测试向量 {test['idx']}: 指令 (指令码: {test['instruction']})")
            if test["actual"] and "details" in test:
                details = test["details"]
                if not details["flush_if_match"]:
                    print(
                        f"  - flush_if不匹配: 预期 {test['expected']['flush_if']}, 实际 {test['actual']['flush_if']}"
                    )
                if not details["nop_if_match"]:
                    print(
                        f"  - nop_if不匹配: 预期 {test['expected']['nop_if']}, 实际 {test['actual']['nop_if']}"
                    )
                if not details["final_rd_match"]:
                    print(
                        f"  - final_rd不匹配: 预期 {test['expected']['final_rd']}, 实际 {test['actual']['final_rd']}"
                    )
            else:
                print("  - 未找到DecoderImpl输出")

    print("\n" + "=" * 80)


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
        pre_pkt, _, _, _, _ = dut.build(icache_dout, reg_file)

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

    run_test_module(sys, check)
