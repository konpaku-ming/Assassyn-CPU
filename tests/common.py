from assassyn.frontend import *
from assassyn.backend import elaborate, config
from assassyn import utils
from assassyn.frontend import SRAM

def run_test_module(sys_builder, check_func):
    print(f"🚀 Compiling system: {sys_builder.name}...")

    # 1. 配置
    print(sys_builder)
    cfg = config(verilog=False, sim_threshold=600000, idle_threshold=600000)

    # 2. 生成源码
    simulator_path, verilog_path = elaborate(sys_builder, **cfg)

    # 3. 编译二进制
    try:
        # build_simulator 内部会调用 cargo build，它的输出我们暂时不管
        # 只要最后 binary_path 存在就行
        binary_path = utils.build_simulator(simulator_path)
        print(f"🔨 Building binary from: {binary_path}")
    except Exception as e:
        print(f"❌ Simulator build failed: {e}")
        raise e

    print(f"🏃 Running simulation (Direct Output Mode)...")
    # 4. 运行模拟器，捕获输出
    raw = utils.run_simulator(binary_path=binary_path)

    print(raw)
    print("🔍 Verifying output...")

    try:
        check_func(raw)
        print(f"✅ {sys_builder.name} Passed!")
    except AssertionError as e:
        print(f"❌ {sys_builder.name} Failed: {e}")
        raise e


def create_initialized_sram(width, depth, init_file=None):
    """
    创建并初始化一个 SRAM 实例
    
    参数:
        width: SRAM 的位宽 (例如: 32)
        depth: SRAM 的深度 (例如: 1024)
        init_file: 初始化文件路径 (可选)
    
    返回:
        初始化好的 SRAM 实例
    """
    
    if init_file:
        sram = SRAM(width=width, depth=depth, init_file=init_file)
    else:
        sram = SRAM(width=width, depth=depth)
    
    return sram
