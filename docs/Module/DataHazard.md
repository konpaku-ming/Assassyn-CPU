这是一份基于 **“真值回传（Truth-based Feedback）”** 和 **“刚性流水线（Rigid Pipeline）”** 思想的 DataHazardUnit 设计方案。

该方案完全抛弃了独立的记分牌寄存器，转而利用 Assassyn 的 `Record` 结构，从流水线各级直接引出当前的控制信号进行决策，实现了逻辑的高度解耦与无状态化。

---

# DataHazardUnit 模块设计方案

## 1. 模块概述

**DataHazardUnit** 是一个 **纯组合逻辑 (`Downstream`)** 模块。它是流水线的“交通指挥官”。

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
        rs1_idx: Value,      # 源寄存器 1 索引 (Bits 5)
        rs2_idx: Value,      # 源寄存器 2 索引 (Bits 5)
        rs1_used: Value,     # 是否需要读取 rs1 (Bits 1) - 避免 LUI 等指令的虚假冒险
        rs2_used: Value,     # 是否需要读取 rs2 (Bits 1)

        # --- 2. 来自流水线各级 (实时状态回传) ---
        # 这些是各级 Module build() 的返回值 (Record 类型)
        ex_ctrl: Value,      # EX 级控制包 (ex_ctrl_t)
        mem_ctrl: Value,     # MEM 级控制包 (mem_ctrl_t)
        wb_ctrl: Value       # WB 级控制包 (wb_ctrl_t)
    ):
        pass
```

### 2.2 输出接口 (Outputs)

输出分为两类：给 EX 级的数据选择信号，和给 IF/ID 级的流控信号。

*   **Forwarding Selectors** (2-bit):
    *   `fwd_op1_sel`: 操作数 1 选择码
    *   `fwd_op2_sel`: 操作数 2 选择码
    *   *编码定义*: `00`: RegFile, `01`: EX_Bypass, `10`: MEM_Bypass, `11`: WB_Bypass

*   **Pipeline Controls** (1-bit):
    *   `stall_if`: 冻结 Fetcher。
    *   `stall_id`: 冻结 Decoder。
    *   `flush_ex`: 向 Execution 发送 NOP (气泡)。

---

## 3. 内部逻辑实现

### 3.1 状态解析 (Unpacking)

首先从输入的复杂 Record 包中提取出与冒险相关的关键位。**注意必须处理 Valid 标志，防止由气泡引发错误的 Forwarding。**

```python
# 提取 EX 级信息
# 必须确保 ex_ctrl 对应的指令是有效的 (非 NOP)
# 这通常由 ex_ctrl 内部的 reg_we=0 (针对 NOP) 保证
ex_rd = ex_ctrl.mem_ctrl.wb_ctrl.rd_addr
ex_reg_we = ex_ctrl.mem_ctrl.wb_ctrl.rf_wen
ex_is_load = ex_ctrl.mem_ctrl.is_load

# 提取 MEM 级信息
mem_rd = mem_ctrl.wb_ctrl.rd_addr
mem_reg_we = mem_ctrl.wb_ctrl.rf_wen

# 提取 WB 级信息
wb_rd = wb_ctrl.rd_addr
wb_reg_we = wb_ctrl.rf_wen
```

### 3.2 前瞻逻辑 (Forwarding Logic)

遵循 **“最近优先 (Most Recent)”** 原则：EX > MEM > WB。

```python
def check_forward(src_idx, src_used):
    # 默认选择 RegFile (00)
    sel = Bits(2)(0b00)
    
    if src_used:
        # 优先级 3: WB 级 (最远)
        with Condition(wb_reg_we & (wb_rd == src_idx) & (wb_rd != 0)):
            sel = Bits(2)(0b11)
            
        # 优先级 2: MEM 级
        with Condition(mem_reg_we & (mem_rd == src_idx) & (mem_rd != 0)):
            sel = Bits(2)(0b10)
            
        # 优先级 1: EX 级 (最近，最高优先级)
        # 注意：这里只负责检测地址匹配，不管是不是 Load (Load-Use 由 Stall 逻辑处理)
        with Condition(ex_reg_we & (ex_rd == src_idx) & (ex_rd != 0)):
            sel = Bits(2)(0b01)
            
    return sel

