# Naive Divider - Restoring Division Implementation

## 概述 (Overview)

`naive_divider.py` 实现了一个基于**恢复除法（Restoring Division）**算法的32位除法器，用于支持 RISC-V M 扩展的除法和取模指令。

This module implements a 32-bit divider based on the **Restoring Division** algorithm to support RISC-V M extension division and remainder instructions.

## 算法原理 (Algorithm)

恢复除法是最简单直观的除法算法之一，其基本思想是：
- 每次迭代计算商的一位（bit）
- 通过试减法判断当前位是0还是1
- 如果余数为负，需要恢复（加回除数）

### 算法步骤 (Algorithm Steps)

对于 N 位无符号整数除法：

```
1. 初始化：
   - R (remainder) = 0
   - Q (quotient) = dividend
   - counter = N (32 for RV32IM)

2. 循环 N 次：
   a. 左移 R，并将 Q 的最高位移入 R 的最低位
   b. R = R - divisor
   c. 如果 R < 0（余数为负）：
      - R = R + divisor  (恢复)
      - Q 左移一位，最低位设为 0
   d. 否则：
      - Q 左移一位，最低位设为 1

3. 完成：
   - Q = 最终商
   - R = 最终余数
```

## 性能特征 (Performance)

| 特性 | 值 |
|------|-----|
| 算法类型 | 恢复除法 (Restoring Division) |
| 每周期计算位数 | 1 bit |
| 迭代次数 | 32 cycles |
| 预处理周期 | 1 cycle |
| 后处理周期 | 1 cycle |
| **总周期数** | **~34 cycles** |

### 与 SRT-4 的对比 (Comparison with SRT-4)

| 特性 | Naive Divider | SRT-4 Divider |
|------|---------------|---------------|
| 算法复杂度 | 简单 | 复杂 |
| 每周期计算位数 | 1 bit | 2 bits |
| 迭代次数 | 32 | 16 |
| 总周期数 | ~34 | ~18 |
| 硬件资源 | 少 | 多（需要查找表） |
| 适用场景 | 简单设计、低资源 | 高性能 |

## 接口说明 (Interface)

### 类定义 (Class Definition)

```python
class NaiveDivider:
    def __init__(self)
    def is_busy(self) -> Bool
    def start_divide(dividend, divisor, is_signed, is_rem)
    def tick()
    def get_result_if_ready() -> (ready, result, error)
    def clear_result()
```

### 方法说明 (Method Description)

#### `start_divide(dividend, divisor, is_signed, is_rem)`
启动除法运算

**参数：**
- `dividend`: 32位被除数 (rs1)
- `divisor`: 32位除数 (rs2)
- `is_signed`: 1表示有符号除法(DIV/REM)，0表示无符号(DIVU/REMU)
- `is_rem`: 1返回余数，0返回商

#### `tick()`
执行状态机的一个时钟周期

每个时钟周期都需要调用此方法以推进除法计算

#### `get_result_if_ready()`
获取除法结果（如果已完成）

**返回值：**
- `ready`: 结果是否就绪
- `result`: 计算结果（商或余数）
- `error`: 是否发生错误（除零）

## 状态机 (State Machine)

### 状态定义 (States)

1. **IDLE** - 空闲状态，等待除法请求
2. **DIV_PRE** - 预处理（符号转换，初始化）
3. **DIV_WORKING** - 迭代计算（32次）
4. **DIV_END** - 后处理（符号校正）
5. **DIV_1** - 快速路径（除数为1）
6. **DIV_ERROR** - 错误处理（除零）

### 状态转换 (State Transitions)

```
IDLE → DIV_ERROR   (除数为0)
IDLE → DIV_1       (除数为1)
IDLE → DIV_PRE     (正常除法)
DIV_PRE → DIV_WORKING
DIV_WORKING → DIV_WORKING  (循环32次)
DIV_WORKING → DIV_END
DIV_END → IDLE
DIV_1 → IDLE
DIV_ERROR → IDLE
```

## 特殊情况处理 (Special Cases)

### 1. 除零 (Division by Zero)
按照 RISC-V 规范：
- DIV/DIVU: 返回 -1 (0xFFFFFFFF)
- REM/REMU: 返回被除数

