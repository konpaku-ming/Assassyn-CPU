# RV32IM CPU 乘除法硬件实现详解

本文档详细介绍本项目中乘法器与除法器的硬件实现原理，并结合 Assassyn 代码进行说明。文档适合对硬件原理不熟悉的初学者阅读。

---

## 目录

1. [概述](#1-概述)
2. [乘法器硬件实现](#2-乘法器硬件实现)
   - [2.1 Wallace Tree 乘法器原理](#21-wallace-tree-乘法器原理)
   - [2.2 Assassyn 代码实现详解](#22-assassyn-代码实现详解)
   - [2.3 时钟周期分析](#23-时钟周期分析)
3. [除法器硬件实现](#3-除法器硬件实现)
   - [3.1 恢复除法算法原理](#31-恢复除法算法原理)
   - [3.2 Radix-4 恢复除法算法](#32-radix-4-恢复除法算法)
   - [3.3 Assassyn 代码实现详解](#33-assassyn-代码实现详解)
   - [3.4 时钟周期分析](#34-时钟周期分析)
4. [RV32IM 扩展指令执行流程](#4-rv32im-扩展指令执行流程)
   - [4.1 乘法指令 (MUL/MULH/MULHSU/MULHU)](#41-乘法指令-mulmulhmulhsumulhu)
   - [4.2 除法指令 (DIV/DIVU)](#42-除法指令-divdivu)
   - [4.3 取模指令 (REM/REMU)](#43-取模指令-remremu)
5. [附录](#5-附录)

---

## 1. 概述

### 1.1 什么是 RV32IM

RV32IM 是 RISC-V 指令集架构的一个变体：
- **RV32I**：32位基础整数指令集
- **M 扩展**：标准乘法和除法扩展

M 扩展包含 8 条指令：

| 指令 | 功能 | 编码 (funct3, funct7) |
|------|------|----------------------|
| MUL | 有符号 × 有符号 → 低32位 | 0x0, 0x01 |
| MULH | 有符号 × 有符号 → 高32位 | 0x1, 0x01 |
| MULHSU | 有符号 × 无符号 → 高32位 | 0x2, 0x01 |
| MULHU | 无符号 × 无符号 → 高32位 | 0x3, 0x01 |
| DIV | 有符号 ÷ 有符号 → 商 | 0x4, 0x01 |
| DIVU | 无符号 ÷ 无符号 → 商 | 0x5, 0x01 |
| REM | 有符号 ÷ 有符号 → 余数 | 0x6, 0x01 |
| REMU | 无符号 ÷ 无符号 → 余数 | 0x7, 0x01 |

### 1.2 为什么乘除法需要特殊硬件

在数字电路中，加法和减法可以在一个时钟周期内完成（使用加法器/减法器）。但乘法和除法的计算复杂度更高：

- **乘法**：32位 × 32位 需要处理 32 个部分积，直接相加会产生巨大的延迟
- **除法**：需要迭代计算每一位商，天然是多周期操作

因此，现代 CPU 使用专门的硬件单元来加速这些操作。

### 1.3 本项目的实现方案

| 运算 | 实现方案 | 周期数 |
|------|----------|--------|
| 乘法 | 3级流水线 Wallace Tree 乘法器 | 3 周期 |
| 除法 | SRT-4 (Sweeney-Robertson-Tocher) 除法器 | ~18 周期 |
| 除法（备选） | 逐位恢复除法器 | ~34 周期 |

---

## 2. 乘法器硬件实现

### 2.1 Wallace Tree 乘法器原理

#### 2.1.1 基础知识：二进制乘法

让我们从一个简单的例子开始，理解二进制乘法的本质。

假设我们要计算 5 × 3（二进制：101 × 011）：

```
        1 0 1  (被乘数 A = 5)
      × 0 1 1  (乘数 B = 3)
      -------
        1 0 1  ← 部分积 pp[0] = A × B[0]，左移 0 位
      1 0 1    ← 部分积 pp[1] = A × B[1]，左移 1 位
    0 0 0      ← 部分积 pp[2] = A × B[2]，左移 2 位
    ---------
    0 1 1 1 1  = 15
```

**关键概念**：
1. **部分积 (Partial Product)**：乘数的每一位与被乘数相乘的结果
2. 对于 N 位乘法，有 N 个部分积
3. 每个部分积需要左移相应的位数
4. 最终结果 = 所有部分积之和

#### 2.1.2 部分积生成的硬件实现

在硬件中，生成部分积非常简单：

```
部分积 pp[i] = A AND (B[i] 复制 32 次)
```

用更形式化的表示：
- 如果 `B[i] = 1`，则 `pp[i] = A`（左移 i 位）
- 如果 `B[i] = 0`，则 `pp[i] = 0`

这只需要 32 个 AND 门阵列就能实现。

#### 2.1.3 问题：如何高效相加 32 个部分积？

最简单的方法是使用链式加法器：

```
结果 = pp[0] + pp[1] + pp[2] + ... + pp[31]
```

但这需要 31 次加法操作，每次加法都有进位传播延迟，总延迟非常大！

#### 2.1.4 Wallace Tree 的解决方案

Wallace Tree 是一种并行压缩结构，使用以下组件快速减少部分积数量：

**3:2 压缩器（全加器）**

```
输入：a, b, c （三个1位数）
输出：sum, carry

sum   = a ⊕ b ⊕ c        （异或）
carry = (a·b) | (b·c) | (a·c)  （多数表决）
```

这个电路的关键特性：将 3 个数压缩成 2 个数（sum + carry），且 carry 需要左移 1 位。

**2:2 压缩器（半加器）**

```
输入：a, b （两个1位数）
输出：sum, carry

sum   = a ⊕ b
carry = a · b
```

**为什么需要 2:2 压缩器？**

- 在 Wallace Tree 的某些列里，压缩到较高层时只剩下 2 个比特（例如 Level 5 的末尾列只剩一行 sum 和一行 carry），这时强行用 3:2 压缩器需要人为补 0，不仅浪费门级，还增加无意义的布线和延迟。
- 使用 2:2 压缩器可以在不引入额外进位链的情况下把列高从 2 行变成 “sum+carry” 两行（其中 carry 左移 1 位），为下一层保持统一的行数，避免最终 CPA 需要处理 5 行甚至更多的结果。
- 在本 CPU 的 3 级流水线实现里，Level 5 需要 1 个 3:2 压缩器 + 1 个 2:2 压缩器才能把 5 行压成 4 行，如果没有 2:2 压缩器，就必须多插一层 3:2 压缩（增加一级延迟或更长的组合路径），会破坏当前每周期一层压缩的节奏。

#### 2.1.5 Wallace Tree 压缩过程

对于 32 个部分积，Wallace Tree 逐层压缩：

```
级别 0: 32 行 (原始部分积)
        ↓ 用 10 个 3:2 压缩器处理 30 行，保留 2 行
级别 1: 22 行
        ↓ 用 7 个 3:2 压缩器
级别 2: 15 行
        ↓ 用 5 个 3:2 压缩器
级别 3: 10 行
        ↓ 用 3 个 3:2 压缩器
级别 4: 7 行
        ↓ 用 2 个 3:2 压缩器
级别 5: 5 行
        ↓ 用 1 个 3:2 压缩器 + 1 个 2:2 压缩器
级别 6: 4 行
        ↓ 用 1 个 3:2 压缩器
级别 7: 3 行
        ↓ 用 1 个 3:2 压缩器
级别 8: 2 行 (最终结果)
```

最后，用一个快速加法器（如 Carry-Lookahead Adder）将最后 2 行相加，得到最终的 64 位乘积。

**Wallace Tree 的优势**：
- 压缩是并行进行的，各列独立
- 延迟与部分积数量的对数成正比：O(log n)
- 32 个部分积只需要约 9 级压缩

### 2.2 Assassyn 代码实现详解

在 `src/multiplier.py` 中，我们实现了 3 周期流水线 Wallace Tree 乘法器。

#### 2.2.1 整体架构

根据 `src/multiplier.py` 的实现，乘法器采用真正的 Wallace Tree 压缩结构：

```python
class WallaceTreeMul:
    """
    3-cycle pipelined Wallace Tree multiplier
    
    Cycle 1 (EX_M1): 部分积生成 + Wallace Tree Levels 1-3 (32 → 10 rows)
    Cycle 2 (EX_M2): Wallace Tree Levels 4-6 (10 → 4 rows)
    Cycle 3 (EX_M3): Wallace Tree Levels 7-8 (4 → 2 rows) + CPA 加法
    """
```

#### 2.2.2 3:2 和 2:2 压缩器的硬件实现

Wallace Tree 的核心组件是压缩器。在 `src/multiplier.py` 中定义了两种压缩器：

**3:2 压缩器（全加器）**：

```python
def full_adder_64bit(a: Bits, b: Bits, c: Bits) -> tuple:
    """
    64-bit 3:2 compressor (Full Adder)
    
    Takes 3 64-bit inputs and produces:
    - sum: 64-bit XOR result (a ⊕ b ⊕ c)
    - carry: 64-bit carry result ((a&b) | (b&c) | (a&c)), shifted left by 1 bit
    """
    # XOR for sum: sum[i] = a[i] ⊕ b[i] ⊕ c[i]
    sum_result = a ^ b ^ c

    # Majority function for carry: carry[i] = (a[i]&b[i]) | (b[i]&c[i]) | (a[i]&c[i])
    carry_unshifted = (a & b) | (b & c) | (a & c)

    # Carry is shifted left by 1 bit (carry[i+1] in hardware)
    carry_shifted = concat(carry_unshifted[0:62], Bits(1)(0))

    return (sum_result, carry_shifted)
```

**2:2 压缩器（半加器）**：

```python
def half_adder_64bit(a: Bits, b: Bits) -> tuple:
    """
    64-bit 2:2 compressor (Half Adder)
    """
    sum_result = a ^ b              # XOR for sum
    carry_unshifted = a & b         # AND for carry
    carry_shifted = concat(carry_unshifted[0:62], Bits(1)(0))
    return (sum_result, carry_shifted)
```

#### 2.2.3 流水线寄存器定义

在 Assassyn 中，我们使用 `RegArray` 定义寄存器。实际代码中的寄存器定义如下：

```python
def __init__(self):
    # 阶段 1 寄存器 (EX_M1)
    self.m1_valid = RegArray(Bits(1), 1, initializer=[0])      # 有效位
    self.m1_op1 = RegArray(Bits(32), 1, initializer=[0])       # 操作数 1
    self.m1_op2 = RegArray(Bits(32), 1, initializer=[0])       # 操作数 2
    self.m1_op1_signed = RegArray(Bits(1), 1, initializer=[0]) # op1 是否有符号
    self.m1_op2_signed = RegArray(Bits(1), 1, initializer=[0]) # op2 是否有符号
    self.m1_result_high = RegArray(Bits(1), 1, initializer=[0]) # 返回高32位还是低32位
    self.m1_rd = RegArray(Bits(5), 1, initializer=[0])         # 目标寄存器

    # 阶段 2 寄存器 (EX_M2) - 存储 10 行中间结果（Level 3 输出）
    self.m2_valid = RegArray(Bits(1), 1, initializer=[0])
    self.m2_result_high = RegArray(Bits(1), 1, initializer=[0])
    self.m2_rd = RegArray(Bits(5), 1, initializer=[0])
    # 10 个 64 位寄存器存储 Wallace Tree Level 3 的输出
    self.m2_row0 = RegArray(Bits(64), 1, initializer=[0])
    self.m2_row1 = RegArray(Bits(64), 1, initializer=[0])
    # ... (m2_row2 到 m2_row9)

    # 阶段 3 寄存器 (EX_M3) - 存储 4 行中间结果（Level 6 输出）
    self.m3_valid = RegArray(Bits(1), 1, initializer=[0])
    self.m3_result_high = RegArray(Bits(1), 1, initializer=[0])
    self.m3_rd = RegArray(Bits(5), 1, initializer=[0])
    # 4 个 64 位寄存器存储 Wallace Tree Level 6 的输出
    self.m3_row0 = RegArray(Bits(64), 1, initializer=[0])
    self.m3_row1 = RegArray(Bits(64), 1, initializer=[0])
    self.m3_row2 = RegArray(Bits(64), 1, initializer=[0])
    self.m3_row3 = RegArray(Bits(64), 1, initializer=[0])

    # 最终结果
    self.m3_result_ready = RegArray(Bits(1), 1, initializer=[0])
    self.m3_result = RegArray(Bits(32), 1, initializer=[0])
```

**硬件含义说明**：
- `RegArray(Bits(64), 1)` 表示一个 64 位宽的寄存器
- `initializer=[0]` 表示复位后初值为 0
- 这些寄存器在真实硬件中是触发器阵列，在时钟上升沿锁存数据
- 阶段间需要存储多行中间结果（10 行或 4 行）以保存 Wallace Tree 的压缩状态

#### 2.2.4 符号扩展函数

```python
def sign_zero_extend(op: Bits, signed: Bits) -> Bits:
    """
    将 32 位操作数扩展到 64 位
    - signed=1: 符号扩展（复制符号位）
    - signed=0: 零扩展
    """
    sign_bit = op[31:31]                                    # 提取符号位
    sign_ext = sign_bit.select(Bits(32)(0xFFFFFFFF), Bits(32)(0))  # 符号位扩展
    ext_high = signed.select(sign_ext, Bits(32)(0))         # 根据是否有符号选择
    return concat(ext_high, op)                             # 拼接成 64 位
```

**硬件含义说明**：
- `op[31:31]` 是位选择操作，提取第 31 位（最高位）
- `select(a, b)` 是多路复用器（MUX）：条件为真选 a，否则选 b
- `concat(high, low)` 是位拼接，将两个信号连接成更宽的信号

#### 2.2.5 阶段 1：部分积生成 + Wallace Tree Levels 1-3

实际代码（`src/multiplier.py` 的 `cycle_m1` 函数）实现了完整的部分积生成和前三层压缩：

```python
def cycle_m1(self):
    """
    EX_M1 阶段：部分积生成 + Wallace Tree Levels 1-3
    
    1. 对乘数 B 的每一位 i，生成 pp[i] = A AND {64{B[i]}}，左移 i 位
    2. 应用 Wallace Tree Levels 1-3，将 32 行压缩到 10 行
    """
    with Condition(self.m1_valid[0] == Bits(1)(1)):
        op1 = self.m1_op1[0]
        op2 = self.m1_op2[0]
        op1_signed = self.m1_op1_signed[0]
        
        # 符号/零扩展到 64 位
        op1_ext = sign_zero_extend(op1, op1_signed)
        
        # 生成 32 个部分积（每个根据 op2 对应位决定是否有效）
        # pp[i] = op2[i] ? (op1_ext << i) : 0
        pp0 = op2[0:0].select(op1_ext, Bits(64)(0))
        pp1 = op2[1:1].select(concat(op1_ext[0:62], Bits(1)(0)), Bits(64)(0))
        pp2 = op2[2:2].select(concat(op1_ext[0:61], Bits(2)(0)), Bits(64)(0))
        # ... (pp3 到 pp31，每个左移相应位数)
        
        # === Wallace Tree Level 1: 32 → 22 rows ===
        # 使用 10 个 3:2 压缩器处理 30 行，保留 2 行
        s1_0, c1_0 = full_adder_64bit(pp0, pp1, pp2)
        s1_1, c1_1 = full_adder_64bit(pp3, pp4, pp5)
        # ... (s1_2 到 s1_9)
        # Passthrough: pp30, pp31
        
        # === Wallace Tree Level 2: 22 → 15 rows ===
        s2_0, c2_0 = full_adder_64bit(s1_0, c1_0, s1_1)
        s2_1, c2_1 = full_adder_64bit(c1_1, s1_2, c1_2)
        # ... (s2_2 到 s2_6)
        
        # === Wallace Tree Level 3: 15 → 10 rows ===
        s3_0, c3_0 = full_adder_64bit(s2_0, c2_0, s2_1)
        s3_1, c3_1 = full_adder_64bit(c2_1, s2_2, c2_2)
        # ... (s3_2 到 s3_4)
        
        # 存储 10 行中间结果到 M2 寄存器
        self.m2_row0[0] = s3_0
        self.m2_row1[0] = c3_0
        # ... (m2_row2 到 m2_row9)
        
        self.m2_valid[0] = Bits(1)(1)
        self.m1_valid[0] = Bits(1)(0)
```

**硬件含义说明**：
- `with Condition(...)` 类似于 Verilog 的 `if` 语句，生成条件控制逻辑
- `concat(op1_ext[0:62], Bits(1)(0))` 实现左移 1 位（高位截断，低位补 0）
- `full_adder_64bit` 是 3:2 压缩器，将 3 个 64 位数压缩成 2 个 64 位数（sum 和 carry）

#### 2.2.6 阶段 2：Wallace Tree Levels 4-6

```python
def cycle_m2(self):
    """
    EX_M2 阶段：Wallace Tree Levels 4-6 (10 → 4 rows)
    """
    with Condition(self.m2_valid[0] == Bits(1)(1)):
        # 读取 Level 3 输出（10 行）
        s3_0 = self.m2_row0[0]
        c3_0 = self.m2_row1[0]
        # ... (s3_1 到 c3_4)
        
        # === Level 4: 10 → 7 rows ===
        s4_0, c4_0 = full_adder_64bit(s3_0, c3_0, s3_1)
        s4_1, c4_1 = full_adder_64bit(c3_1, s3_2, c3_2)
        s4_2, c4_2 = full_adder_64bit(s3_3, c3_3, s3_4)
        # Passthrough: c3_4
        
        # === Level 5: 7 → 5 rows ===
        s5_0, c5_0 = full_adder_64bit(s4_0, c4_0, s4_1)
        s5_1, c5_1 = full_adder_64bit(c4_1, s4_2, c4_2)
        # Passthrough: c3_4
        
        # === Level 6: 5 → 4 rows ===
        s6_0, c6_0 = full_adder_64bit(s5_0, c5_0, s5_1)
        # Passthrough: c5_1, c3_4
        # Output: s6_0, c6_0, c5_1, c3_4
        
        # 存储 4 行中间结果
        self.m3_row0[0] = s6_0
        self.m3_row1[0] = c6_0
        self.m3_row2[0] = c5_1
        self.m3_row3[0] = c3_4
        
        self.m3_valid[0] = Bits(1)(1)
        self.m2_valid[0] = Bits(1)(0)
```

#### 2.2.7 阶段 3：最终压缩 + CPA

```python
def cycle_m3(self):
    """
    EX_M3 阶段：Wallace Tree Levels 7-8 (4 → 2 rows) + CPA 最终加法
    """
    with Condition((self.m3_valid[0] == Bits(1)(1)) & 
                   (self.m3_result_ready[0] == Bits(1)(0))):
        # 读取 Level 6 输出（4 行）
        s6_0 = self.m3_row0[0]
        c6_0 = self.m3_row1[0]
        c5_1 = self.m3_row2[0]
        c3_4 = self.m3_row3[0]
        
        # === Level 7: 4 → 3 rows ===
        s7_0, c7_0 = full_adder_64bit(s6_0, c6_0, c5_1)
        # Passthrough: c3_4
        
        # === Level 8: 3 → 2 rows (最终 Wallace Tree 压缩) ===
        s8_final, c8_final = full_adder_64bit(s7_0, c7_0, c3_4)
        
        # === CPA (Carry-Propagate Adder) 最终加法 ===
        product_64 = carry_propagate_adder_64bit(s8_final, c8_final)
        
        # 根据指令类型选择高 32 位或低 32 位
        partial_low = product_64[0:31].bitcast(Bits(32))
        partial_high = product_64[32:63].bitcast(Bits(32))
        
        result = self.m3_result_high[0].select(
            partial_high,  # MULH/MULHSU/MULHU
            partial_low    # MUL
        )
        
        self.m3_result[0] = result
        self.m3_result_ready[0] = Bits(1)(1)
        self.m3_valid[0] = Bits(1)(0)
```

**CPA (Carry-Propagate Adder) 实现**：

```python
def carry_propagate_adder_64bit(a: Bits, b: Bits) -> Bits:
    """
    64-bit Carry-Propagate Adder
    最后将 2 行相加得到 64 位乘积
    """
    result = (a.bitcast(UInt(64)) + b.bitcast(UInt(64))).bitcast(Bits(64))
    return result
```

### 2.3 时钟周期分析

```
时钟周期    流水线状态              操作
========================================================
N           MUL 指令进入 EX        start_multiply() 被调用，m1_valid=1
N+1         EX_M1 执行             部分积生成 + Level 1-3，结果进入 m2 寄存器
N+2         EX_M2 执行             Wallace Tree Level 4-6，结果进入 m3 寄存器
N+3         EX_M3 执行             Level 7-8 + CPA 加法，m3_result_ready=1
N+4         结果输出               结果通过 MEM 阶段传递
N+5         写回                   结果写回寄存器文件
```

**示意图**：

```
周期 N:   IF → ID → [EX: MUL启动] → MEM → WB
周期 N+1: IF → ID → [EX: M1执行]  → MEM → WB
周期 N+2: IF → ID → [EX: M2执行]  → MEM → WB
周期 N+3: IF → ID → [EX: M3完成]  → MEM → WB  ← 结果可用
周期 N+4: IF → ID → EX → [MEM: MUL结果] → WB
周期 N+5: IF → ID → EX → MEM → [WB: 写回 rd]
```

### 2.4 流水线冒险处理（src/hazard_unit.py）

乘法器在执行期间会产生结构冒险，需要暂停流水线：

```python
# src/execution.py 中返回 mul_busy 信号
mul_busy = self.multiplier.is_busy()

# src/hazard_unit.py 中检测冒险
# 当乘法器或除法器忙时，流水线需要暂停
stall_for_mul_div = mul_busy | div_busy
```

**is_busy() 的实现**：

```python
def is_busy(self):
    """
    检查乘法器是否有正在执行的操作。
    当 M1、M2 或 M3 任一阶段有效时返回 True。
    """
    return self.m1_valid[0] | self.m2_valid[0] | self.m3_valid[0]
```

### 2.5 示例：3×5（MUL，无符号）逐周期变化

| 周期 | EX 阶段状态 | Wallace Tree/CPA 关键数据 | 结果寄存 |
|------|-------------|---------------------------|----------|
| N    | start_multiply() 触发，m1_valid=1，op1=0b11，op2=0b101，result_high=0 | 未生成部分积 | - |
| N+1  | EX_M1：生成 pp0=0b11、pp2=0b1100 等有效部分积；Level1-3 压缩得到 10 行，写入 m2_row[0..9]，m2_valid=1 | 10 行中间值写入 M2 | m1_valid→0 |
| N+2  | EX_M2：读取 m2_row，完成 Level4-6（10→4 行），写入 m3_row0..3，m3_valid=1 | 4 行中间值写入 M3 | m2_valid→0 |
| N+3  | EX_M3：Level7-8 得到 2 行，CPA 相加 product_64=0x...000F（十进制 15） | m3_result_ready=1，m3_result=0x0000_000F（低 32 位） | m3_valid→0 |
| N+4  | MEM：旁路/转发乘法结果 | - | - |
| N+5  | WB：写回 rd=15 | - | - |

**3×5 压缩各级的二进制状态（与代码流程对应）**

只需关注低 6 位即可（高位均为 0）。op1=0b11，op2=0b101，仅 pp0、pp2 有效：

- Level0（32 行原始部分积）：
  - pp0 = 000011 (op1)
  - pp1 = 000000
  - pp2 = 001100 (op1 左移 2 位)
  - pp3..pp31 = 0

- Level1（32→22，3:2 压缩，代码中的 s1_* / c1_*）：  
  - full_adder(pp0, pp1, pp2) →  
    sum = 001111，carry = 000000（低 6 位；高位仍为 0，且按代码左移 1 位后最低位为 0）  
  - 其余压缩器输入全 0，输出全 0。保留的两行（类似 passthrough）也为 0。

- Level2（22→15，s2_* / c2_*）：  
  - full_adder(sum, carry, 0) →  
    s2_0 = 001111，c2_0 = 000000  
  - 其他路径全 0。

- Level3（15→10，s3_* / c3_*，写入 m2_row[0..9]）：  
  - full_adder(s2_0, c2_0, 0) →  
    s3_0 = 001111，c3_0 = 000000  
  - 其余 m2_row1..9 均为 0。

- Level4（10→7，EX_M2：s4_* / c4_*）：  
  - full_adder(m2_row0, m2_row1, m2_row2) →  
    s4_0 = 001111，c4_0 = 000000  
  - 其他输出为 0。

- Level5（7→5，s5_* / c5_*）：  
  - full_adder(s4_0, c4_0, 0) →  
    s5_0 = 001111，c5_0 = 000000  
  - 其他输出为 0。

- Level6（5→4，写入 m3_row0..3）：  
  - full_adder(s5_0, c5_0, 0) →  
    s6_0 = 001111，c6_0 = 000000  
  - m3_row2, m3_row3 = 0。

- Level7（4→3，EX_M3：s7_* / c7_*）：  
  - full_adder(s6_0, c6_0, m3_row2) →  
    s7_0 = 001111，c7_0 = 000000

- Level8（3→2，s8_final / c8_final）：  
  - full_adder(s7_0, c7_0, m3_row3) →  
    s8_final = 001111，c8_final = 000000

- CPA 最终相加：`product_64 = s8_final + c8_final = 0b001111 = 15`  
  - result_high=0 → 取低 32 位 0x0000_000F

整个压缩链条与 `src/multiplier.py` 中的 Level1-8 调用顺序一致；因为只有两行非零部分积，其余压缩器/寄存器都保持 0，结果在各级中保持 `001111`，最终得到正确乘积 15。

---

## 3. 除法器硬件实现

### 3.1 恢复除法算法原理

#### 3.1.1 基础知识：手工除法

回想一下我们如何手工做除法（以 42 ÷ 6 为例）：

```
         0 0 0 0 0 1 1 1  = 7 (商)
       _______________
 6 ) 0 0 1 0 1 0 1 0  = 42 (被除数)
        - 6
       -----
          0 (余数 = 0)
```

**手工除法的步骤**：
1. 从被除数的最高位开始
2. 尝试减去除数
3. 如果够减，商的对应位为 1，保留差
4. 如果不够减，商的对应位为 0，恢复原值
5. 移动到下一位，重复步骤 2-4

#### 3.1.2 恢复除法的硬件表示

恢复除法算法将上述过程形式化：

**寄存器设置**：
- `R`：余数寄存器（初始为 0）
- `Q`：商/被除数寄存器（初始为被除数）
- `D`：除数寄存器

**算法步骤**（对于 N 位除法，执行 N 次迭代）：

```
for i = N-1 downto 0:
    1. 左移 [R, Q] 一位
       R = (R << 1) | Q[MSB]
       Q = Q << 1
    
    2. 试减
       temp = R - D
    
    3. 判断并决定
       if temp >= 0:
           R = temp      # 保留减法结果
           Q[0] = 1      # 商位为 1
       else:
           R = R         # 恢复（不改变）
           Q[0] = 0      # 商位为 0
```

**为什么叫"恢复"除法**：
- 当试减结果为负时，我们"恢复"原来的 R 值
- 实际硬件中，我们只需要不更新 R 寄存器即可

#### 3.1.3 具体例子：42 ÷ 6

```
初始状态：R = 0, Q = 42 = 0b101010, D = 6 = 0b110

迭代 1（处理第 6 位）：
  R = (0 << 1) | Q[5] = 0 | 1 = 1
  Q = Q << 1 = 0b010100
  temp = R - D = 1 - 6 = -5 < 0
  → 恢复，R = 1, Q[0] = 0
  结果：R = 1, Q = 0b010100

迭代 2（处理第 5 位）：
  R = (1 << 1) | Q[5] = 2 | 0 = 2
  Q = Q << 1 = 0b101000
  temp = R - D = 2 - 6 = -4 < 0
  → 恢复，R = 2, Q[0] = 0
  结果：R = 2, Q = 0b101000

迭代 3（处理第 4 位）：
  R = (2 << 1) | Q[5] = 4 | 1 = 5
  Q = Q << 1 = 0b010000
  temp = R - D = 5 - 6 = -1 < 0
  → 恢复，R = 5, Q[0] = 0
  结果：R = 5, Q = 0b010000

迭代 4（处理第 3 位）：
  R = (5 << 1) | Q[5] = 10 | 0 = 10
  Q = Q << 1 = 0b100000
  temp = R - D = 10 - 6 = 4 >= 0
  → 保留，R = 4, Q[0] = 1
  结果：R = 4, Q = 0b100001

迭代 5（处理第 2 位）：
  R = (4 << 1) | Q[5] = 8 | 1 = 9
  Q = Q << 1 = 0b000010
  temp = R - D = 9 - 6 = 3 >= 0
  → 保留，R = 3, Q[0] = 1
  结果：R = 3, Q = 0b000011

迭代 6（处理第 1 位）：
  R = (3 << 1) | Q[5] = 6 | 0 = 6
  Q = Q << 1 = 0b000110
  temp = R - D = 6 - 6 = 0 >= 0
  → 保留，R = 0, Q[0] = 1
  结果：R = 0, Q = 0b000111

最终结果：商 Q = 7, 余数 R = 0
验证：42 = 6 × 7 + 0 ✓
```

### 3.2 SRT-4 除法算法

#### 3.2.1 SRT-4 与 Radix-4 恢复除法的区别

SRT-4（Sweeney-Robertson-Tocher）除法是一种比传统 Radix-4 恢复除法更高效的算法：

| 特性 | Radix-4 恢复除法 | SRT-4 除法 |
|------|-----------------|-----------|
| 商位集合 | {0, 1, 2, 3} | {-2, -1, 0, 1, 2}（冗余表示） |
| 商选择方式 | 与 3D, 2D, D 精确比较 | 基于截断的部分余数查表 |
| 硬件复杂度 | 需要计算 3D | 使用查找表，无需 3D |
| 容错性 | 无 | 允许估计误差 |

**SRT-4 的关键优势**：
1. **冗余商表示**：允许商位为负数，通过后续迭代修正
2. **简化的商选择**：只需查看部分余数的高位，无需精确比较
3. **硬件友好**：避免了计算 3×除数的开销

#### 3.2.2 SRT-4 算法步骤

```
预处理：
  1. 将除数 D 归一化（左移使最高位为1）
  2. 记录移位量 s
  3. 初始化部分余数 w = 被除数
  4. 初始化 Q = 0, QM = -1（用于在线转换）

迭代（16次）：
for i = 15 downto 0:
    1. 商位选择（QDS）
       根据 w 的高 6 位查表选择 q ∈ {-2, -1, 0, 1, 2}
    
    2. 更新部分余数
       w = 4 × w - q × D
    
    3. 在线商转换
       if q >= 0:
           Q_new = 4×Q + q
           QM_new = 4×Q + q - 1
       else:
           Q_new = 4×QM + (4 + q)
           QM_new = 4×QM + (4 + q) - 1

后处理：
  1. 根据最终 w 的符号选择 Q 或 QM
  2. 根据移位量 s 调整商
  3. 计算余数并进行符号修正
```

#### 3.2.3 商位选择函数（QDS）

SRT-4 的核心是商位选择函数。对于归一化的除数 (1/2 ≤ d < 1)：

| 部分余数范围 | 选择的商位 q |
|-------------|-------------|
| w ≥ 6 (估算) | +2 |
| 2 ≤ w < 6 | +1 |
| -2 < w < 2 | 0 |
| -6 < w ≤ -2 | -1 |
| w ≤ -6 | -2 |

**注意**：这些边界是近似的，SRT-4 的冗余性允许重叠区域。

#### 3.2.4 在线商转换（On-the-fly Conversion）

由于商位可以是负数，我们使用两个寄存器 Q 和 QM 进行在线转换：
- **Q**：假设后续商位非负时的累积商
- **QM**：假设后续商位为负时的累积商（Q - 1 在当前位位置）

每次迭代：
- 若 q ≥ 0：使用 Q 的基础值
- 若 q < 0：使用 QM 的基础值

最终选择：
- 若最终部分余数 ≥ 0：使用 Q
- 若最终部分余数 < 0：使用 QM

### 3.3 Assassyn 代码实现详解

在 `src/divider.py` 中，我们实现了 SRT-4 除法器。

#### 3.3.1 状态机设计

```python
# FSM 状态定义
self.IDLE = Bits(3)(0)       # 空闲，等待启动
self.DIV_PRE = Bits(3)(1)    # 预处理
self.DIV_WORKING = Bits(3)(2) # 迭代计算
self.DIV_END = Bits(3)(3)    # 后处理
self.DIV_1 = Bits(3)(4)      # 快速路径：除数=1
self.DIV_ERROR = Bits(3)(5)  # 错误：除数=0
```

**状态转换图**：

```
        启动
          ↓
       ┌─────────────────────────────────────┐
       │                                     │
       ↓                                     │
    ┌──────┐  除数=0   ┌───────────┐         │
    │ IDLE │ ────────→ │ DIV_ERROR │─────────┤
    └──┬───┘           └───────────┘         │
       │                                     │
       │ 除数=1   ┌───────┐                  │
       ├────────→│ DIV_1 │──────────────────┤
       │          └───────┘                  │
       │                                     │
       │ 正常     ┌─────────┐  初始化完成    │
       └────────→│ DIV_PRE │───────────┐    │
                 └─────────┘           │    │
                                       ↓    │
                             ┌─────────────┐│
                             │ DIV_WORKING ││
                             │  (16次循环) ││
                             └──────┬──────┘│
                                    │       │
                                    ↓       │
                              ┌─────────┐   │
                              │ DIV_END │───┘
                              └─────────┘
```

#### 3.3.2 寄存器定义

```python
def __init__(self):
    # 控制寄存器
    self.busy = RegArray(Bits(1), 1, initializer=[0])    # 忙标志
    self.valid_in = RegArray(Bits(1), 1, initializer=[0]) # 输入有效
    self.ready = RegArray(Bits(1), 1, initializer=[0])   # 结果就绪
    self.error = RegArray(Bits(1), 1, initializer=[0])   # 错误标志

    # 输入寄存器
    self.dividend_in = RegArray(Bits(32), 1, initializer=[0])  # 被除数
    self.divisor_in = RegArray(Bits(32), 1, initializer=[0])   # 除数
    self.is_signed = RegArray(Bits(1), 1, initializer=[0])     # 有符号标志
    self.is_rem = RegArray(Bits(1), 1, initializer=[0])        # 返回余数标志

    # 状态机寄存器
    self.state = RegArray(Bits(3), 1, initializer=[0])   # FSM 状态
    self.div_cnt = RegArray(Bits(5), 1, initializer=[0]) # 迭代计数器

    # SRT-4 工作寄存器
    self.dividend_r = RegArray(Bits(32), 1, initializer=[0])  # 无符号被除数
    self.divisor_r = RegArray(Bits(32), 1, initializer=[0])   # 归一化后的除数
    self.div_shift = RegArray(Bits(6), 1, initializer=[0])    # 归一化移位量
    self.shift_rem = RegArray(Bits(35), 1, initializer=[0])   # 部分余数（35位）
    
    # 在线商转换寄存器
    self.Q = RegArray(Bits(32), 1, initializer=[0])     # 商（假设后续非负）
    self.QM = RegArray(Bits(32), 1, initializer=[0])    # 商减1（假设后续为负）
    
    self.div_sign = RegArray(Bits(2), 1, initializer=[0])     # 符号位记录
    self.sign_r = RegArray(Bits(1), 1, initializer=[0])       # 结果符号标志
```

**SRT-4 特有寄存器说明**：
- `div_shift`：记录除数归一化的移位量，用于最后调整商
- `shift_rem`：35 位部分余数，额外的位用于处理 4×w 运算
- `Q` 和 `QM`：在线商转换的两个累积寄存器

#### 3.3.3 启动除法

```python
def start_divide(self, dividend, divisor, is_signed, is_rem):
    """
    启动除法运算
    
    参数：
    - dividend: 被除数 (rs1)
    - divisor: 除数 (rs2)
    - is_signed: 1=有符号除法, 0=无符号除法
    - is_rem: 1=返回余数, 0=返回商
    """
    self.dividend_in[0] = dividend
    self.divisor_in[0] = divisor
    self.is_signed[0] = is_signed
    self.is_rem[0] = is_rem
    self.valid_in[0] = Bits(1)(1)
    self.busy[0] = Bits(1)(1)
    self.ready[0] = Bits(1)(0)
    self.error[0] = Bits(1)(0)
```

#### 3.3.4 IDLE 状态：特殊情况检测

```python
with Condition(self.state[0] == self.IDLE):
    with Condition(self.valid_in[0] == Bits(1)(1)):
        # 检测特殊情况
        div_by_zero = (self.divisor_in[0] == Bits(32)(0))
        div_by_one = (self.divisor_in[0] == Bits(32)(1))

        with Condition(div_by_zero):
            # 除数为 0，进入错误状态
            self.state[0] = self.DIV_ERROR
            self.valid_in[0] = Bits(1)(0)

        with Condition(~div_by_zero & div_by_one):
            # 除数为 1，快速路径
            self.state[0] = self.DIV_1
            self.valid_in[0] = Bits(1)(0)

        with Condition(~div_by_zero & ~div_by_one):
            # 正常除法
            self.state[0] = self.DIV_PRE
            self.valid_in[0] = Bits(1)(0)

            # 有符号数转无符号数
            dividend_is_neg = self.is_signed[0] & self.dividend_in[0][31:31]
            divisor_is_neg = self.is_signed[0] & self.divisor_in[0][31:31]

            # 取绝对值（如果是负数，取反加1）
            dividend_abs = dividend_is_neg.select(
                (~self.dividend_in[0] + Bits(32)(1)).bitcast(Bits(32)),
                self.dividend_in[0]
            )
            divisor_abs = divisor_is_neg.select(
                (~self.divisor_in[0] + Bits(32)(1)).bitcast(Bits(32)),
                self.divisor_in[0]
            )

            # 保存绝对值和符号信息
            self.dividend_r[0] = dividend_abs
            self.divisor_r[0] = divisor_abs
            self.div_sign[0] = concat(
                self.dividend_in[0][31:31], 
                self.divisor_in[0][31:31]
            )
```

**硬件含义说明**：
- `~value + 1` 是二进制补码取负操作
- `div_sign[1:1]` 保存被除数符号，`div_sign[0:0]` 保存除数符号
- 符号位用于最后的结果符号修正

#### 3.3.5 DIV_WORKING 状态：SRT-4 迭代

```python
with Condition(self.state[0] == self.DIV_WORKING):
    # 检查是否完成
    with Condition(self.div_cnt[0] == Bits(5)(1)):
        self.state[0] = self.DIV_END

    # SRT-4 算法：
    # 1. 基于截断的部分余数选择商位
    # 2. 更新部分余数：w = 4×w - q×D
    # 3. 在线商转换更新 Q 和 QM

    # 步骤 1：商位选择（QDS）
    # 提取部分余数的高 6 位用于查表
    w_truncated = self.shift_rem[0][29:34]  # 高 6 位
    q_digit = self.quotient_select(w_truncated)
    
    # 步骤 2：计算新的部分余数
    # w_new = 4 × w - q × D
    w_shifted = concat(self.shift_rem[0][0:32], Bits(2)(0))  # 左移 2 位（乘 4）
    
    # 计算 q × D（其中 q ∈ {-2, -1, 0, 1, 2}）
    d_extended = concat(Bits(3)(0), self.divisor_r[0])
    d_2x = concat(Bits(2)(0), self.divisor_r[0], Bits(1)(0))  # 2×D
    
    # 解码商位并选择乘积
    is_q_pos2 = (q_digit == Bits(3)(0b010))
    is_q_pos1 = (q_digit == Bits(3)(0b001))
    is_q_neg1 = (q_digit == Bits(3)(0b111))
    is_q_neg2 = (q_digit == Bits(3)(0b110))
    is_q_negative = is_q_neg1 | is_q_neg2
    
    # 根据 q 的符号决定加减
    # q >= 0: w_new = w_shifted - qd_value
    # q < 0:  w_new = w_shifted + |q|×D
    new_w = is_q_negative.select(w_plus_qd, w_minus_qd)
    
    # 步骤 3：在线商转换
    # Q_new 和 QM_new 根据 q 的值更新
    Q_shifted = concat(self.Q[0][0:29], Bits(2)(0))   # Q << 2
    QM_shifted = concat(self.QM[0][0:29], Bits(2)(0)) # QM << 2
    
    # 根据 q 选择基础值和加数
    # q=+2: Q_new = 4×Q + 2
    # q=+1: Q_new = 4×Q + 1
    # q= 0: Q_new = 4×Q + 0
    # q=-1: Q_new = 4×QM + 3
    # q=-2: Q_new = 4×QM + 2
    new_Q = is_q_pos2.select(Q_add_2,
            is_q_pos1.select(Q_add_1,
            is_q_neg1.select(QM_add_3, QM_add_2)))
    
    new_QM = new_Q - 1

    # 更新寄存器
    self.shift_rem[0] = new_w
    self.Q[0] = new_Q
    self.QM[0] = new_QM

    # 递减计数器
    self.div_cnt[0] = self.div_cnt[0] - 1
```

**SRT-4 关键操作说明**：
- `quotient_select()`：基于部分余数高位的商位选择函数
- 商位编码：`010=+2, 001=+1, 000=0, 111=-1, 110=-2`
- 在线转换保证最终可以直接获得二进制商

#### 3.3.6 DIV_END 状态：符号修正

```python
with Condition(self.state[0] == self.DIV_END):
    # 符号修正规则：
    # - 商：被除数和除数异号时为负
    # - 余数：与被除数同号
    q_needs_neg = (self.div_sign[0] == Bits(2)(0b01)) | \
                  (self.div_sign[0] == Bits(2)(0b10))
    rem_needs_neg = self.div_sign[0][1:1]  # 被除数符号

    # 检测有符号溢出：(-2^31) / (-1) = -2^31（无法表示为正数）
    min_int = Bits(32)(0x80000000)
    neg_one = Bits(32)(0xFFFFFFFF)
    signed_overflow = (self.sign_r[0] == Bits(1)(1)) & \
                      (self.dividend_in[0] == min_int) & \
                      (self.divisor_in[0] == neg_one)

    with Condition(signed_overflow):
        # RISC-V 规范：溢出时商 = -2^31，余数 = 0
        self.result[0] = self.is_rem[0].select(
            Bits(32)(0),
            Bits(32)(0x80000000)
        )

    with Condition(~signed_overflow):
        # 正常符号修正
        q_signed = (self.sign_r[0] & q_needs_neg).select(
            (~self.quotient[0] + Bits(32)(1)).bitcast(Bits(32)),
            self.quotient[0]
        )
        rem_signed = (self.sign_r[0] & rem_needs_neg).select(
            (~self.remainder[0][0:31] + Bits(32)(1)).bitcast(Bits(32)),
            self.remainder[0][0:31]
        )

        # 根据指令类型选择输出
        self.result[0] = self.is_rem[0].select(rem_signed, q_signed)

    # 完成，回到 IDLE
    self.ready[0] = Bits(1)(1)
    self.busy[0] = Bits(1)(0)
    self.state[0] = self.IDLE
```

### 3.4 时钟周期分析

#### 3.4.1 Radix-4 除法器时序

```
周期数      状态              操作
================================================================
N           IDLE             检测特殊情况，决定下一状态
N+1         DIV_PRE          初始化 quotient=dividend, remainder=0, cnt=16
N+2         DIV_WORKING      第 1 次迭代（处理 bit 31-30）
N+3         DIV_WORKING      第 2 次迭代（处理 bit 29-28）
...         ...              ...
N+17        DIV_WORKING      第 16 次迭代（处理 bit 1-0）
N+18        DIV_END          符号修正，结果就绪
```

**总周期数**：~18 周期（正常情况）

#### 3.4.2 特殊情况

| 情况 | 周期数 |
|------|--------|
| 除数 = 0 | 2 周期 (IDLE → DIV_ERROR) |
| 除数 = 1 | 2 周期 (IDLE → DIV_1) |
| 正常除法 | ~18 周期 |

### 3.5 SRT-4 与 Radix-4 的性能比较

SRT-4 相比 Radix-4 恢复除法的主要优势：

| 特性 | SRT-4 除法器 | Radix-4 恢复除法 |
|------|-------------|-----------------|
| 商位选择 | 查表（QDS），简单阈值比较 | 与 3D, 2D, D 精确比较 |
| 是否需要 3×D | 否 | 是（增加硬件） |
| 容错性 | 有（冗余表示允许误差） | 无 |
| 关键路径 | 较短（简化的比较逻辑） | 较长（需要计算 3D） |

### 3.6 逐位恢复除法（NaiveDivider）

`src/naive_divider.py` 实现了更简单的逐位恢复除法，主要区别：

| 特性 | SRT-4 (SRT4Divider) | 逐位 (NaiveDivider) |
|------|------------------------|---------------------|
| 每周期处理位数 | 2 位 | 1 位 |
| 迭代次数 | 16 次 | 32 次 |
| 总周期数 | ~18 | ~34 |
| 算法类型 | SRT（冗余商表示） | 恢复除法 |
| 硬件复杂度 | 中等（QDS + 在线转换） | 较低（单比较器） |

---

## 4. RV32IM 扩展指令执行流程

本节详细展示每条 M 扩展指令在五级流水线 CPU 中的执行过程。以下内容基于 `src/execution.py` 中的实际实现。

### 4.1 乘法指令 (MUL/MULH/MULHSU/MULHU)

#### 4.1.1 指令解码（src/instruction_table.py）

M 扩展乘法指令的编码如下（opcode=0x33, funct7=0x01, bit25=1）：

```python
# src/instruction_table.py 中的定义
('mul', OP_R_TYPE, 0x0, 0, 1, ImmType.R, ALUOp.MUL, Op1Sel.RS1, Op2Sel.RS2, ...),
('mulh', OP_R_TYPE, 0x1, 0, 1, ImmType.R, ALUOp.MULH, Op1Sel.RS1, Op2Sel.RS2, ...),
('mulhsu', OP_R_TYPE, 0x2, 0, 1, ImmType.R, ALUOp.MULHSU, Op1Sel.RS1, Op2Sel.RS2, ...),
('mulhu', OP_R_TYPE, 0x3, 0, 1, ImmType.R, ALUOp.MULHU, Op1Sel.RS1, Op2Sel.RS2, ...),
```

#### 4.1.2 MUL 指令

**指令格式**：`MUL rd, rs1, rs2`

**功能**：`rd = (rs1 × rs2)[31:0]` （返回乘积的低 32 位）

**EX 阶段处理（src/execution.py）**：

```python
# 检测乘法指令
is_mul = ctrl.alu_func == ALUOp.MUL
is_mulh = ctrl.alu_func == ALUOp.MULH
is_mulhsu = ctrl.alu_func == ALUOp.MULHSU
is_mulhu = ctrl.alu_func == ALUOp.MULHU
is_mul_op = is_mul | is_mulh | is_mulhsu | is_mulhu

# 启动乘法器
with Condition((is_mul_op == Bits(1)(1)) & (mul_busy == Bits(1)(0)) & (flush_if == Bits(1)(0))):
    # 根据指令类型设置符号配置
    op1_signed_flag = is_mul | is_mulh | is_mulhsu  # MUL, MULH, MULHSU 的 op1 有符号
    op2_signed_flag = is_mul | is_mulh              # MUL, MULH 的 op2 有符号
    result_high_flag = is_mulh | is_mulhsu | is_mulhu  # MULH* 返回高 32 位
    
    self.multiplier.start_multiply(
        op1=real_rs1,
        op2=real_rs2,
        op1_signed=op1_signed_flag,
        op2_signed=op2_signed_flag,
        result_high=result_high_flag,
        rd=wb_ctrl.rd_addr
    )
```

**执行流程**：

```
周期 N:   IF 阶段
          ├─ 读取 PC 处的指令
          └─ 发送到 ID

周期 N+1: ID 阶段
          ├─ 解码指令：opcode=0x33, funct3=0x0, funct7=0x01 (bit25=1)
          ├─ 识别为 MUL 指令
          ├─ 读取 rs1, rs2 数据
          ├─ 设置控制信号：
          │   ├─ alu_func = ALUOp.MUL (Bits(16)(0b0000100000000000))
          │   ├─ op1_sel = RS1
          │   ├─ op2_sel = RS2
          │   └─ rd_addr = rd
          └─ 发送到 EX

周期 N+2: EX 阶段 - 启动
          ├─ 检测 is_mul_op = 1
          ├─ 调用 multiplier.start_multiply()
          │   ├─ op1 = real_rs1 (经旁路处理)
          │   ├─ op2 = real_rs2
          │   ├─ op1_signed = 1 (有符号)
          │   ├─ op2_signed = 1 (有符号)
          │   ├─ result_high = 0 (返回低32位)
          │   └─ rd = rd_addr (目标寄存器)
          ├─ m1_valid = 1, mul_busy = 1
          └─ 流水线暂停，后续指令等待

周期 N+3: EX 阶段 - M1 (部分积生成 + Level 1-3)
          ├─ cycle_m1() 执行
          │   ├─ 符号扩展 op1 到 64 位
          │   ├─ 生成 32 个部分积 (pp0-pp31)
          │   ├─ Wallace Tree Level 1: 32 → 22 rows
          │   ├─ Wallace Tree Level 2: 22 → 15 rows
          │   └─ Wallace Tree Level 3: 15 → 10 rows
          ├─ 10 行中间结果存入 m2_row0-m2_row9
          └─ m1_valid = 0, m2_valid = 1

周期 N+4: EX 阶段 - M2 (Level 4-6)
          ├─ cycle_m2() 执行
          │   ├─ Wallace Tree Level 4: 10 → 7 rows
          │   ├─ Wallace Tree Level 5: 7 → 5 rows
          │   └─ Wallace Tree Level 6: 5 → 4 rows
          ├─ 4 行中间结果存入 m3_row0-m3_row3
          └─ m2_valid = 0, m3_valid = 1

周期 N+5: EX 阶段 - M3 (Level 7-8 + CPA)
          ├─ cycle_m3() 执行
          │   ├─ Wallace Tree Level 7: 4 → 3 rows
          │   ├─ Wallace Tree Level 8: 3 → 2 rows
          │   ├─ CPA 加法: 2 → 1 (64位乘积)
          │   └─ 选择低 32 位 (result_high=0)
          ├─ m3_result_ready = 1
          ├─ 读取结果，更新旁路寄存器 ex_bypass
          └─ 向 MEM 发送 (rd=rd_addr, result=mul_result)

周期 N+6: MEM 阶段
          ├─ mem_opcode = NONE (不访存)
          └─ 传递 rd, result 到 WB

周期 N+7: WB 阶段
          ├─ 检测 rd != 0
          └─ 写入：reg_file[rd] = result
```

#### 4.1.3 MULH 指令

**指令格式**：`MULH rd, rs1, rs2`

**功能**：`rd = (signed(rs1) × signed(rs2))[63:32]` （返回有符号乘积的高 32 位）

**与 MUL 的区别**：
- `result_high = 1` （选择高 32 位）
- `op1_signed = 1, op2_signed = 1`

#### 4.1.4 MULHSU 指令

**指令格式**：`MULHSU rd, rs1, rs2`

**功能**：`rd = (signed(rs1) × unsigned(rs2))[63:32]`

**符号处理**：
- `op1_signed = 1` （rs1 有符号扩展）
- `op2_signed = 0` （rs2 零扩展）
- `result_high = 1`

#### 4.1.5 MULHU 指令

**指令格式**：`MULHU rd, rs1, rs2`

**功能**：`rd = (unsigned(rs1) × unsigned(rs2))[63:32]`

**符号处理**：
- `op1_signed = 0, op2_signed = 0` （两个操作数都零扩展）
- `result_high = 1`

### 4.2 除法指令 (DIV/DIVU)

#### 4.2.1 指令解码

除法指令使用单独的 `div_op` 控制信号（与 `alu_func` 分开）：

```python
# src/instruction_table.py 中的定义
('div', OP_R_TYPE, 0x4, 0, 1, ImmType.R, ALUOp.ADD, ..., DivOp.DIV),
('divu', OP_R_TYPE, 0x5, 0, 1, ImmType.R, ALUOp.ADD, ..., DivOp.DIVU),
('rem', OP_R_TYPE, 0x6, 0, 1, ImmType.R, ALUOp.ADD, ..., DivOp.REM),
('remu', OP_R_TYPE, 0x7, 0, 1, ImmType.R, ALUOp.ADD, ..., DivOp.REMU),
```

#### 4.2.2 DIV 指令

**指令格式**：`DIV rd, rs1, rs2`

**功能**：`rd = signed(rs1) / signed(rs2)`

**EX 阶段处理（src/execution.py）**：

```python
# 检测除法指令
is_div_op = ctrl.div_op != DivOp.NONE

# 启动除法器
with Condition((is_div_op == Bits(1)(1)) & (div_busy == Bits(1)(0)) & (flush_if == Bits(1)(0))):
    is_signed_div = (ctrl.div_op == DivOp.DIV) | (ctrl.div_op == DivOp.REM)
    is_rem_op = (ctrl.div_op == DivOp.REM) | (ctrl.div_op == DivOp.REMU)
    
    self.divider.start_divide(
        dividend=real_rs1,
        divisor=real_rs2,
        is_signed=is_signed_div,
        is_rem=is_rem_op,
        rd=wb_ctrl.rd_addr
    )
```

**执行流程**：

```
周期 N:   IF 阶段
          └─ 读取指令

周期 N+1: ID 阶段
          ├─ 解码：opcode=0x33, funct3=0x4, funct7=0x01 (bit25=1)
          ├─ 识别为 DIV 指令
          └─ 设置 div_op = DivOp.DIV (Bits(5)(0b00010))

周期 N+2: EX 阶段 - 启动
          ├─ 检测 is_div_op = 1
          ├─ 调用 divider.start_divide()
          │   ├─ dividend = real_rs1
          │   ├─ divisor = real_rs2
          │   ├─ is_signed = 1
          │   ├─ is_rem = 0
          │   └─ rd = rd_addr
          ├─ busy = 1, state = IDLE, valid_in = 1
          └─ 流水线暂停

周期 N+3: EX 阶段 - IDLE → DIV_PRE
          ├─ tick() 执行
          │   ├─ 检测 valid_in = 1
          │   ├─ 检查除数 ≠ 0, ≠ 1
          │   ├─ 计算被除数和除数的绝对值
          │   ├─ 保存符号信息到 div_sign
          │   └─ state → DIV_PRE
          └─ 流水线保持暂停

周期 N+4: EX 阶段 - DIV_PRE → DIV_WORKING
          ├─ tick() 执行
          │   ├─ quotient = dividend_abs
          │   ├─ remainder = 0 (34 bits)
          │   ├─ div_cnt = 16
          │   └─ state → DIV_WORKING
          └─ 流水线保持暂停

周期 N+5 ~ N+20: EX 阶段 - DIV_WORKING (16 次迭代)
          ├─ 每次 tick() 执行一次 Radix-4 迭代：
          │   ├─ 左移 remainder 2 位，引入 quotient 高 2 位
          │   ├─ 计算 d1=D, d2=2D, d3=3D
          │   ├─ 并行比较：ge_3d, ge_2d, ge_1d
          │   ├─ 选择商位 q_bits (00/01/10/11)
          │   ├─ 更新 remainder 和 quotient
          │   └─ div_cnt -= 1
          └─ 流水线保持暂停

周期 N+21: EX 阶段 - DIV_END
          ├─ tick() 执行
          │   ├─ 符号修正
          │   ├─ result = quotient (因为 is_rem=0)
          │   └─ ready = 1, busy = 0
          └─ 向 MEM 发送 (rd=rd_addr, result=quotient)

周期 N+22: MEM 阶段
          └─ 传递到 WB

周期 N+23: WB 阶段
          └─ reg_file[rd] = result
```

**特殊情况处理**：

1. **除数 = 0**：
   ```
   周期 N+3: IDLE → DIV_ERROR
   周期 N+4: 返回 result = 0xFFFFFFFF (-1)
   总周期: 4 周期
   ```

2. **除数 = 1**：
   ```
   周期 N+3: IDLE → DIV_1
   周期 N+4: 返回 result = rs1 (商=被除数)
   总周期: 4 周期
   ```

3. **有符号溢出 (-2³¹ / -1)**：
   ```
   在 DIV_END 阶段检测并返回 result = 0x80000000 (-2³¹)
   ```

#### 4.2.3 DIVU 指令

**指令格式**：`DIVU rd, rs1, rs2`

**功能**：`rd = unsigned(rs1) / unsigned(rs2)`

**与 DIV 的区别**：
- `is_signed = 0` （不进行符号转换）
- 直接使用原始操作数进行无符号除法

### 4.3 取模指令 (REM/REMU)

#### 4.3.1 REM 指令

**指令格式**：`REM rd, rs1, rs2`

**功能**：`rd = signed(rs1) % signed(rs2)`

**与 DIV 的区别**：
- `is_rem = 1`
- 在 DIV_END 阶段，选择 `result = remainder`（而非 quotient）

**余数符号规则**：
- 余数符号与被除数相同
- 例如：-7 % 3 = -1，7 % -3 = 1

#### 4.3.2 REMU 指令

**指令格式**：`REMU rd, rs1, rs2`

**功能**：`rd = unsigned(rs1) % unsigned(rs2)`

---

## 5. 附录

### 5.1 控制信号编码（src/control_signals.py）

```python
# ALU 功能码（独热编码，16位）
class ALUOp:
    ADD = Bits(16)(0b0000000000000001)     # Bit 0
    SUB = Bits(16)(0b0000000000000010)     # Bit 1
    SLL = Bits(16)(0b0000000000000100)     # Bit 2
    SLT = Bits(16)(0b0000000000001000)     # Bit 3
    SLTU = Bits(16)(0b0000000000010000)    # Bit 4
    XOR = Bits(16)(0b0000000000100000)     # Bit 5
    SRL = Bits(16)(0b0000000001000000)     # Bit 6
    SRA = Bits(16)(0b0000000010000000)     # Bit 7
    OR = Bits(16)(0b0000000100000000)      # Bit 8
    AND = Bits(16)(0b0000001000000000)     # Bit 9
    SYS = Bits(16)(0b0000010000000000)     # Bit 10
    MUL = Bits(16)(0b0000100000000000)     # Bit 11
    MULH = Bits(16)(0b0001000000000000)    # Bit 12
    MULHSU = Bits(16)(0b0010000000000000)  # Bit 13
    MULHU = Bits(16)(0b0100000000000000)   # Bit 14
    NOP = Bits(16)(0b1000000000000000)     # Bit 15

# 除法操作码（独热编码，5位）- 与 ALU 功能码分开
class DivOp:
    NONE = Bits(5)(0b00001)   # 无除法操作
    DIV = Bits(5)(0b00010)    # 有符号除法
    DIVU = Bits(5)(0b00100)   # 无符号除法
    REM = Bits(5)(0b01000)    # 有符号取余
    REMU = Bits(5)(0b10000)   # 无符号取余
```

### 5.2 指令编码

| 指令 | opcode | funct3 | funct7 | bit25 | 机器码示例 |
|------|--------|--------|--------|-------|-----------|
| MUL | 0110011 | 000 | 0000001 | 1 | 0x02A28033 (x0 = x5 × x10) |
| MULH | 0110011 | 001 | 0000001 | 1 | - |
| MULHSU | 0110011 | 010 | 0000001 | 1 | - |
| MULHU | 0110011 | 011 | 0000001 | 1 | - |
| DIV | 0110011 | 100 | 0000001 | 1 | 0x02A2C033 (x0 = x5 / x10) |
| DIVU | 0110011 | 101 | 0000001 | 1 | - |
| REM | 0110011 | 110 | 0000001 | 1 | - |
| REMU | 0110011 | 111 | 0000001 | 1 | - |

**注**：bit25=1 用于区分 M 扩展指令和普通 R-type 指令（如 ADD/SUB 等 bit25=0）。

### 5.3 性能对比

| 操作 | 本项目实现 | 简单实现 | 典型商用 CPU |
|------|-----------|----------|-------------|
| 乘法 | 3 周期（Wallace Tree） | 1 周期（直接乘） | 3-5 周期 |
| 除法 | ~18 周期（Radix-4） | ~34 周期（逐位） | 10-40 周期 |

### 5.4 参考资料

1. RISC-V "M" Standard Extension for Integer Multiplication and Division
2. Computer Arithmetic: Algorithms and Hardware Designs (M.D. Ercegovac, T. Lang)
3. Digital Design and Computer Architecture: RISC-V Edition
4. Assassyn 语言完整说明书（见 `docs/Assassyn_语言完整说明书.md`）

---

*本文档基于 Assassyn-CPU 项目整理，适合硬件初学者理解 CPU 乘除法实现原理。*