fwd_op1_sel = check_forward(rs1_idx, rs1_used)
fwd_op2_sel = check_forward(rs2_idx, rs2_used)
```

### 3.3 阻塞逻辑 (Load-Use Hazard Detection)

检测条件：EX 阶段是 Load 指令，且其目标寄存器 (`ex_rd`) 与 ID 阶段当前指令的源寄存器 (`rs1` 或 `rs2`) 冲突。

```python
# 检查是否与 rs1 冲突
hazard_rs1 = rs1_used & (rs1_idx == ex_rd) & (ex_rd != 0)
# 检查是否与 rs2 冲突
hazard_rs2 = rs2_used & (rs2_idx == ex_rd) & (ex_rd != 0)

# 如果冲突源是 Load 指令，则必须 Stall
is_load_use = ex_is_load & (hazard_rs1 | hazard_rs2)

stall_if = is_load_use
stall_id = is_load_use
flush_ex = is_load_use
```

---

## 4. 系统集成 (Integration Strategy)

在 `main.py` 的 `build_cpu` 顶层函数中，体现了 **回环反馈 (Feedback Loop)** 的连线结构。

```python
# 1. 实例化 HazardUnit
hazard_unit = DataHazardUnit()

# 2. 获取流水线各级的 "真值" (返回值)
# 假设各级 build 函数都返回了当前的 Control Record
ex_ret_ctrl = executor.build(...) 
mem_ret_ctrl = memory.build(...)
wb_ret_ctrl = writeback.build(...)

# 3. 驱动 HazardUnit
# 注意：Decoder 尚未 build 完成，我们需要先进行部分实例化或参数准备
# 实际上，hazard_unit 的调用通常嵌套在 Decoder 内部，
# 或者在顶层通过 wire 传递给 Decoder。
# 推荐方式：将 ex_ret, mem_ret, wb_ret 传给 Decoder，Decoder 内部调用 HazardUnit。
```

**更正的集成代码结构 (在 Decoder 内部调用)**：

```python
class Decoder(Module):
    def build(self, executor, hazard_unit, 
              ex_status, mem_status, wb_status, ...): # 传入回传信号
        
        # ... 1. 纯组合逻辑解码 ...
        rs1, rs2, ... = decode_raw(...)

        # ... 2. 调用 Hazard Unit ...
        stall_if, stall_id, flush_ex, fwd_op1, fwd_op2 = hazard_unit.build(
            rs1_idx=rs1, 
            ex_ctrl=ex_status, 
            mem_ctrl=mem_status,
            ...
        )

        # ... 3. 处理 Stall 与 NOP ...
        # 如果 stall_id 为真，不 pop FIFO
        wait_until(~stall_id) 
        
        # 如果 flush_ex 为真，或者 stall_id 为真，发送 NOP 包给 EX
        packet_to_send = (flush_ex | stall_id).select(NOP_PACKET, real_packet)
        
        # 将 Forwarding 信号打包进 packet 发给 EX
        packet_to_send.ctrl.fwd_op1 = fwd_op1
        packet_to_send.ctrl.fwd_op2 = fwd_op2
        
        executor.async_called(packet=packet_to_send)
```

## 5. 设计总结

1.  **架构**：采用了 **集中式冒险控制 (Centralized Hazard Unit)**。
2.  **状态源**：**无状态 (Stateless)**。直接利用流水线上的信号线作为状态真值，避免了维护影子寄存器可能带来的同步问题。
3.  **流控**：**刚性流控 (Rigid Flow Control)**。利用 `wait_until` 实现本级保持，利用 Mux + NOP Packet 实现下级气泡注入。
4.  **Bypass**：在 ID 级计算出 Forwarding 信号，随流水线包传递给 EX 级。EX 级只需执行简单的 Mux 选择，极大地缩短了 EX 级的关键路径。