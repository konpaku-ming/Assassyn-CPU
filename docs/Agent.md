# 第一部分：Assassyn CPU 项目架构

### 1. 目录结构规范

```text
riscv_cpu/
├── docs/                 # 设计文档与语言说明
│   ├── Module/
│   │   ├── DataHazard.md
│   │   ├── ControlHazard.md
│   │   ├── ID.md
│   │   ├── EX.md
│   │   ├── IF.md
│   │   ├── MEM.md
│   │   └── WB.md
│   ├── Assassyn.md
│   └── Agent.md          # 致 AI Agent 的开发指导文档
│
├── src/                  # 源代码目录
│   ├── control_signals.py         # Decoder使用常量与控制包定义 (1)
│   ├── fetch.py          # IF 阶段 (3)
│   ├── decode.py         # ID 阶段 (1)
│   ├── DataHazardUnit.py # bypass 网络 (2)
│   ├── execute.py        # EX 阶段 (5)
│   ├── memory.py         # MEM 阶段 (6)
│   ├── writeback.py      # WB 阶段 (7)
│   └── top.py            # 顶层集成
├── tests/                # 测试代码目录
│   ├── common.py         # 通用测试工具 (Log解析, 这里的 Driver)
│   ├── test_fetch.py     # IF 单元测试
│   ├── test_decode.py    # ID 单元测试
│   ├── test_execute.py   # EX 单元测试
│   ├── ...
│   └── test_integration.py # 全系统测试 (跑 hex 文件)
└── workload/             # 测试程序二进制文件
```

(1)具体内容在 [ID设计文档](MyCPU/docs/Module/ID.md)
(2)具体内容在 [DataHazardUnit设计文档](MyCPU/docs/Module/DataHazard.md)
(3)具体内容在 [ControlHazardUnit设计文档](MyCPU/docs/Module/ControlHazard.md)
(4)具体内容在 [IF设计文档](MyCPU/docs/Module/IF.md)
(5)具体内容在 [EX设计文档](MyCPU/docs/Module/EX.md)
(6)具体内容在 [MEM设计文档](MyCPU/docs/Module/MEM.md)
(7)具体内容在 [WB设计文档](MyCPU/docs/Module/WB.md)

### 2. 通用测试驱动 (`tests/common.py`)

我们需要一个通用的 `TestDriver`，用于给被测模块（DUT）灌入数据。

```python
from assassyn.frontend import *
from assassyn.backend import elaborate
from assassyn import utils

# 通用仿真运行器
def run_test_module(sys_builder, check_func, cycles=100):
    print(f"🚀 Compiling system: {sys_builder.name}...")
    # 编译
    sim_path, _ = elaborate(sys_builder, verilog=False) # 仅生成二进制用于快速测试
    # 运行
    print(f"🏃 Running simulation ({cycles} cycles)...")
    raw_output = utils.run_simulator(sim_path, cycles=cycles)
    # 验证
    print("🔍 Verifying output...")
    try:
        check_func(raw_output)
        print(f"✅ {sys_builder.name} Passed!")
    except AssertionError as e:
        print(f"❌ {sys_builder.name} Failed: {e}")
        # print(raw_output) # 出错时打印完整日志

# 基础 Mock 模块：用于模拟上下游
class MockModule(Module):
    def __init__(self, ports):
        super().__init__(ports=ports)
    
    @module.combinational
    def build(self):
        # 简单地消耗掉所有输入，防止 FIFO 堵塞
        self.pop_all_ports(False)
```

# Agent 指导文档：Assassyn RV32I 五级流水线 CPU 实现指南

**角色定义**：你是一名精通 Python 元编程和计算机体系结构的硬件工程师。
**任务目标**：基于 `Assassyn` 框架，按照设计文档逐步实现一个 RV32I 处理器，并为每个阶段编写单元测试。任务需要的所有非 Apptainer 内容都在 MyCpu/ 文件夹下。特别注意：所有代码的执行、仿真与验证必须在 Apptainer 容器环境中进行。

## 0. 环境与容器配置 (Environment & Container)

本项目依赖 Apptainer 容器来提供统一的 Assassyn 运行时依赖。

1.  **容器镜像位置**：
    *   假设 `assassyn.sif` (容器镜像) 位于项目根目录或环境变量可访问的路径。
    *   如果镜像不存在，需在 Assassyn 根目录执行 `make build-apptainer` 生成。

2.  **路径挂载规则**：
    *   代码编写在宿主机（Host）进行。
    *   代码运行在容器（Container）内部。

## 1. 核心设计文档位置 (Context)

在进行代码编写前，请严格参考以下已确认的设计逻辑（Context）：
*   **IF 阶段**：关注 `Flush > Stall > Normal` 优先级。
*   **ID 阶段**：关注 `Record` 分层打包、`DataHazardUnit` 的真值回传机制、以及 `decoder_logic` 的查表实现。
*   **EX 阶段**：关注 `Main ALU` 和 `PC Adder` 的调度、以及 `Next_PC` 的预测验证。
*   **MEM 阶段**：关注 `pop_all_ports` 解包、SRAM 数据对齐逻辑。
*   **WB 阶段**：关注极简接口与 `x0` 写保护。

## 2. 目标代码写入地址 (File Structure)

所有代码必须严格写入以下路径：

*   **常量与接口**：
    *   `src/consts.py`: 存放 `ALUOp`, `Op1Sel` 等枚举常量。
    *   `src/control_signals.py`: 存放 `mem_ctrl_signals`, `ex_ctrl_signals`等 `Record` 定义。
