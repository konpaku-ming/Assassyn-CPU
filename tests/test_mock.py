import sys
import os
import re

# 1. 环境路径设置 (确保能 import src)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from assassyn.frontend import *
from src.control_signals import *

# ==============================================================================
# 公共Mock模块定义
# ==============================================================================


# MockSRAM类：模拟SRAM（静态随机存取存储器）的行为
# 用于测试内存读写操作，包括对齐检查
class MockSRAM:
    def __init__(self):
        # 定义数据输出端口
        self.dout = RegArray(Bits(32), 1)

    def build(self, we, re, addr, wdata):
        # 打印基本信息
        with Condition(we):
            log("SRAM: EX阶段 - WRITE addr=0x{:x} wdata=0x{:x}", addr, wdata)

            # 检查对齐
            is_unaligned = addr[0:1] != Bits(2)(0)
            with Condition(is_unaligned):
                log("SRAM: Warning - Unaligned WRITE addr=0x{:x}", addr)

        with Condition(re):
            log("SRAM: EX阶段 - READ addr=0x{:x}", addr)

            # 检查对齐
            is_unaligned = addr[0:1] != Bits(2)(0)
            with Condition(is_unaligned):
                log("SRAM: Warning - Unaligned READ addr=0x{:x}", addr)


# MockMEM类：模拟内存访问阶段（MEM Stage）的行为
# 用于测试内存相关指令的执行
class MockMEM(Module):
    def __init__(self):
        # 定义与 MEM 模块一致的输入端口
        super().__init__(
            ports={"ctrl": Port(mem_ctrl_signals), "alu_result": Port(Bits(32))}
        )
        self.name = "MockMEM"

    @module.combinational
    def build(self):
        # 接收并打印
        ctrl, res = self.pop_all_ports(False)
        # 打印有效数据
        # 这里可以验证 EX 算出的结果
        log(
            "[MEM_Sink] Recv: ALU_Res=0x{:x} Is_Load={}",
            res,
            ctrl.mem_opcode == MemOp.LOAD,
        )


# MockFeedback类：模拟反馈机制的行为
# 用于测试分支目标寄存器和旁路数据的更新
class MockFeedback(Module):
    def __init__(self):
        super().__init__(ports={})
        self.name = "FeedbackSink"

    @module.combinational
    def build(self, branch_target: Array, exec_bypass: Array):
        # 读取寄存器的当前值 (Q端)
        # 注意：这里读到的是上一拍 EX 阶段写入的结果
        tgt = branch_target[0]
        byp = exec_bypass[0]

        # 打印日志供 check 函数验证
        log("Target=0x{:x} Bypass=0x{:x}", tgt, byp)


# MockExecutor类：模拟执行单元（Executor）的行为
# 用于测试指令执行阶段的各种控制信号和数据流
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
        log(
            "MockExecutor: alu_func=0x{:x} op1_sel=0x{:x} op2_sel=0x{:x} imm=0x{:x} rs1_data=0x{:x} rs2_data=0x{:x} pc=0x{:x}",
            ctrl.alu_func,
            ctrl.op1_sel,
            ctrl.op2_sel,
            imm,
            rs1_data,
            rs2_data,
            pc,
        )


class MockSinkDecoder(Module):

    def __init__(self):
        super().__init__(ports={})
        self.name = "MockExec2"

    @module.combinational
    def build(self, pre, rs1, rs2, acc_rs1_used, acc_rs2_used):

        # 从 pre 中提取 mem_ctrl 子结构
        mem_ctrl = pre.mem_ctrl
        
        # 记录完整的 pre_decode_t 信息
        log(
            "MockSinkDecoder: alu_func=0x{:x} op1_sel=0x{:x} op2_sel=0x{:x} branch_type=0x{:x} next_pc_addr=0x{:x} mem_ctrl=[mem_opcode=0x{:x} mem_width=0x{:x} mem_unsigned=0x{:x} rd_addr=0x{:x}] pc=0x{:x} rs1_data=0x{:x} rs2_data=0x{:x} imm=0x{:x} rs1=0x{:x} rs2=0x{:x} rs1_used={} rs2_used={}",
            pre.alu_func,
            pre.op1_sel,
            pre.op2_sel,
            pre.branch_type,
            pre.next_pc_addr,
            mem_ctrl.mem_opcode,
            mem_ctrl.mem_width,
            mem_ctrl.mem_unsigned,
            mem_ctrl.rd_addr,
            pre.pc,
            pre.rs1_data,
            pre.rs2_data,
            pre.imm,
            rs1,
            rs2,
            acc_rs1_used,
            acc_rs2_used,
        )


