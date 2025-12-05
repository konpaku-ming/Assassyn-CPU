import sys
import os

# 1. 环境路径设置 (确保能 import src)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from assassyn.frontend import *

# 导入你的设计
from src.execution import Execution
from src.memory import MemoryAccess
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
        mem_module: Module, 
        ex_mem_bypass: Array, 
        mem_wb_bypass: Array,
        branch_target_reg: Array
    ):
        # --- 测试向量定义 ---
        # 格式: (alu_func, rs1_sel, rs2_sel, op1_sel, op2_sel, is_branch, is_jtype, is_jalr, 
        #       next_pc_addr, pc, rs1_data, rs2_data, imm, ex_mem_fwd, mem_wb_fwd, expected_result)
        # 
        # alu_func: ALU功能码 (独热码)
        # rs1_sel/rs2_sel: 数据来源选择 (独热码)
        # op1_sel/op2_sel: 操作数选择 (独热码)
        # is_branch/is_jtype/is_jalr: 控制信号
        # next_pc_addr: 预测的下一条PC地址
        # pc: 当前PC值
        # rs1_data/rs2_data: 寄存器数据
        # imm: 立即数
        # ex_mem_fwd: EX-MEM旁路数据
        # mem_wb_fwd: MEM-WB旁路数据
        # expected_result: 预期的ALU结果
        
        vectors = [
            # --- ALU 操作测试 ---
            # Case 0: ADD 指令 (rs1 + rs2)
            (ALUOp.ADD, Rs1Sel.RS1, Rs2Sel.RS2, Op1Sel.RS1, Op2Sel.RS2, 
             Bits(1)(0), Bits(1)(0), Bits(1)(0), Bits(32)(0x1004), 
             Bits(32)(0x1000), Bits(32)(10), Bits(32)(20), Bits(32)(0), 
             Bits(32)(0), Bits(32)(0), Bits(32)(30)),
             
            # Case 1: SUB 指令 (rs1 - rs2)
            (ALUOp.SUB, Rs1Sel.RS1, Rs2Sel.RS2, Op1Sel.RS1, Op2Sel.RS2, 
             Bits(1)(0), Bits(1)(0), Bits(1)(0), Bits(32)(0x1004), 
             Bits(32)(0x1000), Bits(32)(20), Bits(32)(10), Bits(32)(0), 
             Bits(32)(0), Bits(32)(0), Bits(32)(10)),
             
            # Case 2: AND 指令 (rs1 & rs2)
            (ALUOp.AND, Rs1Sel.RS1, Rs2Sel.RS2, Op1Sel.RS1, Op2Sel.RS2, 
             Bits(1)(0), Bits(1)(0), Bits(1)(0), Bits(32)(0x1004), 
             Bits(32)(0x1000), Bits(32)(0xF0F0F0F0), Bits(32)(0x0F0F0F0F), Bits(32)(0), 
             Bits(32)(0), Bits(32)(0), Bits(32)(0x00000000)),
             
            # Case 3: OR 指令 (rs1 | rs2)
            (ALUOp.OR, Rs1Sel.RS1, Rs2Sel.RS2, Op1Sel.RS1, Op2Sel.RS2, 
             Bits(1)(0), Bits(1)(0), Bits(1)(0), Bits(32)(0x1004), 
             Bits(32)(0x1000), Bits(32)(0xF0F0F0F0), Bits(32)(0x0F0F0F0F), Bits(32)(0), 
             Bits(32)(0), Bits(32)(0), Bits(32)(0xFFFFFFFF)),
             
            # Case 4: SLL 指令 (rs1 << rs2[4:0])
            (ALUOp.SLL, Rs1Sel.RS1, Rs2Sel.RS2, Op1Sel.RS1, Op2Sel.RS2, 
             Bits(1)(0), Bits(1)(0), Bits(1)(0), Bits(32)(0x1004), 
             Bits(32)(0x1000), Bits(32)(0x0000000F), Bits(32)(2), Bits(32)(0), 
             Bits(32)(0), Bits(32)(0), Bits(32)(0x0000003C)),
             
            # Case 5: SRL 指令 (rs1 >> rs2[4:0])
            (ALUOp.SRL, Rs1Sel.RS1, Rs2Sel.RS2, Op1Sel.RS1, Op2Sel.RS2, 
             Bits(1)(0), Bits(1)(0), Bits(1)(0), Bits(32)(0x1004), 
             Bits(32)(0x1000), Bits(32)(0xFFFFFFFC), Bits(32)(2), Bits(32)(0), 
             Bits(32)(0), Bits(32)(0), Bits(32)(0x3FFFFFFF)),
             
            # Case 6: SRA 指令 (有符号右移)
            (ALUOp.SRA, Rs1Sel.RS1, Rs2Sel.RS2, Op1Sel.RS1, Op2Sel.RS2, 
             Bits(1)(0), Bits(1)(0), Bits(1)(0), Bits(32)(0x1004), 
             Bits(32)(0x1000), Bits(32)(0xFFFFFFF0), Bits(32)(2), Bits(32)(0), 
             Bits(32)(0), Bits(32)(0), Bits(32)(0xFFFFFFFC)),
             
            # Case 7: SLT 指令 (有符号比较)
            (ALUOp.SLT, Rs1Sel.RS1, Rs2Sel.RS2, Op1Sel.RS1, Op2Sel.RS2, 
             Bits(1)(0), Bits(1)(0), Bits(1)(0), Bits(32)(0x1004), 
             Bits(32)(0x1000), Bits(32)(-5), Bits(32)(5), Bits(32)(0), 
             Bits(32)(0), Bits(32)(0), Bits(32)(1)),
             
            # Case 8: SLTU 指令 (无符号比较)
            (ALUOp.SLTU, Rs1Sel.RS1, Rs2Sel.RS2, Op1Sel.RS1, Op2Sel.RS2, 
             Bits(1)(0), Bits(1)(0), Bits(1)(0), Bits(32)(0x1004), 
             Bits(32)(0x1000), Bits(32)(0x80000000), Bits(32)(5), Bits(32)(0), 
             Bits(32)(0), Bits(32)(0), Bits(32)(0)),
             
            # --- 旁路测试 ---
            # Case 9: 使用EX-MEM旁路数据
            (ALUOp.ADD, Rs1Sel.EX_MEM_BYPASS, Rs2Sel.RS2, Op1Sel.RS1, Op2Sel.RS2, 
             Bits(1)(0), Bits(1)(0), Bits(1)(0), Bits(32)(0x1004), 
             Bits(32)(0x1000), Bits(32)(10), Bits(32)(20), Bits(32)(0), 
             Bits(32)(100), Bits(32)(0), Bits(32)(120)),
             
            # Case 10: 使用MEM-WB旁路数据
            (ALUOp.ADD, Rs1Sel.MEM_WB_BYPASS, Rs2Sel.RS2, Op1Sel.RS1, Op2Sel.RS2, 
             Bits(1)(0), Bits(1)(0), Bits(1)(0), Bits(32)(0x1004), 
             Bits(32)(0x1000), Bits(32)(10), Bits(32)(20), Bits(32)(0), 
             Bits(32)(0), Bits(32)(200), Bits(32)(220)),
             
            # --- 分支指令测试 ---
            # Case 11: BEQ (相等分支)
            (ALUOp.ADD, Rs1Sel.RS1, Rs2Sel.RS2, Op1Sel.RS1, Op2Sel.RS2, 
             Bits(1)(1), Bits(1)(0), Bits(1)(0), Bits(32)(0x1008), 
             Bits(32)(0x1000), Bits(32)(10), Bits(32)(10), Bits(32)(8), 
             Bits(32)(0), Bits(32)(0), Bits(32)(0)),  # 10-10=0，BEQ条件成立
             
            # Case 12: BNE (不等分支)
            (ALUOp.SUB, Rs1Sel.RS1, Rs2Sel.RS2, Op1Sel.RS1, Op2Sel.RS2, 
             Bits(1)(1), Bits(1)(0), Bits(1)(0), Bits(32)(0x1008), 
             Bits(32)(0x1000), Bits(32)(10), Bits(32)(20), Bits(32)(8), 
             Bits(32)(0), Bits(32)(0), Bits(32)(0xFFFFFFFE)),  # 10-20=-10≠0，BNE条件成立
             
            # Case 13: BLT (小于分支)
            (ALUOp.SLT, Rs1Sel.RS1, Rs2Sel.RS2, Op1Sel.RS1, Op2Sel.RS2, 
             Bits(1)(1), Bits(1)(0), Bits(1)(0), Bits(32)(0x1008), 
             Bits(32)(0x1000), Bits(32)(5), Bits(32)(10), Bits(32)(8), 
             Bits(32)(0), Bits(32)(0), Bits(32)(1)),  # 5<10，BLT条件成立
             
            # Case 14: BGE (大于等于分支)
            (ALUOp.SLTU, Rs1Sel.RS1, Rs2Sel.RS2, Op1Sel.RS1, Op2Sel.RS2, 
             Bits(1)(1), Bits(1)(0), Bits(1)(0), Bits(32)(0x1008), 
             Bits(32)(0x1000), Bits(32)(10), Bits(32)(5), Bits(32)(8), 
             Bits(32)(0), Bits(32)(0), Bits(32)(0)),  # 10>=5，BGE条件成立
             
            # --- JAL/JALR 指令测试 ---
            # Case 15: JAL (直接跳转)
            (ALUOp.ADD, Rs1Sel.RS1, Rs2Sel.RS2, Op1Sel.PC, Op2Sel.CONST_4, 
             Bits(1)(0), Bits(1)(1), Bits(1)(0), Bits(32)(0x1008), 
             Bits(32)(0x1000), Bits(32)(0), Bits(32)(0), Bits(32)(8), 
             Bits(32)(0), Bits(32)(0), Bits(32)(0x1004)),  # PC+4=0x1004
             
            # Case 16: JALR (间接跳转)
            (ALUOp.ADD, Rs1Sel.RS1, Rs2Sel.RS2, Op1Sel.PC, Op2Sel.CONST_4, 
             Bits(1)(0), Bits(1)(1), Bits(1)(1), Bits(32)(0x2000), 
             Bits(32)(0x1000), Bits(32)(0x2000), Bits(32)(0), Bits(32)(8), 
             Bits(32)(0), Bits(32)(0), Bits(32)(0x1004)),  # PC+4=0x1004，但跳转到0x2008
        ]

        # --- 激励生成逻辑 ---
        # 1. 计数器：跟踪当前测试进度
        cnt = RegArray(UInt(32), 1)
        (cnt & self)[0] <= cnt[0] + UInt(32)(1)

        idx = cnt[0]

        # 2. 组合逻辑 Mux：根据 idx 选择当前的测试向量
        # 初始化默认值
        current_alu_func = Bits(16)(0)
        current_rs1_sel = Bits(3)(0)
        current_rs2_sel = Bits(3)(0)
        current_op1_sel = Bits(3)(0)
        current_op2_sel = Bits(3)(0)
        current_is_branch = Bits(1)(0)
        current_is_jtype = Bits(1)(0)
        current_is_jalr = Bits(1)(0)
        current_next_pc_addr = Bits(32)(0)
        current_pc = Bits(32)(0)
        current_rs1_data = Bits(32)(0)
        current_rs2_data = Bits(32)(0)
        current_imm = Bits(32)(0)
        current_ex_mem_fwd = Bits(32)(0)
        current_mem_wb_fwd = Bits(32)(0)
        current_expected = Bits(32)(0)

        # 这里的循环展开会生成一棵 Mux 树
        for i, (
            alu_func,
            rs1_sel,
            rs2_sel,
            op1_sel,
            op2_sel,
            is_branch,
            is_jtype,
            is_jalr,
            next_pc_addr,
            pc,
            rs1_data,
            rs2_data,
            imm,
            ex_mem_fwd,
            mem_wb_fwd,
            expected,
        ) in enumerate(vectors):
            is_match = idx == UInt(32)(i)
            
            current_alu_func = is_match.select(alu_func, current_alu_func)
            current_rs1_sel = is_match.select(rs1_sel, current_rs1_sel)
            current_rs2_sel = is_match.select(rs2_sel, current_rs2_sel)
            current_op1_sel = is_match.select(op1_sel, current_op1_sel)
            current_op2_sel = is_match.select(op2_sel, current_op2_sel)
            current_is_branch = is_match.select(is_branch, current_is_branch)
            current_is_jtype = is_match.select(is_jtype, current_is_jtype)
            current_is_jalr = is_match.select(is_jalr, current_is_jalr)
            current_next_pc_addr = is_match.select(next_pc_addr, current_next_pc_addr)
            current_pc = is_match.select(pc, current_pc)
            current_rs1_data = is_match.select(rs1_data, current_rs1_data)
            current_rs2_data = is_match.select(rs2_data, current_rs2_data)
            current_imm = is_match.select(imm, current_imm)
            current_ex_mem_fwd = is_match.select(ex_mem_fwd, current_ex_mem_fwd)
            current_mem_wb_fwd = is_match.select(mem_wb_fwd, current_mem_wb_fwd)
            current_expected = is_match.select(expected, current_expected)

        # 3. 构建控制信号包
        # 首先创建mem_ctrl信号
        mem_ctrl = mem_ctrl_signals.bundle(
            mem_opcode=MemOp.NONE,  # EX阶段测试不涉及内存操作
            mem_width=MemWidth.WORD,
            mem_unsigned=MemSign.UNSIGNED,
            rd_addr=Bits(5)(1),  # 默认写入x1寄存器
        )
        
        # 然后创建ex_ctrl信号
        ctrl_pkt = ex_ctrl_signals.bundle(
            alu_func=current_alu_func,
            rs1_sel=current_rs1_sel,
            rs2_sel=current_rs2_sel,
            op1_sel=current_op1_sel,
            op2_sel=current_op2_sel,
            is_branch=current_is_branch,
            is_jtype=current_is_jtype,
            is_jalr=current_is_jalr,
            next_pc_addr=current_next_pc_addr,
            mem_ctrl=mem_ctrl
        )

        # 4. 设置旁路数据
        ex_mem_bypass[0] = current_ex_mem_fwd
        mem_wb_bypass[0] = current_mem_wb_fwd

        # 5. 发送数据
        # 只有当 idx 在向量范围内时才发送 (valid)
        valid_test = idx < UInt(32)(len(vectors))

        with Condition(valid_test):
            # 打印 Driver 发出的请求，方便对比调试
            log(
                "Driver: idx={} alu_func={} rs1_sel={} rs2_sel={} op1_sel={} op2_sel={} is_branch={} is_jtype={} is_jalr={} pc=0x{:x} rs1=0x{:x} rs2=0x{:x} imm=0x{:x} ex_mem_fwd=0x{:x} mem_wb_fwd=0x{:x} expected=0x{:x}",
                idx,
                current_alu_func,
                current_rs1_sel,
                current_rs2_sel,
                current_op1_sel,
                current_op2_sel,
                current_is_branch,
                current_is_jtype,
                current_is_jalr,
                current_pc,
                current_rs1_data,
                current_rs2_data,
                current_imm,
                current_ex_mem_fwd,
                current_mem_wb_fwd,
                current_expected,
            )

            # 建立连接 (async_called)
            dut.async_called(
                ctrl=ctrl_pkt,
                pc=current_pc,
                rs1_data=current_rs1_data,
                rs2_data=current_rs2_data,
                imm=current_imm
            )

        # [关键] 返回 cnt 和预期结果，让它们成为模块的输出
        return cnt, current_expected


