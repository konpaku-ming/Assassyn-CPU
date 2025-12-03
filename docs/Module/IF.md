这是一份关于 **IF (取指) 阶段** 的详细设计文档。

这份设计完全遵循了我们之前确立的 **“模块分离（Module/Impl）”**、**“刚性流水线（Rigid Pipeline）”** 以及 **“优先级多路选择（Priority Mux）”** 的设计原则。

---

# RV32I IF (Instruction Fetch) 模块设计文档

> **版本**：1.0
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

        # --- 反馈控制信号 (来自 ControlHazardUnit / DataHazardUnit) ---
        stall_if: Value,      # 1: 暂停取指 (保持当前 PC)
        flush_if: Value,      # 1: 冲刷流水线 (分支预测错误/跳转)
        target_pc: Value      # 跳转的目标地址
    ):
        pass # 实现见下文
```

---

## 3. 内部逻辑实现

IF 阶段的逻辑核心是一个 **三级优先级多路选择器 (Priority Mux Tree)**。

**优先级**：**Flush (最高)** > **Stall** > **Normal (最低)**

### 3.1 状态 1：Flush (冲刷/跳转)
*   **触发条件**：`flush_if == 1`（通常来自 EX 级的 `branch_taken` 或 ID 级的 `jal`）。
*   **PC 行为**：`Next_PC = target_pc`。
    *   *纠正*：你提到将 PC 置为 `Ins+4`，这是不准确的。如果跳转到 `T`，PC 下一拍必须变成 `T`，这样才能在下一拍取到 `T` 处的指令。`T+4` 是下下拍的事。
*   **SRAM 行为**：立即驱动 `Addr = target_pc`。
    *   为了让 ID 级在下一拍能拿到正确的跳转目标指令，我们必须在当前拍就改变 SRAM 地址。
*   **FIFO 行为**：发送 **气泡 (NOP)**。
    *   因为当前 IF 取出的指令（PC+4）是错误路径上的，不能发给 ID。

### 3.2 状态 2：Stall (暂停)
*   **触发条件**：`stall_if == 1`（通常来自 ID 级的 Load-Use 冒险或 FIFO 满）。
*   **PC 行为**：`Next_PC = Current_PC` (保持不变)。
*   **SRAM 行为**：**保持驱动** `Addr = Current_PC`。
    *   *关键*：ID 级因为 Stall 正在重试读取 SRAM 的输出。如果 IF 级切断了地址或改了地址，SRAM 的输出就会变，导致 ID 级读错。必须稳住地址线！
*   **FIFO 行为**：**不发送** (Valid=0) 或发送气泡。

### 3.3 状态 3：Normal (正常)
*   **触发条件**：无 Flush 且无 Stall。
*   **PC 行为**：`Next_PC = Current_PC + 4`。
*   **SRAM 行为**：驱动 `Addr = Current_PC`。
    *   注意：这里有个微妙的时序。SRAM 读的是 `Current_PC` 的指令。PC 寄存器更新为 `Current+4` 是为了下一拍读下一条。
*   **FIFO 行为**：发送 **有效指令**。

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
    # 构造数据包
    packet = decode_packet_t.bundle(
        pc=current_pc,
        # ... 其他信号
        valid_inst=Bits(1)(1) # 默认有效
    )
    
    # 决定是否发送
    # 如果 Stall，不发送 (Assassyn 侧 valid=0)
    # 如果 Flush，发送 NOP (Assassyn 侧 valid=1, 但包内业务 flag=0) 
    # 或者直接都不发送，让 ID 级自己去处理气泡
    
    # 采用刚性流水线策略：
    # Stall 时：什么都不做 (不调用 async_called)
    # Flush 时：发送气泡 (NOP)
    
    with Condition(~stall_if):
        # 只有不 Stall 时才推数据
        # 如果 Flush，这里要把 packet 替换为 NOP 包
        real_packet = flush_if.select(NOP_PACKET, packet)
        decoder.async_called(packet=real_packet)
```

---

## 5. 极端情况分析：Flush 与 Stall 同时出现

你问：*“最差劲的情况，是 Flush 与 Stall 信号同时出现。为什么能够出现这个情况？”*

**场景复现：**
1.  **ID 级**：正在处理一条 `LW` 指令，并检测到了 Load-Use 冒险（针对 EX 级）。于是发出 `Stall_IF`。
2.  **EX 级**：正在处理一条 `BEQ` 指令（分支），并且判断**预测失败**，需要跳转。于是发出 `Flush_IF`。

**判定原则：Flush 拥有绝对优先权。**

*   **原因**：
    *   Stall 是为了“保住”当前流水线里的指令，让它正确执行。
    *   Flush 意味着当前流水线里的指令（包括 ID 级那个正在喊 Stall 的 `LW`）都是**错误路径上的废指令**。
    *   既然是废指令，就没有“保住”的必要了。直接杀掉，跳转到新地址。

**硬件行为**：
在 `final_next_pc` 的 Mux 树中，`flush_if` 处于最外层（最后选择），它会无视 `stall_if` 的值，强行将 PC 修改为 `target_pc`，并打破死锁。

**结论**：
你的设计中不需要特殊处理这个“冲突”，只需要确保 **Mux 的优先级顺序是 Flush > Stall** 即可。逻辑会自动处理一切。