import sys
import os
import re

# 1. 环境路径设置 (确保能 import src)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from assassyn.frontend import *
from assassyn.backend import elaborate, config
from assassyn import utils

# 导入Decoder模块和相关信号定义
from src.decoder import Decoder, DecoderImpl
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
        self,
        dut: Module,
        icache_dout: Array,
        reg_file: Array,
        executor: Module,
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
            (Bits(32)(0x00000000), Bits(32)(0x003100b3),
             Bits(32)(0x00000002), Bits(32)(0x00000003),
             Bits(4)(0x2), Bits(4)(0x3), Bits(1)(0), Bits(32)(0)),
            
            # sub x1, x2, x3 -> 0x403100b3 (funct3=0b000, funct7=0b0100000)
            (Bits(32)(0x00000004), Bits(32)(0x403100b3),
             Bits(32)(0x00000005), Bits(32)(0x00000003),
             Bits(4)(0x2), Bits(4)(0x3), Bits(1)(0), Bits(32)(0)),
            
            # and x1, x2, x3 -> 0x003170b3 (funct3=0b111, funct7=0b0000000)
            (Bits(32)(0x00000008), Bits(32)(0x003170b3),
             Bits(32)(0x0000000F), Bits(32)(0x0000000A),
             Bits(4)(0x2), Bits(4)(0x3), Bits(1)(0), Bits(32)(0)),
            
            # or x1, x2, x3 -> 0x003160b3 (funct3=0b110, funct7=0b0000000)
            (Bits(32)(0x0000000C), Bits(32)(0x003160b3),
             Bits(32)(0x0000000F), Bits(32)(0x000000A0),
             Bits(4)(0x2), Bits(4)(0x3), Bits(1)(0), Bits(32)(0)),
            
            # xor x1, x2, x3 -> 0x003140b3 (funct3=0b100, funct7=0b0000000)
            (Bits(32)(0x00000010), Bits(32)(0x003140b3),
             Bits(32)(0x0000000F), Bits(32)(0x000000A0),
             Bits(4)(0x2), Bits(4)(0x3), Bits(1)(0), Bits(32)(0)),
            
            # sll x1, x2, x3 -> 0x003110b3 (funct3=0b001, funct7=0b0000000)
            (Bits(32)(0x00000014), Bits(32)(0x003110b3),
             Bits(32)(0x00000001), Bits(32)(0x00000002),
             Bits(4)(0x2), Bits(4)(0x3), Bits(1)(0), Bits(32)(0)),
            
            # srl x1, x2, x3 -> 0x003150b3 (funct3=0b101, funct7=0b0000000)
            (Bits(32)(0x00000018), Bits(32)(0x003150b3),
             Bits(32)(0x00000080), Bits(32)(0x00000002),
             Bits(4)(0x2), Bits(4)(0x3), Bits(1)(0), Bits(32)(0)),
            
            # sra x1, x2, x3 -> 0x403150b3 (funct3=0b101, funct7=0b0100000)
            (Bits(32)(0x0000001C), Bits(32)(0x403150b3),
             Bits(32)(0x80000000), Bits(32)(0x00000002),
             Bits(4)(0x2), Bits(4)(0x3), Bits(1)(0), Bits(32)(0)),
            
            # slt x1, x2, x3 -> 0x003120b3 (funct3=0b010, funct7=0b0000000)
            (Bits(32)(0x00000020), Bits(32)(0x003120b3),
             Bits(32)(0x00000001), Bits(32)(0x00000002),
             Bits(4)(0x2), Bits(4)(0x3), Bits(1)(0), Bits(32)(0)),
            
            # sltu x1, x2, x3 -> 0x003130b3 (funct3=0b011, funct7=0b0000000)
            (Bits(32)(0x00000024), Bits(32)(0x003130b3),
             Bits(32)(0x00000001), Bits(32)(0x00000002),
             Bits(4)(0x2), Bits(4)(0x3), Bits(1)(0), Bits(32)(0)),
            
            # I-Type指令测试 (ALU)
            # addi x1, x2, 5 -> 0x00510113
            (Bits(32)(0x00000028), Bits(32)(0x00510113),
             Bits(32)(0x0000000A), Bits(32)(0x00000000),
             Bits(4)(0x2), Bits(4)(0x0), Bits(1)(0), Bits(32)(0)),
            
            # andi x1, x2, 0xF -> 0x00F17113
            (Bits(32)(0x0000002C), Bits(32)(0x00F17113),
             Bits(32)(0x000000FF), Bits(32)(0x00000000),
             Bits(4)(0x2), Bits(4)(0x0), Bits(1)(0), Bits(32)(0)),
            
            # ori x1, x2, 0xA0 -> 0x0A016113
            (Bits(32)(0x00000030), Bits(32)(0x0A016113),
             Bits(32)(0x0000000F), Bits(32)(0x00000000),
             Bits(4)(0x2), Bits(4)(0x0), Bits(1)(0), Bits(32)(0)),
            
            # xori x1, x2, 0xA0 -> 0x0A014113
            (Bits(32)(0x00000034), Bits(32)(0x0A014113),
             Bits(32)(0x000000FF), Bits(32)(0x00000000),
             Bits(4)(0x2), Bits(4)(0x0), Bits(1)(0), Bits(32)(0)),
            
            # slli x1, x2, 2 -> 0x00210113
            (Bits(32)(0x00000038), Bits(32)(0x00210113),
             Bits(32)(0x00000001), Bits(32)(0x00000000),
             Bits(4)(0x2), Bits(4)(0x0), Bits(1)(0), Bits(32)(0)),
            
            # srli x1, x2, 2 -> 0x00215113
            (Bits(32)(0x0000003C), Bits(32)(0x00215113),
             Bits(32)(0x00000080), Bits(32)(0x00000000),
             Bits(4)(0x2), Bits(4)(0x0), Bits(1)(0), Bits(32)(0)),
            
            # srai x1, x2, 2 -> 0x40215113
            (Bits(32)(0x00000040), Bits(32)(0x40215113),
             Bits(32)(0x80000000), Bits(32)(0x00000000),
             Bits(4)(0x2), Bits(4)(0x0), Bits(1)(0), Bits(32)(0)),
            
            # slti x1, x2, 5 -> 0x00512113
            (Bits(32)(0x00000044), Bits(32)(0x00512113),
             Bits(32)(0x00000001), Bits(32)(0x00000000),
             Bits(4)(0x2), Bits(4)(0x0), Bits(1)(0), Bits(32)(0)),
            
            # sltiu x1, x2, 5 -> 0x00513113
            (Bits(32)(0x00000048), Bits(32)(0x00513113),
             Bits(32)(0x00000001), Bits(32)(0x00000000),
             Bits(4)(0x2), Bits(4)(0x0), Bits(1)(0), Bits(32)(0)),
            
            # I-Type指令测试 (Load)
            # lw x1, 4(x2) -> 0x00410203
            (Bits(32)(0x0000004C), Bits(32)(0x00410203),
             Bits(32)(0x00001000), Bits(32)(0x00000000),
             Bits(4)(0x2), Bits(4)(0x0), Bits(1)(0), Bits(32)(0)),
            
            # lh x1, 2(x2) -> 0x00211203
            (Bits(32)(0x00000050), Bits(32)(0x00211203),
             Bits(32)(0x00001000), Bits(32)(0x00000000),
             Bits(4)(0x2), Bits(4)(0x0), Bits(1)(0), Bits(32)(0)),
            
            # lb x1, 1(x2) -> 0x00110203
            (Bits(32)(0x00000054), Bits(32)(0x00110203),
             Bits(32)(0x00001000), Bits(32)(0x00000000),
             Bits(4)(0x2), Bits(4)(0x0), Bits(1)(0), Bits(32)(0)),
            
            # lhu x1, 2(x2) -> 0x00214203
            (Bits(32)(0x00000058), Bits(32)(0x00214203),
             Bits(32)(0x00001000), Bits(32)(0x00000000),
             Bits(4)(0x2), Bits(4)(0x0), Bits(1)(0), Bits(32)(0)),
            
            # lbu x1, 1(x2) -> 0x00114203
            (Bits(32)(0x0000005C), Bits(32)(0x00114203),
             Bits(32)(0x00001000), Bits(32)(0x00000000),
             Bits(4)(0x2), Bits(4)(0x0), Bits(1)(0), Bits(32)(0)),
            
            # S-Type指令测试
            # sw x1, 4(x2) -> 0x00512023
            (Bits(32)(0x00000060), Bits(32)(0x00512023),
             Bits(32)(0x00001000), Bits(32)(0x0000000A),
             Bits(4)(0x2), Bits(4)(0x1), Bits(1)(0), Bits(32)(0)),
            
            # sh x1, 2(x2) -> 0x00511223
            (Bits(32)(0x00000064), Bits(32)(0x00511223),
             Bits(32)(0x00001000), Bits(32)(0x0000000A),
             Bits(4)(0x2), Bits(4)(0x1), Bits(1)(0), Bits(32)(0)),
            
            # sb x1, 1(x2) -> 0x00510223
            (Bits(32)(0x00000068), Bits(32)(0x00510223),
             Bits(32)(0x00001000), Bits(32)(0x0000000A),
             Bits(4)(0x2), Bits(4)(0x1), Bits(1)(0), Bits(32)(0)),
            
            # B-Type指令测试
            # beq x1, x2, 8 -> 0x00208463
            (Bits(32)(0x0000006C), Bits(32)(0x00208463),
             Bits(32)(0x00000001), Bits(32)(0x00000001),
             Bits(4)(0x1), Bits(4)(0x2), Bits(1)(0), Bits(32)(0)),
            
            # bne x1, x2, 8 -> 0x00209463
            (Bits(32)(0x00000070), Bits(32)(0x00209463),
             Bits(32)(0x00000001), Bits(32)(0x00000002),
             Bits(4)(0x1), Bits(4)(0x2), Bits(1)(0), Bits(32)(0)),
            
            # blt x1, x2, 8 -> 0x0020C463
            (Bits(32)(0x00000074), Bits(32)(0x0020C463),
             Bits(32)(0x00000001), Bits(32)(0x00000002),
             Bits(4)(0x1), Bits(4)(0x2), Bits(1)(0), Bits(32)(0)),
            
            # bge x1, x2, 8 -> 0x0020D463
            (Bits(32)(0x00000078), Bits(32)(0x0020D463),
             Bits(32)(0x00000002), Bits(32)(0x00000001),
             Bits(4)(0x1), Bits(4)(0x2), Bits(1)(0), Bits(32)(0)),
            
            # bltu x1, x2, 8 -> 0x0020E463
            (Bits(32)(0x0000007C), Bits(32)(0x0020E463),
             Bits(32)(0x00000001), Bits(32)(0x00000002),
             Bits(4)(0x1), Bits(4)(0x2), Bits(1)(0), Bits(32)(0)),
            
            # bgeu x1, x2, 8 -> 0x0020F463
            (Bits(32)(0x00000080), Bits(32)(0x0020F463),
             Bits(32)(0x00000002), Bits(32)(0x00000001),
             Bits(4)(0x1), Bits(4)(0x2), Bits(1)(0), Bits(32)(0)),
            
            # U-Type指令测试
            # lui x1, 0x12345 -> 0x123450b7
            (Bits(32)(0x00000084), Bits(32)(0x123450b7),
             Bits(32)(0x00000000), Bits(32)(0x00000000),
             Bits(4)(0x0), Bits(4)(0x0), Bits(1)(0), Bits(32)(0)),
            
            # auipc x1, 0x12345 -> 0x12345097
            (Bits(32)(0x00000088), Bits(32)(0x12345097),
             Bits(32)(0x00000000), Bits(32)(0x00000000),
             Bits(4)(0x0), Bits(4)(0x0), Bits(1)(0), Bits(32)(0)),
            
            # J-Type指令测试
            # jal x1, 0x100 -> 0x0FE000EF
            (Bits(32)(0x0000008C), Bits(32)(0x0FE000EF),
             Bits(32)(0x00000000), Bits(32)(0x00000000),
             Bits(4)(0x0), Bits(4)(0x0), Bits(1)(0), Bits(32)(0)),
            
            # jalr x1, x2, 4 -> 0x004102e7
            (Bits(32)(0x00000090), Bits(32)(0x004102e7),
             Bits(32)(0x00000100), Bits(32)(0x00000000),
             Bits(4)(0x2), Bits(4)(0x0), Bits(1)(0), Bits(32)(0)),
            
            # 特殊指令测试
            # ecall -> 0x00000073
            (Bits(32)(0x00000094), Bits(32)(0x00000073),
             Bits(32)(0x00000000), Bits(32)(0x00000000),
             Bits(4)(0x0), Bits(4)(0x0), Bits(1)(0), Bits(32)(0)),
            
            # ebreak -> 0x00100073
            (Bits(32)(0x00000098), Bits(32)(0x00100073),
             Bits(32)(0x00000000), Bits(32)(0x00000000),
             Bits(4)(0x0), Bits(4)(0x0), Bits(1)(0), Bits(32)(0)),
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
            current_branch_target = is_match.select(branch_target, current_branch_target)

        # 设置icache_dout和reg_file的值
        icache_dout[0] = current_instruction
        
        # 初始化寄存器文件
        for i in range(32):
            reg_file[i] = Bits(32)(0)
        
        # 根据rs1_sel和rs2_sel设置相应的寄存器值
        # 这里我们假设rs1_sel和rs2_sel是寄存器索引
        if current_rs1_sel < 32:
            reg_file[current_rs1_sel] = current_rs1_data
        if current_rs2_sel < 32:
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
        
        # 添加测试向量详细日志
        log(
            "Driver: 测试向量详情 - rs1_sel=0x{:x} rs2_sel=0x{:x} stall_if=0x{:x} branch_target=0x{:x}",
            current_rs1_sel,
            current_rs2_sel,
            current_stall_if,
            current_branch_target,
        )

        return cnt


