# Assassyn CPU 架构教程：从零开始理解硬件实现

> 本文档面向硬件新手，详细介绍本项目中 RISC-V RV32IM CPU 的实现原理，以及如何使用 Assassyn 语言描述硬件。

## 目录

1. [CPU 基础概念](#1-cpu-基础概念)
2. [五级流水线架构](#2-五级流水线架构)
3. [各部件详解](#3-各部件详解)
4. [组合逻辑与时序逻辑](#4-组合逻辑与时序逻辑)
5. [Assassyn 语言与硬件描述](#5-assassyn-语言与硬件描述)
6. [部件间通信机制](#6-部件间通信机制)
7. [完整代码示例解析](#7-完整代码示例解析)

---

## 1. CPU 基础概念

### 1.1 什么是 CPU？

CPU（Central Processing Unit，中央处理器）是计算机的"大脑"，负责执行程序指令。一个简单的 CPU 工作流程如下：

```
取指令 → 译码 → 执行 → 访存 → 写回
```

每个步骤称为一个"阶段"（Stage），本项目实现的是经典的**五级流水线**架构。

### 1.2 RISC-V 指令集

本项目实现的是 **RISC-V RV32IM** 指令集：
- **RV32**: 32 位地址空间和寄存器宽度
- **I**: 基础整数指令（加减法、逻辑运算、分支跳转等）
- **M**: 乘除法扩展（MUL、DIV、REM 等）

RISC-V 是一种**精简指令集**（RISC），特点是：
- 固定长度指令（32 位）
- 加载-存储架构（只有 Load/Store 指令访问内存）
- 32 个通用寄存器（x0-x31，其中 x0 恒为 0）

### 1.3 流水线的概念

想象一个洗衣店的工作流程：

| 时间 | 洗衣机 | 烘干机 | 折叠台 |
|------|--------|--------|--------|
| T1   | 衣服A  | -      | -      |
| T2   | 衣服B  | 衣服A  | -      |
| T3   | 衣服C  | 衣服B  | 衣服A  |
| T4   | 衣服D  | 衣服C  | 衣服B  |

**流水线**就是让多条指令同时处于不同的执行阶段，从而提高吞吐量。

**不使用流水线**：每条指令需要 5 个周期完成，N 条指令需要 5N 个周期。

**使用流水线**：理想情况下，流水线填满后每个周期完成一条指令，N 条指令约需 N+4 个周期。

---

## 2. 五级流水线架构

### 2.1 架构总览

本项目实现的 CPU 采用经典的五级流水线架构：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           五级流水线 CPU 架构图                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────┐     ┌──────┐     ┌──────┐     ┌──────┐     ┌──────┐             │
│  │  IF  │────►│  ID  │────►│  EX  │────►│ MEM  │────►│  WB  │             │
│  │ 取指  │     │ 译码  │     │ 执行  │     │ 访存  │     │ 写回  │             │
│  └──┬───┘     └──┬───┘     └──┬───┘     └──┬───┘     └──┬───┘             │
│     │           │           │           │           │                     │
│     │           │           ▼           ▼           ▼                     │
│     │           │      ┌────────────────────────────────┐                 │
│     │           │      │       数据旁路 (Forwarding)      │                 │
│     │           │      └────────────────────────────────┘                 │
│     │           │                                                         │
│     │           │      ┌────────────────────────────────┐                 │
│     │           └─────►│     冒险检测 (Hazard Unit)       │                 │
│     │                  └────────────────────────────────┘                 │
│     │                                                                     │
│     │           ┌────────────────────────────────────────┐                │
│     └──────────►│    分支预测 (BTB + Tournament Predictor) │                │
│                 └────────────────────────────────────────┘                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 各阶段简介

| 阶段 | 英文名称 | 主要功能 | 对应文件 |
|------|----------|----------|----------|
| **IF** | Instruction Fetch | 取指令：从内存读取下一条要执行的指令 | `fetch.py` |
| **ID** | Instruction Decode | 译码：解析指令含义，读取寄存器 | `decoder.py` |
| **EX** | Execute | 执行：ALU 运算、计算分支地址 | `execution.py` |
| **MEM** | Memory Access | 访存：Load/Store 指令读写数据内存 | `memory.py` |
| **WB** | Write Back | 写回：将结果写入寄存器堆 | `writeback.py` |

### 2.3 流水线寄存器

为了让每个阶段独立工作，需要在相邻阶段之间添加**流水线寄存器**（Pipeline Registers）来保存中间数据：

```
    IF  ──►  IF/ID  ──►  ID  ──►  ID/EX  ──►  EX  ──►  EX/MEM  ──►  MEM  ──►  MEM/WB  ──►  WB
            寄存器            寄存器             寄存器               寄存器
```

在 Assassyn 中，这些流水线寄存器通过 **FIFO（先进先出队列）** 来实现，由框架自动生成。

---

## 3. 各部件详解

### 3.1 IF 阶段：取指 (Instruction Fetch)

**功能**：根据 PC（程序计数器）从指令缓存读取指令。

**主要组件**：
- **PC 寄存器**：存储当前指令地址
- **指令缓存（SRAM）**：存储程序指令
- **分支预测器**：预测分支指令的跳转目标

**工作流程**：
```
1. 读取 PC 值
2. 用 PC 地址访问指令缓存
3. 查询分支预测器，决定下一个 PC
4. 更新 PC 寄存器
5. 将指令和 PC 发送给 ID 阶段
```

**代码位置**：`src/fetch.py`

```python
# 简化的 IF 阶段核心逻辑
class FetcherImpl(Downstream):
    @downstream.combinational
    def build(self, pc_reg, decoder, stall_if, branch_target, ...):
        # 读取当前 PC
        current_pc = stall_if.select(last_pc_reg[0], pc_reg[0])
        
        # 处理分支跳转
        flush_if = branch_target[0] != Bits(32)(0)
        final_current_pc = flush_if.select(branch_target[0], current_pc)
        
        # 计算下一个 PC（默认 +4，或使用分支预测）
        default_next_pc = (final_current_pc.bitcast(UInt(32)) + UInt(32)(4)).bitcast(Bits(32))
        
        # 更新 PC 寄存器（时序逻辑）
        pc_reg[0] <= final_next_pc
        
        # 发送到解码器
        call = decoder.async_called(pc=final_current_pc, next_pc=final_next_pc)
```

### 3.2 ID 阶段：译码 (Instruction Decode)

**功能**：解析指令格式，生成控制信号，读取源寄存器。

**主要组件**：
- **指令解码器**：识别指令类型、提取字段
- **立即数生成器**：根据指令格式生成立即数
- **寄存器堆**：存储 32 个通用寄存器
- **控制信号生成**：生成 ALU 操作码、分支类型等

**RISC-V 指令格式**：

```
R-Type: | funct7 | rs2 | rs1 | funct3 | rd | opcode |  (用于寄存器-寄存器运算)
I-Type: |    imm[11:0]  | rs1 | funct3 | rd | opcode |  (用于立即数运算、Load)
S-Type: | imm[11:5] | rs2 | rs1 | funct3 | imm[4:0] | opcode |  (用于 Store)
B-Type: | imm[12|10:5] | rs2 | rs1 | funct3 | imm[4:1|11] | opcode |  (用于分支)
U-Type: |        imm[31:12]        | rd | opcode |  (用于 LUI/AUIPC)
J-Type: |   imm[20|10:1|11|19:12]  | rd | opcode |  (用于 JAL)
```

**代码位置**：`src/decoder.py`

```python
# 简化的 ID 阶段核心逻辑
class Decoder(Module):
    @module.combinational
    def build(self, icache_dout, reg_file):
        # 获取指令
        # icache_dout[0] 是 SRAM 的输出端口，返回原始数据
        # bitcast(Bits(32)) 将其重新解释为 32 位向量，不改变底层数据
        inst = icache_dout[0].bitcast(Bits(32))
        
        # 提取指令字段
        opcode = inst[0:6]
        rd = inst[7:11]
        funct3 = inst[12:14]
        rs1 = inst[15:19]
        rs2 = inst[20:24]
        
        # 生成立即数（I 型为例）
        sign = inst[31:31]
        pad_20 = sign.select(Bits(20)(0xFFFFF), Bits(20)(0))
        imm_i = concat(pad_20, inst[20:31])
        
        # 读取寄存器堆
        raw_rs1_data = reg_file[rs1]
        raw_rs2_data = reg_file[rs2]
        
        # 返回解码结果
        return pre_decode_packet, rs1, rs2
```

### 3.3 EX 阶段：执行 (Execute)

**功能**：执行 ALU 运算、计算分支条件和目标地址。

**主要组件**：
- **ALU（算术逻辑单元）**：执行加减、逻辑、移位、比较运算
- **分支单元**：判断分支条件，计算跳转地址
- **旁路选择器**：选择 ALU 操作数来源（寄存器/旁路数据）
- **乘法器**：3 周期 Wallace Tree 乘法器
- **除法器**：约 10 周期 Radix-16 除法器

**ALU 操作**：

| 操作 | 功能 | 示例指令 |
|------|------|----------|
| ADD | 加法 | ADD, ADDI |
| SUB | 减法 | SUB |
| AND/OR/XOR | 逻辑运算 | AND, OR, XOR |
| SLL/SRL/SRA | 移位 | SLL, SRL, SRA |
| SLT/SLTU | 比较 | SLT, SLTU |

**代码位置**：`src/execution.py`

```python
# 简化的 EX 阶段核心逻辑
class Execution(Module):
    @module.combinational
    def build(self, mem_module, ex_bypass, mem_bypass, wb_bypass, ...):
        # 弹出端口数据
        ctrl, pc, rs1, rs2, imm = self.pop_all_ports(False)
        
        # 旁路处理：选择正确的操作数来源
        real_rs1 = ctrl.rs1_sel.select1hot(
            rs1,           # 原始寄存器值
            fwd_from_mem,  # EX-MEM 旁路
            fwd_from_wb,   # MEM-WB 旁路
            fwd_from_wb_stage  # WB 旁路
        )
        
        # 操作数选择
        alu_op1 = ctrl.op1_sel.select1hot(real_rs1, pc, Bits(32)(0))
        alu_op2 = ctrl.op2_sel.select1hot(real_rs2, imm, Bits(32)(4))
        
        # ALU 运算
        op1_signed = alu_op1.bitcast(Int(32))
        op2_signed = alu_op2.bitcast(Int(32))
        add_res = (op1_signed + op2_signed).bitcast(Bits(32))
        sub_res = (op1_signed - op2_signed).bitcast(Bits(32))
        and_res = alu_op1 & alu_op2
        # ... 其他运算
        
        # 结果选择（独热码多路选择器）
        alu_result = ctrl.alu_func.select1hot(
            add_res, sub_res, sll_res, slt_res, ...
        )
        
        # 更新旁路寄存器
        ex_bypass[0] = alu_result
        
        # 发送到 MEM 阶段
        mem_call = mem_module.async_called(ctrl=mem_ctrl, alu_result=alu_result)
```

### 3.4 MEM 阶段：访存 (Memory Access)

**功能**：执行 Load/Store 指令，读写数据内存。

**主要组件**：
- **数据内存（SRAM）**：存储程序数据
- **数据对齐器**：处理字节/半字/字访问
- **符号扩展器**：对 Load 数据进行符号/零扩展

**访存操作**：

| 指令 | 操作 | 说明 |
|------|------|------|
| LB/LBU | 加载字节 | 有符号/无符号扩展 |
| LH/LHU | 加载半字 | 有符号/无符号扩展 |
| LW | 加载字 | 32 位 |
| SB | 存储字节 | 8 位 |
| SH | 存储半字 | 16 位 |
| SW | 存储字 | 32 位 |

**代码位置**：`src/memory.py`

```python
# 简化的 MEM 阶段核心逻辑
class MemoryAccess(Module):
    @module.combinational
    def build(self, wb_module, sram_dout, mem_bypass_reg):
        ctrl, alu_result = self.pop_all_ports(False)
        
        # 读取 SRAM 数据
        raw_mem = sram_dout[0].bitcast(Bits(32))
        
        # 根据地址低位选择字节/半字
        half_selected = alu_result[1:1].select(raw_mem[16:31], raw_mem[0:15])
        byte_selected = alu_result[0:0].select(half_selected[8:15], half_selected[0:7])
        
        # 符号扩展
        pad_bit_8 = mem_unsigned.select(Bits(1)(0), byte_selected[7:7])
        padding_8 = pad_bit_8.select(Bits(24)(0xFFFFFF), Bits(24)(0))
        byte_extended = concat(padding_8, byte_selected)
        
        # 最终数据选择
        is_load = mem_opcode == MemOp.LOAD
        final_data = is_load.select(processed_mem_result, alu_result)
        
        # 更新旁路寄存器
        mem_bypass_reg[0] = final_data
        
        # 发送到 WB 阶段
        wb_call = wb_module.async_called(ctrl=wb_ctrl, wdata=final_data)
```

### 3.5 WB 阶段：写回 (Write Back)

**功能**：将运算结果或内存数据写入目标寄存器。

**代码位置**：`src/writeback.py`

```python
# 简化的 WB 阶段核心逻辑
class WriteBack(Module):
    @module.combinational
    def build(self, reg_file, wb_bypass_reg):
        wb_ctrl, wdata = self.pop_all_ports(False)
        rd = wb_ctrl.rd_addr
        
        # 写入寄存器堆（x0 不能被写入）
        with Condition(rd != Bits(5)(0)):
            reg_file[rd] = wdata
            wb_bypass_reg[0] = wdata
        
        # 检测停机指令
        with Condition(wb_ctrl.halt_if == Bits(1)(1)):
            finish()
        
        return rd
```

### 3.6 冒险检测单元 (Hazard Unit)

**功能**：检测数据冒险，生成旁路选择信号和流水线暂停信号。

**数据冒险类型**：

1. **RAW (Read After Write)**：指令需要读取前一条指令的结果
   - **解决方案**：数据旁路（Forwarding）或流水线暂停（Stall）

2. **Load-Use 冒险**：Load 指令后紧跟使用其结果的指令
   - **解决方案**：必须暂停一个周期

**代码位置**：`src/data_hazard.py`

```python
# 简化的冒险检测逻辑
class DataHazardUnit(Downstream):
    @downstream.combinational
    def build(self, rs1_idx, rs2_idx, ex_rd, ex_is_load, mem_rd, wb_rd):
        # Load-Use 冒险检测
        load_use_hazard_rs1 = ex_is_load & (rs1_idx == ex_rd)
        load_use_hazard_rs2 = ex_is_load & (rs2_idx == ex_rd)
        
        # 是否需要暂停
        stall_if = load_use_hazard_rs1 | load_use_hazard_rs2
        
        # rs1 旁路选择（优先级：EX > MEM > WB）
        rs1_sel = (rs1_idx == ex_rd).select(Rs1Sel.EX_BYPASS,
                  (rs1_idx == mem_rd).select(Rs1Sel.MEM_BYPASS,
                  (rs1_idx == wb_rd).select(Rs1Sel.WB_BYPASS,
                                            Rs1Sel.RS1)))
        
        # rs2 旁路选择（逻辑与 rs1 相同）
        rs2_sel = (rs2_idx == ex_rd).select(Rs2Sel.EX_BYPASS,
                  (rs2_idx == mem_rd).select(Rs2Sel.MEM_BYPASS,
                  (rs2_idx == wb_rd).select(Rs2Sel.WB_BYPASS,
                                            Rs2Sel.RS2)))
        
        return rs1_sel, rs2_sel, stall_if
```

### 3.7 分支预测单元

**功能**：预测分支指令的跳转方向和目标地址。

**组件**：
- **BTB（Branch Target Buffer）**：缓存分支目标地址
- **Tournament Predictor**：组合 Bimodal 和 Gshare 预测器

**代码位置**：`src/btb.py`、`src/tournament_predictor.py`

---

## 4. 组合逻辑与时序逻辑

### 4.1 基础概念

**组合逻辑（Combinational Logic）**：
- 输出只取决于当前输入
- 没有记忆能力
- 例如：加法器、多路选择器、比较器

**时序逻辑（Sequential Logic）**：
- 输出取决于当前输入和历史状态
- 有记忆能力（使用寄存器/触发器）
- 例如：计数器、状态机、寄存器堆

### 4.2 在 CPU 中的体现

```
                    组合逻辑                     时序逻辑
                   ┌─────────────────────────┐   ┌─────────┐
              ────►│  ALU 运算、多路选择器     │───►│ 流水线   │───►
  输入数据          │  地址计算、比较器         │    │ 寄存器   │    输出数据
                   └─────────────────────────┘   └─────────┘
                                                     ▲
                                                     │
                                                  时钟信号
```

**组合逻辑示例**：
```python
# ALU 加法（纯组合逻辑，没有状态）
add_result = (op1_signed + op2_signed).bitcast(Bits(32))

# 多路选择器（纯组合逻辑）
alu_result = ctrl.alu_func.select1hot(add_res, sub_res, sll_res, ...)
```

**时序逻辑示例**：
```python
# PC 寄存器更新（时序逻辑，在下一个时钟周期生效）
pc_reg[0] <= next_pc

# 流水线寄存器（通过 async_called 隐式实现）
call = decoder.async_called(pc=current_pc, next_pc=next_pc)
```

### 4.3 Assassyn 中的区分

在 Assassyn 中，通过赋值运算符区分：

| 赋值方式 | 语义 | 类型 |
|----------|------|------|
| `reg[i] = value` | 组合逻辑赋值，立即生效 | 组合逻辑 |
| `reg[i] <= value` | 时序逻辑赋值，下一周期生效 | 时序逻辑 |

```python
# 组合逻辑：寄存器堆写入（当前周期立即可见）
with Condition(rd != Bits(5)(0)):
    reg_file[rd] = wdata  # 使用 = 号

# 时序逻辑：PC 更新（下一周期生效）
pc_reg[0] <= next_pc  # 使用 <= 号
```

---

## 5. Assassyn 语言与硬件描述

### 5.1 什么是 Assassyn？

Assassyn 是一种基于 Python 的**硬件描述语言（HDL）**，它让你可以：
- 使用熟悉的 Python 语法编写硬件电路
- 自动生成 Verilog 代码或直接仿真
- 实现延迟不敏感的弹性流水线设计

### 5.2 核心数据类型

```python
from assassyn.frontend import *

# 位向量（无符号）- 用于控制信号、地址、原始数据
opcode = Bits(7)(0b0110011)  # 7 位宽，值为 0110011
addr = Bits(32)(0x1000)       # 32 位地址

# 无符号整数 - 用于算术运算
counter = UInt(32)(0)
next_counter = counter + UInt(32)(1)

# 有符号整数 - 用于有符号算术
signed_val = Int(32)(-1)
result = signed_val + Int(32)(5)

# 类型转换
bits_val = Bits(32)(0xFFFFFFFF)
signed_val = bits_val.bitcast(Int(32))  # 解释为 -1
```

### 5.3 存储单元

```python
# 寄存器数组（RegArray）
# 用于：PC、寄存器堆、状态寄存器
pc_reg = RegArray(Bits(32), 1, initializer=[0])  # 单个 32 位寄存器
reg_file = RegArray(Bits(32), 32)                 # 32 个 32 位寄存器

# 读取
current_pc = pc_reg[0]
rs1_data = reg_file[rs1_addr]

# 组合逻辑写入（立即生效）
reg_file[rd_addr] = write_data

# 时序逻辑写入（下一周期生效）
pc_reg[0] <= next_pc

# SRAM（大容量存储器）
# 用于：指令缓存、数据缓存
cache = SRAM(width=32, depth=65536, init_file="workload.exe")
cache.build(we=write_enable, re=read_enable, addr=address, wdata=write_data)
data_out = cache.dout[0]
```

### 5.4 结构体（Record）

```python
# 定义控制信号结构体
wb_ctrl_signals = Record(
    rd_addr=Bits(5),    # 目标寄存器地址
    halt_if=Bits(1),    # 停机标志
)

mem_ctrl_signals = Record(
    mem_opcode=Bits(3),     # 内存操作类型
    mem_width=Bits(3),      # 访问宽度
    mem_unsigned=Bits(1),   # 是否无符号
    wb_ctrl=wb_ctrl_signals, # 嵌套结构体
)

# 创建实例（打包）
wb_ctrl = wb_ctrl_signals.bundle(
    rd_addr=Bits(5)(3),
    halt_if=Bits(1)(0),
)

# 解析（解包）
view = wb_ctrl_signals.view(packed_data)
rd = view.rd_addr
```

### 5.5 选择器

```python
# 二路选择器：select(true_val, false_val)
result = condition.select(value_if_true, value_if_false)

# 示例：选择下一个 PC
next_pc = is_branch.select(branch_target, pc_plus_4)

# 独热码多路选择器：select1hot(opt0, opt1, opt2, ...)
alu_result = alu_func.select1hot(
    add_result,   # bit 0: ADD
    sub_result,   # bit 1: SUB
    sll_result,   # bit 2: SLL
    slt_result,   # bit 3: SLT
    # ...
)
```

### 5.6 位操作

```python
# 位截取 [低位:高位]（闭区间，与 Verilog 类似）
opcode = inst[0:6]     # 提取位 0 到 6，共 7 位
funct3 = inst[12:14]   # 提取位 12 到 14，共 3 位
sign_bit = inst[31:31] # 提取单独的第 31 位（符号位），结果是 1 位宽的 Bits(1)

# 位拼接
imm_i = concat(sign_ext, inst[20:31])
imm_b = concat(pad_19, inst[31:31], inst[7:7], inst[25:30], inst[8:11], Bits(1)(0))
```

### 5.7 条件控制

```python
# Condition 块：控制硬件操作是否执行
with Condition(rd != Bits(5)(0)):
    reg_file[rd] = wdata  # 只有 rd != 0 时才写入

# 嵌套条件
with Condition(is_branch == Bits(1)(1)):
    with Condition(is_taken == Bits(1)(1)):
        debug_log("Branch taken!")

# 停机控制
with Condition(halt_if == Bits(1)(1)):
    finish()  # 结束仿真
```

---

## 6. 部件间通信机制

### 6.1 Module 与 Downstream

Assassyn 提供两种架构单元：

**Module（时序逻辑模块）**：
- 拥有端口（Ports）定义
- 可以包含状态（RegArray）
- 有独立的时钟域
- 用于流水线的各个阶段

**Downstream（纯组合逻辑模块）**：
- 没有端口
- 无状态
- 用于组合逻辑、反馈回路

```python
# Module 定义
class Execution(Module):
    def __init__(self):
        super().__init__(
            ports={
                "ctrl": Port(ex_ctrl_signals),
                "pc": Port(Bits(32)),
                "rs1_data": Port(Bits(32)),
                "rs2_data": Port(Bits(32)),
                "imm": Port(Bits(32)),
            }
        )
    
    @module.combinational
    def build(self, mem_module, ...):
        # 消费端口数据
        ctrl, pc, rs1, rs2, imm = self.pop_all_ports(False)
        # 实现逻辑
        ...

# Downstream 定义
class DataHazardUnit(Downstream):
    def __init__(self):
        super().__init__()
    
    @downstream.combinational
    def build(self, rs1_idx, rs2_idx, ex_rd, ...):
        # 纯组合逻辑
        ...
```

### 6.2 异步调用（async_called）

模块间通信通过 `async_called()` 实现，框架自动生成 FIFO 缓冲区：

```python
# 发送端（ID 阶段发送到 EX 阶段）
class DecoderImpl(Downstream):
    @downstream.combinational
    def build(self, executor, ...):
        # 连接到 Executor
        call = executor.async_called(
            ctrl=final_ex_ctrl,
            pc=pre.pc,
            rs1_data=pre.rs1_data,
            rs2_data=pre.rs2_data,
            imm=pre.imm,
        )
        
        # 设置 FIFO 深度
        call.bind.set_fifo_depth(
            ctrl=1,
            pc=1,
            rs1_data=1,
            rs2_data=1,
            imm=1
        )

# 接收端（EX 阶段消费数据）
class Execution(Module):
    @module.combinational
    def build(self, ...):
        # 从端口读取数据
        ctrl, pc, rs1, rs2, imm = self.pop_all_ports(False)
```

### 6.3 通信流程图

```
┌─────────────┐                           ┌─────────────┐
│   Decoder   │                           │  Executor   │
│  (发送端)    │                           │  (接收端)    │
│             │                           │             │
│  async_     │     ┌─────────────┐       │  pop_all_   │
│  called()   │────►│    FIFO     │──────►│  ports()    │
│             │     │  (自动生成)  │       │             │
└─────────────┘     └─────────────┘       └─────────────┘

     生产者              缓冲区                 消费者
```

### 6.4 数据旁路实现

数据旁路是通过**全局寄存器**实现的，各阶段可以直接访问：

```python
# 在 main.py 中创建旁路寄存器
ex_bypass_reg = RegArray(Bits(32), 1)
mem_bypass_reg = RegArray(Bits(32), 1)
wb_bypass_reg = RegArray(Bits(32), 1)

# EX 阶段写入旁路寄存器
ex_bypass_reg[0] = alu_result

# EX 阶段读取旁路数据
fwd_from_mem = ex_bypass_reg[0]
fwd_from_wb = mem_bypass_reg[0]

# 选择正确的数据来源
real_rs1 = ctrl.rs1_sel.select1hot(
    rs1,           # 原始值
    fwd_from_mem,  # EX-MEM 旁路
    fwd_from_wb,   # MEM-WB 旁路
    fwd_from_wb_stage  # WB 旁路
)
```

---

## 7. 完整代码示例解析

### 7.1 系统构建流程

在 `main.py` 中，CPU 的构建遵循特定顺序：

```python
def build_cpu(depth_log, enable_branch_prediction=True):
    sys = SysBuilder("rv32i_cpu")
    
    with sys:
        # 1. 创建物理资源
        cache = SRAM(width=32, depth=1 << depth_log, init_file=RAM_path)
        reg_file = RegArray(Bits(32), 32)
        
        # 旁路寄存器
        ex_bypass_reg = RegArray(Bits(32), 1)
        mem_bypass_reg = RegArray(Bits(32), 1)
        wb_bypass_reg = RegArray(Bits(32), 1)
        branch_target_reg = RegArray(Bits(32), 1)
        
        # 2. 实例化模块
        fetcher = Fetcher()
        fetcher_impl = FetcherImpl()
        decoder = Decoder()
        decoder_impl = DecoderImpl()
        hazard_unit = HazardUnit()
        executor = Execution()
        memory_unit = MemoryAccess()
        memory_single = SingleMemory()
        writeback = WriteBack()
        
        # 3. 逆序构建（从后往前）
        # 这样可以先知道后级模块的接口，再连接前级
        
        # WB 阶段
        wb_rd = writeback.build(reg_file=reg_file, wb_bypass_reg=wb_bypass_reg)
        
        # MEM 阶段
        mem_rd, mem_is_store = memory_unit.build(
            wb_module=writeback,
            sram_dout=cache.dout,
            mem_bypass_reg=mem_bypass_reg,
        )
        
        # EX 阶段
        ex_rd, ex_addr, ex_is_load, ... = executor.build(
            mem_module=memory_unit,
            ex_bypass=ex_bypass_reg,
            mem_bypass=mem_bypass_reg,
            wb_bypass=wb_bypass_reg,
            branch_target_reg=branch_target_reg,
        )
        
        # ID 阶段
        pre_pkt, rs1, rs2 = decoder.build(
            icache_dout=cache.dout,
            reg_file=reg_file,
        )
        
        # Hazard Unit
        rs1_sel, rs2_sel, stall_if = hazard_unit.build(
            rs1_idx=rs1,
            rs2_idx=rs2,
            ex_rd=ex_rd,
            ex_is_load=ex_is_load,
            mem_rd=mem_rd,
            wb_rd=wb_rd,
        )
        
        # ID 实现
        decoder_impl.build(
            pre=pre_pkt,
            executor=executor,
            rs1_sel=rs1_sel,
            rs2_sel=rs2_sel,
            stall_if=stall_if,
            branch_target_reg=branch_target_reg,
        )
        
        # IF 阶段
        pc_reg, pc_addr, last_pc_reg = fetcher.build()
        current_pc = fetcher_impl.build(
            pc_reg=pc_reg,
            decoder=decoder,
            stall_if=stall_if,
            branch_target=branch_target_reg,
        )
        
        # 内存驱动
        memory_single.build(
            if_addr=current_pc,
            mem_addr=ex_addr,
            re=ex_is_load,
            we=ex_is_store,
            wdata=ex_rs2,
            width=ex_width,
            sram=cache,
        )
    
    return sys
```

### 7.2 一条指令的执行流程

以 `ADD x3, x1, x2`（将 x1 和 x2 相加，结果存入 x3）为例：

```
周期 1: IF 阶段
├── 读取 PC = 0x1000
├── 从 cache[0x400] 读取指令 0x002081B3
│   （注：0x400 = 0x1000 >> 2，因为 SRAM 按字（4字节）寻址）
├── 分支预测：PC+4 = 0x1004
└── 发送 {pc=0x1000, next_pc=0x1004} 到 ID

周期 2: ID 阶段
├── 接收指令 0x002081B3
├── 解码：
│   ├── opcode = 0b0110011 (R-type)
│   ├── rd = x3
│   ├── funct3 = 0b000 (ADD)
│   ├── rs1 = x1
│   ├── rs2 = x2
│   └── funct7[5] = 0 (ADD, not SUB)
├── 读取寄存器：rs1_data = reg_file[1], rs2_data = reg_file[2]
├── 生成控制信号：alu_func=ADD, op1_sel=RS1, op2_sel=RS2
└── 发送 {ctrl, pc, rs1_data, rs2_data, imm} 到 EX

周期 3: EX 阶段
├── 接收数据
├── 冒险检测：检查是否需要旁路
├── 选择操作数：alu_op1=rs1_data, alu_op2=rs2_data
├── ALU 运算：add_result = rs1_data + rs2_data
├── 更新旁路寄存器：ex_bypass = add_result
└── 发送 {ctrl, alu_result} 到 MEM

周期 4: MEM 阶段
├── 接收数据
├── 检测：不是 Load/Store 指令
├── final_data = alu_result（直接传递）
├── 更新旁路寄存器：mem_bypass = final_data
└── 发送 {rd=x3, wdata} 到 WB

周期 5: WB 阶段
├── 接收数据
├── 写入寄存器堆：reg_file[3] = wdata
└── 更新旁路寄存器：wb_bypass = wdata
```

### 7.3 数据冒险处理示例

考虑以下指令序列：

```assembly
ADD x3, x1, x2   # 指令 1: 写 x3
SUB x4, x3, x5   # 指令 2: 读 x3 (数据冒险！)
```

**问题**：指令 2 需要读取 x3，但指令 1 的结果还在流水线中。

**解决方案**：数据旁路

```
周期 3: 指令 1 在 EX 阶段
├── 计算 x3 = x1 + x2
└── ex_bypass = 计算结果

周期 4: 指令 2 在 EX 阶段，指令 1 在 MEM 阶段
├── Hazard Unit 检测：指令 2 的 rs1(x3) == 指令 1 的 rd(x3)
├── 生成旁路选择信号：rs1_sel = EX_BYPASS
├── 指令 2 从旁路获取 x3 的值
└── 正确计算 x4 = x3 - x5
```

---

## 总结

本文档详细介绍了：

1. **CPU 基础知识**：五级流水线架构、RISC-V 指令集
2. **各部件功能**：IF/ID/EX/MEM/WB 阶段的详细实现
3. **逻辑类型**：组合逻辑与时序逻辑的区别
4. **Assassyn 语言**：数据类型、存储单元、选择器、条件控制
5. **硬件连接**：Module 与 Downstream、async_called 通信机制
6. **完整示例**：系统构建流程、指令执行流程、数据冒险处理

通过学习本文档，你应该能够：
- 理解五级流水线 CPU 的工作原理
- 阅读和理解本项目的源代码
- 使用 Assassyn 语言描述简单的硬件电路
- 理解数据冒险和分支预测的基本概念

如需进一步学习，可以参考 `docs/` 目录下的其他文档：
- [Assassyn_语言完整说明书.md](Assassyn_语言完整说明书.md)：Assassyn 完整语法参考
- [Module/](Module/)：各模块的详细设计文档