*   **模块实现**：
    *   `src/fetch.py`: `Fetcher`, `FetcherImpl`
    *   `src/decode.py`: `Decoder`, `instructions_table`
    *   `src/DataHazardUnit.py`: `DataHazardUnit`
    *   `src/execute.py`: `Execution`
    *   `src/memory.py`: `MemoryAccess`
    *   `src/writeback.py`: `WriteBack`
*   **测试脚本**：
    *   `tests/test_{module_name}.py`: 对应模块的单元测试。

## 3. 如何使用测试平台 (Workflow)

对于每一个模块的开发，必须遵循 **“定义 -> 实现 -> 测试”** 的闭环：

### 第一步：实现模块
在 `src/` 下编写代码。确保使用 `from assassyn.frontend import *`。

### 第二步：编写单元测试
在 `tests/` 下创建一个测试脚本。
*   **Mock 上游**：创建一个 `Driver` 模块，构造特定的 `Record` 包并通过 `async_called` 发送给 DUT（被测模块）。
*   **Mock 下游**：创建一个 `Sink` 模块，接收 DUT 的输出。
*   **Check 函数**：编写 Python 函数解析 `log()` 输出，验证逻辑是否符合预期。

**测试模板示例 (以 EX 为例)：**
```python
# tests/test_execute.py
from src.execute import Execution
from tests.common import run_test_module

class ExDriver(Module):
    def build(self, dut):
        # 构造一个测试包 (ADD 指令)
        # 发送给 dut
        dut.async_called(packet=test_packet)

def check(output):
    # 检查日志中是否有 "ALU Result: 30"
    assert "ALU_Res: 30" in output

if __name__ == "__main__":
    sys = SysBuilder('test_ex')
    with sys:
        dut = Execution()
        driver = ExDriver()
        driver.build(dut)
        # ... 构建下游 Mock ...
    run_test_module(sys, check)
```

### 第三步：运行验证

**这是与传统开发最大的不同点。** 你不能直接使用 `python` 命令，必须通过 `apptainer` 包装器。

### 3.1 编写测试驱动 (`tests/common.py`)
代码编写逻辑不变，依然使用 `run_simulator`。Assassyn 库在容器内会自动调用容器内的 Verilator。

### 3.2 运行测试 (Execution Command)

当你需要运行测试脚本（例如 `tests/test_fetch.py`）时，请使用以下指令格式：

```bash
# 格式：apptainer exec --bind <宿主机代码目录> <镜像路径> python <脚本路径>

# 示例（假设在 riscv_cpu 根目录下运行）：
apptainer exec --bind $(pwd) /assassyn.sif python tests/test_fetch.py
```

*   **`--bind $(pwd)`**: 极其重要！这将当前目录挂载到容器内，确保 Python 能找到 `src` 和 `tests` 模块。
*   **验证标准**：如果终端输出了 Assassyn 的 Logo 和仿真日志（`log()` 内容），说明容器调用成功。

## 4. 分步开发路线图 (Roadmap)

请按以下顺序执行开发，**每完成一步，必须生成对应的测试代码并验证**。

### Phase 1: 基础设施 (Infrastructure)
1.  **定义常量 (`src/consts.py`)**：根据设计文档，定义 `ALUOp`, `Op1Sel`, `ImmType` 等。
2.  **定义接口 (`src/interfaces.py`)**：实现 `wb_ctrl_t` -> `mem_ctrl_t` -> `ex_ctrl_t` -> `decode_packet_t` 的嵌套 Record 结构。

### Phase 2: 取指与状态 (Fetch & Feedback)
1.  **实现 IF (`src/fetch.py`)**：编写 `Fetcher` 和 `FetcherImpl`。
2.  **测试 IF**：
    *   **Case 1**: 正常计数 (PC, PC+4, PC+8...)。
    *   **Case 2**: 模拟 Flush 信号，验证 PC 是否跳变。

### Phase 3: 译码与冒险 (Decode & Hazard)
1.  **实现 ID (`src/decode.py`)**：编写 `Decoder`，集成指令真值表和 Hazard Unit。
2.  **测试 ID**：
    *   **Case 1**: 输入 `ADD` 机器码，验证输出的控制包 (`alu_func`, `op_sel`) 是否正确。
    *   **Case 2**: 构造 RAW 冒险 (rs1 冲突)，验证 `stall` 信号是否生成。
3. **实现 Data Hazard Unit (`src/DataHazardUnit.py`)**：编写 `DataHazardUnit`，实现旁路逻辑。

### Phase 4: 执行 (Execute)
1.  **实现 EX (`src/execute.py`)**：编写 `Execution`，实现操作数 Mux、ALU、PC Adder 和 Forwarding Mux。
2.  **测试 EX**：
    *   **Case 1**: 算术运算 (`10 + 20 = 30`)。
    *   **Case 2**: Forwarding 测试 (模拟从 MEM/WB 旁路拿到数据)。
    *   **Case 3**: 分支测试 (模拟 `BEQ` Taken，验证 `flush` 信号)。

### Phase 5: 访存与写回 (Mem & WB)
1.  **实现 MEM (`src/memory.py`)**：实现数据对齐和 Mux。
2.  **实现 WB (`src/writeback.py`)**：实现寄存器写入。
3.  **测试 MEM/WB**：模拟 Load 数据路径，验证数据能否正确传递。

### Phase 6: 系统集成 (Top)
1.  **实现 Top (`src/top.py`)**：实例化所有模块，连接全局寄存器 (`branch_flush_reg`, `bypass_regs`) 和模块接口。
2.  **集成测试**：运行 `rv32ui-p-add` 等标准测试集。

---

**请确认你已理解上述设计约束与开发流程，再根据指令进行工作**