# ==============================================================================
# 2. 验证逻辑 (Python Check)
# ==============================================================================
def check(raw_output):
    print(">>> 开始验证Decoder模块输出...")

    # 解析输出，检查Decoder是否正确解码了所有指令
    lines = raw_output.split('\n')
    
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
            match = re.search(r"Driver: idx=(\d+) pc=(0x\w+) instruction=(0x\w+) rs1_data=(0x\w+) rs2_data=(0x\w+)", line)
            if match:
                idx = int(match.group(1))
                pc = match.group(2)
                instruction = match.group(3)
                rs1_data = match.group(4)
                rs2_data = match.group(5)
                
                # 存储测试向量信息
                if idx not in decoder_outputs:
                    decoder_outputs[idx] = {
                        'driver': {
                            'idx': idx,
                            'pc': pc,
                            'instruction': instruction,
                            'rs1_data': rs1_data,
                            'rs2_data': rs2_data
                        },
                        'decoder': None
                    }
        
        # 检查Decoder输出
        if "ID_Shell:" in line:
            # 尝试提取Decoder输出信息
            decoder_match = re.search(r"ID_Shell:.*?alu_func=(0x\w+).*?op1_sel=(0x\w+).*?op2_sel=(0x\w+).*?imm=(0x\w+)", line)
            if decoder_match:
                # 找到最近的Driver idx
                for prev_line_idx in range(max(0, lines.index(line) - 10), lines.index(line)):
                    prev_line = lines[prev_line_idx]
                    if "Driver: idx=" in prev_line:
                        driver_match = re.search(r"Driver: idx=(\d+)", prev_line)
                        if driver_match:
                            idx = int(driver_match.group(1))
                            if idx in decoder_outputs:
                                decoder_outputs[idx]['decoder'] = {
                                    'alu_func': decoder_match.group(1),
                                    'op1_sel': decoder_match.group(2),
                                    'op2_sel': decoder_match.group(3),
                                    'imm': decoder_match.group(4)
                                }
                            break
    
    # 第二遍解析：验证每个测试向量
    for idx in sorted(decoder_outputs.keys()):
        driver_info = decoder_outputs[idx]['driver']
        decoder_info = decoder_outputs[idx]['decoder']
        
        # 获取指令码
        instruction = int(driver_info['instruction'], 16)
        
        # 解析指令
        opcode = instruction & 0x7F  # 低7位
        funct3 = (instruction >> 12) & 0x7  # 位12-14
        rd = (instruction >> 7) & 0x1F  # 位7-11
        rs1 = (instruction >> 15) & 0x1F  # 位15-19
        rs2 = (instruction >> 20) & 0x1F  # 位20-24
        funct7 = (instruction >> 25) & 0x7F  # 位25-31
        bit30 = (instruction >> 30) & 0x1  # 位30
        
        # 计算立即数
        imm = calculate_immediate(instruction, opcode)
            
        # 计算预期的控制信号
        expected_signals = get_expected_signals(opcode, funct3, funct7, bit30, imm)
        
        # 验证结果
        test_result = {
            'idx': idx,
            'instruction': driver_info['instruction'],
            'instruction_name': expected_signals['name'],
            'expected': expected_signals,
            'actual': decoder_info,
            'passed': False
        }
        
        # 如果有Decoder输出，进行验证
        if decoder_info:
            # 验证ALU功能码
            alu_match = int(decoder_info['alu_func'], 16) == expected_signals['alu_func']
            
            # 验证操作数选择
            op1_match = int(decoder_info['op1_sel'], 16) == expected_signals['op1_sel']
            op2_match = int(decoder_info['op2_sel'], 16) == expected_signals['op2_sel']
            
            # 验证立即数
            imm_match = int(decoder_info['imm'], 16) == expected_signals['imm']
            
            # 整体验证
            test_result['passed'] = alu_match and op1_match and op2_match and imm_match
            test_result['details'] = {
                'alu_match': alu_match,
                'op1_match': op1_match,
                'op2_match': op2_match,
                'imm_match': imm_match
            }
            
            if test_result['passed']:
                success_count += 1
                print(f"✅ 测试向量 {idx}: {expected_signals['name']} 指令解码成功")
            else:
                print(f"❌ 测试向量 {idx}: {expected_signals['name']} 指令解码失败")
                if not alu_match:
                    print(f"   ALU功能码不匹配: 预期 {hex(expected_signals['alu_func'])}, 实际 {decoder_info['alu_func']}")
                if not op1_match:
                    print(f"   操作数1选择不匹配: 预期 {hex(expected_signals['op1_sel'])}, 实际 {decoder_info['op1_sel']}")
                if not op2_match:
                    print(f"   操作数2选择不匹配: 预期 {hex(expected_signals['op2_sel'])}, 实际 {decoder_info['op2_sel']}")
                if not imm_match:
                    print(f"   立即数不匹配: 预期 {hex(expected_signals['imm'])}, 实际 {decoder_info['imm']}")
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
    if opcode == 0b0010011 or opcode == 0b0000011 or opcode == 0b1100111:  # OP_I_TYPE, OP_LOAD, OP_JALR
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
        imm = ((instruction >> 31) << 12) | ((instruction >> 7) & 0x1) << 11 | \
              ((instruction >> 25) & 0x3F) << 5 | ((instruction >> 8) & 0xF) << 1
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
        imm = ((instruction >> 31) << 20) | ((instruction >> 12) & 0xFF) << 12 | \
              ((instruction >> 20) & 0x1) << 11 | ((instruction >> 21) & 0x3FF) << 1
        # 符号扩展
        if imm & 0x100000:
            imm -= 0x200000
        return imm
    
    # 默认情况
    return 0


