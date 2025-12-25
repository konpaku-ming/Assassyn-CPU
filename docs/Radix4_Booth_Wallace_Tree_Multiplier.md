# Radix-4 Booth + Wallace Tree 乘法器实现文档

## 概述

本文档描述了 Assassyn-CPU 中实现的 3 周期 Radix-4 Booth 编码 + Wallace Tree 乘法器架构。

## 架构总览

### 流水线结构

乘法器采用 3 级流水线设计，每个乘法操作需要 3 个时钟周期完成：

```
Cycle 1 (EX1): Booth 编码 + 部分积生成
Cycle 2 (EX2): Wallace Tree 压缩 (大部分层级)
Cycle 3 (EX3): 最终压缩 + 进位传播加法器
```

### 支持的操作

- **MUL**: 有符号 × 有符号 → 返回低 32 位
- **MULH**: 有符号 × 有符号 → 返回高 32 位
- **MULHSU**: 有符号 × 无符号 → 返回高 32 位
- **MULHU**: 无符号 × 无符号 → 返回高 32 位

## Radix-4 Booth 编码算法

### 基本原理

Radix-4 Booth 编码通过一次检查 3 位来重新编码乘数，从而减少部分积的数量。

### 编码规则

对于乘数的每个位置 i，检查位 [i+1, i, i-1]（最低位下方补 0）：

| 位模式 [i+1, i, i-1] | Booth 数字 | 部分积 |
|---------------------|-----------|--------|
| 000                 | 0         | 0      |
| 001                 | +1        | +M     |
| 010                 | +1        | +M     |
| 011                 | +2        | +2M    |
| 100                 | -2        | -2M    |
| 101                 | -1        | -M     |
| 110                 | -1        | -M     |
| 111                 | 0         | 0      |

其中 M 是被乘数（multiplicand）。

### 部分积生成

- 对于 32 位乘数，Radix-4 Booth 编码生成 **17 个部分积**（而非普通方法的 32 个）
- 每个部分积的计算方式：
  - 0: 全零
  - ±M: 被乘数或其补码
  - ±2M: 被乘数左移 1 位或其补码

### 优势

1. **减少部分积数量**: 从 32 个减少到 17 个
2. **简化硬件**: 2M 只需简单的左移操作
3. **性能提升**: 更少的部分积意味着更浅的 Wallace Tree

## Wallace Tree 压缩

### 基本原理

Wallace Tree 使用 3:2 压缩器（全加器）将多个部分积逐层减少为两个数，这两个数可以用最终的进位传播加法器相加。

### 3:2 压缩器

3:2 压缩器（也称为全加器）接受 3 个输入位，产生 2 个输出：

```
输入: a, b, c
输出:
  sum   = a ⊕ b ⊕ c
  carry = (a & b) | (b & c) | (a & c)
```

进位输出被左移 1 位位置。

### 压缩层级

对于 17 个部分积，Wallace Tree 的压缩过程如下：

| 层级 | 输入行数 | 压缩器数量 | 输出行数 | 说明 |
|-----|---------|-----------|---------|------|
| 0   | 17      | -         | 17      | 初始部分积 |
| 1   | 17      | 5         | 12      | 使用 5 个压缩器处理 15 行 → 10 行，保留 2 行 |
| 2   | 12      | 4         | 8       | 使用 4 个压缩器处理 12 行 → 8 行 |
| 3   | 8       | 2-3       | 6       | 继续压缩 |
| 4   | 6       | 2         | 4       | 继续压缩 |
| 5   | 4       | 1         | 3       | 继续压缩 |
| 6   | 3       | 1         | 2       | 最终得到 2 行 |

### 硬件资源

- **总全加器数量**: 约 50-70 个（对于 64 位输出）
- **树深度**: 6-7 层
- **延迟**: O(log n)，其中 n 是部分积数量

## 3 周期流水线实现

### Cycle 1 (EX1): Booth 编码 + 部分积生成

**硬件操作**：
1. 对乘数进行 Radix-4 Booth 重编码
2. 为每个 Booth 数字生成部分积：
   - 使用多路复用器选择: 0, ±M, ±2M
   - 2M 通过左移 1 位实现
3. 符号扩展所有部分积到 65 位
4. 输出 17 个部分积阵列

**流水线寄存器**：
- `ex1_op1`, `ex1_op2`: 操作数
- `ex1_op1_signed`, `ex1_op2_signed`: 符号位标志
- `ex1_result_high`: 结果选择（高/低 32 位）

### Cycle 2 (EX2): Wallace Tree 压缩

**硬件操作**：
1. 执行 4-5 层 3:2 压缩
2. 将 17 行减少到 3-4 行
3. 大部分的计算工作在此阶段完成

**流水线寄存器**：
- `ex2_partial_low`, `ex2_partial_high`: 中间结果
- `ex2_result_high`: 结果选择标志

**资源使用**：
- 约 40-50 个全加器
- 并行工作，关键路径约 4-5 个全加器延迟

### Cycle 3 (EX3): 最终压缩 + 进位传播加法器

**硬件操作**：
1. 执行剩余的压缩层（1-2 层）
2. 将结果减少到 2 行
3. 使用进位传播加法器（CPA）将最终 2 行相加
4. 根据操作类型选择高/低 32 位输出

