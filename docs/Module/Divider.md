# Radix-16 除法器设计文档

> **依赖**：Assassyn Framework, `divider.py`

## 1. 概述

本 CPU 实现了一个 **Radix-16 除法器**，支持 RISC-V M 扩展的所有除法指令。

### 1.1 支持的指令

| 指令 | 描述 | 符号 | 结果 |
| :--- | :--- | :--- | :--- |
| `DIV` | 有符号除法 | signed | 商 |
| `DIVU` | 无符号除法 | unsigned | 商 |
| `REM` | 有符号取余 | signed | 余数 |
| `REMU` | 无符号取余 | unsigned | 余数 |

### 1.2 执行周期

| 情况 | 周期数 |
| :--- | :--- |
| 除数为 0 | 1 周期 (特殊处理) |
| 除数为 1 | 1 周期 (快速路径) |
| 正常情况 | ~10 周期 (1 预处理 + 8 迭代 + 1 后处理) |

## 2. 状态机设计

```
                          ┌─────────┐
                    ┌────>│  IDLE   │<────┐
                    │     └────┬────┘     │
                    │          │ valid_in │
                    │          ▼          │
                    │   ┌────────────┐    │
                    │   │ Check      │    │
                    │   │ Special    │    │
                    │   │ Cases      │    │
                    │   └──┬───┬───┬─┘    │
                    │      │   │   │      │
              ┌─────┴──┐   │   │   │  ┌───┴────┐
              │DIV_ERR │<──┘   │   └─>│ DIV_1  │
              │(÷0)    │       │      │(÷1)    │
              └────────┘       │      └────────┘
                               ▼
                        ┌────────────┐
                        │  DIV_PRE   │
                        │(预处理)    │
                        └─────┬──────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │  DIV_WORKING    │
                     │  (8 迭代)       │<──┐
                     └────────┬────────┘   │
                              │            │
                              └────────────┘
                              │ cnt == 0
                              ▼
                        ┌────────────┐
                        │  DIV_END   │
                        │(后处理)    │
                        └─────┬──────┘
                              │
                              └───────> IDLE
```

## 3. 详细实现

### 3.1 IDLE 状态

检测特殊情况：

```python
with Condition(self.state[0] == self.IDLE):
    with Condition(self.valid_in[0] == Bits(1)(1)):
        div_by_zero = (self.divisor_in[0] == Bits(32)(0))
        div_by_one = (self.divisor_in[0] == Bits(32)(1))

        with Condition(div_by_zero):
            self.state[0] = self.DIV_ERROR
        with Condition(~div_by_zero & div_by_one):
            self.state[0] = self.DIV_1
        with Condition(~div_by_zero & ~div_by_one):
            self.state[0] = self.DIV_PRE
```

### 3.2 DIV_ERROR 状态 (除以 0)

按 RISC-V 规范返回特殊值：

```python
# 商 = -1 (0xFFFFFFFF)
# 余数 = 被除数
quotient_on_div0 = Bits(32)(0xFFFFFFFF)
self.result[0] = self.is_rem[0].select(
    self.dividend_in[0],  # 余数 = 被除数
    quotient_on_div0,     # 商 = -1
)
```

### 3.3 DIV_1 状态 (除以 1)

快速路径：

```python
# 商 = 被除数
# 余数 = 0
self.result[0] = self.is_rem[0].select(
    Bits(32)(0),          # 余数 = 0
    self.dividend_in[0],  # 商 = 被除数
)
```

### 3.4 DIV_PRE 状态 (预处理)

#### 有符号数转换

将有符号数转换为无符号数：

```python
# 检测负数
dividend_is_neg = self.is_signed[0] & self.dividend_in[0][31:31]
divisor_is_neg = self.is_signed[0] & self.divisor_in[0][31:31]

# 取绝对值
dividend_abs = dividend_is_neg.select(
    (~self.dividend_in[0] + Bits(32)(1)).bitcast(Bits(32)),
    self.dividend_in[0]
)
divisor_abs = divisor_is_neg.select(
    (~self.divisor_in[0] + Bits(32)(1)).bitcast(Bits(32)),
    self.divisor_in[0]
)

# 保存符号信息供后处理使用
self.div_sign[0] = concat(dividend_is_neg, divisor_is_neg)
```

#### 除数倍数预计算

计算 1d 到 15d，用于 QDS (Quotient Digit Selection)：

```python
d_36 = concat(Bits(4)(0), divisor)  # 36-bit 避免溢出

# 使用高效的组合计算
d1 = d_36
d2 = d_36 << 1
d3 = d2 + d1
d4 = d_36 << 2
d5 = d4 + d1
d6 = d4 + d2
d7 = d4 + d3
d8 = d_36 << 3
d9 = d8 + d1
d10 = d8 + d2
d11 = d8 + d3
d12 = d8 + d4
d13 = d8 + d5
d14 = d8 + d6
d15 = d8 + d7
```

### 3.5 DIV_WORKING 状态 (迭代)

Radix-16 每次迭代处理 4 位商：