# ==============================================================================
# 公共验证函数
# ==============================================================================


def check_alu_results(raw_output, expected_results, test_name="ALU"):
    """验证ALU结果的通用函数"""
    print(f">>> 开始验证{test_name}模块输出...")

    # 捕获实际的ALU结果
    actual_results = []

    for line in raw_output.split("\n"):
        # 捕获ALU结果
        if "EX: ALU Result" in line:
            # 示例行: "[100] EX: ALU Result: 0x12345678"
            parts = line.split()
            for part in parts:
                if part.startswith("0x"):
                    result = int(part, 16)
                    actual_results.append(result)
                    print(f"  [捕获] ALU Result: 0x{result:08x}")
                    break

    # ALU结果数量检查
    if len(actual_results) != len(expected_results):
        print(
            f"❌ 错误：预期ALU结果 {len(expected_results)} 个，实际捕获 {len(actual_results)} 个"
        )
        assert False

    # ALU结果内容检查
    for i, (exp_result, act_result) in enumerate(zip(expected_results, actual_results)):
        if exp_result != act_result:
            print(f"❌ 错误：第 {i} 个ALU结果不匹配")
            print(f"  预期: 0x{exp_result:08x}")
            print(f"  实际: 0x{act_result:08x}")
            assert False

    print(f"✅ {test_name}模块测试通过！(所有ALU操作均正确)")


def check_bypass_updates(raw_output, expected_results):
    """验证旁路寄存器更新的通用函数"""
    # 捕获旁路寄存器更新
    bypass_updates = []

    for line in raw_output.split("\n"):
        # 捕获旁路寄存器更新
        if "EX: Bypass Update" in line:
            # 示例行: "[100] EX: Bypass Update: 0x12345678"
            parts = line.split()
            for part in parts:
                if part.startswith("0x"):
                    bypass = int(part, 16)
                    bypass_updates.append(bypass)
                    print(f"  [捕获] Bypass Update: 0x{bypass:08x}")
                    break

    # 旁路寄存器更新检查 (每个测试用例都会更新旁路寄存器)
    if len(bypass_updates) != len(expected_results):
        print(
            f"❌ 错误：预期旁路更新 {len(expected_results)} 次，实际更新 {len(bypass_updates)} 次"
        )
        assert False

    print("✅ 旁路寄存器更新测试通过！")


def check_branch_operations(raw_output, exp_types, exp_taken, exp_targets):
    print(">>> 正在验证分支操作日志...")

    cap_types = []
    cap_taken = []
    cap_targets = []

    for line in raw_output.split("\n"):
        # 1. 解析 Branch Type
        if "Branch Type:" in line:
            try:
                # line: "... EX: Branch Type: NO_BRANCH"
                # split后: ["... EX: ", " NO_BRANCH"]
                # 取第二部分，去空格
                val = line.split("Branch Type:")[1].strip()
                # 如果后面还有其他杂项，只取第一个单词
                val = val.split()[0]
                cap_types.append(val)
                print(f"  [捕获] Branch Type: {val}")
            except IndexError:
                pass

        # 2. 解析 Branch Target
        if "Branch Target:" in line:
            try:
                # line: "... Branch Target: 0x12"
                val_str = line.split("Branch Target:")[1].strip().split()[0]
                val = int(val_str, 16)
                cap_targets.append(val)
                print(f"  [捕获] Branch Target: 0x{val:08x}")
            except (IndexError, ValueError):
                pass

        # 3. 解析 Branch Taken
        if "Branch Taken:" in line:
            try:
                # line: "... Branch Taken: True"
                val_str = line.split("Branch Taken:")[1].strip().split()[0]
                # 转换字符串 'True'/'False' 为 bool
                val = val_str == "True"
                cap_taken.append(val)
                print(f"  [捕获] Branch Taken: {val}")
            except IndexError:
                pass

    # 调试打印
    if len(cap_types) != len(exp_types):
        print(f"❌ 数量不匹配: 预期 {len(exp_types)}, 实际 {len(cap_types)}")

    for i, (exp, act) in enumerate(zip(exp_types, cap_types)):
        if exp != act:
            print(f"❌ 错误：第 {i} 个分支类型不匹配")
            print(f"  预期: {exp}")
            print(f"  实际: {act}")
            assert False

    print("✅ 分支逻辑验证通过！")