# ==============================================================================
# 2. Sink 模块定义：用于接收EX模块的输出
# ==============================================================================
class Sink(Module):
    def __init__(self):
        super().__init__(ports={})

    @module.combinational
    def build(self, dut: Module, mem_module: Module):
        # 创建一个虚拟的SRAM用于测试
        sram_dout = RegArray(Bits(32), 1)
        
        # 创建一个模拟的SRAM模块用于测试
        class MockSRAM:
            def __init__(self):
                self.data = RegArray(Bits(32), 1024)  # 1024个32位字的SRAM
                
            def build(self, we, wdata, addr, re):
                # 如果是写操作且写使能有效
                with Condition(we):
                    # 将地址右移2位，因为我们是字对齐的
                    word_addr = addr >> 2
                    # 确保地址在范围内
                    with Condition(word_addr < 1024):
                        self.data[word_addr] = wdata
                        log("SRAM: Write addr=0x{:x} data=0x{:x}", word_addr << 2, wdata)
                
                # 如果是读操作且读使能有效
                with Condition(re):
                    # 将地址右移2位，因为我们是字对齐的
                    word_addr = addr >> 2
                    # 确保地址在范围内
                    with Condition(word_addr < 1024):
                        sram_dout[0] = self.data[word_addr]
                        log("SRAM: Read addr=0x{:x} data=0x{:x}", word_addr << 2, self.data[word_addr])
        
        # 创建旁路寄存器
        ex_mem_bypass = RegArray(Bits(32), 1)
        mem_wb_bypass = RegArray(Bits(32), 1)
        
        # 创建分支目标寄存器
        branch_target_reg = RegArray(Bits(32), 1)
        
        # 创建模拟的SRAM
        mock_sram = MockSRAM()
        
        # 调用DUT的build方法
        rd_addr, is_load = dut.build(
            mem_module=mem_module,
            sram_dout=sram_dout,
            ex_mem_bypass=ex_mem_bypass,
            mem_wb_bypass=mem_wb_bypass,
            branch_target_reg=branch_target_reg,
            dcache=mock_sram  # 使用模拟的SRAM
        )
        
        # 返回DUT的输出
        return rd_addr, is_load, ex_mem_bypass, mem_wb_bypass, branch_target_reg


