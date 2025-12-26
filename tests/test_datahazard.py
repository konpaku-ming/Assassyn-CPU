import sys
import os

# 1. 环境路径设置 (确保能 import src)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from assassyn.frontend import *
from assassyn.backend import elaborate
from assassyn import utils

# 导入你的设计
from src.data_hazard import DataHazardUnit
from src.control_signals import *
from tests.common import run_test_module


# ==============================================================================
# 1. Driver 模块定义：前三行不能改，这是Assassyn的约定。
# ==============================================================================
class Driver(Module):
    def __init__(self):
        super().__init__(ports={})

    @module.combinational
    # [修改] build 函数返回 cnt，使其成为 Output Wire
    def build(self, dut: Module, hazard_impl: Module):
        # --- Test vector definition ---
        # Format: [0]rs1_idx [1]rs2_idx [2]rs1_used [3]rs2_used [4]ex_rd 
        #         [5]ex_is_load [6]ex_mul_busy [7]mem_rd [8]wb_rd
        # Note: [6]ex_mul_busy is NEW parameter added for MUL stall implementation
        vectors = [
            # Test case 1: No hazard
            (0x2, 0x3, 1, 1, 0x4, 0, 0, 0x7, 0xA),
            # Test case 2: EX stage bypass (rs2)
            (0x2, 0x4, 1, 1, 0x4, 0, 0, 0x7, 0xA),
            # Test case 3: MEM stage bypass (rs2)
            (0x2, 0x7, 1, 1, 0x4, 0, 0, 0x7, 0xA),
            # Test case 4: WB stage bypass (rs2)
            (0x2, 0xA, 1, 1, 0x4, 0, 0, 0x7, 0xA),
            # Test case 5: Load-Use hazard (must stall)
            (0x2, 0x4, 1, 1, 0x4, 1, 0, 0x7, 0xA),
            # Test case 6: Zero register (should not cause hazard)
            (0x0, 0x2, 1, 1, 0x0, 0, 0, 0x7, 0xA),
            # Test case 7: MUL busy (must stall)
            (0x2, 0x3, 1, 1, 0x4, 0, 1, 0x7, 0xA),
        ]

        # --- 激励生成逻辑 ---
        # 1. 计数器：跟踪当前测试进度
        cnt = RegArray(UInt(32), 1)
        (cnt & self)[0] <= cnt[0] + UInt(32)(1)

        idx = cnt[0]

        # 2. 组合逻辑 Mux：根据 idx 选择当前的测试向量
        # 初始化默认值
        rs1_idx = Bits(5)(0)
        rs2_idx = Bits(5)(0)
        rs1_used = Bits(1)(0)
        rs2_used = Bits(1)(0)
        ex_rd = Bits(5)(0)
        ex_is_load = Bits(1)(0)
        ex_mul_busy = Bits(1)(0)
        mem_rd = Bits(5)(0)
        wb_rd = Bits(5)(0)

        # 这里的循环展开会生成一棵 Mux 树
        for i, (r1, r2, u1, u2, ex, ex_load, ex_mul, mem, wb) in enumerate(vectors):
            is_match = idx == UInt(32)(i)
            rs1_idx = is_match.select(Bits(5)(r1), rs1_idx)
            rs2_idx = is_match.select(Bits(5)(r2), rs2_idx)
            rs1_used = is_match.select(Bits(1)(u1), rs1_used)
            rs2_used = is_match.select(Bits(1)(u2), rs2_used)
            ex_rd = is_match.select(Bits(5)(ex), ex_rd)
            ex_is_load = is_match.select(Bits(1)(ex_load), ex_is_load)
            ex_mul_busy = is_match.select(Bits(1)(ex_mul), ex_mul_busy)
            mem_rd = is_match.select(Bits(5)(mem), mem_rd)
            wb_rd = is_match.select(Bits(5)(wb), wb_rd)

        # 4. 发送数据
        # 只有当 idx 在向量范围内时才发送 (valid)
        valid_test = idx < UInt(32)(len(vectors))

        with Condition(valid_test):
            # 打印 Driver 发出的请求，方便对比调试
            log(
                "Driver: Case {} rs1=x{} rs2=x{} ex_rd=x{} ex_is_load={} ex_mul_busy={} mem_rd=x{} wb_rd=x{}",
                idx,
                rs1_idx,
                rs2_idx,
                ex_rd,
                ex_is_load,
                ex_mul_busy,
                mem_rd,
                wb_rd,
            )

            # 建立连接 (async_called)
            call = dut.async_called(
                rs1_idx=rs1_idx,
                rs2_idx=rs2_idx,
                rs1_used=rs1_used,
                rs2_used=rs2_used,
                ex_rd=ex_rd,
                ex_is_load=ex_is_load,
                ex_mul_busy=ex_mul_busy,
                mem_rd=mem_rd,
                wb_rd=wb_rd,
            )
            call.bind.set_fifo_depth(
                rs1_idx=1,
                rs2_idx=1,
                rs1_used=1,
                rs2_used=1,
                ex_rd=1,
                ex_is_load=1,
                ex_mul_busy=1,
                mem_rd=1,
                wb_rd=1,
            )  # 设置 FIFO 深度，防止阻塞

        # [关键] 返回 cnt，让它成为模块的输出
        return cnt


