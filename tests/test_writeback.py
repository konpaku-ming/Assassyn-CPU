import sys
import os

# 1. 环境路径设置 (确保能 import src)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from assassyn.frontend import *
from assassyn.backend import elaborate
from assassyn import utils

# 导入你的设计
from src.writeback import WriteBack
from tests.common import run_test_module


# ==============================================================================
# 1. Driver 模块定义：前三行不能改，这是Assassyn的约定。
# ==============================================================================
class Driver(Module):
    def __init__(self):
        super().__init__(ports={})

    @module.combinational
    # [修改] build 函数返回 cnt，使其成为 Output Wire
    def build(self, dut: Module):
        # --- 测试向量定义 ---
        # 格式: (rd_addr, wdata)
        vectors = [
            (1, 0x11111111),  # Case 0: 正常写 x1
            (5, 0x55555555),  # Case 1: 正常写 x5
            (0, 0xDEADBEEF),  # Case 2: 写 x0 (应该被忽略)
            (10, 0xAAAAAAAA),  # Case 3: 正常写 x10
            (0, 0x00000000),  # Case 4: NOP (rd=0, data=0)
            (31, 0xFFFFFFFF),  # Case 5: 边界测试 x31
        ]

        # --- 激励生成逻辑 ---
        # 1. 计数器：跟踪当前测试进度
        cnt = RegArray(UInt(32), 1)
        (cnt & self)[0] <= cnt[0] + UInt(32)(1)
        
        idx = cnt[0]

        # 2. 组合逻辑 Mux：根据 idx 选择当前的 rd 和 data
        # 初始化默认值
        current_rd = Bits(5)(0)
        current_data = Bits(32)(0)

        # 这里的循环展开会生成一棵 Mux 树
        for i, (rd, data) in enumerate(vectors):
            is_match = idx == UInt(32)(i)
            current_rd = is_match.select(Bits(5)(rd), current_rd)
            current_data = is_match.select(Bits(32)(data), current_data)
        ctrl_pkt = current_rd

        # 4. 发送数据
        # 只有当 idx 在向量范围内时才发送 (valid)
        valid_test = idx < UInt(32)(len(vectors))

        with Condition(valid_test):
            # 打印 Driver 发出的请求，方便对比调试
            log("Driver: Sending rd=x{} val=0x{:x}", current_rd, current_data)

            # 建立连接 (async_called)
            call = dut.async_called(ctrl=ctrl_pkt, wdata=current_data)
            call.bind.set_fifo_depth(ctrl=1, wdata=1)  # 设置 FIFO 深度，防止阻塞

        # [关键] 返回 cnt，让它成为模块的输出
        return cnt


# ==============================================================================
# 2. 验证逻辑 (Python Check)
# ==============================================================================
def check(raw_output):
    print(">>> 开始验证日志...")

    # 预期发生的写入操作 (过滤掉 rd=0 的 case)
    expected_writes = [
        (1, 0x11111111),
        (5, 0x55555555),
        # Case 2 (x0) 不应出现
        (10, 0xAAAAAAAA),
        # Case 4 (x0) 不应出现
        (31, 0xFFFFFFFF),
    ]

    # 实际捕捉到的写入操作
    captured_writes = []

    for line in raw_output.split("\n"):
        # 假设 WriteBack 模块里的 log 格式是: "WB: Write x{rd} <= 0x{data}"
        if "WB: Write" in line:
            # 简单解析字符串
            # 示例行: "[100] WB: Write x5 <= 0x55555555"
            parts = line.split()
            # 找到 x... 部分
            for part in parts:
                if part.startswith("x") and part[1:].isdigit():
                    rd = int(part[1:])
                if part.startswith("0x"):
                    data = int(part, 16)

            captured_writes.append((rd, data))
            print(f"  [捕获] x{rd} <= 0x{data:08x}")

    # --- 断言比对 ---

    # 1. 数量检查
    if len(captured_writes) != len(expected_writes):
        print(
            f"❌ 错误：预期写入 {len(expected_writes)} 次，实际写入 {len(captured_writes)} 次"
        )
        print("  可能是 x0 的写入没有被屏蔽，或者有效写入丢失。")
        assert False

    # 2. 内容检查
    for i, (exp_rd, exp_data) in enumerate(expected_writes):
        act_rd, act_data = captured_writes[i]

        if act_rd != exp_rd or act_data != exp_data:
            print(f"❌ 错误：第 {i} 次写入不匹配")
            print(f"  预期: x{exp_rd} <= 0x{exp_data:x}")
            print(f"  实际: x{act_rd} <= 0x{act_data:x}")
            assert False

    print("✅ WriteBack 测试通过！(所有 x0 写入均被正确忽略)")


# ==============================================================================
# 3. 主执行入口
# ==============================================================================
if __name__ == "__main__":
    sys = SysBuilder("test_wb_module")

    with sys:
        reg_file = RegArray(Bits(32), 32)
        dut = WriteBack()
        driver = Driver()

        # [关键] 获取 Driver 的返回值 (cnt)
        driver_cnt = driver.build(dut)

        # 获取 DUT 的返回值 (rd)
        wb_rd = dut.build(reg_file)

        # [关键] 暴露 Driver 的计数器，防止被 DCE 优化掉
        sys.expose_on_top(driver_cnt, kind="Output")

        # 暴露 DUT 的输出
        sys.expose_on_top(reg_file, kind="Output")
        sys.expose_on_top(wb_rd, kind="Output")

    run_test_module(sys, check)
