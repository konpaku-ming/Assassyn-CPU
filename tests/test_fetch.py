import sys
import os
import re

# 1. 环境路径设置 (确保能 import src)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from assassyn.frontend import *

# 导入你的设计
from src.fetch import Fetcher, FetcherImpl
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
        icache: SRAM,
        stall_if: Value,
        branch_target: Array,
    ):
        # --- 测试向量定义 ---
        # 格式: (stall, branch_target, expected_pc, expected_inst)
        # 
        # stall: 是否暂停取指
        # branch_target: 分支目标地址（0表示无分支）
        # expected_pc: 预期的PC值
        # expected_inst: 预期的指令值
        
        vectors = [
            # Case 0: 正常取指 (PC递增)
            (Bits(1)(0), Bits(32)(0), Bits(32)(0x0), Bits(32)(0x00000013)),  # NOP指令
            (Bits(1)(0), Bits(32)(0), Bits(32)(0x4), Bits(32)(0x00000093)),  # ADDI指令
            (Bits(1)(0), Bits(32)(0), Bits(32)(0x8), Bits(32)(0x00000113)),  # ADDI指令
            (Bits(1)(0), Bits(32)(0), Bits(32)(0xC), Bits(32)(0x00000193)),  # ADDI指令
            
            # Case 1: Stall测试 (PC保持不变)
            (Bits(1)(1), Bits(32)(0), Bits(32)(0xC), Bits(32)(0x00000193)),  # PC应该保持0xC
            (Bits(1)(1), Bits(32)(0), Bits(32)(0xC), Bits(32)(0x00000193)),  # PC应该保持0xC
            (Bits(1)(1), Bits(32)(0), Bits(32)(0xC), Bits(32)(0x00000193)),  # PC应该保持0xC
            
            # Case 2: Flush测试 (PC跳变)
            (Bits(1)(0), Bits(32)(0x1000), Bits(32)(0x1000), Bits(32)(0x00000013)),  # PC跳变到0x1000
            (Bits(1)(0), Bits(32)(0), Bits(32)(0x1004), Bits(32)(0x00000093)),  # PC继续递增
            (Bits(1)(0), Bits(32)(0), Bits(32)(0x1008), Bits(32)(0x00000113)),  # PC继续递增
            
            # Case 3: Stall后恢复正常
            (Bits(1)(0), Bits(32)(0), Bits(32)(0x100C), Bits(32)(0x00000193)),  # PC继续递增
            (Bits(1)(1), Bits(32)(0), Bits(32)(0x100C), Bits(32)(0x00000193)),  # PC保持0x100C
            (Bits(1)(0), Bits(32)(0), Bits(32)(0x1010), Bits(32)(0x00000213)),  # PC继续递增
            
            # Case 4: Flush时Stall (Flush优先级更高)
            (Bits(1)(1), Bits(32)(0x2000), Bits(32)(0x2000), Bits(32)(0x00000013)),  # PC跳变到0x2000，忽略Stall
            (Bits(1)(0), Bits(32)(0), Bits(32)(0x2004), Bits(32)(0x00000093)),  # PC继续递增
        ]

        # --- 激励生成逻辑 ---
        # 1. 计数器：跟踪当前测试进度
        cnt = RegArray(UInt(32), 1)
        (cnt & self)[0] <= cnt[0] + UInt(32)(1)

        idx = cnt[0]

        # 2. 组合逻辑 Mux：根据 idx 选择当前的测试向量
        # 初始化默认值
        current_stall = Bits(1)(0)
        current_branch_target = Bits(32)(0)
        current_expected_pc = Bits(32)(0)
        current_expected_inst = Bits(32)(0)

        # 这里的循环展开会生成一棵 Mux 树
        for i, (stall, branch_target, expected_pc, expected_inst) in enumerate(vectors):
            is_match = idx == UInt(32)(i)

            current_stall = is_match.select(stall, current_stall)
            current_branch_target = is_match.select(branch_target, current_branch_target)
            current_expected_pc = is_match.select(expected_pc, current_expected_pc)
            current_expected_inst = is_match.select(expected_inst, current_expected_inst)

        # 3. 设置控制信号
        stall_if[0] = current_stall
        branch_target[0] = current_branch_target

        # 4. 初始化SRAM数据
        # 根据PC地址预置一些指令数据
        with Condition(idx == UInt(32)(0)):
            icache.build(we=Bits(1)(1), re=Bits(1)(0), addr=Bits(32)(0x0), wdata=Bits(32)(0x00000013))
            icache.build(we=Bits(1)(1), re=Bits(1)(0), addr=Bits(32)(0x4), wdata=Bits(32)(0x00000093))
            icache.build(we=Bits(1)(1), re=Bits(1)(0), addr=Bits(32)(0x8), wdata=Bits(32)(0x00000113))
            icache.build(we=Bits(1)(1), re=Bits(1)(0), addr=Bits(32)(0xC), wdata=Bits(32)(0x00000193))
            icache.build(we=Bits(1)(1), re=Bits(1)(0), addr=Bits(32)(0x1000), wdata=Bits(32)(0x00000013))
            icache.build(we=Bits(1)(1), re=Bits(1)(0), addr=Bits(32)(0x1004), wdata=Bits(32)(0x00000093))
            icache.build(we=Bits(1)(1), re=Bits(1)(0), addr=Bits(32)(0x1008), wdata=Bits(32)(0x00000113))
            icache.build(we=Bits(1)(1), re=Bits(1)(0), addr=Bits(32)(0x100C), wdata=Bits(32)(0x00000193))
            icache.build(we=Bits(1)(1), re=Bits(1)(0), addr=Bits(32)(0x1010), wdata=Bits(32)(0x00000213))
            icache.build(we=Bits(1)(1), re=Bits(1)(0), addr=Bits(32)(0x2000), wdata=Bits(32)(0x00000013))
            icache.build(we=Bits(1)(1), re=Bits(1)(0), addr=Bits(32)(0x2004), wdata=Bits(32)(0x00000093))

        # 5. 打印 Driver 发出的请求，方便对比调试
        with Condition(idx < UInt(32)(len(vectors))):
            log(
                "Driver: idx={} stall={} branch_target=0x{:x} expected_pc=0x{:x} expected_inst=0x{:x}",
                idx,
                current_stall,
                current_branch_target,
                current_expected_pc,
                current_expected_inst,
            )

        # [关键] 返回 cnt 和预期结果，让它们成为模块的输出
        return cnt, current_expected_pc, current_expected_inst


