# DataHazardUnit 模块设计方案

## 1. 模块概述

**DataHazardUnit** 是一个 **纯组合逻辑 (`Downstream`)** 模块。

*   **职责**：
    1.  **前瞻控制 (Forwarding Logic)**：检测 RAW 冒险，生成多路选择信号，控制 EX 阶段 ALU 的操作数来源。
    2.  **阻塞控制 (Stall Logic)**：检测 Load-Use 冒险，生成流水线停顿（Stall）和气泡（Flush）信号。
*   **特性**：无内部状态（Stateless）。它依赖流水线各级“回传”的实时控制信号包作为真值来源。

## 2. 接口定义

### 2.1 输入接口 (Inputs)

HazardUnit 需要两类信息：**“当前想要什么”** (ID级) 和 **“前面正在产出什么”** (EX/MEM/WB级)。

```python
class DataHazardUnit(Downstream):
    @downstream.combinational
    def build(self,
        # --- 1. 来自 ID 级 (当前指令需求) ---
        rs1_idx: Bits(5),    # 源寄存器 1 索引 (Bits 5)
        rs2_idx: Bits(5),    # 源寄存器 2 索引 (Bits 5)
        rs1_used: Bits(1),   # 是否需要读取 rs1 (Bits 1) - 避免 LUI 等指令的虚假冒险
        rs2_used: Bits(1),   # 是否需要读取 rs2 (Bits 1)

        # --- 2. 来自流水线各级 (实时状态回传) ---
        # 各级 Module build() 的返回值
        ex_rd:Bits(5),     # EX 级控制包
        ex_is_load:Bits(1),  # EX 级是否为 Load 指令
        mem_rd:Bits(5),      # MEM 级目标寄存器索引
        wb_rd:Bits(5),    # WB 级目标寄存器索引
    ):
    pass
```

### 2.2 输出接口 (Outputs)

输出分为两类：给 EX 级的数据选择信号，和给 IF/ID 级的流控信号。

*   **Forwarding Selectors** (4-bit):
    *   `rs1_op1`: 操作数 1 选择码
    *   `rs2_op2`: 操作数 2 选择码
    *   *编码定义*: 见`control_signals.py`

*   **Pipeline Controls** (1-bit):
    *   `stall_if`: 冻结 Fetcher 与 Decoder。

## 3. DataHazardUnit 内部实现

### 3.1 时空映射：ID 站在“现在”预测“未来”

假设当前是 **Cycle T**。
*   **ID 级**：指令 `Inst_Current`。
*   **EX 级**：指令 `Inst_N-1`。
*   **MEM 级**：指令 `Inst_N-2`。
*   **WB 级**：指令 `Inst_N-3`。

当 `Inst_Current` 到达 EX 级时（**Cycle T+1**）：
*   `Inst_N-1` 将到达 MEM 级 -> 要从 `ex_bypass_reg` 读取其结果。
*   `Inst_N-2` 将到达 WB 级 -> 要从 `mem_bypass_reg` 读取其结果。
*   `Inst_N-3` 将退休 -> 要从 `wb_bypass_reg` 读取其结果。

### 3.2 build() 逻辑

基于上述映射，`DataHazardUnit` 的决策逻辑如下：

#### 3.2.1 检测 Load-Use (必须 Stall)
这是唯一需要暂停的情况。
*   **条件**：`rs1_idx == ex_rd` **且** `ex_is_load`。
*   **原因**：`Inst_N-1` 是 Load。在 Cycle T+1，它在 MEM 级刚开始读 SRAM，数据还没出来。EX 级的 `mem_forward_data` 线拿不到数据。
*   **动作**：`stall_if = 1`。

#### 3.2.2 检测 Forwarding (生成 Mux 选择码)
如果没有 Stall，我们生成选择码 `rs1_sel` 与 `rs2_sel`。

以`rs1_sel` 为例，生成逻辑如下：

1.  **优先级 1**：`rs1_idx == ex_rd` (且不是 Load)
    *   **动作**：`rs1_sel = Bits(4)(0010)`

2.  **优先级 2**：`rs1_idx == mem_rd`
    *   **动作**：`rs1_sel = Bits(4)(0100)`

3.  **优先级 3**：`rs1_idx == wb_rd`
    *   **动作**：`rs1_sel = Bits(4)(1000)`

如果都没有匹配，则 `rs1_sel = Bits(4)(0001)`。