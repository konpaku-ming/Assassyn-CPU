# BTB 实现与 DCache 修复

## 概述

本文档描述了对 Assassyn CPU 模拟器所做的修复和增强，以解决关键的 dcache 崩溃问题，并通过分支目标缓冲器 (BTB) 实现分支预测。

## 已解决的问题

### 1. DCache 索引越界崩溃

**问题描述**：模拟器出现崩溃：
```
thread 'main' panicked at src/modules/dcache.rs:78:27:
index out of bounds: the len is 65536 but the index is 262120
```

**根本原因**：在 `src/execution.py` 中，dcache 使用字节地址直接访问，而不是字索引。SRAM 有 65536 个字（每个 4 字节），支持从 0x00000000 到 0x0003FFFF 的字节地址。然而，字节地址 262120 (0x0003FFE8) 被直接用作 65536 元素数组的索引，导致崩溃。

**修复方案**：通过右移 2 位将字节地址转换为字地址：
```python
# 修复前（错误）：
dcache.build(addr=alu_result, ...)  # alu_result 是字节地址

# 修复后（正确）：
dcache_addr = alu_result >> UInt(32)(2)  # 转换为字地址
dcache.build(addr=dcache_addr, ...)
```

这与指令缓存中使用的地址方案相匹配（参见 `src/fetch.py` 第 67 行）。

### 2. 缺少分支预测

**问题描述**：CPU 没有分支预测机制，在分支密集型代码（如循环）上造成性能损失。

**解决方案**：实现了直接映射的分支目标缓冲器 (BTB)，提供单周期分支目标预测。

## BTB 实现细节

### 架构

BTB 是一个**直接映射**缓存，具有以下特征：
- **64 个条目**（可配置）
- **6 位索引位**（log2(64)）
- **字对齐的 PC 地址**（跳过最低 2 位）
- 存储：有效位、完整 PC 作为标签和目标地址

### 组件

#### 1. BTB 模块 (`src/btb.py`)

实现了两个类：

**BTB (Module)**： 
- 保存存储数组（有效位、标签、目标地址）
- 所有条目初始化为无效

**BTBImpl (Downstream)**：
- **predict()**：执行单周期查找
  - 从 PC[7:2] 提取索引（64 个条目的第 7-2 位）
  - 从 PC[31:8] 提取标签（高位）
  - 返回 (hit, target)，其中 hit 表示有效预测
  
- **update()**：在分支解析时更新 BTB
  - 在执行阶段分支跳转时调用
  - 存储完整的 PC 作为标签和分支目标

### 集成点

#### 1. 取指阶段 (`src/fetch.py`)

`FetcherImpl.build()` 方法现在：
1. 使用当前 PC 查询 BTB
2. 如果 BTB 命中，使用预测目标作为 next_pc
3. 如果 BTB 未命中，使用 PC+4（顺序执行）

```python
btb_hit, btb_predicted_target = btb_impl.predict(
    pc=final_current_pc,
    btb_valid=btb_valid,
    btb_tags=btb_tags,
    btb_targets=btb_targets,
)

predicted_next_pc = btb_hit.select(btb_predicted_target, final_current_pc + UInt(32)(4))
```

#### 2. 执行阶段 (`src/execution.py`)

`Execution.build()` 方法现在：
1. 解析实际分支行为
2. 在分支跳转时更新 BTB
3. 在预测错误时刷新流水线（现有逻辑）

```python
should_update_btb = is_branch & is_taken & ~flush_if
btb_impl.update(
    pc=pc,
    target=calc_target,
    should_update=should_update_btb,
    btb_valid=btb_valid,
    btb_tags=btb_tags,
    btb_targets=btb_targets,
)
```

#### 3. 顶层 (`src/main.py`)

`build_cpu()` 函数现在：
1. 实例化 BTB 和 BTBImpl 模块
2. 在流水线阶段之前构建 BTB 存储
3. 将 BTB 引用传递给取指和执行阶段

## BTB 地址方案

### 索引计算
```
PC (32 位):  [31...........8][7......2][1:0]
                                索引      偏移

index = (pc >> 2) & 0x3F          # 提取 6 位（64 个条目）
stored_tag = pc                    # 存储完整 PC 用于精确匹配
```

### 标签匹配（简化）
BTB 将完整的 PC 存储为标签并比较完整的 PC：
```python
# 在 predict 中：
entry_tag = btb_tags[index]       # 之前存储的完整 PC
tag_match = (entry_tag == pc)     # 精确的 PC 比较
hit = valid & tag_match

# 在 update 中：
btb_tags[index] = pc              # 存储完整 PC
```

这种方法更简单，避免了位操作错误，同时保持了正确性。

### 标签匹配
查找 PC 时：
1. 提取索引以找到 BTB 条目
2. 检查有效位
3. 比较存储的 PC 与查找的 PC（完整 PC 比较）
4. 如果有效且 PC 完全匹配则命中

**注意**：BTB 使用完整的 PC 比较以保证简单性和正确性。这意味着：
- 每个 BTB 索引可以保存一个唯一的 PC
- 映射到同一索引的不同 PC 将导致替换（冲突缺失）
- 没有别名问题 - 只有精确的 PC 匹配才会导致命中

## 测试与验证

### 单元测试
验证脚本 (`validate_fixes.py`) 验证：
1. DCache 地址转换的正确性
2. BTB 索引产生正确的索引
3. BTB 标签匹配正确识别命中/未命中

### 预期结果

通过这些更改：
- **DCache 崩溃已修复**：地址已正确转换为字索引
- **分支预测已启用**：BTB 提供单周期预测
- **0to100 和 my0to100 应该能运行**：两个工作负载都应该能够执行而不会崩溃

## 性能考虑

### BTB 优势
- **单周期预测**：预测的分支没有流水线气泡
- **减少预测错误惩罚**：正确的预测避免刷新
- **简单实现**：直接映射，复杂度最小

### BTB 限制
- **容量**：只有 64 个条目，在大代码上可能会抖动
- **冲突缺失**：多个分支映射到同一索引
- **无方向预测**：假设分支跳转（无条件预测）

### 潜在改进
1. **更大的 BTB**：将条目增加到 128 或 256
2. **2 位饱和计数器**：添加方向预测
3. **组相联**：减少冲突缺失
4. **返回地址栈**：优化函数返回

## 修改的文件

1. **src/btb.py**（新文件）：BTB 实现
   - 带有存储数组的 BTB 模块
   - 带有预测和更新方法的 BTBImpl

2. **src/execution.py**： 
   - 修复了 dcache 地址转换（第 ~240 行）
   - 在分支解析时添加 BTB 更新

3. **src/fetch.py**：
   - 在 FetcherImpl 中添加 BTB 预测
   - 命中时使用 BTB 目标，否则使用 PC+4

4. **src/main.py**：
   - 导入 BTB 模块
   - 在 build_cpu 中实例化 BTB
   - 将 BTB 连接到流水线各级

## 调试说明

### 如果 DCache 崩溃仍然发生
1. 检查所有内存访问是否使用字地址
2. 验证地址空间不超过 256KB（64K 字 × 4 字节）
3. 在执行阶段添加边界检查

### 如果 BTB 不工作
1. 检查模拟输出中的 BTB 日志
2. 验证标签比较逻辑与存储匹配
3. 确保分支正确更新 BTB
4. 检查索引计算中的差一错误

## 参考

- 原始问题：dcache.rs:78 中的索引越界
- 崩溃地址：262120 (0x0003FFE8) → 字索引 65530（有效）
- 解决方案：地址转换防止将字节地址误用作索引
- BTB 设计遵循标准的直接映射缓存架构