# ==============================================================================
# 2. Sink 模块定义：用于接收IF模块的输出
# ==============================================================================
class Sink(Module):
    def __init__(self):
        super().__init__(ports={})

    @module.combinational
    def build(self, dut: Module, icache: SRAM):
        # 创建控制信号
        stall_if = RegArray(Bits(1), 1)
        branch_target = RegArray(Bits(32), 1)
        
        # 初始化为默认值
        stall_if[0] <= Bits(1)(0)
        branch_target[0] <= Bits(32)(0)
        
        # 调用DUT的build方法
        pc_reg = dut.build()
        
        # 创建FetcherImpl并调用其build方法
        fetcher_impl = FetcherImpl()
        fetcher_impl.build(
            pc_reg=pc_reg,
            icache=icache,
            decoder=self,  # 使用Sink作为decoder的Mock
            stall_if=stall_if,
            branch_target=branch_target
        )
        
        # 返回DUT的输出
        return pc_reg, stall_if, branch_target


# ==============================================================================
# 3. 验证逻辑 (Python Check)
# ==============================================================================
def check(raw_output):
    print(">>> 开始验证IF模块输出...")

    # 预期结果列表 (必须与Driver中的vectors严格对应)
    expected_pcs = [
        0x00000000,  # Case 0: 正常取指
        0x00000004,
        0x00000008,
        0x0000000C,
        0x0000000C,  # Case 1: Stall测试
        0x0000000C,
        0x0000000C,
        0x00001000,  # Case 2: Flush测试
        0x00001004,
        0x00001008,
        0x0000100C,  # Case 3: Stall后恢复正常
        0x0000100C,
        0x00001010,
        0x00002000,  # Case 4: Flush时Stall
        0x00002004,
    ]

    expected_insts = [
        0x00000013,  # Case 0: 正常取指
        0x00000093,
        0x00000113,
        0x00000193,
        0x00000193,  # Case 1: Stall测试
        0x00000193,
        0x00000193,
        0x00000013,  # Case 2: Flush测试
        0x00000093,
        0x00000113,
        0x00000193,  # Case 3: Stall后恢复正常
        0x00000193,
        0x00000213,
        0x00000013,  # Case 4: Flush时Stall
        0x00000093,
    ]

    # 捕获实际的PC和指令值
    actual_pcs = []
    actual_insts = []

    for line in raw_output.split("\n"):
        # 捕获PC和指令值
        if "IF: PC=" in line:
            # 示例行: "IF: PC=0x00000000 Inst=0x00000013 Stall=0 Flush=0"
            pc_match = re.search(r"PC=(0x[0-9a-fA-F]+)", line)
            inst_match = re.search(r"Inst=(0x[0-9a-fA-F]+)", line)
            
            if pc_match and inst_match:
                pc = int(pc_match.group(1), 16)
                inst = int(inst_match.group(1), 16)
                actual_pcs.append(pc)
                actual_insts.append(inst)
                print(f"  [捕获] PC=0x{pc:08x} Inst=0x{inst:08x}")

    # --- 断言比对 ---

    # 1. PC值数量检查
    if len(actual_pcs) != len(expected_pcs):
        print(f"❌ 错误：预期PC值 {len(expected_pcs)} 个，实际捕获 {len(actual_pcs)} 个")
        assert False

    # 2. PC值内容检查
    for i, (exp_pc, act_pc) in enumerate(zip(expected_pcs, actual_pcs)):
        if exp_pc != act_pc:
            print(f"❌ 错误：第 {i} 个PC值不匹配")
            print(f"  预期: 0x{exp_pc:08x}")
            print(f"  实际: 0x{act_pc:08x}")
            assert False

    # 3. 指令值数量检查
    if len(actual_insts) != len(expected_insts):
        print(f"❌ 错误：预期指令值 {len(expected_insts)} 个，实际捕获 {len(actual_insts)} 个")
        assert False

    # 4. 指令值内容检查
    for i, (exp_inst, act_inst) in enumerate(zip(expected_insts, actual_insts)):
        if exp_inst != act_inst:
            print(f"❌ 错误：第 {i} 个指令值不匹配")
            print(f"  预期: 0x{exp_inst:08x}")
            print(f"  实际: 0x{act_inst:08x}")
            assert False

    print("✅ IF模块测试通过！(所有PC递增、Stall和Flush功能均正确)")