# ==============================================================================
# 3. 验证逻辑 (Python Check)
# ==============================================================================
def check(raw_output):
    print(">>> 开始验证EX模块输出...")
    
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
        0x00000078,  # Case 9: 使用EX-MEM旁路 (100+20=120)
        0x000000DC,  # Case 10: 使用MEM-WB旁路 (200+20=220)
        0x00000000,  # Case 11: BEQ (10-10=0)
        0xFFFFFFFE,  # Case 12: BNE (10-20=-10)
        0x00000001,  # Case 13: BLT (5<10=1)
        0x00000000,  # Case 14: BGE (10>=5=0)
        0x00001004,  # Case 15: JAL (PC+4=0x1004)
        0x00001004,  # Case 16: JALR (PC+4=0x1004)
    ]
    
    # 捕获实际的ALU结果
    actual_results = []
    bypass_updates = []
    branch_updates = []
    
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
        
        # 捕获分支目标更新
        if "EX: Branch Target" in line:
            # 示例行: "[100] EX: Branch Target: 0x12345678"
            parts = line.split()
            for part in parts:
                if part.startswith("0x"):
                    target = int(part, 16)
                    branch_updates.append(target)
                    print(f"  [捕获] Branch Target: 0x{target:08x}")
                    break
    
    # --- 断言比对 ---
    
    # 1. ALU结果数量检查
    if len(actual_results) != len(expected_results):
        print(f"❌ 错误：预期ALU结果 {len(expected_results)} 个，实际捕获 {len(actual_results)} 个")
        assert False
    
    # 2. ALU结果内容检查
    for i, (exp_result, act_result) in enumerate(zip(expected_results, actual_results)):
        if exp_result != act_result:
            print(f"❌ 错误：第 {i} 个ALU结果不匹配")
            print(f"  预期: 0x{exp_result:08x}")
            print(f"  实际: 0x{act_result:08x}")
            assert False
    
    # 3. 旁路寄存器更新检查 (每个测试用例都会更新旁路寄存器)
    if len(bypass_updates) != len(expected_results):
        print(f"❌ 错误：预期旁路更新 {len(expected_results)} 次，实际更新 {len(bypass_updates)} 次")
        assert False
    
    # 4. 分支目标更新检查 (只有分支指令会更新分支目标寄存器)
    # 在我们的测试中，Case 11-14 是分支指令
    expected_branch_updates = 4  # Case 11-14
    if len(branch_updates) != expected_branch_updates:
        print(f"❌ 错误：预期分支目标更新 {expected_branch_updates} 次，实际更新 {len(branch_updates)} 次")
        assert False
    
    print("✅ EX模块测试通过！(所有ALU操作、分支指令和旁路功能均正确)")