def get_expected_signals(opcode, funct3, funct7, bit30, imm_i):
    """根据指令码获取预期的控制信号"""
    # 默认值
    result = {
        'name': 'UNKNOWN',
        'alu_func': 0,
        'op1_sel': 0,
        'op2_sel': 0,
        'imm': 0
    }
    
    # R-Type指令
    if opcode == 0b0110011:  # OP_R_TYPE
        if funct3 == 0x0:
            if bit30 == 0:  # add
                result.update({
                    'name': 'add',
                    'alu_func': 0b0000000000000001,  # ALUOp.ADD
                    'op1_sel': 0b001,  # Op1Sel.RS1
                    'op2_sel': 0b001,  # Op2Sel.RS2
                    'imm': 0
                })
            else:  # sub
                result.update({
                    'name': 'sub',
                    'alu_func': 0b0000000000000010,  # ALUOp.SUB
                    'op1_sel': 0b001,  # Op1Sel.RS1
                    'op2_sel': 0b001,  # Op2Sel.RS2
                    'imm': 0
                })
        elif funct3 == 0x1:  # sll
            result.update({
                'name': 'sll',
                'alu_func': 0b0000000000000100,  # ALUOp.SLL
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b001,  # Op2Sel.RS2
                'imm': 0
            })
        elif funct3 == 0x2:  # slt
            result.update({
                'name': 'slt',
                'alu_func': 0b0000000000001000,  # ALUOp.SLT
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b001,  # Op2Sel.RS2
                'imm': 0
            })
        elif funct3 == 0x3:  # sltu
            result.update({
                'name': 'sltu',
                'alu_func': 0b0000000000010000,  # ALUOp.SLTU
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b001,  # Op2Sel.RS2
                'imm': 0
            })
        elif funct3 == 0x4:  # xor
            result.update({
                'name': 'xor',
                'alu_func': 0b0000000000100000,  # ALUOp.XOR
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b001,  # Op2Sel.RS2
                'imm': 0
            })
        elif funct3 == 0x5:
            if bit30 == 0:  # srl
                result.update({
                    'name': 'srl',
                    'alu_func': 0b0000000001000000,  # ALUOp.SRL
                    'op1_sel': 0b001,  # Op1Sel.RS1
                    'op2_sel': 0b001,  # Op2Sel.RS2
                    'imm': 0
                })
            else:  # sra
                result.update({
                    'name': 'sra',
                    'alu_func': 0b0000000010000000,  # ALUOp.SRA
                    'op1_sel': 0b001,  # Op1Sel.RS1
                    'op2_sel': 0b001,  # Op2Sel.RS2
                    'imm': 0
                })
        elif funct3 == 0x6:  # or
            result.update({
                'name': 'or',
                'alu_func': 0b0000000100000000,  # ALUOp.OR
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b001,  # Op2Sel.RS2
                'imm': 0
            })
        elif funct3 == 0x7:  # and
            result.update({
                'name': 'and',
                'alu_func': 0b0000001000000000,  # ALUOp.AND
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b001,  # Op2Sel.RS2
                'imm': 0
            })
    
    # I-Type指令 (ALU)
    elif opcode == 0b0010011:  # OP_I_TYPE
        if funct3 == 0x0:  # addi
            result.update({
                'name': 'addi',
                'alu_func': 0b0000000000000001,  # ALUOp.ADD
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b010,  # Op2Sel.IMM
                'imm': imm_i
            })
        elif funct3 == 0x1:  # slli
            result.update({
                'name': 'slli',
                'alu_func': 0b0000000000000100,  # ALUOp.SLL
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b010,  # Op2Sel.IMM
                'imm': imm_i
            })
        elif funct3 == 0x2:  # slti
            result.update({
                'name': 'slti',
                'alu_func': 0b0000000000001000,  # ALUOp.SLT
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b010,  # Op2Sel.IMM
                'imm': imm_i
            })
        elif funct3 == 0x3:  # sltiu
            result.update({
                'name': 'sltiu',
                'alu_func': 0b0000000000010000,  # ALUOp.SLTU
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b010,  # Op2Sel.IMM
                'imm': imm_i
            })
        elif funct3 == 0x4:  # xori
            result.update({
                'name': 'xori',
                'alu_func': 0b0000000000100000,  # ALUOp.XOR
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b010,  # Op2Sel.IMM
                'imm': imm_i
            })
        elif funct3 == 0x5:
            if bit30 == 0:  # srli
                result.update({
                    'name': 'srli',
                    'alu_func': 0b0000000001000000,  # ALUOp.SRL
                    'op1_sel': 0b001,  # Op1Sel.RS1
                    'op2_sel': 0b010,  # Op2Sel.IMM
                    'imm': imm_i
                })
            else:  # srai
                result.update({
                    'name': 'srai',
                    'alu_func': 0b0000000010000000,  # ALUOp.SRA
                    'op1_sel': 0b001,  # Op1Sel.RS1
                    'op2_sel': 0b010,  # Op2Sel.IMM
                    'imm': imm_i
                })
        elif funct3 == 0x6:  # ori
            result.update({
                'name': 'ori',
                'alu_func': 0b0000000100000000,  # ALUOp.OR
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b010,  # Op2Sel.IMM
                'imm': imm_i
            })
        elif funct3 == 0x7:  # andi
            result.update({
                'name': 'andi',
                'alu_func': 0b0000001000000000,  # ALUOp.AND
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b010,  # Op2Sel.IMM
                'imm': imm_i
            })
    
    # Load指令
    elif opcode == 0b0000011:  # OP_LOAD
        if funct3 == 0x0:  # lb
            result.update({
                'name': 'lb',
                'alu_func': 0b0000000000000001,  # ALUOp.ADD
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b010,  # Op2Sel.IMM
                'imm': imm_i
            })
        elif funct3 == 0x1:  # lh
            result.update({
                'name': 'lh',
                'alu_func': 0b0000000000000001,  # ALUOp.ADD
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b010,  # Op2Sel.IMM
                'imm': imm_i
            })
        elif funct3 == 0x2:  # lw
            result.update({
                'name': 'lw',
                'alu_func': 0b0000000000000001,  # ALUOp.ADD
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b010,  # Op2Sel.IMM
                'imm': imm_i
            })
        elif funct3 == 0x4:  # lbu
            result.update({
                'name': 'lbu',
                'alu_func': 0b0000000000000001,  # ALUOp.ADD
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b010,  # Op2Sel.IMM
                'imm': imm_i
            })
        elif funct3 == 0x5:  # lhu
            result.update({
                'name': 'lhu',
                'alu_func': 0b0000000000000001,  # ALUOp.ADD
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b010,  # Op2Sel.IMM
                'imm': imm_i
            })
    
    # S-Type指令
    elif opcode == 0b0100011:  # OP_STORE
        if funct3 == 0x0:  # sb
            result.update({
                'name': 'sb',
                'alu_func': 0b0000000000000001,  # ALUOp.ADD
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b010,  # Op2Sel.IMM
                'imm': imm_i
            })
        elif funct3 == 0x1:  # sh
            result.update({
                'name': 'sh',
                'alu_func': 0b0000000000000001,  # ALUOp.ADD
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b010,  # Op2Sel.IMM
                'imm': imm_i
            })
        elif funct3 == 0x2:  # sw
            result.update({
                'name': 'sw',
                'alu_func': 0b0000000000000001,  # ALUOp.ADD
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b010,  # Op2Sel.IMM
                'imm': imm_i
            })
    
    # B-Type指令
    elif opcode == 0b1100011:  # OP_BRANCH
        if funct3 == 0x0:  # beq
            result.update({
                'name': 'beq',
                'alu_func': 0b0000000000000010,  # ALUOp.SUB
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b001,  # Op2Sel.RS2
                'imm': imm_i
            })
        elif funct3 == 0x1:  # bne
            result.update({
                'name': 'bne',
                'alu_func': 0b0000000000000010,  # ALUOp.SUB
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b001,  # Op2Sel.RS2
                'imm': imm_i
            })
        elif funct3 == 0x4:  # blt
            result.update({
                'name': 'blt',
                'alu_func': 0b0000000000001000,  # ALUOp.SLT
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b001,  # Op2Sel.RS2
                'imm': imm_i
            })
        elif funct3 == 0x5:  # bge
            result.update({
                'name': 'bge',
                'alu_func': 0b0000000000001000,  # ALUOp.SLT
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b001,  # Op2Sel.RS2
                'imm': imm_i
            })
        elif funct3 == 0x6:  # bltu
            result.update({
                'name': 'bltu',
                'alu_func': 0b0000000000010000,  # ALUOp.SLTU
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b001,  # Op2Sel.RS2
                'imm': imm_i
            })
        elif funct3 == 0x7:  # bgeu
            result.update({
                'name': 'bgeu',
                'alu_func': 0b0000000000010000,  # ALUOp.SLTU
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b001,  # Op2Sel.RS2
                'imm': imm_i
            })
    
    # U-Type指令
    elif opcode == 0b0110111:  # OP_LUI
        result.update({
            'name': 'lui',
            'alu_func': 0b0000000000000001,  # ALUOp.ADD
            'op1_sel': 0b100,  # Op1Sel.ZERO
            'op2_sel': 0b010,  # Op2Sel.IMM
            'imm': imm_i
        })
    elif opcode == 0b0010111:  # OP_AUIPC
        result.update({
            'name': 'auipc',
            'alu_func': 0b0000000000000001,  # ALUOp.ADD
            'op1_sel': 0b010,  # Op1Sel.PC
            'op2_sel': 0b010,  # Op2Sel.IMM
            'imm': imm_i
        })
    
    # J-Type指令
    elif opcode == 0b1101111:  # OP_JAL
        result.update({
            'name': 'jal',
            'alu_func': 0b0000000000000001,  # ALUOp.ADD
            'op1_sel': 0b010,  # Op1Sel.PC
            'op2_sel': 0b100,  # Op2Sel.CONST_4
            'imm': imm_i
        })
    elif opcode == 0b1100111:  # OP_JALR
        result.update({
            'name': 'jalr',
            'alu_func': 0b0000000000000001,  # ALUOp.ADD
            'op1_sel': 0b010,  # Op1Sel.PC
            'op2_sel': 0b100,  # Op2Sel.CONST_4
            'imm': imm_i
        })
    
    # 特殊指令
    elif opcode == 0b1110011:  # OP_SYSTEM
        if funct3 == 0x0:  # ecall/ebreak
            result.update({
                'name': 'ecall/ebreak',
                'alu_func': 0b1000000000000000,  # ALUOp.NOP
                'op1_sel': 0b001,  # Op1Sel.RS1
                'op2_sel': 0b010,  # Op2Sel.IMM
                'imm': imm_i
            })
    
    return result


