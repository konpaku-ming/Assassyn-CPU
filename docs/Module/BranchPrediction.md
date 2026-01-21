# 分支预测系统设计文档

> **依赖**：Assassyn Framework, `btb.py`, `tournament_predictor.py`

## 1. 概述

本 CPU 实现了一套完整的分支预测系统，包含两个主要组件：
1. **BTB (Branch Target Buffer)**：预测分支目标地址
2. **Tournament Predictor**：预测分支方向（taken/not-taken）

两者协同工作：BTB 提供目标地址，Tournament Predictor 决定是否跳转。

## 2. BTB (Branch Target Buffer)

### 2.1 结构

BTB 是一个直接映射的缓存，存储分支指令的 PC 和目标地址映射：

```python
class BTB(Module):
    def __init__(self, num_entries=64, index_bits=6):
        # BTB 存储数组
        btb_valid = RegArray(Bits(1), num_entries)    # 有效位
        btb_tags = RegArray(Bits(32), num_entries)    # 完整 PC 作为标签
        btb_targets = RegArray(Bits(32), num_entries) # 目标地址
```

### 2.2 索引计算

使用 PC 的低位（跳过最低 2 位，因为指令字对齐）作为索引：

```python
# 对于 64 项 BTB：使用 PC[7:2] 作为索引
index_32 = (pc >> UInt(32)(2)) & Bits(32)(self.index_mask)
index = index_32[0:self.index_bits - 1].bitcast(Bits(self.index_bits))
```

### 2.3 预测逻辑

```python
def predict(self, pc, btb_valid, btb_tags, btb_targets):
    index = ...  # 计算索引
    
    # 查找 BTB 项
    entry_valid = btb_valid[index]
    entry_tag = btb_tags[index]
    entry_target = btb_targets[index]
    
    # 检查命中：有效位 AND PC 匹配
    tag_match = entry_tag == pc
    hit = entry_valid & tag_match
    
    return hit, entry_target
```

### 2.4 更新逻辑

在 EX 阶段，当分支 taken 时更新 BTB：

```python
def update(self, pc, target, should_update, btb_valid, btb_tags, btb_targets):
    index = ...  # 计算索引
    
    with Condition(should_update == Bits(1)(1)):
        btb_valid[index] <= Bits(1)(1)
        btb_tags[index] <= pc
        btb_targets[index] <= target
```

## 3. Tournament Predictor

### 3.1 架构

Tournament Predictor 结合了两种预测器的优点：

```
                    ┌─────────────────┐
                    │    Selector     │
                    │  (2-bit CTR)    │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
    ┌─────────────────┐           ┌─────────────────┐
    │    Bimodal      │           │     Gshare      │
    │  (2-bit CTR)    │           │  (2-bit CTR)    │
    │ indexed by PC   │           │ indexed by      │
    │                 │           │  PC XOR GHR     │
    └─────────────────┘           └─────────────────┘
```

### 3.2 组件详解

#### Bimodal Predictor

- 2-bit 饱和计数器数组
- 索引：PC[7:2]
- 预测：计数器 >= 2 时预测 taken

#### Gshare Predictor

- 2-bit 饱和计数器数组
- 索引：PC[7:2] XOR GHR（全局历史寄存器）
- 预测：计数器 >= 2 时预测 taken
- 能够捕获分支间的相关性

#### Selector

- 2-bit 饱和计数器数组
- 索引：PC[7:2]
- 决策：计数器 >= 2 时选择 Gshare，否则选择 Bimodal

#### GHR (Global History Register)

- 6-bit 移位寄存器
- 存储最近 6 次分支的实际结果
- 每次分支后左移并插入新结果

### 3.3 预测逻辑

```python
def predict(self, pc, bimodal_counters, gshare_counters, global_history, selector_counters):
    pc_index = self._get_pc_index(pc)
    gshare_index = self._get_gshare_index(pc, global_history[0])
    
    # 读取预测器状态
    bimodal_state = bimodal_counters[pc_index]
    gshare_state = gshare_counters[gshare_index]
    selector_state = selector_counters[pc_index]
    
    # 各预测器的预测
    bimodal_taken = bimodal_state[1:1]  # MSB 表示 taken
    gshare_taken = gshare_state[1:1]
    
    # 选择器决策
    use_gshare = selector_state[1:1]
    
    # 最终预测
    predict_taken = use_gshare.select(gshare_taken, bimodal_taken)
    
    return predict_taken
```

### 3.4 更新逻辑

在 EX 阶段，对所有分支指令更新预测器：

```python
def update(self, pc, actual_taken, is_branch, ...):
    with Condition(is_branch == Bits(1)(1)):
        # 1. 更新 Bimodal 计数器
        # taken: 增加 (饱和于 3)
        # not-taken: 减少 (饱和于 0)
        
        # 2. 更新 Gshare 计数器 (同样的饱和逻辑)
        
        # 3. 更新 Selector 计数器
        # Gshare 正确而 Bimodal 错误: 增加 (偏向 Gshare)
        # Bimodal 正确而 Gshare 错误: 减少 (偏向 Bimodal)
        # 都正确或都错误: 不变
        
        # 4. 更新 GHR (左移并插入 actual_taken)
```

## 4. IF 阶段集成

```python
# 1. BTB 预测
btb_hit, btb_predicted_target = btb_impl.predict(pc, ...)

# 2. Tournament Predictor 预测
tp_predict_taken = tp_impl.predict(pc, ...)

# 3. 组合决策
predicted_next_pc = btb_hit.select(
    tp_predict_taken.select(btb_predicted_target, pc + 4),  # BTB 命中
    pc + 4,  # BTB 未命中
)
```

逻辑表：

| BTB Hit | TP Predict | 下一 PC |
| :---: | :---: | :--- |
| 0 | - | PC + 4 |
| 1 | Not-Taken | PC + 4 |
| 1 | Taken | BTB Target |

## 5. EX 阶段更新

```python
# 更新 BTB (仅在 taken 时)
should_update_btb = is_branch & is_taken & ~flush_if
btb_impl.update(pc, calc_target, should_update_btb, ...)

# 更新 Tournament Predictor (所有分支)
tp_should_update = is_branch & ~flush_if
tp_impl.update(pc, is_taken, tp_should_update, ...)
```

## 6. 配置参数

| 参数 | 默认值 | 描述 |
| :--- | :---: | :--- |
| `num_entries` | 64 | BTB/预测器表项数 |
| `index_bits` | 6 | 索引位数 (log2(num_entries)) |
| `history_bits` | 6 | GHR 位数 |

## 7. 性能分析

### 7.1 存储开销

- BTB: 64 × (1 + 32 + 32) = 4160 bits ≈ 520 bytes
- Bimodal: 64 × 2 = 128 bits
- Gshare: 64 × 2 = 128 bits
- GHR: 6 bits
- Selector: 64 × 2 = 128 bits
- **总计**: ≈ 600 bytes

### 7.2 预测准确率

Tournament Predictor 的优势：
- **Bimodal**: 适合有固定模式的分支（如循环末尾）
- **Gshare**: 适合依赖历史的分支（如 if-else 链）
- **Tournament**: 自动学习使用哪个预测器更好

典型准确率：
- 简单循环: > 95%
- 复杂条件: 80-90%
- 随机分支: ~50% (无法预测)

### 7.3 冲突处理

由于使用直接映射，不同 PC 可能映射到同一项：
- BTB: 使用完整 PC 作为标签，避免误命中
- 预测器: 冲突会导致训练干扰，但影响有限
