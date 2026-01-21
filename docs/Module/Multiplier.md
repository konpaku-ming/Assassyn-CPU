# Wallace Tree 乘法器设计文档

> **依赖**：Assassyn Framework, `multiplier.py`

## 1. 概述

本 CPU 实现了一个 **3 周期 Wallace Tree 乘法器**，支持 RISC-V M 扩展的所有乘法指令。

### 1.1 支持的指令

| 指令 | 描述 | 操作数符号 | 结果位置 |
| :--- | :--- | :--- | :--- |
| `MUL` | 乘法 | signed × signed | 低 32 位 |
| `MULH` | 高位乘法 | signed × signed | 高 32 位 |
| `MULHSU` | 混合符号高位乘法 | signed × unsigned | 高 32 位 |
| `MULHU` | 无符号高位乘法 | unsigned × unsigned | 高 32 位 |

## 2. 流水线结构

```
    Cycle 1 (M1)           Cycle 2 (M2)           Cycle 3 (M3)
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Partial Product │    │ Wallace Tree    │    │ Final Addition  │
│ Generation      │ -> │ Compression     │ -> │ (CLA)           │
│ + 2 Levels      │    │ Levels 3-8      │    │                 │
│ (32 -> 15 rows) │    │ (15 -> 2 rows)  │    │ (2 -> 1 row)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 3. 详细实现

### 3.1 Cycle M1: 部分积生成 + 2 级压缩

#### 部分积生成

对于 32×32 乘法，生成 32 个部分积：

```python
# 符号/零扩展操作数到 64 位
op1_ext = sign_zero_extend(op1, op1_signed)  # 64-bit

# 生成 32 个部分积
# pp[i] = (op2[i] ? op1_ext : 0) << i
pp0 = op2[0:0].select(op1_ext, Bits(64)(0))
pp1 = op2[1:1].select(concat(op1_ext[0:62], Bits(1)(0)), Bits(64)(0))
# ... pp2 到 pp31
```

#### 有符号乘法修正

对于 MULH/MULHSU，当 op2 为负数时需要修正：

```python
# 当 op2 有符号且为负时，需要从高 32 位减去 op1
need_correction = op2_signed & op2[31:31]
signed_correction = need_correction.select(op1, Bits(32)(0))
```

#### Level 1 压缩 (32 → 22 rows)

使用 3:2 压缩器（全加器）：

```python
# 10 组 3:2 压缩，2 个直通
s1_0, c1_0 = full_adder_64bit(pp0, pp1, pp2)
s1_1, c1_1 = full_adder_64bit(pp3, pp4, pp5)
# ... 
# 直通: pp30, pp31
```

#### Level 2 压缩 (22 → 15 rows)

```python
# 7 组 3:2 压缩，1 个直通
s2_0, c2_0 = full_adder_64bit(s1_0, c1_0, s1_1)
# ...
# 直通: pp31
```

### 3.2 Cycle M2: Wallace Tree 压缩 (Levels 3-8)

继续使用 3:2 压缩器，逐步减少行数：

```
Level 3: 15 → 10 rows (5 组)
Level 4: 10 → 7 rows  (3 组 + 1 直通)
Level 5: 7 → 5 rows   (2 组 + 1 直通)
Level 6: 5 → 4 rows   (1 组 + 2 直通)
Level 7: 4 → 3 rows   (1 组 + 1 直通)
Level 8: 3 → 2 rows   (1 组)
```

最终输出 2 行（sum 和 carry）。

### 3.3 Cycle M3: 最终加法 (CLA)

使用 **Carry-Lookahead Adder (CLA)** 完成最后的 64 位加法。

#### 有符号修正集成

将修正值通过 3:2 压缩器集成到最终加法中：

```python
# 构建修正值：在高 32 位放置 ~signed_correction
# 对于二补码：-correction = ~correction + 1
correction_neg_64 = concat(~signed_correction, Bits(32)(0))
correction_plus_one = Bits(64)(0x100000000)  # 1 << 32

# 使用 3:2 压缩器合并
s9_0, c9_0 = full_adder_64bit(s8_final, c8_final, correction_neg_64)
s_final, c_final = full_adder_64bit(s9_0, c9_0, correction_plus_one)