# ==============================================================================
# 4. 主执行入口
# ==============================================================================
if __name__ == "__main__":
    sys = SysBuilder("test_fetch_module")

    with sys:
        # 创建测试模块
        fetcher = Fetcher()
        # 创建SRAM作为ICache
        icache = SRAM(width=32, depth=1024, init_file="")
        driver = Driver()
        sink = Sink()

        # 创建控制信号
        stall_if = RegArray(Bits(1), 1)
        branch_target = RegArray(Bits(32), 1)

        # [关键] 获取 Driver 的返回值
        driver_cnt, driver_expected_pc, driver_expected_inst = driver.build(
            fetcher, icache, stall_if, branch_target
        )

        # 获取 Sink 的返回值
        pc_reg, stall_if_out, branch_target_out = sink.build(fetcher, icache)
        
        # [关键] 暴露 Driver 的计数器，防止被 DCE 优化掉
        sys.expose_on_top(driver_cnt, kind="Output")
        sys.expose_on_top(driver_expected_pc, kind="Output")
        sys.expose_on_top(driver_expected_inst, kind="Output")

        # 暴露其他信号
        sys.expose_on_top(pc_reg, kind="Output")
        sys.expose_on_top(stall_if_out, kind="Output")
        sys.expose_on_top(branch_target_out, kind="Output")

    run_test_module(sys, check)