### 2. 除以1 (Division by 1)
快速路径：
- 商 = 被除数
- 余数 = 0

### 3. 有符号溢出 (Signed Overflow)
`-2^31 / -1` 的情况：
- DIV: 返回 -2^31 (0x80000000)
- REM: 返回 0

### 4. 负数处理 (Negative Numbers)
- 预处理时转换为无符号数
- 后处理时根据符号位恢复正负号
- 商的符号：异号为负
- 余数的符号：与被除数相同

## 寄存器说明 (Registers)

### 控制寄存器 (Control Registers)
- `busy`: 除法器忙标志
- `valid_in`: 输入有效标志
- `ready`: 结果就绪标志
- `error`: 错误标志
- `state`: FSM状态

### 输入寄存器 (Input Registers)
- `dividend_in`: 输入被除数
- `divisor_in`: 输入除数
- `is_signed`: 有符号标志
- `is_rem`: 余数标志

### 工作寄存器 (Working Registers)
- `dividend_r`: 无符号被除数
- `divisor_r`: 无符号除数
- `quotient`: 商累加器 (32位)
- `remainder`: 余数寄存器 (33位，用于检测符号)
- `div_cnt`: 迭代计数器
- `div_sign`: 符号位 {被除数符号, 除数符号}
- `sign_r`: 结果符号标志

### 输出寄存器 (Output Registers)
- `result`: 最终结果（商或余数）

## 测试 (Testing)

测试文件：`tests/test_naive_divider.py`

### 测试用例 (Test Cases)
- 基本除法和取模运算
- 有符号和无符号运算
- 负数运算
- 特殊情况（除零、除1、溢出）
- 边界情况

### 运行测试 (Run Tests)
```bash
python tests/test_naive_divider.py
```

## 实现细节 (Implementation Details)

### 关键代码段 (Key Code Sections)

#### 迭代计算 (Iteration)
```python
# 1. 左移余数，带入商的最高位
shifted_remainder = concat(self.remainder[0][0:31], quotient_msb)

# 2. 试减
temp_remainder = shifted_remainder - divisor_extended

# 3. 判断并恢复
if temp_remainder < 0:
    remainder = shifted_remainder  # 恢复
    quotient = quotient << 1 | 0   # 商位为0
else:
    remainder = temp_remainder     # 保持
    quotient = quotient << 1 | 1   # 商位为1
```

#### 符号校正 (Sign Correction)
```python
# 商：异号为负
q_needs_neg = (dividend_sign XOR divisor_sign)
if q_needs_neg:
    quotient = -quotient

# 余数：与被除数同号
if dividend_sign:
    remainder = -remainder
```

## 集成说明 (Integration)

本除法器与 `SRT4Divider` 具有相同的接口，可以直接替换使用：

```python
# 在 execution.py 中
from .naive_divider import NaiveDivider

# 实例化
divider = NaiveDivider()  # 替代 SRT4Divider()

# 使用方式相同
divider.start_divide(dividend, divisor, is_signed, is_rem)
divider.tick()
ready, result, error = divider.get_result_if_ready()
```

## 优缺点分析 (Pros and Cons)

### 优点 (Advantages)
1. **算法简单**：易于理解和实现
2. **资源占用少**：不需要复杂的查找表
3. **验证容易**：逻辑清晰，容易调试
4. **适合教学**：展示了除法的基本原理

### 缺点 (Disadvantages)
1. **性能较低**：需要34个周期，而SRT-4只需18个周期
2. **吞吐率低**：每周期只计算1位

### 适用场景 (Use Cases)
- 资源受限的嵌入式系统
- 教学演示
- 对性能要求不高的应用
- 作为高性能除法器的备份实现

## 参考资料 (References)

1. RISC-V "M" Standard Extension for Integer Multiplication and Division
2. Computer Arithmetic: Algorithms and Hardware Designs
3. Digital Design and Computer Architecture (RISC-V Edition)

## 版本历史 (Version History)

- v1.0 (2025-12-27): 初始实现，支持所有RISC-V M扩展除法指令

## 作者 (Author)

Created for Assassyn-CPU project