def generate_test_report(test_results):
    """生成详细的测试报告"""
    print("\n" + "="*80)
    print("Decoder测试详细报告")
    print("="*80)
    
    # 统计各类指令的测试情况
    instruction_stats = {}
    failed_tests = []
    
    for result in test_results:
        instr_name = result['instruction_name']
        if instr_name not in instruction_stats:
            instruction_stats[instr_name] = {'total': 0, 'passed': 0}
        
        instruction_stats[instr_name]['total'] += 1
        if result['passed']:
            instruction_stats[instr_name]['passed'] += 1
        else:
            failed_tests.append(result)
    
    # 打印指令统计
    print("\n指令类型统计:")
    print("-"*60)
    for instr, stats in instruction_stats.items():
        pass_rate = (stats['passed'] / stats['total']) * 100 if stats['total'] > 0 else 0
        print(f"{instr:10} | 通过: {stats['passed']:2d}/{stats['total']:2d} | 通过率: {pass_rate:5.1f}%")
    
    # 打印失败的测试用例
    if failed_tests:
        print("\n失败的测试用例:")
        print("-"*60)
        for test in failed_tests:
            print(f"测试向量 {test['idx']}: {test['instruction_name']} (指令: {test['instruction']})")
            if test['actual'] and 'details' in test:
                details = test['details']
                if not details['alu_match']:
                    print(f"  - ALU功能码不匹配: 预期 {hex(test['expected']['alu_func'])}, 实际 {test['actual']['alu_func']}")
                if not details['op1_match']:
                    print(f"  - 操作数1选择不匹配: 预期 {hex(test['expected']['op1_sel'])}, 实际 {test['actual']['op1_sel']}")
                if not details['op2_match']:
                    print(f"  - 操作数2选择不匹配: 预期 {hex(test['expected']['op2_sel'])}, 实际 {test['actual']['op2_sel']}")
                if not details['imm_match']:
                    print(f"  - 立即数不匹配: 预期 {hex(test['expected']['imm'])}, 实际 {test['actual']['imm']}")
            else:
                print("  - 未找到Decoder输出")
    
    print("\n" + "="*80)


