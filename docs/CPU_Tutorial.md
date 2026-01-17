# CPU 架构原理与 Assassyn 实现教程

> **本文档面向硬件新手**，详细介绍 CPU 的基本架构和组成部件，并对照本仓库代码说明如何使用 Assassyn 硬件描述语言实现一个 RV32IM 五级流水线 CPU。

## 目录

1. [CPU 基础知识](#1-cpu-基础知识)
2. [数字电路基础](#2-数字电路基础)
3. [CPU 核心组件详解](#3-cpu-核心组件详解)
4. [流水线技术](#4-流水线技术)
5. [Assassyn 语言简介](#5-assassyn-语言简介)
6. [本仓库 CPU 实现详解](#6-本仓库-cpu-实现详解)
7. [冒险与解决方案](#7-冒险与解决方案)
8. [分支预测](#8-分支预测)
9. [乘除法器实现](#9-乘除法器实现)
10. [总结与进阶学习](#10-总结与进阶学习)

---

## 1. CPU 基础知识

### 1.1 什么是 CPU？

**CPU（Central Processing Unit，中央处理单元）** 是计算机的"大脑"，负责执行程序中的指令。从硬件角度看，CPU 是一个由数十亿个晶体管组成的集成电路，这些晶体管按照特定的逻辑组织在一起，实现数据的处理和控制。

### 1.2 CPU 的基本工作原理

CPU 的工作可以简化为一个不断重复的循环：

```
┌─────────────────────────────────────────────────────────────┐
│                     CPU 基本工作循环                          │
│                                                             │
│   ┌─────────┐      ┌─────────┐      ┌─────────┐            │
│   │  取指   │ ──── │  译码   │ ──── │  执行   │            │
│   │ (Fetch) │      │(Decode) │      │(Execute)│            │
│   └─────────┘      └─────────┘      └─────────┘            │
│        │                                  │                 │
│        │                                  │                 │
│        └──────────────────────────────────┘                 │
│                      (重复)                                  │
└─────────────────────────────────────────────────────────────┘
```

1. **取指（Fetch）**：从内存中读取下一条要执行的指令
2. **译码（Decode）**：解析指令的含义，确定要执行什么操作
3. **执行（Execute）**：实际执行指令规定的操作（如加法、减法等）

### 1.3 指令集架构（ISA）

**指令集架构** 定义了 CPU 能够理解和执行的指令集合。本仓库实现的是 **RISC-V RV32IM** 指令集：

- **RISC-V**：一种开源的精简指令集架构
- **RV32I**：32 位基础整数指令集（包含加减、逻辑运算、分支跳转、访存等指令）
- **M 扩展**：乘法/除法/取余指令

**为什么选择 RISC-V？**

| 特点 | 说明 |
|------|------|
| 开源免费 | 没有专利限制，适合学习和研究 |
| 设计简洁 | 指令格式规整，易于理解和实现 |
| 模块化 | 可以根据需求选择扩展功能 |
| 主流趋势 | 越来越多的芯片采用 RISC-V |

---

## 2. 数字电路基础

在深入了解 CPU 之前，我们需要理解一些基本的数字电路概念。

### 2.1 信号与位宽

在数字电路中，信息以**二进制信号**的形式表示：

- **高电平（1）**：通常表示 3.3V 或 5V 的电压
- **低电平（0）**：通常表示 0V 的电压

**位宽（Bit Width）** 指信号的位数。例如：
- 1 位信号：只能表示 0 或 1
- 32 位信号：可以表示 2^32 种不同的值（约 43 亿种）

在 Assassyn 中，使用 `Bits(width)` 定义位宽：

```python
# 定义一个 32 位宽的信号
signal = Bits(32)(0x12345678)

# 定义一个 1 位的控制信号
enable = Bits(1)(1)
```

### 2.2 组合逻辑与时序逻辑

数字电路分为两大类：

#### 2.2.1 组合逻辑电路

**组合逻辑** 的输出只取决于当前输入，没有记忆功能。

常见的组合逻辑元件：

| 元件 | 功能 | Assassyn 表示 |
|------|------|---------------|
| 与门 (AND) | 所有输入为 1 时输出 1 | `a & b` |
| 或门 (OR) | 任一输入为 1 时输出 1 | `a | b` |
| 非门 (NOT) | 输入取反 | `~a` |
| 异或门 (XOR) | 输入不同时输出 1 | `a ^ b` |
| 多路选择器 (MUX) | 根据选择信号选择输入 | `sel.select(a, b)` |

```python
# Assassyn 中的组合逻辑示例
result = (a & b) | (c ^ d)  # 与或异或组合
output = sel.select(input_a, input_b)  # 选择器：sel=1选a，sel=0选b
```

#### 2.2.2 时序逻辑电路

**时序逻辑** 的输出不仅取决于当前输入，还取决于历史状态。它具有"记忆"功能。

核心元件是 **寄存器（Register）**：

```
          ┌─────────────┐
   D ────►│             │
          │   寄存器     │──── Q
  CLK ───►│             │
          └─────────────┘

工作原理：
- 在时钟上升沿（CLK 从 0 变为 1），将输入 D 的值"锁存"
- 输出 Q 保持上次锁存的值不变，直到下一个时钟上升沿
```

在 Assassyn 中，使用 `RegArray` 定义寄存器：

```python
# 定义一个 32 位寄存器
pc_reg = RegArray(Bits(32), 1, initializer=[0])

# 读取寄存器当前值（组合逻辑读取）
current_pc = pc_reg[0]

# 在下一个时钟周期更新寄存器（时序逻辑写入）
pc_reg[0] <= next_pc  # 注意：使用 <= 表示时序赋值
```

### 2.3 时钟与时钟周期

**时钟信号** 是一个周期性的方波信号，用于同步 CPU 中所有时序逻辑元件的动作。

```
时钟信号波形：
     ┌───┐   ┌───┐   ┌───┐   ┌───┐
     │   │   │   │   │   │   │   │
─────┘   └───┘   └───┘   └───┘   └───

     ↑       ↑       ↑       ↑
   上升沿  上升沿  上升沿  上升沿

一个时钟周期
├─────────────┤
```

- **时钟周期**：两个相邻上升沿之间的时间间隔
- **时钟频率**：每秒钟有多少个时钟周期（单位：Hz）
- 例如：1 GHz 的 CPU 意味着每秒执行 10 亿个时钟周期

---

## 3. CPU 核心组件详解

### 3.1 程序计数器（PC, Program Counter）

**PC 寄存器** 存储下一条要执行的指令的地址。每执行完一条指令，PC 通常加 4（因为 RISC-V 指令是 4 字节）。

```
              ┌──────────────────────────────────────┐
              │          程序计数器 (PC)              │
              │                                      │
  next_pc ───►│  ┌──────────┐        ┌─────────┐    │
              │  │  MUX     │───────►│  寄存器  │────├──► current_pc
  branch_addr►│  │          │        │   32位   │    │
              │  └──────────┘        └─────────┘    │
              │       ▲                    ▲        │
              │       │                    │        │
              │   branch_taken           CLK        │
              └──────────────────────────────────────┘
```

**本仓库实现**（`src/fetch.py`）：

```python
class Fetcher(Module):
    @module.combinational
    def build(self):
        # PC 寄存器，初始化为 0（Reset Vector）
        pc_reg = RegArray(Bits(32), 1, initializer=[0])
        
        # 用于驱动 FetcherImpl
        pc_addr = pc_reg[0]
        
        # 记录上一个周期的 PC，用于在 Stall 时保持稳定
        last_pc_reg = RegArray(Bits(32), 1, initializer=[0])
        
        return pc_reg, pc_addr, last_pc_reg
```

### 3.2 指令存储器（Instruction Memory）

指令存储器存放程序的所有指令。CPU 根据 PC 的值读取相应地址的指令。

```
              ┌──────────────────────────────────────┐
              │         指令存储器 (SRAM)              │
              │                                      │
   addr ─────►│   地址 0x0000: 指令1                  │
              │   地址 0x0004: 指令2                  │──── instruction
              │   地址 0x0008: 指令3                  │
              │   ...                                │
              └──────────────────────────────────────┘
```

**本仓库实现**（`src/main.py`）：

```python
# 创建统一的指令/数据存储器（64KB）
cache = SRAM(width=32, depth=1 << depth_log, init_file=RAM_path)
cache.name = "cache"
```

**SRAM 的硬件特性**：
- **读延迟**：读取需要 1 个时钟周期才能返回数据
- **写操作**：写入在当前周期完成
- **地址对齐**：SRAM 按字（32 位）寻址，需要将字节地址右移 2 位

### 3.3 寄存器堆（Register File）

RISC-V 有 32 个通用寄存器（x0-x31），其中 **x0 恒为 0**。

```
              ┌──────────────────────────────────────┐
              │           寄存器堆 (32个寄存器)         │
              │                                      │
  rs1_addr ──►│   x0  = 0 (恒为零)                   │──── rs1_data
  rs2_addr ──►│   x1  = 返回地址 (ra)                │──── rs2_data
   rd_addr ──►│   x2  = 栈指针 (sp)                  │
   wr_data ──►│   x3  - x31 = 通用寄存器             │
    wr_en ───►│                                      │
              └──────────────────────────────────────┘

特点：
- 2 个读端口（同时读取 rs1 和 rs2）
- 1 个写端口（写入 rd）
- 写 x0 被忽略（x0 恒为 0）
```

**本仓库实现**（`src/main.py`）：

```python
# 寄存器堆：32 个 32 位寄存器
reg_file = RegArray(Bits(32), 32)
```

**写回逻辑**（`src/writeback.py`）：

```python
# 当目标寄存器不是 x0 时才写入
with Condition(rd != Bits(5)(0)):
    reg_file[rd] = wdata
```

### 3.4 算术逻辑单元（ALU）

**ALU** 是 CPU 的运算核心，执行加减法、逻辑运算、比较运算、移位运算等。

```
              ┌──────────────────────────────────────┐
              │              ALU                     │
              │                                      │
   op1 ──────►│   ┌─────────────────────────────┐   │
              │   │  加法器                      │   │
              │   │  减法器                      │   │
   op2 ──────►│   │  与/或/异或门                │───├──► result
              │   │  比较器                      │   │
  alu_op ────►│   │  移位器                      │   │
              │   └─────────────────────────────┘   │
              │                                      │
              └──────────────────────────────────────┘

支持的操作（RV32I）：
- ADD/SUB：加法/减法
- SLL/SRL/SRA：逻辑左移/逻辑右移/算术右移
- SLT/SLTU：有符号/无符号比较
- AND/OR/XOR：逻辑运算
```

**本仓库实现**（`src/execution.py`）：

```python
# ALU 各种运算
op1_signed = alu_op1.bitcast(Int(32))
op2_signed = alu_op2.bitcast(Int(32))

# 加法和减法
add_res = (op1_signed + op2_signed).bitcast(Bits(32))
sub_res = (op1_signed - op2_signed).bitcast(Bits(32))

# 逻辑运算
and_res = alu_op1 & alu_op2
or_res = alu_op1 | alu_op2
xor_res = alu_op1 ^ alu_op2

# 移位运算
shamt = alu_op2[0:4].bitcast(UInt(5))  # 移位量（低 5 位）
sll_res = alu_op1 << shamt  # 逻辑左移
srl_res = alu_op1 >> shamt  # 逻辑右移
sra_res = op1_signed >> shamt  # 算术右移（保持符号位）

# 比较运算
slt_res = (op1_signed < op2_signed).bitcast(Bits(32))  # 有符号比较
sltu_res = (alu_op1 < alu_op2).bitcast(Bits(32))  # 无符号比较

# 使用独热码选择结果
alu_result = ctrl.alu_func.select1hot(
    add_res, sub_res, sll_res, slt_res, sltu_res,
    xor_res, srl_res, sra_res, or_res, and_res, ...
)
```

### 3.5 数据存储器（Data Memory）

数据存储器用于存放程序运行时的数据，支持不同宽度的读写：

- **LB/SB**：读/写 1 字节（8 位）
- **LH/SH**：读/写半字（16 位）
- **LW/SW**：读/写字（32 位）

**本仓库实现**（`src/memory.py`）：

```python
# 数据对齐与符号扩展
# 根据地址低 2 位选择正确的字节/半字

# 选择半字
half_selected = alu_result[1:1].select(raw_mem[16:31], raw_mem[0:15])

# 选择字节
byte_selected = alu_result[0:0].select(half_selected[8:15], half_selected[0:7])

# 符号扩展（对于 LB/LH）
pad_bit_8 = mem_unsigned.select(Bits(1)(0), byte_selected[7:7])
padding_8 = pad_bit_8.select(Bits(24)(0xFFFFFF), Bits(24)(0))
byte_extended = concat(padding_8, byte_selected)
```

### 3.6 控制单元（Control Unit）

控制单元负责解码指令并生成控制信号，指导各个部件协同工作。

```
              ┌──────────────────────────────────────┐
              │           控制单元                    │
              │                                      │
instruction ─►│   解码逻辑                           │
              │   ┌───────────────────────────┐     │
              │   │ opcode → 指令类型          │     │──► alu_func
              │   │ funct3 → 具体操作          │     │──► mem_op
              │   │ funct7 → 区分变体          │     │──► branch_type
              │   └───────────────────────────┘     │──► ...
              │                                      │
              └──────────────────────────────────────┘
```

**本仓库实现**（`src/decoder.py`）：

```python
# 物理切片：从 32 位指令中提取各字段
opcode = inst[0:6]    # 操作码
rd = inst[7:11]       # 目标寄存器
funct3 = inst[12:14]  # 功能码 3
rs1 = inst[15:19]     # 源寄存器 1
rs2 = inst[20:24]     # 源寄存器 2
bit30 = inst[30:30]   # 用于区分 ADD/SUB, SRL/SRA

# 查表译码（遍历指令表生成控制信号）
for entry in rv32i_table:
    # 匹配 opcode, funct3, bit30
    match_if = opcode == t_op
    if t_f3 is not None:
        match_if &= funct3 == Bits(3)(t_f3)
    if t_b30 is not None:
        match_if &= bit30 == Bits(1)(t_b30)
    
    # 累加控制信号
    acc_alu_func |= match_if.select(t_alu, Bits(16)(0))
    acc_mem_op |= match_if.select(t_mem_op, Bits(3)(0))
    ...
```

---

## 4. 流水线技术

### 4.1 为什么需要流水线？

假设每条指令需要经过 5 个阶段，每个阶段需要 1ns：

**单周期 CPU**：
- 每条指令需要 5ns
- 执行 5 条指令需要 25ns

**五级流水线 CPU**：
- 像工厂流水线一样，不同指令同时处于不同阶段
- 理想情况下，每 1ns 完成一条指令
- 执行 5 条指令只需要 9ns（前 5ns 填充流水线 + 4ns）

```
单周期 CPU：
时间: |----5ns----|----5ns----|----5ns----|----5ns----|----5ns----|
指令:    inst1        inst2        inst3        inst4        inst5

五级流水线 CPU：
时间: |--1--|--1--|--1--|--1--|--1--|--1--|--1--|--1--|--1--|
      |IF|ID|EX|MEM|WB|                                    inst1
          |IF|ID|EX|MEM|WB|                                inst2
              |IF|ID|EX|MEM|WB|                            inst3
                  |IF|ID|EX|MEM|WB|                        inst4
                      |IF|ID|EX|MEM|WB|                    inst5
```

### 4.2 五级流水线阶段

本仓库实现了经典的五级流水线：

```
┌──────┐     ┌──────┐     ┌──────┐     ┌──────┐     ┌──────┐
│  IF  │────►│  ID  │────►│  EX  │────►│ MEM  │────►│  WB  │
│ 取指 │     │ 译码 │     │ 执行 │     │ 访存 │     │ 写回 │
└──────┘     └──────┘     └──────┘     └──────┘     └──────┘
    │            │            │            │            │
    ▼            ▼            ▼            ▼            ▼
 读取指令    解码指令      ALU运算     读写内存     写回寄存器
 计算PC+4    读寄存器      计算地址
             生成控制信号  判断分支
```

### 4.3 流水线寄存器

流水线各级之间通过 **流水线寄存器（Pipeline Register）** 传递数据。这些寄存器在时钟上升沿锁存数据。

```
┌────────┐   ┌─────────┐   ┌────────┐   ┌──────────┐   ┌─────────┐   ┌────────┐
│   IF   │──►│ IF/ID   │──►│   ID   │──►│  ID/EX   │──►│   EX    │──►│  ...   │
│        │   │ 流水线  │   │        │   │  流水线   │   │         │   │        │
│        │   │ 寄存器  │   │        │   │  寄存器   │   │         │   │        │
└────────┘   └─────────┘   └────────┘   └──────────┘   └─────────┘   └────────┘
```

**本仓库实现**：使用 Assassyn 的 `async_called` 机制自动生成 FIFO 作为流水线寄存器：

```python
# 在 DecoderImpl 中，向 EX 阶段发送数据
call = executor.async_called(
    ctrl=final_ex_ctrl,
    pc=pre.pc,
    rs1_data=pre.rs1_data,
    rs2_data=pre.rs2_data,
    imm=pre.imm,
)
# 设置 FIFO 深度为 1（刚性流水线）
call.bind.set_fifo_depth(ctrl=1, pc=1, rs1_data=1, rs2_data=1, imm=1)
```

---

## 5. Assassyn 语言简介

### 5.1 什么是 Assassyn？

**Assassyn** 是一种基于 Python 的硬件描述语言（HDL），用于描述数字电路。与传统的 Verilog/VHDL 相比，Assassyn 更加直观，适合硬件新手学习。

### 5.2 核心数据类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `Bits(n)` | n 位无符号位向量 | `Bits(32)(0x12345678)` |
| `UInt(n)` | n 位无符号整数（用于算术运算）| `UInt(32)(100)` |
| `Int(n)` | n 位有符号整数（补码表示）| `Int(32)(-1)` |
| `Record` | 硬件结构体（类似 C 的 struct）| `Record(a=Bits(5), b=Bits(32))` |

### 5.3 存储类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `RegArray(type, depth)` | 寄存器数组 | `RegArray(Bits(32), 32)` |
| `SRAM(width, depth)` | 大容量存储器 | `SRAM(width=32, depth=65536)` |

### 5.4 模块类型

| 类型 | 说明 | 使用场景 |
|------|------|---------|
| `Module` | 时序逻辑模块（有端口、有时钟）| 流水线各级 |
| `Downstream` | 纯组合逻辑模块（无状态）| 冒险检测单元 |

### 5.5 重要操作

```python
# 类型转换（重解释，不改变位模式）
signed_val = bits_val.bitcast(Int(32))

# 位截取（Assassyn 使用 [低位:高位] 闭区间格式）
byte = word[0:7]  # 取低 8 位

# 位拼接
result = concat(high_bits, low_bits)

# 二路选择器（MUX）
output = condition.select(true_value, false_value)

# 独热码选择器（多路 MUX）
result = onehot.select1hot(opt0, opt1, opt2, ...)

# 时序赋值（下一时钟沿生效）
reg[0] <= new_value

# 组合赋值（立即生效）
wire = value
```

---

## 6. 本仓库 CPU 实现详解

### 6.1 整体架构

```
                            ┌─────────────────────────────────────────────────────┐
                            │               RV32IM CPU 架构                        │
                            │                                                     │
  ┌──────────────────────────────────────────────────────────────────────────────┐│
  │                              五级流水线                                       ││
  │                                                                              ││
  │  ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐                       ││
  │  │  IF  │──►│  ID  │──►│  EX  │──►│ MEM  │──►│  WB  │                       ││
  │  │fetch │   │decode│   │ exec │   │memory│   │write │                       ││
  │  │.py   │   │er.py │   │ution │   │.py   │   │back  │                       ││
  │  │      │   │      │   │.py   │   │      │   │.py   │                       ││
  │  └──────┘   └──────┘   └──────┘   └──────┘   └──────┘                       ││
  │      │          │          │          │          │                          ││
  │      ▼          ▼          ▼          ▼          ▼                          ││
  │   ┌──────────────────────────────────────────────────────┐                  ││
  │   │                    旁路网络 (Forwarding)               │                  ││
  │   │                   data_hazard.py                     │                  ││
  │   └──────────────────────────────────────────────────────┘                  ││
  │                                                                              ││
  └──────────────────────────────────────────────────────────────────────────────┘│
                            │                                                     │
                            │           ┌─────────────┐                           │
                            │           │ 分支预测系统 │                           │
                            │           │  btb.py +   │                           │
                            │           │ tournament  │                           │
                            │           │_predictor.py│                           │
                            │           └─────────────┘                           │
                            │                                                     │
                            │   ┌─────────────┐    ┌─────────────┐               │
                            │   │ 乘法器      │    │ 除法器      │               │
                            │   │multiplier.py│    │ divider.py  │               │
                            │   │(3周期流水线) │    │(~10周期状态机)│              │
                            │   └─────────────┘    └─────────────┘               │
                            │                                                     │
                            └─────────────────────────────────────────────────────┘
```

### 6.2 IF 阶段：取指（Instruction Fetch）

**文件**：`src/fetch.py`

**硬件功能**：
1. 维护 PC 寄存器
2. 计算下一条指令地址
3. 向指令存储器发起读请求

**关键代码解析**：

```python
class FetcherImpl(Downstream):
    @downstream.combinational
    def build(self, pc_reg, pc_addr, last_pc_reg, decoder, stall_if, branch_target, ...):
        # 处理流水线暂停
        current_stall_if = stall_if.optional(Bits(1)(0))
        current_pc = current_stall_if.select(last_pc_reg[0], pc_addr)
        
        # 处理分支重定向
        flush_if = branch_target[0] != Bits(32)(0)
        final_current_pc = flush_if.select(branch_target[0], current_pc)
        
        # 默认下一 PC = 当前 PC + 4
        default_next_pc = (final_current_pc.bitcast(UInt(32)) + UInt(32)(4)).bitcast(Bits(32))
        
        # 分支预测（如果启用）
        if btb_impl is not None:
            btb_hit, btb_predicted_target = btb_impl.predict(...)
            predicted_next_pc = btb_hit.select(
                tp_predict_taken.select(btb_predicted_target, default_next_pc),
                default_next_pc,
            )
        
        # 更新 PC 寄存器
        pc_reg[0] <= final_next_pc
        
        # 向 Decoder 发送指令
        call = decoder.async_called(pc=final_current_pc, next_pc=final_next_pc, stall=current_stall_if)
        call.bind.set_fifo_depth(pc=1)
```

**硬件理解**：
- `pc_reg[0] <= final_next_pc`：这是一个 D 触发器，在时钟上升沿更新
- `async_called`：生成一个 FIFO（深度为 1），作为 IF/ID 流水线寄存器
- 多路选择器用于处理 stall/flush 条件

### 6.3 ID 阶段：译码（Instruction Decode）

**文件**：`src/decoder.py`

**硬件功能**：
1. 解析指令格式，提取各字段
2. 查表生成控制信号
3. 读取寄存器堆
4. 生成立即数

**关键代码解析**：

```python
class Decoder(Module):
    def __init__(self):
        super().__init__(
            ports={
                "pc": Port(Bits(32)),
                "next_pc": Port(Bits(32)),
                "stall": Port(Bits(1)),
            }
        )
    
    @module.combinational
    def build(self, icache_dout, reg_file):
        # 弹出端口数据
        pc_val, next_pc_val, stall_if = self.pop_all_ports(False)
        inst = icache_dout[0].bitcast(Bits(32))
        
        # 物理切片
        opcode = inst[0:6]
        rd = inst[7:11]
        funct3 = inst[12:14]
        rs1 = inst[15:19]
        rs2 = inst[20:24]
        
        # 立即数生成
        sign = inst[31:31]
        pad_20 = sign.select(Bits(20)(0xFFFFF), Bits(20)(0))  # 符号扩展
        imm_i = concat(pad_20, inst[20:31])  # I 型立即数
        
        # 查表译码（累加控制信号）
        for entry in rv32i_table:
            match_if = opcode == t_op
            acc_alu_func |= match_if.select(t_alu, Bits(16)(0))
            ...
        
        # 读取寄存器堆
        raw_rs1_data = reg_file[rs1]
        raw_rs2_data = reg_file[rs2]
```

**硬件理解**：
- 指令切片是纯组合逻辑（多路分线器）
- 查表译码生成一个巨大的多路选择器树
- 立即数生成器是一组固定的连线和扩展逻辑

### 6.4 EX 阶段：执行（Execution）

**文件**：`src/execution.py`

**硬件功能**：
1. ALU 运算
2. 分支目标计算
3. 分支条件判断
4. 数据旁路选择

**关键代码解析**：

```python
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
        # M 扩展功能单元
        self.multiplier = WallaceTreeMul()
        self.divider = Radix16Divider()
    
    @module.combinational
    def build(self, mem_module, ex_bypass, mem_bypass, wb_bypass, branch_target_reg, ...):
        # 旁路数据选择（解决数据冒险）
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
        add_res = (op1_signed + op2_signed).bitcast(Bits(32))
        alu_result = ctrl.alu_func.select1hot(add_res, sub_res, ...)
        
        # 分支处理
        target_base = is_jalr.select(real_rs1, pc)
        calc_target = (target_base_signed + imm_signed).bitcast(Bits(32))
        is_taken = is_taken_eq | is_taken_ne | ...
        
        # 更新旁路寄存器
        ex_bypass[0] = final_result
```

**硬件理解**：
- ALU 是多个运算单元的并行组合，通过 MUX 选择结果
- 旁路网络是一组多路选择器，根据冒险检测结果选择数据源
- 分支目标计算器是一个专用加法器

### 6.5 MEM 阶段：访存（Memory Access）

**文件**：`src/memory.py`

**硬件功能**：
1. 处理 Load/Store 指令
2. 数据对齐和符号扩展
3. 传递 ALU 结果

**关键代码解析**：

```python
class MemoryAccess(Module):
    @module.combinational
    def build(self, wb_module, sram_dout, mem_bypass_reg):
        ctrl, alu_result = self.pop_all_ports(False)
        
        # 读取 SRAM 数据
        raw_mem = sram_dout[0].bitcast(Bits(32))
        
        # 数据对齐（根据地址低位选择字节/半字）
        half_selected = alu_result[1:1].select(raw_mem[16:31], raw_mem[0:15])
        byte_selected = alu_result[0:0].select(half_selected[8:15], half_selected[0:7])
        
        # 符号扩展
        pad_bit_8 = mem_unsigned.select(Bits(1)(0), byte_selected[7:7])
        padding_8 = pad_bit_8.select(Bits(24)(0xFFFFFF), Bits(24)(0))
        byte_extended = concat(padding_8, byte_selected)
        
        # 最终数据选择（Load 用内存数据，否则用 ALU 结果）
        final_data = is_load.select(processed_mem_result, alu_result)
        
        # 更新旁路寄存器
        mem_bypass_reg[0] = final_data
```

**硬件理解**：
- 数据对齐器是一组多路选择器
- 符号扩展逻辑根据最高位填充 0 或 1

### 6.6 WB 阶段：写回（Write Back）

**文件**：`src/writeback.py`

**硬件功能**：
1. 将计算结果写回寄存器堆
2. 处理仿真终止

**关键代码解析**：

```python
class WriteBack(Module):
    @module.combinational
    def build(self, reg_file, wb_bypass_reg):
        wb_ctrl, wdata = self.pop_all_ports(False)
        rd = wb_ctrl.rd_addr
        halt_if = wb_ctrl.halt_if
        
        # 写回逻辑（x0 不写入）
        with Condition(rd != Bits(5)(0)):
            reg_file[rd] = wdata
            wb_bypass_reg[0] = wdata
        
        # 仿真终止检测
        with Condition(halt_if == Bits(1)(1)):
            finish()
        
        return rd
```

**硬件理解**：
- `reg_file[rd] = wdata` 驱动寄存器堆的写端口
- `Condition` 生成写使能信号

---

## 7. 冒险与解决方案

### 7.1 什么是流水线冒险？

流水线中存在三种冒险：

| 类型 | 描述 | 示例 |
|------|------|------|
| **结构冒险** | 多条指令同时需要同一硬件资源 | 同时访问内存 |
| **数据冒险** | 后续指令依赖前面指令的结果 | `add x1, x2, x3` 后接 `sub x4, x1, x5` |
| **控制冒险** | 分支指令改变执行流程 | `beq x1, x2, label` |

### 7.2 数据冒险与旁路（Forwarding）

**问题场景**：

```
Cycle 1: add x1, x2, x3    ; x1 = x2 + x3，结果在 Cycle 5 写回
Cycle 2: sub x4, x1, x5    ; 需要 x1 的值，但 x1 还没写回！
```

**解决方案：数据旁路**

不等数据写回寄存器堆，直接从流水线中"旁路"过来：

```
                 ┌─────────────────────────────────────────────┐
                 │              旁路网络                         │
                 │                                             │
  EX_bypass ────►│  ┌───────────────────────┐                 │
                 │  │                       │                 │
  MEM_bypass ───►│  │       多路选择器       │────────────────►│ 实际 rs1 数据
                 │  │                       │                 │
  WB_bypass ────►│  │                       │                 │
                 │  └───────────────────────┘                 │
  原始 rs1 ─────►│           ▲                                │
                 │           │                                │
                 │       rs1_sel                              │
                 └─────────────────────────────────────────────┘
```

**本仓库实现**（`src/data_hazard.py`）：

```python
class DataHazardUnit(Downstream):
    @downstream.combinational
    def build(self, rs1_idx, rs2_idx, ex_rd, ex_is_load, mem_rd, wb_rd, ...):
        # 检测旁路条件（优先级：EX > MEM > WB）
        rs1_wb_pass = (rs1_idx == wb_rd).select(Rs1Sel.WB_BYPASS, Rs1Sel.RS1)
        rs1_mem_bypass = (rs1_idx == mem_rd).select(Rs1Sel.MEM_BYPASS, rs1_wb_pass)
        rs1_ex_bypass = ((rs1_idx == ex_rd) & ~ex_result_not_ready).select(
            Rs1Sel.EX_BYPASS, rs1_mem_bypass
        )
        
        # 检测 Load-Use 冒险（必须暂停）
        load_use_hazard = ex_is_load & (rs1_idx == ex_rd)
        stall_if = load_use_hazard | mul_busy | div_busy
        
        return rs1_sel, rs2_sel, stall_if
```

### 7.3 Load-Use 冒险

**问题场景**：

```
lw  x1, 0(x2)    ; 从内存加载数据到 x1，数据在 MEM 阶段才可用
add x3, x1, x4   ; 需要 x1，但 EX 阶段时 lw 还在 MEM 阶段！
```

**解决方案**：暂停流水线 1 个周期

```
Cycle: | 1   | 2   | 3   | 4   | 5   | 6   | 7   |
lw:    | IF  | ID  | EX  | MEM | WB  |     |     |
add:   |     | IF  | ID  |stall| EX  | MEM | WB  |
                              ↑
                         暂停 1 周期，等待 lw 的数据
```

### 7.4 控制冒险与分支预测

**问题场景**：

```
beq x1, x2, label    ; 分支指令，需要在 EX 阶段才知道是否跳转
??? (下一条指令)      ; 取哪条指令？
```

**解决方案**：分支预测

在 IF 阶段预测分支结果，如果预测错误则刷新流水线。详见第 8 节。

---

## 8. 分支预测

### 8.1 为什么需要分支预测？

如果等到分支结果确定再取下一条指令，会浪费 2 个周期（分支惩罚）。分支预测通过"猜测"分支方向，让流水线继续工作。

### 8.2 BTB（分支目标缓冲器）

**文件**：`src/btb.py`

BTB 缓存历史分支的目标地址：

```
              ┌──────────────────────────────────────┐
              │              BTB (64 条目)            │
              │                                      │
  PC[7:2] ───►│   Index  │ Valid │  Tag   │ Target  │
              │     0    │   1   │ 0x400  │ 0x420   │
              │     1    │   0   │   -    │   -     │
              │    ...   │  ...  │  ...   │  ...    │
              └──────────────────────────────────────┘
```

**关键代码**：

```python
class BTBImpl:
    def predict(self, pc, btb_valid, btb_tags, btb_targets):
        # 计算索引
        index = (pc >> UInt(32)(2)) & Bits(32)(0x3F)
        
        # 查找
        entry_valid = btb_valid[index]
        entry_tag = btb_tags[index]
        entry_target = btb_targets[index]
        
        # 判断命中
        hit = entry_valid & (entry_tag == pc)
        return hit, entry_target
    
    def update(self, pc, target, should_update, ...):
        with Condition(should_update == Bits(1)(1)):
            btb_valid[index] <= Bits(1)(1)
            btb_tags[index] <= pc
            btb_targets[index] <= target
```

### 8.3 Tournament 预测器

**文件**：`src/tournament_predictor.py`

结合两种预测算法，选择更准确的那个：

```
                 ┌─────────────────────────────────────────┐
                 │         Tournament Predictor            │
                 │                                         │
  PC ───────────►│  ┌────────────┐    ┌────────────┐      │
                 │  │  Bimodal   │    │   Gshare   │      │
  GHR ──────────►│  │  (局部)    │    │   (全局)    │      │
                 │  └─────┬──────┘    └─────┬──────┘      │
                 │        │                 │              │
                 │        └────────┬────────┘              │
                 │                 │                       │
                 │         ┌───────▼───────┐              │
                 │         │   Selector    │              │
                 │         │  (选择器)      │              │
                 │         └───────┬───────┘              │
                 │                 │                       │
                 │                 ▼                       │
                 │          predict_taken                 │
                 └─────────────────────────────────────────┘
```

**预测流程**：
1. Bimodal：用 PC 索引查找 2-bit 计数器
2. Gshare：用 PC XOR 全局历史索引查找计数器
3. Selector：选择历史上更准确的预测器

---

## 9. 乘除法器实现

### 9.1 Wallace Tree 乘法器

**文件**：`src/multiplier.py`

乘法器使用 Wallace Tree 压缩算法，将 32x32 乘法分解为 3 个流水线阶段：

```
                 ┌─────────────────────────────────────────┐
                 │        Wallace Tree 乘法器              │
                 │                                         │
                 │  Cycle 1 (M1): 生成 32 个部分积         │
                 │                Wallace Tree Level 1-3   │
                 │                32 → 10 行               │
                 │                                         │
                 │  Cycle 2 (M2): Wallace Tree Level 4-6   │
                 │                10 → 4 行                │
                 │                                         │
                 │  Cycle 3 (M3): Wallace Tree Level 7-8   │
                 │                4 → 2 行                 │
                 │                + CPA 最终加法           │
                 └─────────────────────────────────────────┘
```

**3:2 压缩器（全加器）**：

```python
def full_adder_64bit(a, b, c):
    # XOR 计算和
    sum_result = a ^ b ^ c
    # 多数投票计算进位
    carry_unshifted = (a & b) | (b & c) | (a & c)
    carry_shifted = concat(carry_unshifted[0:62], Bits(1)(0))
    return (sum_result, carry_shifted)
```

### 9.2 Radix-16 除法器

**文件**：`src/divider.py`

除法器使用 Radix-16（基 16）算法，每个周期计算 4 位商：

```
                 ┌─────────────────────────────────────────┐
                 │        Radix-16 除法器                   │
                 │                                         │
                 │  状态机：                                │
                 │    IDLE → DIV_PRE → DIV_WORKING → END   │
                 │                                         │
                 │  DIV_PRE: 计算 1d, 2d, ..., 15d         │
                 │                                         │
                 │  DIV_WORKING: (8 次迭代)                 │
                 │    - 左移余数 4 位                       │
                 │    - QDS 选择商位 (0-15)                 │
                 │    - 更新余数                            │
                 │                                         │
                 │  总周期: 1 + 8 + 1 = 10 周期            │
                 └─────────────────────────────────────────┘
```

**QDS（商位选择）算法**：

```python
def quotient_select(self, shifted_rem, d1, d2, ..., d15):
    # 并行比较（在硬件中同时进行）
    ge_8d = (shifted_rem >= d8)
    ge_4d = (shifted_rem >= d4)
    # ... 更多比较
    
    # 二叉搜索树结构选择商位
    q3 = ge_8d
    q2 = ge_8d.select(ge_12d, ge_4d)
    q1 = ...
    q0 = ...
    
    return concat(q3, q2, q1, q0)  # 4-bit 商位
```

---

## 10. 总结与进阶学习

### 10.1 本仓库实现的 CPU 特性总结

| 特性 | 实现 | 文件 |
|------|------|------|
| 指令集 | RV32I + M 扩展 | - |
| 流水线 | 五级流水线 | `fetch.py`, `decoder.py`, `execution.py`, `memory.py`, `writeback.py` |
| 数据冒险 | 全旁路 + Load-Use 暂停 | `data_hazard.py` |
| 控制冒险 | BTB + Tournament Predictor | `btb.py`, `tournament_predictor.py` |
| 乘法 | 3 周期 Wallace Tree | `multiplier.py` |
| 除法 | ~10 周期 Radix-16 | `divider.py` |

### 10.2 关键设计决策

1. **刚性流水线**：FIFO 深度为 1，简化控制逻辑
2. **统一内存**：指令和数据共享一个 SRAM
3. **独热码控制信号**：使用 `select1hot` 简化多路选择器
4. **模块化设计**：Module/Downstream 分离时序/组合逻辑

### 10.3 进阶学习建议

1. **阅读现有文档**：
   - `docs/Assassyn_语言完整说明书.md`：Assassyn 语法详解
   - `docs/Module/*.md`：各模块设计文档
   - `docs/Module/BranchPrediction.md`：分支预测详解

2. **运行测试用例**：
   ```bash
   # 运行单元测试（需要 Assassyn 环境）
   apptainer exec --bind $(pwd) /path/to/assassyn.sif pytest tests/
   ```

3. **修改代码实验**：
   - 尝试修改 BTB 大小，观察性能变化
   - 添加新的 ALU 操作
   - 实现其他分支预测算法

4. **扩展阅读**：
   - 《计算机组成与设计：硬件/软件接口》
   - 《计算机体系结构：量化研究方法》
   - RISC-V 官方规范

---

## 附录 A：文件结构索引

```
src/
├── main.py                  # 顶层模块，构建 CPU 系统
├── fetch.py                 # IF 阶段：取指
├── decoder.py               # ID 阶段：译码
├── execution.py             # EX 阶段：执行
├── memory.py                # MEM 阶段：访存
├── writeback.py             # WB 阶段：写回
├── control_signals.py       # 控制信号定义
├── instruction_table.py     # 指令译码表
├── data_hazard.py           # 数据冒险检测单元
├── hazard_unit.py           # 冒险单元入口
├── btb.py                   # 分支目标缓冲器
├── tournament_predictor.py  # Tournament 预测器
├── multiplier.py            # Wallace Tree 乘法器
├── divider.py               # Radix-16 除法器
└── debug_utils.py           # 调试工具
```

## 附录 B：控制信号编码参考

### B.1 ALU 功能码（独热码）

| 信号 | 编码 | 操作 |
|------|------|------|
| `ALUOp.ADD` | `0x0001` | 加法 |
| `ALUOp.SUB` | `0x0002` | 减法 |
| `ALUOp.SLL` | `0x0004` | 逻辑左移 |
| `ALUOp.SLT` | `0x0008` | 有符号比较 |
| `ALUOp.SLTU` | `0x0010` | 无符号比较 |
| `ALUOp.XOR` | `0x0020` | 异或 |
| `ALUOp.SRL` | `0x0040` | 逻辑右移 |
| `ALUOp.SRA` | `0x0080` | 算术右移 |
| `ALUOp.OR` | `0x0100` | 或 |
| `ALUOp.AND` | `0x0200` | 与 |
| `ALUOp.MUL` | `0x0800` | 乘法（低 32 位）|
| `ALUOp.NOP` | `0x8000` | 空操作 |

### B.2 内存操作码

| 信号 | 编码 | 操作 |
|------|------|------|
| `MemOp.NONE` | `0b001` | 无内存操作 |
| `MemOp.LOAD` | `0b010` | 加载 |
| `MemOp.STORE` | `0b100` | 存储 |

### B.3 分支类型

| 信号 | 编码 | 条件 |
|------|------|------|
| `BranchType.NO_BRANCH` | `0x0001` | 无分支 |
| `BranchType.BEQ` | `0x0002` | 相等 |
| `BranchType.BNE` | `0x0004` | 不相等 |
| `BranchType.BLT` | `0x0008` | 有符号小于 |
| `BranchType.BGE` | `0x0010` | 有符号大于等于 |
| `BranchType.BLTU` | `0x0020` | 无符号小于 |
| `BranchType.BGEU` | `0x0040` | 无符号大于等于 |
| `BranchType.JAL` | `0x0080` | 直接跳转 |
| `BranchType.JALR` | `0x0100` | 寄存器跳转 |

---

*本文档基于 Assassyn-CPU 仓库整理，希望能帮助硬件新手理解 CPU 的基本原理和实现方法。*