**进位传播加法器选项**：
- **行波进位加法器** (Ripple-Carry): 简单但较慢
- **超前进位加法器** (Carry-Lookahead): 更快，面积较大
- **进位选择加法器** (Carry-Select): 平衡方案
- **Kogge-Stone 加法器**: 最快，面积最大

**流水线寄存器**：
- `ex3_result`: 最终 32 位结果
- `ex3_valid`: 结果有效标志

## 代码实现

### 文件结构

```
src/
├── multiplier.py          # 3 周期乘法器实现
└── execution.py           # 执行阶段集成
```

### 核心类

#### `BoothWallaceMul` (multiplier.py)

管理 3 周期乘法流水线的主要类：

```python
class BoothWallaceMul:
    def __init__(self):
        # 流水线寄存器
        self.ex1_valid, self.ex1_op1, self.ex1_op2, ...
        self.ex2_valid, self.ex2_partial_low, ...
        self.ex3_valid, self.ex3_result
    
    def start_multiply(self, op1, op2, op1_signed, op2_signed, result_high):
        """启动新的乘法操作"""
    
    def cycle_ex1(self):
        """执行 EX1 阶段：Booth 编码 + 部分积生成"""
    
    def cycle_ex2(self):
        """执行 EX2 阶段：Wallace Tree 压缩"""
    
    def cycle_ex3(self):
        """执行 EX3 阶段：最终压缩 + CPA"""
    
    def get_result_if_ready(self):
        """获取就绪的乘法结果"""
```

### 执行阶段集成 (execution.py)

```python
# 初始化乘法器
multiplier = BoothWallaceMul()

# 检测乘法操作
is_mul_op = (ctrl.alu_func == ALUOp.MUL) | ...

# 启动乘法
with Condition(is_mul_op & ~flush_if):
    multiplier.start_multiply(alu_op1, alu_op2, ...)

# 推进流水线
multiplier.cycle_ex1()
multiplier.cycle_ex2()
multiplier.cycle_ex3()

# 获取结果
mul_result_valid, mul_result_value = multiplier.get_result_if_ready()
```

## 性能分析

### 面积 (Area)

- **Booth 编码器**: 17 个 Booth 数字生成器
- **部分积选择器**: 17 × 64 位多路复用器
- **Wallace Tree**: 50-70 个全加器
- **进位传播加法器**: 64 位 CPA
- **流水线寄存器**: ~200 个触发器

### 时序 (Timing)

- **总延迟**: 3 个时钟周期
- **吞吐量**: 每周期 1 个新乘法（流水线满载时）
- **关键路径** (每个周期):
  - EX1: Booth 编码 + 部分积选择
  - EX2: ~4-5 个全加器延迟
  - EX3: 最终压缩 + CPA

### 功耗 (Power)

- **动态功耗**: 主要来自 Wallace Tree 的切换活动
- **静态功耗**: 流水线寄存器的保持功耗
- **优化**: 门控时钟可在非乘法周期关闭乘法器

## 验证与测试

### 测试用例 (tests/test_mul_extension.py)

测试覆盖：
- MUL: 正数、负数、零、边界情况
- MULH: 有符号高位结果
- MULHSU: 混合符号高位结果
- MULHU: 无符号高位结果

### 功能验证

乘法器实现已验证：
1. 数学正确性：所有 RISC-V M 扩展操作
2. 符号处理：正确的符号/零扩展
3. 边界情况：最大值、最小值、零

## 与单周期实现的比较

### 原实现（单周期）

```python
# 直接使用 64 位乘法
product = op1_extended.bitcast(UInt(64)) * op2_extended.bitcast(UInt(64))
result = product[0:31] or product[32:63]
```

### 新实现（3 周期）

- **优势**:
  - 更真实的硬件实现
  - 更短的关键路径（更高的时钟频率）
  - 更好的面积/性能平衡
  - 支持流水线并行

- **权衡**:
  - 增加了延迟（3 周期 vs 1 周期）
  - 需要更复杂的流水线控制
  - 增加了数据冒险处理的复杂性

## 未来改进

### 短期

1. **流水线控制**: 实现完整的 3 周期停顿逻辑
2. **冒险处理**: 为进行中的乘法添加前递逻辑
3. **性能优化**: 添加早期终止（对于小操作数）

### 长期

1. **可配置延迟**: 支持 1/2/3 周期模式
2. **除法支持**: 添加除法单元
3. **融合乘加**: 实现 FMA (a×b+c) 操作
4. **SIMD 扩展**: 支持向量乘法操作

## 参考资料

1. Booth, A.D. (1951). "A signed binary multiplication technique"
2. Wallace, C.S. (1964). "A Suggestion for a Fast Multiplier"
3. RISC-V ISA Specification - M Extension
4. Weste & Harris (2010). "CMOS VLSI Design" - Chapter 11: Datapath Subsystems

## 版本历史

- v1.0 (2025-12-25): 初始实现
  - 3 周期流水线结构
  - Radix-4 Booth 编码
  - Wallace Tree 压缩
  - 完整文档
