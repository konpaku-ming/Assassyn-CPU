import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from assassyn.frontend import *
from tests.common import run_test_module
from src.fetch import Fetcher, FetcherImpl


# --- Driver ---
class Driver(Module):
    def __init__(self):
        super().__init__(ports={})

    @module.combinational
    def build(self, branch_target: Array, dut: Module):
        # 向量: (stall, target)
        vectors = [
            (0, 0),  # Cyc 0: 正常 (Fetch 0)
            (0, 0),  # Cyc 1: 正常 (Fetch 4)
            (1, 0),  # Cyc 2: Stall (Fetch 4, 且 Hold)
            (1, 0),  # Cyc 3: Stall (Fetch 4) -> 重复！
            (0, 0),  # Cyc 4: 恢复 (Fetch 0x8)
            (0, 0x1000),  # Cyc 5: 正常 (Fetch 0xc)
            (0, 0),  # Cyc 6: Flush (Fetch 0x1000)
            (1, 0x2000),  # Cyc 7: Stall (Fetch 0x1000)
            (1, 0),  # Cyc 8: Flush (Fetch 0x2000)
        ]

        cnt = RegArray(UInt(32), 1, initializer=[0])
        (cnt & self)[0] <= cnt[0] + UInt(32)(1)
        idx = cnt[0]

        s, t = Bits(1)(0), Bits(32)(0)

        for i, v in enumerate(vectors):
            is_match = idx == UInt(32)(i)
            s = is_match.select(Bits(1)(v[0]), s)
            t = is_match.select(Bits(32)(v[1]), t)

        valid_test = idx < UInt(32)(len(vectors))
        with Condition(valid_test):
            call = dut.async_called()

        test_end_cycle = UInt(32)(len(vectors) + 2)

        with Condition(idx >= test_end_cycle):
            log("Driver: All vectors applied. Finishing simulation.")
            finish()

        # 驱动全局寄存器
        branch_target[0] = t

        return s


# --- Sink ---
class MockDecoder(Module):
    def __init__(self):
        super().__init__(ports={"pc": Port(Bits(32)), "next_pc": Port(Bits(32)), "stall": Port(Bits(1))})

    @module.combinational
    def build(self):
        # 模拟 ID 级接收 (Always Pop)
        # 注意：即使是重复的 PC，这里也会打印出来
        pc, next_pc, stall = self.pop_all_ports(False)
        log("DEC: Recv PC=0x{:x}", pc)
        return pc


# --- Check ---
def check(output):
    print(">>> Verifying Fetch Logic...")
    captured = []
    for line in output.split("\n"):
        if "DEC: Recv PC=" in line:
            pc = int(line.split("=")[-1], 16)
            captured.append(pc)

    expected = [
        0x0,
        0x4,
        0x4,  # Stall 开始前一拍
        0x4,  # Stall 期间重复收到 0x8
        0x8,  # 恢复后
        0xc,  # 一周期延迟
        0x1000,
        0x1000,
        0x2000,
        0x2004,
        0x2008,
    ]

    print(f"Captured Sequence: {[hex(x) for x in captured]}")
    print(f"Expected Sequence: {[hex(x) for x in expected]}")

    # 3. 长度检查
    # 如果捕获的长度小于预期，说明仿真过早结束或逻辑没跑通
    if len(captured) < len(expected):
        print(f"❌ Error: Insufficient data captured.")
        print(f"   Expected {len(expected)} items, got {len(captured)}.")
        assert False, "Captured sequence too short"

    # 4. [核心] 逐项遍历比对
    mismatch_found = False
    for i, exp_val in enumerate(expected):
        act_val = captured[i]
        
        if act_val != exp_val:
            print(f"❌ Mismatch at index {i} (Cycle ~{i}):")
            print(f"   Expected: 0x{exp_val:x}")
            print(f"   Actual:   0x{act_val:x}")
            
            # 简单的错误原因推断
            if exp_val == 0x4 and act_val == 0x8:
                print("   -> Possible Cause: Stall failed, PC incremented.")
            elif exp_val == 0x1000 and act_val != 0x1000:
                print("   -> Possible Cause: Flush failed or delayed.")
                
            mismatch_found = True
            # 我们找到第一个错误就停止，或者你可以选择继续打印所有错误
            break 
    
    if mismatch_found:
        assert False, "Sequence mismatch detected"

    # 5. 关键特征点验证 (保留你的原有断言作为双重保险)
    assert 0x0 in captured, "Reset Vector Missed"
    
    # 验证 Stall 行为: 检查是否有重复元素
    # 如果预期里有重复的 0x4，我们验证实际抓取中 0x4 的数量
    cnt_4 = captured.count(0x4)
    if cnt_4 < 2:
        print(f"❌ Stall Check Failed: 0x4 appeared only {cnt_4} times, expected >= 2")
        assert False, "Stall Behavior Missed"

    # 验证 Flush 行为
    if 0x1000 not in captured:
        print("❌ Flush Check Failed: Target 0x1000 never appeared")
        assert False, "Flush Jump Missed"

    print("✅ IF Logic Passed:")
    print("  - Sequence matched exactly.")
    print("  - Stall verified (Repeated PC).")
    print("  - Flush verified (Target Jump).")


# --- Top ---
if __name__ == "__main__":
    sys = SysBuilder("test_fetch")
    with sys:
        fetcher = Fetcher()
        decoder = MockDecoder()
        driver = Driver()

        # 全局控制信号
        br_target = RegArray(Bits(32), 1)
        pc_reg, pc_addr, last_pc_reg = fetcher.build()
        pc = decoder.build()
        stall_wire = driver.build(br_target, fetcher)

        impl = FetcherImpl()
        impl.build(
            pc_reg=pc_reg,
            pc_addr=pc_addr,
            last_pc_reg=last_pc_reg,
            decoder=decoder,
            stall_if=stall_wire,
            branch_target=br_target,
        )

    run_test_module(sys, check)
