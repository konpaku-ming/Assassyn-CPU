import sys
import os
import io
import contextlib
import warnings

# --- 环境设置 ---
# 尝试导入 assassyn。
# 如果你是在教程仓库结构中运行，可能需要保留 sys.path.append 设置
# 这里保留了路径添加逻辑以防万一
try:
    lib_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../python/'))
    if os.path.exists(lib_path):
        sys.path.append(lib_path)
except NameError:
    # 如果在某些非文件上下文中运行（如交互式终端），忽略路径添加
    pass

try:
    from assassyn.frontend import *
    from assassyn.backend import elaborate
    from assassyn import utils
except ImportError as e:
    print("❌ 错误: 无法导入 'assassyn' 库。")
    print("请确保已安装该库，或将 assassin/python 目录添加到 PYTHONPATH 中。")
    print(f"详细错误: {e}")
    sys.exit(1)

warnings.filterwarnings("ignore")

# --- 辅助函数 (替代 function_t.run_quietly) ---
def run_quietly(func):
    """
    执行函数并捕获标准输出，防止编译日志刷屏。
    返回: (函数返回值, 捕获的stdout字符串, 捕获的stderr字符串)
    """
    f = io.StringIO()
    # 这里简单地将 stdout 重定向，assassyn 的部分底层日志可能写在 stderr，视具体实现而定
    with contextlib.redirect_stdout(f):
        ret = func()
    return ret, f.getvalue(), ""

# --- 2.1 验证逻辑 (check) ---
def check(raw):
    expected = 0
    cnt_found = False
    
    # 遍历输出行
    lines = raw.split('\n')
    for i in lines:
        if 'cnt:' in i:
            cnt_found = True
            try:
                val = int(i.split()[-1])
                assert val == expected, f"预期值 {expected}，实际值 {val}"
                expected += 1
            except (ValueError, IndexError):
                continue
    
    if not cnt_found:
        print("⚠️ 警告: 输出中未找到 'cnt:' 日志，无法验证计数逻辑。")
        return

    # 默认仿真通常运行 100 个周期
    assert expected == 100, f"预期运行 100 个周期，实际运行了 {expected} 个周期"
    print(f"✅ 验证通过！计数器按预期工作：从 0 计数到 {expected-1}")

# --- 2.2 硬件模块定义 (Driver) ---
class Driver(Module):
    def __init__(self):
        super().__init__(ports={})

    @module.combinational
    def build(self):
        # 创建一个 32 位宽，深度为 1 的寄存器数组
        cnt = RegArray(UInt(32), 1)

        # 组合逻辑：计算当前值 + 1
        v = cnt[0] + UInt(32)(1)
        
        # 时序逻辑：下一个时钟沿更新寄存器
        (cnt & self)[0] <= v

        # 仿真打印
        log('cnt: {}', cnt[0])

# --- 3. 主执行函数 ---
def main():
    print("🚀 开始构建和仿真...")

    # 1. 构建系统
    # SysBuilder 创建系统上下文
    sys_builder = SysBuilder('driver')
    with sys_builder:
        driver = Driver()
        driver.build()
    
    print("系统结构已构建。")

    # 2. 生成仿真器 (Elaboration)
    def generate_simulator():
        # 检测是否安装了 Verilator
        has_verilator = utils.has_verilator()
        return elaborate(sys_builder, verilog=has_verilator)

    print("正在生成仿真模型 (Compile)...")
    (simulator_path, verilator_path), _, _ = run_quietly(generate_simulator)
    print(f"✅ 仿真器生成完成。路径: {simulator_path}")

    # 3. 运行 Python/RTL 仿真器
    def run_sim():
        # 默认运行 100 cycle
        return utils.run_simulator(simulator_path)

    print("正在运行仿真...")
    raw, _, _ = run_quietly(run_sim)

    print("\n=== 模拟器输出 (前10行) ===")
    lines = raw.split('\n')
    for line in lines:
        if 'cnt:' in line:
            print(line.strip())
            if int(line.split()[-1]) >= 9: # 只打印到 9 避免刷屏
                print("... (省略后续输出)")
                break

    # 验证输出
    print("\n>>> 开始验证 Python 仿真结果:")
    check(raw)

    # 4. 运行 Verilator 验证 (如果可用)
    if verilator_path:
        print("\n=== Verilator 验证 ===")

        def run_verilator():
            return utils.run_verilator(verilator_path)
        
        print("正在运行 Verilator...")
        raw_verilator, _, _ = run_quietly(run_verilator)

        # 显示 Verilator 的部分输出
        for line in raw_verilator.split('\n'):
            if 'cnt:' in line:
                # 简单展示前几个
                if int(line.split()[-1]) < 3:
                    print(f"[Verilator] {line.strip()}")
                elif int(line.split()[-1]) == 3:
                    print("[Verilator] ...")

        # 验证 Verilator 的输出
        print("\n>>> 开始验证 Verilator 结果:")
        check(raw_verilator)
    else:
        print("\n⚠️ Verilator 未安装或未找到，跳过 Verilator 验证环节。")

if __name__ == "__main__":
    main()