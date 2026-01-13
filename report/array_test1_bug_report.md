# Array Test 1 CPU 错误诊断报告

## 问题描述

在执行 `array_test1` 测试时，CPU 返回值为 `0x6c` (108)，而预期结果应为 `123` (0x7b)。

## 测试源代码分析

测试源代码 (`testcases/array_test1.c`) 的核心逻辑：

```c
#include "io.inc"

int a[4];
int main() {
  int b[4];
  int i;
  for (i = 0; i < 4; i++) {
    a[i] = 0;
    b[i] = i + 1;
  }
  for (i = 0; i < 4; i++) {
    printInt(a[i]);  // 打印 0, 0, 0, 0
  }

  int *p;
  p = b;
  for (i = 0; i < 4; i++) {
    printInt(p[i]);  // 打印 1, 2, 3, 4
  }
  return judgeResult % Mod; // 期望返回 123
}
```

其中 `io.inc` 定义了：

```c
int judgeResult = 0;
const int Mod = 253;

void printInt(int x) {
  judgeResult ^= x;
  judgeResult += 173;
}
```

### 预期执行结果

| 调用次数 | printInt 参数 | judgeResult 计算过程 | judgeResult 值 |
|---------|--------------|---------------------|---------------|
| 1 | 0 | 0 ^ 0 + 173 | 173 (0xAD) |
| 2 | 0 | 173 ^ 0 + 173 | 346 (0x15A) |
| 3 | 0 | 346 ^ 0 + 173 | 519 (0x207) |
| 4 | 0 | 519 ^ 0 + 173 | 692 (0x2B4) |
| 5 | 1 | 692 ^ 1 + 173 | 866 (0x362) |
| 6 | 2 | 866 ^ 2 + 173 | 1037 (0x40D) |
| 7 | 3 | 1037 ^ 3 + 173 | 1211 (0x4BB) |
| 8 | 4 | 1211 ^ 4 + 173 | 1388 (0x56C) |

最终：`1388 % 253 = 123`

## 问题诊断

### 日志分析

通过分析执行日志 (`logs/arrar_test1.log`)，追踪了 `judgeResult` 变量（存储在地址 `0x11b0`）的存储操作：

| Cycle | Store Data | 期望值 | 状态 |
|-------|-----------|--------|-----|
| 60 | 0xAD | 0xAD | ✓ OK |
| 78 | 0x15A | 0x15A | ✓ OK |
| 92 | 0x107 | 0x207 | ✗ 错误 |
| 106 | 0xB4 | 0x2B4 | ✗ 错误 |
| 123 | 0x162 | 0x362 | ✗ 错误 |
| 138 | 0x10D | 0x40D | ✗ 错误 |
| 153 | 0xBB | 0x4BB | ✗ 错误 |
| 168 | 0x16C | 0x56C | ✗ 错误 |

### 关键发现

从第 3 次 `printInt` 调用开始，存储的值开始出错。具体分析：

1. **Cycle 78**: 存储 `0x15A` 到地址 `0x11b0` (正确)
2. **Cycle 88-89**: 从地址 `0x11b0` 加载，但得到 `0x5A` 而非 `0x15A`

**重要现象**：值 `0x15A` (十进制 346) 变成了 `0x5A` (十进制 90)

```
0x15A = 0001 0101 1010 (二进制)
0x5A  =      0101 1010 (二进制)
```

高位的 `0x100` (bit 8) 丢失了！

### 根本原因

在 `src/memory.py` 的 `SingleMemory` 类中，存储操作的掩码生成逻辑存在 bug。

**错误代码** (第 173-178 行)：

```python
raw_mask = final_width.select1hot(
    Bits(32)(0xFFFFFFFF),  # Word  ← 错误：这应该是 BYTE
    Bits(32)(0x0000FFFF),  # Half  ← 正确
    Bits(32)(0x000000FF),  # Byte  ← 错误：这应该是 WORD
).bitcast(UInt(32))
```

根据 `control_signals.py` 中 `MemWidth` 的定义：
- `BYTE = 0b001` (bit 0)
- `HALF = 0b010` (bit 1)
- `WORD = 0b100` (bit 2)

`select1hot` 函数按照 bit 位置依次选择参数：
- 第 1 个参数对应 bit 0 (BYTE)
- 第 2 个参数对应 bit 1 (HALF)
- 第 3 个参数对应 bit 2 (WORD)

因此，当执行 WORD 存储时（`mem_width = 0b100`），实际使用的是 BYTE 掩码 (`0x000000FF`)，导致只有最低 8 位被正确存储！

## 修复方案

**修正后的代码**：

```python
raw_mask = final_width.select1hot(
    Bits(32)(0x000000FF),  # Byte (bit 0)
    Bits(32)(0x0000FFFF),  # Half (bit 1)
    Bits(32)(0xFFFFFFFF),  # Word (bit 2)
).bitcast(UInt(32))
```

## 影响范围

此 bug 影响所有 32 位字（WORD）存储操作，会导致：
1. 高 24 位数据在存储时被清零
2. 仅当数据值小于 256 (0xFF) 时存储结果正确
3. 数据值超过 255 时，高位数据丢失

## 验证建议

修复后应重新运行以下测试：
1. `array_test1` - 验证返回值为 123
2. 所有涉及 32 位内存写入的测试用例

## 总结

| 项目 | 内容 |
|-----|------|
| 问题类型 | 内存存储操作 bug |
| 根本原因 | `select1hot` 参数顺序与 `MemWidth` 定义不匹配 |
| 影响范围 | 所有 WORD 存储操作 |
| 修复位置 | `src/memory.py` 第 173-178 行 |
| 修复方式 | 调整 `select1hot` 参数顺序 |