# ==============================================================================
# 3. 主执行入口
# ==============================================================================
if __name__ == "__main__":
    print("="*80)
    print("MyCPU Decoder模块测试")
    print("="*80)
    print("测试说明：")
    print("1. 本测试验证Decoder模块是否能正确解码RISC-V指令")
    print("2. 测试覆盖R-Type、I-Type、S-Type、B-Type、U-Type和J-Type指令")
    print("3. 验证控制信号(ALU功能码、操作数选择、立即数)的正确性")
    print("4. 在apptainer容器中运行测试:")
    print("   - source setup.sh")
    print("   - cd MyCPU")
    print("   - python tests/test_decoder.py")
    print("="*80)
    
    sys = SysBuilder("test_decoder_module")

    with sys:
        # 创建测试模块
        dut = Decoder()
        dut_impl = DecoderImpl()
        driver = Driver()

        # 创建必要的辅助模块和数据结构
        icache_dout = RegArray(Bits(32), 1)
        reg_file = RegArray(Bits(32), 32)  # 32个寄存器
        
        # 创建Mock执行单元模块
        class MockExecutor(Module):
            def __init__(self):
                super().__init__(
                    ports={
                        "ctrl": Port(ex_ctrl_signals),
                        "pc": Port(Bits(32)),
                        "rs1_data": Port(Bits(32)),
                        "rs2_data": Port(Bits(32)),
                        "imm": Port(Bits(32)),
                    }
                )
                self.name = "MockExecutor"
            
            @module.combinational
            def build(self):
                # 弹出所有端口数据
                ctrl = self.ctrl.pop()
                pc = self.pc.pop()
                rs1_data = self.rs1_data.pop()
                rs2_data = self.rs2_data.pop()
                imm = self.imm.pop()
                
                # 记录输入数据
                log("MockExecutor: alu_func=0x{:x} op1_sel=0x{:x} op2_sel=0x{:x} imm=0x{:x}",
                    ctrl.alu_func, ctrl.op1_sel, ctrl.op2_sel, imm)
                
                # 不需要实际执行，仅用于测试连接
        
        executor = MockExecutor()
        rs1_sel = Bits(4)(0)
        rs2_sel = Bits(4)(0)
        stall_if = Bits(1)(0)
        branch_target_reg = RegArray(Bits(32), 1)

        # 构建Driver
        driver.build(
            dut,
            icache_dout,
            reg_file,
            executor,
            rs1_sel,
            rs2_sel,
            stall_if,
            branch_target_reg,
        )

        # 构建Decoder
        pre_pkt, rs1, rs2, rs1_used, rs2_used = dut.build(icache_dout, reg_file)

        # 构建DecoderImpl
        dut_impl.build(
            pre_pkt,
            executor,
            rs1_sel,
            rs2_sel,
            stall_if,
            branch_target_reg,
        )
        
        # 添加日志输出，显示测试模块连接信息
        log("Test Setup: Driver -> Decoder -> DecoderImpl -> MockExecutor 连接完成")
        log("Test Setup: 测试向量数量: 30")
        log("Test Setup: 开始执行Decoder测试...")

    run_test_module(sys, check)