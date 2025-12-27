# DIV指令Op1数值跳变问题分析报告

## 执行摘要

本报告详细分析了Assassyn CPU中除法指令出现的数值跳变问题。经过深入调查，发现了两个关键bug：

1. **除数归一化bug**：`find_leading_one()` 函数实现错误，导致除数归一化失败
2. **流水线stall时序bug**：MUL/DIV指令启动时，busy信号延迟一个周期才生效，导致下一条指令错误地进入EX阶段

这两个问题共同导致了除法结果错误和Op1数值跳变现象。

## 问题概述

在div1to10测试中，除法指令的Op1出现异常数值跳变现象。测试程序计算 10! ÷ 1, 10! ÷ 2, ..., 10! ÷ 10，初始值为3628800 (0x375f00)。

## 预期结果 vs 实际结果

| 运算 | 预期结果 | 实际结果 | 状态 |
|------|---------|---------|------|
| 10! ÷ 1 | 0x375f00 (3628800) | 0x375f00 | ✓ 正确 |
| 10! ÷ 2 | 0x1baf80 (1814400) | 0x0 | ✗ 错误 |
| 10! ÷ 3 | 0x127500 (1209600) | 0x55555554 | ✗ 错误 |
| 后续除法 | ... | 0x55555554 | ✗ 都错误 |

## 根本原因分析

### 第一个错误：10! ÷ 2 = 0x0

通过日志分析发现：

1. **Cycle 16**: DIV by 2 启动，被除数=0x375f00（正确）
2. **Cycle 17**: Divider 进入 DIV_PRE 预处理状态
3. **Cycle 35**: Divider 进入 DIV_END 后处理状态
4. **Cycle 36**: Divider 完成，日志显示 result=0x375f00（这是寄存器中的旧值）
5. **Cycle 37**: 结果被消费，实际值为 0x0（**错误！**）

### 第二个错误：10! ÷ 3 使用错误的被除数

1. **Cycle 37**: DIV by 2 的结果 0x0 被注入流水线
2. **Cycle 39**: WB 阶段将 0x0 写入 x10
3. **Cycle 40**: DIV by 3 启动，但被除数=0x0（**应该是 0x1baf80！**）

### 问题定位

**核心问题**: SRT-4除法器在计算 0x375f00 ÷ 2 时产生了错误的结果 0x0。

可能的原因：
1. 商累加器 `Q` 在迭代过程中没有正确更新
2. 除数归一化/移位逻辑有bug
3. 后处理阶段的符号矫正逻辑有问题
4. 余数调整逻辑有误

## 流水线Stall机制检查

流水线的Stall机制**工作正常**：

- DataHazardUnit 正确检测到 `div_busy=1`
- 流水线在除法计算期间正确产生 stall_if=1
- IF/ID 级插入 NOP 直到除法完成

## 除法结果写回检查

除法结果的写回流程也基本正常：

1. 除法结果通过 `div_pending_rd` 和 `div_pending_valid` 机制保存
2. 结果 ready 时通过 bypass 机制注入 MEM 阶段
3. 最终通过 WB 阶段写入寄存器文件

**但是**，写回的值是错误的（0x0 而不是 0x1baf80），说明问题出在除法器的计算逻辑上。

## 问题根本原因 (更新)

**已找到两个关键bug！**

### Bug 1: 除数归一化错误

`find_leading_one()` 函数实现错误（已在第一次修复中解决）。

### Bug 2: 流水线stall时序错误 ⭐ **新发现**

**问题描述**：
MUL/DIV指令启动时，busy信号存在一个周期的延迟，导致下一条指令错误地进入EX阶段。

**时序分析**：
```
Cycle 16: DIV指令在EX阶段
  - 调用 divider.start_divide()
  - 设置 self.busy[0] = 1 （寄存器更新，在周期结束时生效）
  - 返回 div_busy = divider.is_busy() = 0 （读取的是旧值）
  
End of Cycle 16: 
  - self.busy[0] 寄存器更新为 1
  
Cycle 17: ADDI指令错误地进入EX阶段
  - DataHazardUnit 读取 div_busy = 1
  - 设置 stall_if = 1
  - 但为时已晚，ADDI已经进入EX！
```

**根本原因**：
在execution.py中，`div_busy = divider.is_busy()` 只检查divider内部的busy寄存器，但该寄存器在当前周期内还未更新。需要同时检查是否有DIV指令正在启动。

