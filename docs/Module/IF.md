# RV32I IF (Instruction Fetch) 模块设计文档

> **依赖**：Assassyn Framework, BTB, Tournament Predictor

## 1. 模块概述

IF 模块负责 CPU 的第一级流水线工作：维护程序计数器（PC），并向指令存储器（SRAM）发起读请求。该模块支持可选的 **分支预测**（BTB + Tournament Predictor），以减少分支惩罚。

为了解决 **反馈环路（Feedback Loop）** 带来的构建依赖问题（即 IF 依赖 ID/EX 的 Stall/Flush 信号，而 ID/EX 又依赖 IF 的数据），我们将设计拆分为两部分：
*   **`Fetcher` (Module)**：状态容器。持有 PC 寄存器，定义对外接口。
*   **`FetcherImpl` (Downstream)**：逻辑内核。实现 PC 的更新逻辑、分支预测逻辑和流控逻辑。

## 2. 接口定义

### 2.1 Fetcher (Module) —— 状态持有者

```python
class Fetcher(Module):
    def __init__(self):
        super().__init__(
            ports={}, no_arbiter=True  # Fetcher 是起点，通常不需要被别人 async_called
        )
        self.name = "Fetcher"

    @module.combinational
    def build(self):
        # 1. PC 寄存器
        # 初始化为 0 (Reset Vector)
        pc_reg = RegArray(Bits(32), 1, initializer=[0])
        # 用于驱动 FetcherImpl（Assassyn特性）
        pc_addr = pc_reg[0]
        # 记录上一个周期的PC，用于在 Stall 时稳住输入（Assassyn不允许"不输入"）
        last_pc_reg = RegArray(Bits(32), 1, initializer=[0])

        # 暴露寄存器引用供 Impl 使用
        return pc_reg, pc_addr, last_pc_reg
```

### 2.2 FetcherImpl (Downstream) —— 逻辑实现者

`FetcherImpl` 需要在顶层构建的最后阶段调用，此时所有的反馈信号都已就绪。

```python
class FetcherImpl(Downstream):
    def __init__(self):
        super().__init__()
        self.name = "Fetcher_Impl"

    @downstream.combinational
    def build(
        self,
        # --- 资源引用 ---
        pc_reg: Array,  # 引用 Fetcher 的 PC
        pc_addr: Bits(32),  # 引用 Fetcher 的 PC 地址
        last_pc_reg: Array,  # 引用 Fetcher 的 Last PC
        decoder: Module,  # 下一级模块 (用于发送指令)
        # --- 反馈控制信号 (来自 DataHazardUnit/ControlHazardReg) ---
        stall_if: Value,  # 暂停取指 (保持当前 PC)
        branch_target: Array,  # 不为0时，根据目标地址冲刷流水线
        # --- BTB 分支预测 (可选) ---
        btb_impl: "BTBImpl" = None,  # BTB 实现逻辑
        btb_valid: Array = None,  # BTB 有效位数组
        btb_tags: Array = None,  # BTB 标签数组
        btb_targets: Array = None,  # BTB 目标地址数组
        # --- Tournament Predictor (方向预测，可选) ---
        tp_impl: "TournamentPredictorImpl" = None,  # Tournament Predictor 实现逻辑
        tp_bimodal: Array = None,  # Bimodal 计数器数组
        tp_gshare: Array = None,  # Gshare 计数器数组
        tp_ghr: Array = None,  # 全局历史寄存器
        tp_selector: Array = None,  # 选择器计数器数组
    ):
        # 实现见下文
```

## 3. 内部逻辑实现

IF 阶段的逻辑核心是一个 **多路选择器**，根据 Stall、Flush 和分支预测信号选择不同的 PC 值。

### 3.1 PC 选择（基础逻辑）

首先根据 stall_if 信号选择当前 PC 值：
```python
current_stall_if = stall_if.optional(Bits(1)(0))
current_pc = current_stall_if.select(last_pc_reg[0], pc_addr)
```

然后根据 branch_target 判断是否需要 Flush：
```python
flush_if = branch_target[0] != Bits(32)(0)
target_pc = branch_target[0]
final_current_pc = flush_if.select(target_pc, current_pc)
```

### 3.2 分支预测逻辑

默认情况下，下一个 PC 为当前 PC + 4：
```python
default_next_pc = (final_current_pc.bitcast(UInt(32)) + UInt(32)(4)).bitcast(Bits(32))
```

**当启用 BTB 时**，使用 BTB 进行分支目标预测：
```python
btb_hit, btb_predicted_target = btb_impl.predict(
    pc=final_current_pc,
    btb_valid=btb_valid,
    btb_tags=btb_tags,
    btb_targets=btb_targets,
)
```

**当同时启用 Tournament Predictor 时**，使用 Tournament Predictor 决定是否跳转：
```python
tp_predict_taken = tp_impl.predict(
    pc=final_current_pc,
    bimodal_counters=tp_bimodal,
    gshare_counters=tp_gshare,
    global_history=tp_ghr,
    selector_counters=tp_selector,
)

# BTB 命中 + TP 预测跳转 → 使用 BTB 目标
# BTB 命中 + TP 预测不跳转 → PC + 4
# BTB 未命中 → PC + 4
predicted_next_pc = btb_hit.select(
    tp_predict_taken.select(btb_predicted_target, default_next_pc),
    default_next_pc,
)
```

### 3.3 PC 更新逻辑

更新寄存器：
```python
pc_reg[0] <= final_next_pc
last_pc_reg[0] <= final_current_pc
```

### 3.4 下游驱动

向 Decoder 发送当前 PC 值、预测的下一个 PC 值以及 Stall 信号：
```python
call = decoder.async_called(
    pc=final_current_pc,
    next_pc=final_next_pc,
    stall=current_stall_if,
)
call.bind.set_fifo_depth(pc=1)
```

### 3.5 返回值

返回当前 PC 值，供 SingleMemory 模块使用：
```python
return final_current_pc
```

## 4. 分支预测配置

CPU 支持通过 `enable_branch_prediction` 参数控制分支预测功能：

| 配置 | 行为 |
| :--- | :--- |
| `enable_branch_prediction=True` | 使用 BTB + Tournament Predictor 进行分支预测 |
| `enable_branch_prediction=False` | 默认 PC+4，不使用分支预测 |

关于分支预测的详细设计，请参阅 [BranchPrediction.md](./BranchPrediction.md)。