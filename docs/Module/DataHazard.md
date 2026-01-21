# DataHazardUnit 模块设计文档

> **依赖**：Assassyn Framework, `control_signals.py`

## 1. 模块概述

**DataHazardUnit** 是一个 **纯组合逻辑 (`Downstream`)** 模块。

*   **职责**：
    1.  **前瞻控制 (Forwarding Logic)**：检测 RAW 冒险，生成多路选择信号，控制 EX 阶段 ALU 的操作数来源。
    2.  **阻塞控制 (Stall Logic)**：检测 Load-Use 冒险、MUL/DIV 多周期占用、以及内存访问冲突，生成流水线停顿（Stall）信号。
*   **特性**：无内部状态（Stateless）。它依赖流水线各级"回传"的实时控制信号包作为真值来源。

## 2. 接口定义

### 2.1 输入接口

HazardUnit 需要两类信息：**"当前想要什么"** (ID级) 和 **"前面正在产出什么"** (EX/MEM/WB级)。

```python
class DataHazardUnit(Downstream):
    @downstream.combinational
    def build(
        self,
        # --- 1. 来自 ID 级 (当前指令需求) ---
        rs1_idx: Value,      # 源寄存器 1 索引
        rs2_idx: Value,      # 源寄存器 2 索引
        rs1_used: Value = None,  # 是否需要读取 rs1 (避免虚假冒险)
        rs2_used: Value = None,  # 是否需要读取 rs2

        # --- 2. 来自流水线各级 (实时状态回传) ---
        ex_rd: Value = None,         # EX 级目标寄存器索引
        ex_is_load: Value = None,    # EX 级是否为 Load 指令
        ex_is_store: Value = None,   # EX 级是否为 Store 指令
        ex_mul_busy: Value = None,   # EX 级乘法器忙状态
        ex_div_busy: Value = None,   # EX 级除法器忙状态
        mem_rd: Value = None,        # MEM 级目标寄存器索引
        mem_is_store: Value = None,  # MEM 级是否为 Store 指令
        wb_rd: Value = None,         # WB 级目标寄存器索引
    ):
```

### 2.2 输出接口

输出分为两类：给 EX 级的数据选择信号，和给 IF/ID 级的流控信号。

*   **Forwarding Selectors** (4-bit 独热码):
    *   `rs1_sel`: rs1 操作数来源选择
    *   `rs2_sel`: rs2 操作数来源选择
    *   编码：`RS1(0001)` / `EX_BYPASS(0010)` / `MEM_BYPASS(0100)` / `WB_BYPASS(1000)`

*   **Pipeline Controls** (1-bit):
    *   `stall_if`: 冻结 Fetcher 与 Decoder

## 3. 时空映射

假设当前是 **Cycle T**：
*   **ID 级**：指令 `Inst_Current`
*   **EX 级**：指令 `Inst_N-1`
*   **MEM 级**：指令 `Inst_N-2`
*   **WB 级**：指令 `Inst_N-3`

当 `Inst_Current` 到达 EX 级时（**Cycle T+1**）：
*   `Inst_N-1` 将到达 MEM 级 → 要从 `ex_bypass_reg` 读取其结果
*   `Inst_N-2` 将到达 WB 级 → 要从 `mem_bypass_reg` 读取其结果
*   `Inst_N-3` 将退休 → 要从 `wb_bypass_reg` 读取其结果

## 4. 内部实现

### 4.1 Stall 条件检测

```python
# 1. Load-Use 冒险 (必须 Stall)
# 当前指令需要的源寄存器与 EX 级的 Load 指令的目标寄存器相同
load_use_hazard_rs1 = rs1_used_val & ~rs1_is_zero & ex_is_load_val & (rs1_idx_val == ex_rd_val)
load_use_hazard_rs2 = rs2_used_val & ~rs2_is_zero & ex_is_load_val & (rs2_idx_val == ex_rd_val)

# 2. MUL 多周期占用 - 乘法器未完成时阻塞流水线
mul_busy_hazard = ex_mul_busy_val

# 3. DIV 多周期占用 - 除法器未完成时阻塞流水线
div_busy_hazard = ex_div_busy_val

# 4. 综合所有 Stall 条件
stall_if = (
    load_use_hazard_rs1 | load_use_hazard_rs2 |
    mul_busy_hazard | div_busy_hazard |
    ex_is_store_val | mem_is_store_val | ex_is_load_val
)
```

### 4.2 Forwarding 逻辑

如果没有 Stall，我们生成选择码 `rs1_sel` 与 `rs2_sel`：

```python
# EX 结果未就绪的情况：Load/MUL busy/DIV busy
ex_result_not_ready = ex_is_load_val | ex_mul_busy_val | ex_div_busy_val

# rs1 旁路选择 (优先级：EX > MEM > WB > RegFile)
rs1_wb_pass = (rs1_idx_val == wb_rd_val).select(Rs1Sel.WB_BYPASS, Rs1Sel.RS1)
rs1_mem_bypass = (rs1_idx_val == mem_rd_val).select(Rs1Sel.MEM_BYPASS, rs1_wb_pass)
rs1_ex_bypass = ((rs1_idx_val == ex_rd_val) & ~ex_result_not_ready).select(
    Rs1Sel.EX_BYPASS, rs1_mem_bypass
)
rs1_sel = (rs1_used_val & ~rs1_is_zero).select(rs1_ex_bypass, Rs1Sel.RS1)

# rs2 旁路选择 (同样的优先级逻辑)
rs2_wb_pass = (rs2_idx_val == wb_rd_val).select(Rs2Sel.WB_BYPASS, Rs2Sel.RS2)
rs2_mem_bypass = (rs2_idx_val == mem_rd_val).select(Rs2Sel.MEM_BYPASS, rs2_wb_pass)
rs2_ex_bypass = ((rs2_idx_val == ex_rd_val) & ~ex_result_not_ready).select(
    Rs2Sel.EX_BYPASS, rs2_mem_bypass
)
rs2_sel = (rs2_used_val & ~rs2_is_zero).select(rs2_ex_bypass, Rs2Sel.RS2)
```

## 5. Stall 条件汇总

| 条件 | 原因 | 周期数 |
| :--- | :--- | :--- |
| Load-Use | Load 数据在 MEM 阶段才可用 | 1 |
| MUL busy | 乘法器正在执行多周期乘法 | 3 |
| DIV busy | 除法器正在执行多周期除法 | ~10 |
| EX Store | 等待 Store 的 RMW 完成 | 1 |
| MEM Store | 等待 Store 的 RMW 完成 | 1 |
| EX Load | 等待 Load 的内存访问 | 1 |

## 6. x0 寄存器处理

为避免对 x0 寄存器的虚假冒险检测，HazardUnit 会检查源寄存器是否为 x0：

```python
rs1_is_zero = rs1_idx_val == Bits(5)(0)
rs2_is_zero = rs2_idx_val == Bits(5)(0)

# 只有非 x0 寄存器才参与冒险检测
rs1_sel = (rs1_used_val & ~rs1_is_zero).select(rs1_ex_bypass, Rs1Sel.RS1)
```

这确保了即使指令的 rs1/rs2 字段编码为 0，也不会触发不必要的 Stall 或 Forwarding。