**影响**：
虽然流水线后续会正确stall，但DIV指令本身已经离开EX阶段，后续指令占据了EX。这导致：
1. DIV指令的上下文（操作数、rd等）必须通过pending机制保存
2. 如果pending机制有任何问题，会导致结果错误
3. 违反了用户期望的"DIV指令应该在EX阶段停留18个周期"的行为

### 错误的实现
```python
def find_leading_one(self, d):
    pos = Bits(5)(0)
    for i in range(0, 32):
        bit_set = (d[i:i] == Bits(1)(1))
        pos = bit_set.select(Bits(5)(i), pos)
    return pos  # 对于 divisor=2, 返回 1
```

这个实现返回 MSB 的位置（对于 divisor=2 返回 1）。

### 正确的实现应该是

根据 Verilog 参考代码 find_1.v，该函数应该返回 `30 - MSB_position`：
- 对于 divisor=2 (MSB 在位置 1)
- 应该返回 30 - 1 = 29
- 然后 div_shift = pos_1 + 1 = 30
- 移位后: 2 << 30 = 0x80000000 ✓

### 错误的影响

使用错误的实现时：
- pos_1 = 1（错误）
- div_shift = 2（错误，应该是 30）
- 移位后: 2 << 2 = 8 = 0b1000
- 归一化后的除数高4位 = 0x0（错误，应该是 0x8）

这导致 SRT-4 算法的商选择表查找失败，产生错误的商值。

## 修复方案

### 修复1: 除数归一化 (divider.py)

修改 `find_leading_one()` 函数使其与Verilog find_1.v模块行为一致：

```python
def find_leading_one(self, d):
    # Find the MSB position first
    msb_pos = Bits(5)(0)
    for i in range(0, 32):
        bit_set = (d[i:i] == Bits(1)(1))
        msb_pos = bit_set.select(Bits(5)(i), msb_pos)
    
    # Return 30 - MSB_position to match Verilog find_1 behavior
    pos_1 = (Bits(5)(30).bitcast(UInt(5)) - msb_pos.bitcast(UInt(5))).bitcast(Bits(5))
    return pos_1
```

### 修复2: 流水线stall时序 (execution.py) ⭐ **新增**

修改 `mul_busy` 和 `div_busy` 的计算，使其在MUL/DIV启动的同一周期就返回busy状态：

```python
# CRITICAL: Include mul_can_start/div_can_start to signal busy immediately
# when a new MUL/DIV starts in the current cycle. Otherwise, there's a
# one-cycle delay before the busy signal propagates, allowing the next
# instruction to incorrectly enter EX.
mul_busy = multiplier.is_busy() | mul_can_start
div_busy = divider.is_busy() | div_can_start
```

这样当DIV指令在cycle N启动时：
- `div_can_start = True`
- `div_busy = True` (立即生效)
- DataHazardUnit 在同一周期检测到 `div_busy=1`
- 阻止下一条指令进入EX
- DIV指令保持在EX阶段直到完成

## 日志关键信息摘要

```
Cycle 16: DIV by 2 starts, dividend=0x375f00, divisor=0x2
Cycle 17: Divider: Starting normal division (DIV_PRE)
Cycle 35: Divider: Iterations complete, entering post-processing
Cycle 36: Divider: Completed, result=0x375f00 (寄存器中的旧值)
Cycle 37: EX: SRT-4 divider result ready and consumed: 0x0 (错误！)
Cycle 39: WB: Write x10 <= 0x0
Cycle 40: Divider: Start division, dividend=0x0, divisor=0x3 (使用了错误的被除数)
```

## 修复验证

由于运行环境限制，无法直接运行测试验证。但根据以下分析，修复应该是正确的：

1. **理论分析**：修复后的实现与Verilog参考代码find_1.v的行为完全一致
2. **数学验证**：对于divisor=2，修复后返回29，div_shift=30，2<<30=0x80000000，高4位=0x8 ✓
3. **代码审查**：实现逻辑严格遵循Verilog模块的设计意图

## 总结

本次问题源于两个独立但相互影响的bug：

1. **除数归一化错误**：导致SRT-4算法无法正确计算商
2. **流水线stall时序错误**：导致DIV指令无法在EX阶段停留完整周期

两个bug必须同时修复才能彻底解决问题。第一次修复只解决了归一化问题，但stall时序问题仍然存在，导致用户测试时仍然失败。

修复后的预期行为：
1. DIV指令在cycle N进入EX并启动除法器
2. div_busy在cycle N立即变为1
3. 流水线从cycle N+1开始stall
4. DIV指令在EX停留直到除法完成（约18个周期）
5. 除法结果正确计算并写回目标寄存器

建议在有条件时运行完整测试套件以验证修复效果。