# CLA 最终加法
product_64 = carry_lookahead_adder_64bit(s_final, c_final)
```

#### CLA 层次结构

```
64-bit CLA
├── 16-bit CLA (bits 0-15)
│   ├── 4-bit CLA (bits 0-3)
│   ├── 4-bit CLA (bits 4-7)
│   ├── 4-bit CLA (bits 8-11)
│   └── 4-bit CLA (bits 12-15)
├── 16-bit CLA (bits 16-31)
├── 16-bit CLA (bits 32-47)
└── 16-bit CLA (bits 48-63)
```

每级使用 **Lookahead Carry Unit (LCU)** 并行计算进位。

#### 结果选择

```python
partial_low = product_64[0:31]   # MUL 结果
partial_high = product_64[32:63] # MULH/MULHSU/MULHU 结果

result = self.m3_result_high[0].select(partial_high, partial_low)
```

## 4. 流水线状态

### 4.1 M1 阶段寄存器

```python
self.m1_valid = RegArray(Bits(1), 1)          # 有效位
self.m1_op1 = RegArray(Bits(32), 1)           # 操作数 1
self.m1_op2 = RegArray(Bits(32), 1)           # 操作数 2
self.m1_op1_signed = RegArray(Bits(1), 1)     # op1 是否有符号
self.m1_op2_signed = RegArray(Bits(1), 1)     # op2 是否有符号
self.m1_result_high = RegArray(Bits(1), 1)    # 返回高 32 位？
self.m1_rd = RegArray(Bits(5), 1)             # 目标寄存器
```

### 4.2 M2 阶段寄存器

```python
self.m2_valid = RegArray(Bits(1), 1)
self.m2_result_high = RegArray(Bits(1), 1)
self.m2_rd = RegArray(Bits(5), 1)
self.m2_signed_correction = RegArray(Bits(32), 1)
# 15 个中间行 (64-bit each)
self.m2_row0 = RegArray(Bits(64), 1)
# ... m2_row1 到 m2_row14
```

### 4.3 M3 阶段寄存器

```python
self.m3_valid = RegArray(Bits(1), 1)
self.m3_result_high = RegArray(Bits(1), 1)
self.m3_rd = RegArray(Bits(5), 1)
self.m3_signed_correction = RegArray(Bits(32), 1)
# 2 个最终行
self.m3_row0 = RegArray(Bits(64), 1)
self.m3_row1 = RegArray(Bits(64), 1)
# 结果
self.m3_result_ready = RegArray(Bits(1), 1)
self.m3_result = RegArray(Bits(32), 1)
```

## 5. 接口

### 5.1 启动乘法

```python
def start_multiply(self, op1, op2, op1_signed, op2_signed, result_high, rd=Bits(5)(0)):
    """
    Args:
        op1: 第一个操作数 (32-bit)
        op2: 第二个操作数 (32-bit)
        op1_signed: op1 是否有符号
        op2_signed: op2 是否有符号
        result_high: 是否返回高 32 位
        rd: 目标寄存器
    """
```

### 5.2 查询状态

```python
def is_busy(self):
    """返回乘法器是否正在工作"""
    return self.m1_valid[0] | self.m2_valid[0] | self.m3_valid[0]

def get_result_if_ready(self):
    """返回 (ready, result, rd)"""
    return (self.m3_result_ready[0], self.m3_result[0], self.m3_rd[0])

def clear_result(self):
    """清除结果"""
    self.m3_result_ready[0] = Bits(1)(0)
```

## 6. 性能特性

| 指标 | 值 |
| :--- | :--- |
| 延迟 | 3 周期 |
| 吞吐量 | 1/3 (每 3 周期完成 1 次乘法) |
| 资源 | ~15 个 64-bit 寄存器 + Wallace Tree 逻辑 + 64-bit CLA |

## 7. 3:2 压缩器 (Full Adder)

核心压缩单元：

```python
def full_adder_64bit(a: Bits, b: Bits, c: Bits) -> tuple:
    """
    64-bit 3:2 compressor (Full Adder)
    
    输入: 3 个 64-bit 值
    输出: (sum, carry)
        - sum: a ⊕ b ⊕ c
        - carry: ((a&b) | (b&c) | (a&c)) << 1
    """
    sum_result = a ^ b ^ c
    carry_unshifted = (a & b) | (b & c) | (a & c)
    carry_shifted = concat(carry_unshifted[0:62], Bits(1)(0))
    return (sum_result, carry_shifted)
```
