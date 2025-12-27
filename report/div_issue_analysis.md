# DIV指令Op1数值跳变问题分析报告

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

## 问题根本原因

**已找到！** `find_leading_one()` 函数实现错误。

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

修改 divider.py 中的 `find_leading_one()` 函数：

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

## 日志关键信息摘要

```
Cycle 16: DIV by 2 starts, dividend=0x375f00, divisor=0x2
Cycle 17: Divider: Starting normal division (DIV_PRE)
Cycle 35: Divider: Iterations complete, entering post-processing
Cycle 36: Divider: Completed, result=0x375f00 (旧值)
Cycle 37: EX: SRT-4 divider result ready and consumed: 0x0 (错误！)
Cycle 39: WB: Write x10 <= 0x0
Cycle 40: Divider: Start division, dividend=0x0, divisor=0x3 (错误的被除数)
```
