# 除法器错误分析报告

## 问题描述

使用新的恢复除法器（naive_divider）运行 single_div 测试时，计算 0x375f00 / 2 得到错误的结果 0x375f00（即被除数本身），而不是期望的结果 0x1BAF80。

## 测试程序分析

从 `workloads/single_div.exe` 可以看出测试程序的逻辑：

```assembly
lui  a0, 886        # a0 = 0x376000
addi a0, a0, -256   # a0 = 0x375f00 (3629824)
li   a1, 2          # a1 = 2
div  a0, a0, a1     # a0 = a0 / 2 = 0x1BAF80 (1814912)
ebreak              # 停止
```

期望结果：0x375f00 / 2 = 0x1BAF80 (1814912)
实际结果：0x375f00 (3629824，即被除数本身)

## 日志分析

从 `logs/single_div.log` 中可以看到关键信息：

### 除法开始
```
Cycle @7.00: NaiveDivider: Start division, dividend=0x375f00, divisor=0x2, signed=1
```

### 除法迭代
```
Cycle @9.00: NaiveDivider: Preprocessing complete, starting 32 iterations
Cycle @42.00: NaiveDivider: Iterations complete, entering post-processing
```

除法器执行了 32 次迭代（恢复除法算法标准流程）。

### 除法结束
```
Cycle @43.00: NaiveDivider: DIV_END - quotient=0x375f00, remainder=0x0
Cycle @43.00: NaiveDivider: q_signed=0x375f00, rem_signed=0x0, is_rem=0
Cycle @43.00: NaiveDivider: Completed, result=0x0
```

**问题关键**：经过 32 次迭代后，商（quotient）寄存器的值仍然是 0x375f00，没有发生变化！

### 结果写回
```
Cycle @44.00: EX: Naive divider result ready: 0x375f00, error=0
Cycle @44.00: EX: Injecting pending DIV result to MEM (rd=x10, result=0x375f00)
```

最终将错误的结果 0x375f00 写入寄存器 x10。

## 问题根源分析

### 恢复除法算法原理

恢复除法采用移位寄存器方法：
1. 初始化：商 Q = 被除数 D，余数 R = 0
2. 对于每次迭代（共 32 次）：
   - 提取 Q 的最高位 Q[31]
   - 将 R 左移一位并插入 Q[31]：R = (R << 1) | Q[31]
   - 尝试减法：temp = R - 除数
   - 如果 temp < 0（负数）：
     * 恢复：R 保持不变
     * Q 左移一位并插入 0：Q = (Q << 1) | 0
   - 否则：
     * 保持减法结果：R = temp
     * Q 左移一位并插入 1：Q = (Q << 1) | 1
3. 32 次迭代后，Q 包含最终的商，R 包含余数

### 代码实现分析

在 `src/naive_divider.py` 的 DIV_WORKING 状态中（第 238-287 行）：

```python
# 提取商的最高位
quotient_msb = self.quotient[0][31:31]

# 余数左移并插入商的最高位
shifted_remainder = concat(self.remainder[0][0:31], quotient_msb)

# 减法
divisor_extended = concat(Bits(1)(0), self.divisor_r[0])
temp_remainder = (shifted_remainder - divisor_extended)

# 判断结果是否为负
is_negative = temp_remainder[32:32]

# 根据判断结果更新商
with Condition(is_negative == Bits(1)(1)):
    self.remainder[0] = shifted_remainder
    self.quotient[0] = concat(self.quotient[0][0:30], Bits(1)(0))  # 左移并插入 0

with Condition(is_negative != Bits(1)(1)):
    self.remainder[0] = temp_remainder
    self.quotient[0] = concat(self.quotient[0][0:30], Bits(1)(1))  # 左移并插入 1
```

### 预期行为

对于 0x375f00 / 2 的第一次迭代：
- 初始 Q = 0x00375F00 = 0b00000000001101110101111100000000
- 提取 Q[31] = 0
- shifted_R = 0，temp_R = 0 - 2 = -2（负数）
- 应该执行：Q = concat(Q[0:30], 0)
  * Q[0:30] = 0b0000000001101110101111100000000（31 位，即 bits 0-30）
  * concat(31位, 1位) = 0b00000000011011101011111000000000（32 位）
  * 结果 = 0x006EBE00

按此逻辑，32 次迭代后，原始的 32 位应该全部移出，32 个新计算的商位应该移入，最终商应该是 0x1BAF80。

### 实际行为

从日志可见，32 次迭代后商仍然是 0x375f00，说明**商寄存器根本没有被更新**！

### 可能的原因

1. **位切片操作问题**：`quotient[0:30]` 可能没有正确提取 bits 0-30
2. **concat 操作问题**：concat 可能没有按预期拼接位
3. **条件赋值问题**：Condition 块内的赋值可能没有生效
4. **寄存器更新时序问题**：赋值可能因某种原因被丢失

## 是流水线问题还是计算错误？

**结论：这是计算错误，而非流水线问题。**

理由：
1. 流水线正确处理了除法器的多周期操作（暂停、等待、继续）
2. 数据冒险单元正确检测到 div_busy 并暂停流水线
3. 除法完成后正确将结果注入 MEM 阶段
4. 问题出在除法器内部的计算逻辑，具体是商寄存器的移位更新操作

## 问题定位

问题的根源在于 `src/naive_divider.py` 第 271 行和第 278 行的商寄存器更新操作：

```python
self.quotient[0] = concat(self.quotient[0][0:30], Bits(1)(0))  # 或 Bits(1)(1)
```

这个操作应该实现 Q = (Q << 1) | bit 的功能，即：
- 将 Q 的 bits [0:30] 左移到 bits [1:31]
- 在 bit [0] 处插入新的商位

但实际运行时这个赋值似乎没有生效，导致商寄存器保持初始值不变。

## 建议的修复方案

需要修改 DIV_WORKING 状态中的商更新逻辑。可能的修复方向：

1. **检查位切片语法**：确认 `[0:30]` 是否正确提取了 31 位
2. **重构 concat 操作**：尝试使用不同的方式实现左移
3. **添加调试日志**：在迭代过程中输出商的值，观察变化
4. **参考 SRT 除法器**：查看 `divider.py` 中类似的移位操作如何实现

## 下一步行动

1. 修改代码以修复商寄存器更新问题
2. 重新运行 single_div 测试验证修复
3. 运行其他除法测试（div1to10 等）确保修复的通用性
4. 更新测试日志