# ==============================================================================
# 4. 主执行入口
# ==============================================================================
if __name__ == "__main__":
    sys = SysBuilder("test_execute_module")

    with sys:
        # 创建测试模块
        dut = Execution()
        mem_module = MemoryAccess()  # 虚拟的MEM模块，用于测试
        driver = Driver()
        sink = Sink()
        
        # 创建旁路寄存器和分支目标寄存器
        ex_mem_bypass = RegArray(Bits(32), 1)
        mem_wb_bypass = RegArray(Bits(32), 1)
        branch_target_reg = RegArray(Bits(32), 1)
        
        # [关键] 获取 Driver 的返回值
        driver_cnt, driver_expected = driver.build(
            dut, mem_module, ex_mem_bypass, mem_wb_bypass, branch_target_reg
        )
        
        # 获取 Sink 的返回值
        rd_addr, is_load, ex_mem_bypass_out, mem_wb_bypass_out, branch_target_out = sink.build(dut, mem_module)
        
        # [关键] 暴露 Driver 的计数器，防止被 DCE 优化掉
        sys.expose_on_top(driver_cnt, kind="Output")
        sys.expose_on_top(driver_expected, kind="Output")
        
        # 暴露其他信号
        sys.expose_on_top(ex_mem_bypass_out, kind="Output")
        sys.expose_on_top(mem_wb_bypass_out, kind="Output")
        sys.expose_on_top(branch_target_out, kind="Output")
        sys.expose_on_top(rd_addr, kind="Output")
        sys.expose_on_top(is_load, kind="Output")

    run_test_module(sys, check)