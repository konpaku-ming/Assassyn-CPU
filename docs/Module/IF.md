# RV32I IF (Instruction Fetch) 模块设计文档

> **依赖**：Assassyn, SRAM, Downstream 机制

## 1. 模块概述

IF 模块负责 CPU 的第一级流水线工作：维护程序计数器（PC），并向指令存储器（SRAM/ICache）发起读请求。

为了解决 **反馈环路（Feedback Loop）** 带来的构建依赖问题（即 IF 依赖 ID/EX 的 Stall/Flush 信号，而 ID/EX 又依赖 IF 的数据），我们将设计拆分为两部分：
*   **`Fetcher` (Module)**：状态容器。持有 PC 寄存器，定义对外接口。
*   **`FetcherImpl` (Downstream)**：逻辑内核。实现 PC 的更新逻辑、SRAM 驱动逻辑和流控逻辑。

## 2. 接口定义

### 2.1 Fetcher (Module) —— 状态持有者

```python
class Fetcher(Module):
    def __init__(self):
        super().__init__(
            ports={}, # Fetcher 是起点，通常不需要被别人 async_called
            no_arbiter=True
        )
        self.name = 'F'

    @module.combinational
    def build(self):
        # 1. PC 寄存器
        # 初始化为 0 (Reset Vector)
        pc_reg = RegArray(Bits(32), 1, initializer=[0])
        
        # 暴露寄存器引用供 Impl 使用
        return pc_reg
```

### 2.2 FetcherImpl (Downstream) —— 逻辑实现者

`FetcherImpl` 需要在顶层构建的最后阶段调用，此时所有的反馈信号都已就绪。

```python
class FetcherImpl(Downstream):
    @downstream.combinational
    def build(self,
        # --- 资源引用 ---
        pc_reg: Array,        # 引用 Fetcher 的 PC
        icache: SRAM,         # 引用 ICache
        decoder: Module,      # 下一级模块 (用于发送指令)

        # --- 反馈控制信号 (来自 DataHazardUnit/ControlHazardUnit) ---
        stall_if: Value,      # 暂停取指 (保持当前 PC)
        branch_target: Array, # 不为0时，根据目标地址冲刷流水线
    ):
    pass # 实现见下文
```

---

## 3. 内部逻辑实现

IF 阶段的逻辑核心是一个 **三级优先级多路选择器 (Priority Mux Tree)**。

**优先级**：**Flush (最高)** > **Stall** > **Normal (最低)**

### 3.0 通用行为：取出当前 PC_reg 中值

`now_pc = pc_reg[0]`

### 3.1 状态 1：Flush (冲刷/跳转)
*   **触发条件**：`branch_target != 0`（来自 EX 级的 `branch` 信息）。
*   **SRAM 行为**：`now_pc = branch_target`，使用 `now_pc` 驱动SRAM。
    *   为了让 ID 级在下一拍能拿到正确的跳转目标指令，我们必须在当前拍就改变 SRAM 地址。
*   **PC 行为**：`next_pc = now_pc`。

### 3.2 状态 2：Stall (暂停)
*   **触发条件**：`stall_if == 1`（通常来自 ID 级的 Load-Use 冒险）。
*   **SRAM 行为**：直接用 `now_pc` 驱动 SRAM ，保持上一周期pc。
    *   ID 级因为 Stall 正在重试读取 SRAM 的输出。
*   **PC 行为**：`next_pc = now_pc` (保持不变)。

### 3.3 状态 3：Normal (正常)
*   **触发条件**：无 Flush 且无 Stall。
*   **SRAM 行为**：直接用 `now_pc + 4` 驱动 SRAM。
*   **PC 行为**：`next_PC = now_pc + 4`。

### 3.4 通用行为：写回

`next_pc` 计算完成后，写回 `pc_reg[0]`。

---

## 4. 逻辑代码映射

```python
    # 读取当前 PC
    current_pc = pc_reg[0]
    
    # --- 1. 计算 Next PC (时序逻辑输入) ---
    # 默认：PC + 4
    pc_next_normal = current_pc + 4
    
    # 处理 Stall：保持原值
    pc_next_stall = stall_if.select(current_pc, pc_next_normal)
    
    # 处理 Flush：跳转目标 (优先级最高，覆盖 Stall)
    final_next_pc = flush_if.select(target_pc, pc_next_stall)
    
    # 更新 PC 寄存器
    pc_reg[0] <= final_next_pc

    # --- 2. 驱动 SRAM (组合逻辑输出) ---
    # 决定给 SRAM 喂什么地址
    # 如果 Flush，为了让下一拍 ID 能拿到新指令，必须立刻喂 Target
    # 如果 Stall，必须喂 Current 稳住输出
    # 如果 Normal，喂 Current (读取当前指令)
    # 综上：只有 Flush 时喂 Target，否则喂 Current
    sram_addr = flush_if.select(target_pc, current_pc)
    
    icache.build(we=0, re=1, addr=sram_addr, ...)

    # --- 3. 驱动下游 Decoder (流控) --- 
    # 如果 Flush，这里要把 pc 替换为 0
    decoder.async_called(pc=final_next_pc)
```