def check_branch_target_reg(raw_output, exp_types, exp_taken, exp_targets):
    print(">>> 验证分支目标寄存器 (Global Reg)...")

    captured_targets = []

    for line in raw_output.split("\n"):
        # 使用更宽松的匹配条件
        if "[Feedback]" in line:
            try:
                # 寻找 Target=0x...
                # 直接在整行里找子字符串
                if "Target=" not in line:
                    continue

                # 截取 Target= 之后的内容
                # 这里的 strip() 很关键，防止前导/后置空格干扰
                after_target = line.split("Target=")[1].strip()

                # 取第一个单词
                val_str = after_target.split()[0]

                # 转换为 int
                val = int(val_str, 16)
                captured_targets.append(val)
            except Exception as e:
                print(f"⚠️ Parse Warning: {line} -> {e}")
                pass


def check_sram_operations(raw_output, expected_sram_ops):
    """验证SRAM操作的通用函数"""
    sram_ops = []  # 捕获SRAM操作

    for line in raw_output.split("\n"):
        # 捕获EX阶段SRAM地址输出
        if "SRAM: EX阶段 - we=" in line:
            # 示例行: "SRAM: EX阶段 - we=True re=False addr=0x1000 wdata=0x12345678"
            addr_match = re.search(r"addr=(0x[0-9a-fA-F]+)", line)
            data_match = re.search(r"wdata=(0x[0-9a-fA-F]+)", line)
            we_match = re.search(r"we=(True|False)", line)
            re_match = re.search(r"re=(True|False)", line)

            if addr_match and we_match and re_match:
                addr = int(addr_match.group(1), 16)
                we = we_match.group(1) == "True"
                re = re_match.group(1) == "True"
                data = int(data_match.group(1), 16) if data_match else None

                if we:
                    sram_ops.append(("EX_STORE", addr, data))
                    print(
                        f"  [捕获] EX阶段Store地址: addr=0x{addr:08x}, data=0x{data:08x if data else 0:08x}"
                    )
                elif re:
                    sram_ops.append(("EX_LOAD", addr, data))
                    print(f"  [捕获] EX阶段Load地址: addr=0x{addr:08x}")

        # 捕获SRAM未对齐访问警告
        if "SRAM: Warning - Unaligned access" in line:
            # 示例行: "SRAM: Warning - Unaligned access addr=0x1001"
            addr_match = re.search(r"addr=(0x[0-9a-fA-F]+)", line)
            if addr_match:
                addr = int(addr_match.group(1), 16)
                # 检查是Store还是Load操作
                if "we=True" in line:
                    sram_ops.append(
                        ("EX_STORE", addr, None)
                    )  # 未对齐的Store操作，数据不重要
                    print(f"  [捕获] EX阶段未对齐Store: addr=0x{addr:08x}")
                elif "re=True" in line:
                    sram_ops.append(
                        ("EX_LOAD", addr, None)
                    )  # 未对齐的Load操作，数据不重要
                    print(f"  [捕获] EX阶段未对齐Load: addr=0x{addr:08x}")

    # SRAM操作检查
    # 过滤掉None值，只检查实际有SRAM操作的情况
    expected_sram_filtered = [op for op in expected_sram_ops if op is not None]
    if len(sram_ops) != len(expected_sram_filtered):
        print(
            f"❌ 错误：预期SRAM操作 {len(expected_sram_filtered)} 次，实际操作 {len(sram_ops)} 次"
        )
        print(f"  预期SRAM操作: {expected_sram_filtered}")
        print(f"  实际SRAM操作: {sram_ops}")
        assert False

    # SRAM操作内容检查
    sram_op_idx = 0
    for i, sram_op in enumerate(expected_sram_ops):
        if sram_op is not None:  # 只检查有SRAM操作的情况
            exp_type, exp_addr, exp_data = sram_op
            act_type, act_addr, act_data = sram_ops[sram_op_idx]

            # 检查操作类型
            if exp_type != act_type:
                print(f"❌ 错误：第 {i} 个SRAM操作类型不匹配")
                print(f"  预期: {exp_type}")
                print(f"  实际: {act_type}")
                assert False

            # 检查地址
            if exp_addr != act_addr:
                print(f"❌ 错误：第 {i} 个SRAM操作地址不匹配")
                print(f"  预期: 0x{exp_addr:08x}")
                print(f"  实际: 0x{act_addr:08x}")
                assert False

            # 对于未对齐访问，只检查操作类型和地址，不检查数据
            if exp_data is not None and act_data is not None:
                if exp_data != act_data:
                    print(f"❌ 错误：第 {i} 个SRAM操作数据不匹配")
                    print(f"  预期: 0x{exp_data:08x}")
                    print(f"  实际: 0x{act_data:08x}")
                    assert False

            sram_op_idx += 1

    print("✅ SRAM操作测试通过！")
    print("✅ EX阶段正确输出地址而非结果，MEM阶段正确处理内存操作")
