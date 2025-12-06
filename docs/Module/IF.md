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
        self.name = "F"

    @module.combinational
    def build(self):
        # 1. PC 寄存器
        # 初始化为 0 (Reset Vector)
        pc_reg = RegArray(Bits(32), 1, initializer=[0])
        # 记录上一个周期的PC，用于在 Stall 时稳住输入（Assassyn不允许"不输入"）
        last_pc_reg = RegArray(Bits(32), 1, initializer=[0])

        # 暴露寄存器引用供 Impl 使用
        return pc_reg, last_pc_reg
```

### 2.2 FetcherImpl (Downstream) —— 逻辑实现者

`FetcherImpl` 需要在顶层构建的最后阶段调用，此时所有的反馈信号都已就绪。

```python
class FetcherImpl(Downstream):
    def __init__(self):
        super().__init__()
        self.name = "F1"

    @downstream.combinational
    def build(
        self,
        # --- 资源引用 ---
        pc_reg: Array,  # 引用 Fetcher 的 PC
        last_pc_reg: Array,  # 引用 Fetcher 的 Last PC
        icache: SRAM,  # 引用 ICache
        decoder: Module,  # 下一级模块 (用于发送指令)
        # --- 反馈控制信号 (来自 DataHazardUnit/ControlHazardUnit) ---
        stall_if: Bits(1),  # 暂停取指 (保持当前 PC)
        branch_target: Array,  # 不为0时，根据目标地址冲刷流水线
    ):
    # 实现见下文
```


## 3. 内部逻辑实现

IF 阶段的逻辑核心是一个 **多路选择器**，根据 Stall 和 Flush 信号选择不同的 PC 值。

### 3.0 通用行为：PC 选择

首先根据 stall_if 信号选择当前 PC 值：
```python
current_pc = stall_if.select(last_pc_reg[0], pc_reg[0])
```

然后根据 branch_target 判断是否需要 Flush：
```python
flush_if = branch_target[0] != Bits(32)(0)
target_pc = branch_target[0]
final_current_pc = flush_if.select(target_pc, current_pc)
```

### 3.1 SRAM 驱动逻辑

SRAM 地址由 final_current_pc 右移 2 位得到（字节地址转换为字地址）：
```python
sram_addr = (final_current_pc) >> UInt(32)(2)
icache.build(we=Bits(1)(0), re=Bits(1)(1), addr=sram_addr, wdata=Bits(32)(0))
```

### 3.2 PC 更新逻辑

下一周期的 PC 值为当前 PC 加 4：
```python
final_next_pc = final_current_pc + UInt(32)(4)
```

更新寄存器：
```python
pc_reg[0] <= final_next_pc
last_pc_reg[0] <= final_current_pc
```

### 3.3 下游驱动

向 Decoder 发送当前 PC 值：
```python
call = decoder.async_called(pc=final_current_pc)
call.bind.set_fifo_depth(pc=1)
```