```python
# 8 次迭代，每次处理 4 位，共 32 位
self.div_cnt[0] = Bits(5)(8)

# 每次迭代
# 1. 移位余数并引入新的 4 位被除数
next_bits = dividend_cur[28:31]  # 取被除数高 4 位
shifted_rem = concat(rem_cur[0:31], next_bits)

# 2. QDS (商位选择)
q_digit = self.quotient_select(shifted_rem, d1, d2, ..., d15)

# 3. 更新余数
new_rem = shifted_rem - q_digit * d

# 4. 更新商
new_quot = concat(quot_cur[0:27], q_digit)
```

#### QDS (Quotient Digit Selection)

使用二分查找树选择 0-15 的商位：

```
                            >= 8d?
                     ┌────────┴────────┐
                    Yes               No
                 >= 12d?           >= 4d?
               ┌────┴────┐       ┌────┴────┐
              Yes       No      Yes       No
           >= 14d?   >= 10d?  >= 6d?   >= 2d?
             ...       ...      ...      ...
```

每层仅需 1 次比较，共 4 层 = 4 次比较。

### 3.6 DIV_END 状态 (后处理)

#### 符号修正

```python
# 商的符号：被除数和除数符号不同时为负
q_needs_neg = (div_sign == 0b01) | (div_sign == 0b10)

# 余数的符号：与被除数相同
rem_needs_neg = div_sign[1:1]

# 应用符号
q_signed = (sign_r & q_needs_neg).select(~q_out + 1, q_out)
rem_signed = (sign_r & rem_needs_neg).select(~rem_out + 1, rem_out)
```

#### 溢出处理

检测有符号溢出：(-2^31) / (-1)

```python
min_int = Bits(32)(0x80000000)
neg_one = Bits(32)(0xFFFFFFFF)
signed_overflow = is_signed & (dividend == min_int) & (divisor == neg_one)

# 溢出时：商 = -2^31, 余数 = 0
with Condition(signed_overflow):
    self.result[0] = is_rem.select(Bits(32)(0), min_int)
```

## 4. 寄存器列表

### 4.1 控制寄存器

```python
self.busy = RegArray(Bits(1), 1)       # 忙状态
self.valid_in = RegArray(Bits(1), 1)   # 输入有效
self.state = RegArray(Bits(3), 1)      # FSM 状态
self.div_cnt = RegArray(Bits(5), 1)    # 迭代计数器
```

### 4.2 输入寄存器

```python
self.dividend_in = RegArray(Bits(32), 1)  # 被除数
self.divisor_in = RegArray(Bits(32), 1)   # 除数
self.is_signed = RegArray(Bits(1), 1)     # 有符号标志
self.is_rem = RegArray(Bits(1), 1)        # 取余标志
self.rd_in = RegArray(Bits(5), 1)         # 目标寄存器
```

### 4.3 工作寄存器

```python
self.dividend_r = RegArray(Bits(32), 1)   # 无符号被除数
self.divisor_r = RegArray(Bits(32), 1)    # 无符号除数
self.quotient = RegArray(Bits(32), 1)     # 商累加器
self.remainder = RegArray(Bits(36), 1)    # 部分余数 (36-bit)

# 除数倍数 (d1 到 d15)
self.d1 = RegArray(Bits(36), 1)
# ... 到 d15

# 符号信息
self.div_sign = RegArray(Bits(2), 1)      # {dividend[31], divisor[31]}
self.sign_r = RegArray(Bits(1), 1)        # 是否有符号操作
```

### 4.4 输出寄存器

```python
self.result = RegArray(Bits(32), 1)    # 结果
self.ready = RegArray(Bits(1), 1)      # 结果就绪
self.error = RegArray(Bits(1), 1)      # 除以 0 错误
self.rd_out = RegArray(Bits(5), 1)     # 目标寄存器
```

## 5. 接口

### 5.1 启动除法

```python
def start_divide(self, dividend, divisor, is_signed, is_rem, rd=Bits(5)(0)):
    """
    Args:
        dividend: 被除数 (32-bit, rs1)
        divisor: 除数 (32-bit, rs2)
        is_signed: 是否有符号操作
        is_rem: 是否返回余数 (False 返回商)
        rd: 目标寄存器
    """
```

### 5.2 查询状态

```python
def is_busy(self):
    """返回除法器是否正在工作"""
    return self.busy[0]

def get_result_if_ready(self):
    """返回 (ready, result, rd, error)"""
    return (self.ready[0], self.result[0], self.rd_out[0], self.error[0])

def clear_result(self):
    """清除结果"""
    self.ready[0] = Bits(1)(0)
```

## 6. 性能特性

| 指标 | 值 |
| :--- | :--- |
| 延迟 (÷0 或 ÷1) | 1 周期 |
| 延迟 (正常) | ~10 周期 |
| 每迭代处理位数 | 4 位 |
| 迭代次数 | 8 |

## 7. Radix-16 vs Radix-2 比较

| 指标 | Radix-2 | Radix-16 |
| :--- | :--- | :--- |
| 迭代次数 | 32 | 8 |
| 每迭代比较次数 | 1 | 4 (并行) |
| 总延迟 | ~34 周期 | ~10 周期 |
| 硬件复杂度 | 低 | 高 |
| 存储需求 | 1×d | 15×d |

Radix-16 通过增加硬件复杂度换取约 3.4× 的速度提升。