# ==============================================================================
# DataHazardUnit模块定义
# ==============================================================================
class DataHazardUnitWrapper(Module):
    def __init__(self):
        super().__init__(
            ports={
                "rs1_idx": Port(Bits(5)),
                "rs2_idx": Port(Bits(5)),
                "rs1_used": Port(Bits(1)),
                "rs2_used": Port(Bits(1)),
                "ex_rd": Port(Bits(5)),
                "ex_is_load": Port(Bits(1)),
                "ex_mul_busy": Port(Bits(1)),
                "mem_rd": Port(Bits(5)),
                "wb_rd": Port(Bits(5)),
            }
        )

    @module.combinational
    def build(self):
        # 消费端口数据
        rs1_idx, rs2_idx, rs1_used, rs2_used, ex_rd, ex_is_load, ex_mul_busy, mem_rd, wb_rd = (
            self.pop_all_ports(False)
        )

        # 返回结果
        return rs1_idx, rs2_idx, rs1_used, rs2_used, ex_rd, ex_is_load, ex_mul_busy, mem_rd, wb_rd


# ==============================================================================
# 2. 验证逻辑 (Python Check)
# ==============================================================================
def check(raw_output):
    print(">>> 开始验证 DataHazardUnit 日志...")

    # 预期结果映射表 (Case ID -> (rs1_sel, rs2_sel, stall))
    # 注意：这里的预期值必须跟上面修改后的 vectors 对应
    # Sel: 1=REG, 2=EX, 4=MEM, 8=WB
    expected_map = {
        0: (1, 1, 0),  # No Hazard
        1: (1, 2, 0),  # EX Fwd (rs2)
        2: (1, 4, 0),  # MEM Fwd (rs2)
        3: (1, 8, 0),  # WB Fwd (rs2)
        4: (1, 1, 1),  # Load-Use hazard -> Stall
        5: (1, 1, 0),  # Zero register (no hazard)
        6: (1, 1, 1),  # MUL busy -> Stall
    }

    captured_data = {}
    
    dhu_output_index = 0

    print("--- Log Analysis ---")
    for line in raw_output.split("\n"):
        # 我们只关心 DHU 的输出行
        if "DataHazardUnit:" in line and "rs1_sel=" in line:
            try:

                def get_val(k):
                    return int(line.split(k + "=")[1].split()[0])

                rs1 = get_val("rs1_sel")
                rs2 = get_val("rs2_sel")
                stall = get_val("stall_if")

                # [核心逻辑]: 第 N 条输出直接对应 Case N
                # 假设第一条有效的 DHU 输出对应 Case 0
                case_id = dhu_output_index

                captured_data[case_id] = (rs1, rs2, stall)
                print(f"  [Captured Case {case_id}] rs1={rs1} rs2={rs2} stall={stall}")

                dhu_output_index += 1

            except Exception as e:
                print(f"⚠️ Parse Error: {line}")

    # --- 验证比对 ---
    print(f"--- Verification (Captured {len(captured_data)} cases) ---")
    all_pass = True

    # 只验证我们定义了期望的 Case
    for cid, exp in expected_map.items():
        if cid not in captured_data:
            print(f"❌ Case {cid} Missing")
            all_pass = False
            continue

        act = captured_data[cid]

        # 比对逻辑
        if act != exp:
            # 允许 Stall 时 sel 的差异 (硬件可能会输出默认值)
            # 如果 stall 匹配(都为1)，忽略 sel 差异
            if exp[2] == 1 and act[2] == 1:
                pass
            else:
                print(f"❌ Case {cid} Failed. Exp:{exp} Act:{act}")
                all_pass = False

    if all_pass:
        print("✅ DataHazardUnit Verified")
    else:
        # 抛出异常让测试框架捕获
        raise AssertionError("Verification Failed")


# ==============================================================================
# 3. 主执行入口
# ==============================================================================
if __name__ == "__main__":
    sys = SysBuilder("test_datahazard")

    with sys:
        # 实例化DataHazardUnit
        hazard_impl = DataHazardUnit()

        # 实例化DataHazardUnitWrapper
        hazard_wrapper = DataHazardUnitWrapper()

        # 实例化Driver
        driver = Driver()

        # [关键] 获取 Driver 的返回值 (cnt)
        driver_cnt = driver.build(hazard_wrapper, hazard_impl)

        # 获取 DUT 的返回值 (rs1_sel, rs2_sel, stall_if)
        rs1_idx, rs2_idx, rs1_used, rs2_used, ex_rd, ex_is_load, ex_mul_busy, mem_rd, wb_rd = (
            hazard_wrapper.build()
        )

        hazard_impl.build(
            rs1_idx=rs1_idx,
            rs2_idx=rs2_idx,
            rs1_used=rs1_used,
            rs2_used=rs2_used,
            ex_rd=ex_rd,
            ex_is_load=ex_is_load,
            ex_mul_busy=ex_mul_busy,
            mem_rd=mem_rd,
            wb_rd=wb_rd,
        )

    run_test_module(sys, check)
