# 分支预测原理与实现详解

> **本文档面向硬件新手，详细讲解分支预测的原理、本仓库的具体实现，以及分支预测在流水线中的时序行为。**

## 目录

1. [什么是分支预测？](#1-什么是分支预测)
2. [分支预测的核心组件](#2-分支预测的核心组件)
3. [BTB (Branch Target Buffer) 详解](#3-btb-branch-target-buffer-详解)
4. [Tournament Predictor 详解](#4-tournament-predictor-详解)
5. [分支预测在流水线中的时序行为](#5-分支预测在流水线中的时序行为)
6. [分支预测失误的处理](#6-分支预测失误的处理)
7. [性能影响分析](#7-性能影响分析)

---

## 1. 什么是分支预测？

### 1.1 问题背景

在现代 CPU 流水线中，指令的取指 (IF) 阶段需要知道下一条要执行的指令地址。对于顺序执行的指令，下一条指令地址就是当前 PC + 4（假设指令长度为 4 字节）。

但是，对于**分支指令**（如 `beq`, `bne`, `jal` 等），情况就复杂了：
- 分支是否跳转（taken/not taken）需要在 EX 阶段才能确定
- 跳转目标地址也需要计算后才能知道

如果 IF 阶段傻傻地等待 EX 阶段的结果，流水线就会停顿，严重影响性能。

### 1.2 解决方案：分支预测

分支预测是一种"投机执行"技术：在分支结果出来之前，先**猜测**分支的行为，让流水线继续工作。

分支预测需要回答两个问题：
1. **方向预测**：分支是否会跳转？（taken vs not taken）
2. **目标预测**：如果跳转，跳转到哪里？

### 1.3 本仓库的分支预测架构

本仓库实现了一个完整的分支预测系统，包含两个核心组件：

| 组件 | 功能 | 预测内容 |
|------|------|---------|
| **BTB** (Branch Target Buffer) | 分支目标缓冲器 | 预测**跳转目标地址** |
| **Tournament Predictor** | 竞争预测器 | 预测**是否跳转** |

这两个组件协同工作：
- BTB 存储历史上看到的分支指令及其目标地址
- Tournament Predictor 决定某个分支指令是否应该跳转
- 只有当 BTB 命中**且** Tournament Predictor 预测跳转时，才使用 BTB 提供的目标地址

---

## 2. 分支预测的核心组件

### 2.1 硬件组成概览

```
                    ┌─────────────────────────────────────────────────────┐
                    │                   分支预测系统                        │
                    │                                                     │
   当前 PC ──────────►   ┌───────────────┐      ┌──────────────────────┐  │
                    │   │     BTB       │      │  Tournament Predictor │  │
                    │   │  (目标地址预测) │      │     (方向预测)         │  │
                    │   │               │      │                      │  │
                    │   │  64 条目      │      │  Bimodal + Gshare    │  │
                    │   │  直接映射      │      │  + Selector          │  │
                    │   └───────┬───────┘      └──────────┬───────────┘  │
                    │           │                         │               │
                    │           │ hit/miss, target        │ taken/not-taken│
                    │           │                         │               │
                    │           └─────────┬───────────────┘               │
                    │                     │                               │
                    │                     ▼                               │
                    │              ┌──────────────┐                       │
                    │              │   Next PC    │                       │
                    │              │   选择逻辑    │                       │
                    │              └──────────────┘                       │
                    └─────────────────────────────────────────────────────┘
```

### 2.2 数据流说明

1. **IF 阶段**：用当前 PC 查询 BTB 和 Tournament Predictor
2. **预测结果**：
   - 如果 BTB 命中且 Tournament Predictor 预测跳转 → 使用 BTB 的目标地址
   - 如果 BTB 命中但 Tournament Predictor 预测不跳转 → 使用 PC+4
   - 如果 BTB 未命中 → 使用 PC+4
3. **EX 阶段**：计算实际的分支结果，如果预测错误，刷新流水线并更新预测器

---

## 3. BTB (Branch Target Buffer) 详解

### 3.1 BTB 是什么？

BTB（分支目标缓冲器）是一个硬件缓存，用于存储之前执行过的分支指令的**目标地址**。

可以把 BTB 想象成一张表：

| 索引 (Index) | 有效位 (Valid) | 标签 (Tag) | 目标地址 (Target) |
|--------------|----------------|------------|-------------------|
| 0            | 0              | -          | -                 |
| 1            | 1              | 0x00400008 | 0x00400020        |
| 2            | 0              | -          | -                 |
| ...          | ...            | ...        | ...               |
| 63           | 1              | 0x004000FC | 0x00400010        |

### 3.2 BTB 的硬件结构

本仓库的 BTB 是一个 **64 条目、直接映射** 的缓存结构，使用 **SRAM** 存储。

**代码对照** (`src/btb.py`)：

```python
class BTB(Module):
    def __init__(self, num_entries=64, index_bits=6):
        # num_entries=64: BTB 有 64 个条目
        # index_bits=6: 使用 6 位来索引 (2^6 = 64)
        ...

    @module.combinational
    def build(self):
        # BTB 使用 SRAM 存储，每个条目 65 位
        # 位布局: [64]=valid, [63:32]=tag (32位PC), [31:0]=target (32位目标地址)
        btb_sram = SRAM(width=65, depth=self.num_entries)
        btb_sram.name = "btb_sram"
        return btb_sram
```

**硬件细节解释**：
- `SRAM(width=65, depth=64)` 表示一个 65 位宽、64 条目深的 SRAM
- 每个条目包含：1 位有效位 + 32 位标签 + 32 位目标地址 = 65 位
- SRAM 读取有 **1 周期延迟**：本周期发起读请求，下周期得到数据

**SRAM vs RegArray**：
- SRAM 使用真正的存储器单元，面积效率高，适合大容量存储
- RegArray 使用触发器实现，面积大但可以组合读取（无延迟）
- BTB 使用 SRAM 更符合实际硬件实现

### 3.3 BTB 的索引机制

BTB 使用 PC 的一部分作为索引来定位条目：

```
  31                   8  7     2  1  0
 ┌──────────────────────┬────────┬────┐
 │       高位地址        │  索引  │ 00 │  ← PC 地址
 └──────────────────────┴────────┴────┘
                          │
                          │  使用 PC[7:2] 作为索引
                          ▼
                    ┌──────────┐
                    │  BTB表   │
                    │  条目 0  │
                    │  条目 1  │
                    │   ...    │
                    │  条目 63 │
                    └──────────┘
```

**为什么跳过最低 2 位？**

因为 RISC-V 指令是 4 字节对齐的，PC 的最低 2 位永远是 `00`，没有区分意义。

**代码对照** (`src/btb.py` - `BTBImpl.predict` 方法)：

```python
def predict(self, pc, btb_sram):
    # 读取 SRAM 输出（来自上一周期的读取）
    entry = btb_sram.dout[0].bitcast(Bits(65))
    
    # 解包条目：[64]=valid, [63:32]=tag, [31:0]=target
    entry_valid = entry[64:64]
    entry_tag = entry[32:63]
    entry_target = entry[0:31]
    
    # 判断是否命中：有效位为1 且 存储的PC与参数PC完全匹配
    tag_match = entry_tag == pc
    hit = entry_valid & tag_match
    
    return hit, entry_target
```

**SRAM 时序说明**：
- SRAM 读取有 1 周期延迟
- 本周期用 PC_T 读取 BTB，下周期得到条目
- 因此 `predict()` 的参数 `pc` 应该是上周期用于读取的 PC（即 `last_pc_reg`）
- 只有当当前 PC 等于上周期的 PC（如 stall 或正确预测后的循环）时，BTB 预测才有效

### 3.4 BTB 的更新策略

BTB 只在分支**实际跳转**时才更新。这是因为：
- 如果分支从未跳转过，就没有必要记录它的目标地址
- 这样可以节省 BTB 空间，让它专注于那些会跳转的分支

**代码对照** (`src/btb.py` - `BTBImpl.drive_sram` 方法)：

```python
def drive_sram(self, read_pc, write_pc, write_target, should_write, btb_sram):
    # 提取读/写索引
    read_index = self._extract_index(read_pc)
    write_index = self._extract_index(write_pc)
    
    # 打包写入数据：valid=1, tag=write_pc, target=write_target
    write_data = self._pack_entry(Bits(1)(1), write_pc, write_target)
    
    # 写入优先：如果需要写入，使用写入地址；否则使用读取地址
    sram_addr = should_write.select(write_index, read_index)
    
    # 驱动 SRAM
    btb_sram.build(
        addr=sram_addr,
        re=~should_write,  # 不写入时读取
        we=should_write,
        wdata=write_data,
    )
```

### 3.5 BTB 的局限性

BTB 只能告诉我们"如果这个分支跳转，目标地址是什么"，但不能决定"这个分支是否应该跳转"。

这就是为什么我们还需要 **Tournament Predictor**。

---

## 4. Tournament Predictor 详解

### 4.1 为什么需要方向预测器？

即使 BTB 命中，我们也不一定要使用那个目标地址。考虑这种情况：

```c
for (int i = 0; i < 100; i++) {
    // 循环体
}
```

这个循环的分支指令会执行 101 次：
- 前 100 次跳转（继续循环）
- 最后 1 次不跳转（退出循环）

如果 BTB 命中就盲目跳转，最后一次就会预测错误。好的方向预测器应该能"学习"分支的行为模式。

### 4.2 Tournament Predictor 的架构

Tournament Predictor 是一个"混合预测器"，它结合了两种不同的预测算法：

```
                        ┌──────────────────────────────────────────┐
                        │           Tournament Predictor           │
                        │                                          │
  PC ──────────────────►│  ┌────────────────┐  ┌────────────────┐  │
                        │  │   Bimodal      │  │    Gshare      │  │
                        │  │   预测器        │  │    预测器       │  │
                        │  │   (局部预测)    │  │   (全局预测)    │  │
                        │  └───────┬────────┘  └───────┬────────┘  │
                        │          │                   │           │
                        │          ▼                   ▼           │
                        │        taken?             taken?         │
                        │          │                   │           │
                        │          └─────────┬─────────┘           │
  Global History ──────►│                    │                     │
                        │                    ▼                     │
                        │            ┌──────────────┐              │
                        │            │   Selector   │              │
                        │            │   (选择器)    │              │
                        │            └───────┬──────┘              │
                        │                    │                     │
                        │                    ▼                     │
                        │             最终预测结果                  │
                        └──────────────────────────────────────────┘
```

### 4.3 两种基础预测器

#### 4.3.1 Bimodal 预测器（局部预测器）

Bimodal 预测器使用 **2-bit 饱和计数器** 来预测每个分支的行为。

**2-bit 饱和计数器状态机**：

```
           跳转                跳转                跳转
      ┌───────────┐      ┌───────────┐      ┌───────────┐
      │           ▼      │           ▼      │           ▼
  ┌───┴───┐    ┌───┴───┐    ┌───┴───┐    ┌───────┐
  │  00   │    │  01   │    │  10   │    │  11   │
  │ 强不跳│◄───│ 弱不跳│◄───│ 弱跳转│◄───│ 强跳转│
  └───────┘    └───────┘    └───────┘    └───────┘
      │           │           │              │
      └───────────┘           └──────────────┘
        不跳转                   不跳转
```

**状态说明**：
- `00` (0): 强烈预测不跳转 (Strongly Not Taken)
- `01` (1): 弱预测不跳转 (Weakly Not Taken)
- `10` (2): 弱预测跳转 (Weakly Taken)
- `11` (3): 强烈预测跳转 (Strongly Taken)

**预测规则**：MSB (最高位) 为 1 时预测跳转，为 0 时预测不跳转。

**代码对照** (`src/tournament_predictor.py`)：

```python
# Bimodal 预测器：64 个 2-bit 计数器，初始化为 "Weakly Taken" (2)
bimodal_counters = RegArray(
    Bits(2), self.num_entries, initializer=[2] * self.num_entries
)

# 预测时：
bimodal_state = bimodal_counters[pc_index]
bimodal_taken = bimodal_state[1:1]  # 取 MSB (最高位)
```

#### 4.3.2 Gshare 预测器（全局预测器）

Gshare 预测器使用**全局历史寄存器 (GHR)** 来捕捉分支之间的相关性。

**核心思想**：有些分支的行为取决于之前分支的结果。例如：

```c
if (a > 0) {        // 分支 1
    if (a > 10) {   // 分支 2 - 其行为与分支 1 高度相关
        ...
    }
}
```

**Gshare 的索引计算**：

```
              PC[7:2]          Global History Register
               6 bits              6 bits
            ┌────────┐         ┌────────┐
            │xxxxxx  │         │hhhhhhh │
            └───┬────┘         └───┬────┘
                │                   │
                └──────────┬────────┘
                           │
                        XOR (异或)
                           │
                           ▼
                    ┌────────────┐
                    │   Index    │  → 用于访问 Gshare 计数器表
                    └────────────┘
```

**代码对照** (`src/tournament_predictor.py`)：

```python
# 全局历史寄存器：6-bit 移位寄存器
global_history = RegArray(Bits(self.history_bits), 1, initializer=[0])

# Gshare 计数器表
gshare_counters = RegArray(Bits(2), self.num_entries, initializer=[2] * self.num_entries)

def _get_gshare_index(self, pc, global_history):
    # 从 PC 中提取索引位
    pc_bits = (pc >> UInt(32)(2)) & Bits(32)(self.index_mask)
    pc_index = pc_bits[0:self.index_bits - 1].bitcast(Bits(self.index_bits))
    
    # 获取全局历史寄存器的值
    ghr = global_history[0:self.history_bits - 1].bitcast(Bits(self.history_bits))
    
    # 将 GHR 调整为与 index_bits 相同的位宽
    # (这里假设 history_bits >= index_bits，取低 index_bits 位)
    ghr_matched = ghr[0:self.index_bits - 1].bitcast(Bits(self.index_bits))
    
    # 关键：PC 索引 与 全局历史 做 XOR
    return pc_index ^ ghr_matched
```

### 4.4 选择器 (Selector)

选择器决定听从哪个预测器的建议。它也是一个 2-bit 饱和计数器：

```
  选择器状态：
  00, 01 → 使用 Bimodal 预测器
  10, 11 → 使用 Gshare 预测器
```

**更新规则**：
- 如果 Gshare 对了而 Bimodal 错了 → 向 Gshare 方向更新（加 1）
- 如果 Bimodal 对了而 Gshare 错了 → 向 Bimodal 方向更新（减 1）
- 如果两个都对或都错 → 不更新

**代码对照** (`src/tournament_predictor.py`)：

```python
# 预测时选择器决策
selector_state = selector_counters[pc_index]
use_gshare = selector_state[1:1]  # MSB 为 1 时使用 Gshare

# 最终预测
predict_taken = use_gshare.select(gshare_taken, bimodal_taken)

# 更新时（简化逻辑）
gshare_better = gshare_correct & (~bimodal_correct)
bimodal_better = bimodal_correct & (~gshare_correct)

# Gshare 更好：选择器向 Gshare 方向移动（增加）
# Bimodal 更好：选择器向 Bimodal 方向移动（减少）
```

### 4.5 全局历史寄存器的更新

每次分支指令执行后，全局历史寄存器会**左移**并插入最新的分支结果：

```
  执行前 GHR: [ 0 | 1 | 1 | 0 | 1 | 0 ]
              MSB             LSB
                    
  分支结果: taken (1)
  
  操作: 左移 1 位，最高位丢弃，新结果从最低位插入
                    
  执行后 GHR: [ 1 | 1 | 0 | 1 | 0 | 1 ]
              MSB             LSB
```

**代码对照** (`src/tournament_predictor.py`)：

```python
# 更新全局历史寄存器
# 1. 左移 1 位 (最高位移出丢弃)
# 2. OR 上新的分支结果 (插入最低位)
ghr_shifted = (ghr << UInt(self.history_bits)(1)) | actual_taken.bitcast(Bits(self.history_bits))
ghr_new = ghr_shifted[0:self.history_bits - 1].bitcast(Bits(self.history_bits))
global_history[0] <= ghr_new
```

---

## 5. 分支预测在流水线中的时序行为

这一节详细说明分支预测在五级流水线中每个时钟周期的行为。

### 5.1 流水线结构回顾

```
  ┌────┐   ┌────┐   ┌────┐   ┌────┐   ┌────┐
  │ IF │──►│ ID │──►│ EX │──►│MEM │──►│ WB │
  └────┘   └────┘   └────┘   └────┘   └────┘
    │                  │
    │  BTB/TP 预测     │  实际计算分支结果
    │  Next PC 选择    │  检测预测错误
    │                  │  更新 BTB/TP
```

### 5.2 正常执行流程（预测正确）

假设有一条分支指令 `beq x1, x2, label`，下面按时钟周期详细说明：

#### 第 N 周期：IF 阶段（取指）

**时序行为**：

```
时钟周期 N 开始时：
├── PC 寄存器包含当前指令地址（假设 PC = 0x400）
│
├── [组合逻辑阶段]
│   ├── 读取 PC 值
│   ├── BTB 查询
│   │   ├── 计算索引：index = PC[7:2] = 0x400[7:2] = 0
│   │   ├── 读取 btb_valid[0], btb_tags[0], btb_targets[0]
│   │   └── 判断是否命中：hit = valid & (tag == PC)
│   │
│   ├── Tournament Predictor 查询
│   │   ├── 计算 Bimodal 索引：pc_index = PC[7:2]
│   │   ├── 计算 Gshare 索引：gshare_index = PC[7:2] XOR GHR
│   │   ├── 读取计数器状态
│   │   └── 生成预测结果：predict_taken
│   │
│   └── Next PC 选择
│       ├── 如果 BTB 命中 & TP 预测跳转 → Next_PC = BTB_target
│       └── 否则 → Next_PC = PC + 4
│
└── [时钟上升沿]
    ├── PC 寄存器更新为 Next_PC
    └── 向 ID 阶段发送当前 PC 和指令
```

**代码对照** (`src/fetch.py` - `FetcherImpl.build`)：

```python
# 读取当前 PC
current_pc = current_stall_if.select(last_pc_reg[0], pc_addr)

# BTB 预测
btb_hit, btb_predicted_target = btb_impl.predict(
    pc=final_current_pc,
    btb_valid=btb_valid,
    btb_tags=btb_tags,
    btb_targets=btb_targets,
)

# Tournament Predictor 预测
tp_predict_taken = tp_impl.predict(
    pc=final_current_pc,
    bimodal_counters=tp_bimodal,
    gshare_counters=tp_gshare,
    global_history=tp_ghr,
    selector_counters=tp_selector,
)

# Next PC 选择逻辑
predicted_next_pc = btb_hit.select(
    tp_predict_taken.select(btb_predicted_target, default_next_pc),
    default_next_pc,
)

# 更新 PC 寄存器（在时钟上升沿生效）
pc_reg[0] <= final_next_pc
```

#### 第 N+1 周期：ID 阶段（译码）

**时序行为**：

```
时钟周期 N+1 开始时：
├── 从 IF/ID 流水线寄存器读取 PC 和指令
│
├── [组合逻辑阶段]
│   ├── 指令译码
│   │   ├── 解析 opcode, rs1, rs2, rd, funct3, funct7
│   │   └── 识别指令类型（分支/跳转/其他）
│   │
│   ├── 立即数生成
│   │   └── 对于 B-type: imm = {sign, inst[7], inst[30:25], inst[11:8], 0}
│   │
│   └── 寄存器读取
│       ├── 读取 rs1 的值
│       └── 读取 rs2 的值
│
└── [时钟上升沿]
    └── 向 EX 阶段发送控制信号和数据
```

此时 BTB 和 Tournament Predictor **不参与**，它们的工作在 IF 阶段已完成。

#### 第 N+2 周期：EX 阶段（执行）

这是分支预测**验证和更新**发生的关键周期。

**时序行为**：

```
时钟周期 N+2 开始时：
├── 从 ID/EX 流水线寄存器读取数据
│
├── [组合逻辑阶段 - 分支处理]
│   │
│   ├── 1. 计算分支目标地址
│   │   ├── 对于 Branch (beq/bne 等): target = PC + imm
│   │   └── 对于 JALR: target = (rs1 + imm) & ~1
│   │
│   ├── 2. 计算分支条件
│   │   ├── BEQ: taken = (rs1 == rs2)
│   │   ├── BNE: taken = (rs1 != rs2)
│   │   ├── BLT: taken = (rs1 < rs2)  [有符号]
│   │   ├── BGE: taken = (rs1 >= rs2) [有符号]
│   │   ├── BLTU: taken = (rs1 < rs2) [无符号]
│   │   ├── BGEU: taken = (rs1 >= rs2)[无符号]
│   │   └── JAL/JALR: taken = 1 (总是跳转)
│   │
│   ├── 3. 确定实际的 Next PC
│   │   ├── 如果 taken: actual_next_pc = target
│   │   └── 如果 not taken: actual_next_pc = PC + 4
│   │
│   ├── 4. 检测预测错误
│   │   └── miss = (actual_next_pc != predicted_next_pc)
│   │
│   ├── 5. 如果预测错误，设置 branch_target_reg
│   │   └── branch_target_reg[0] = actual_next_pc
│   │
│   ├── 6. 更新 BTB（如果分支跳转）
│   │   └── btb_impl.update(pc, target, is_taken & is_branch)
│   │
│   └── 7. 更新 Tournament Predictor
│       └── tp_impl.update(pc, is_taken, is_branch)
│
└── [时钟上升沿]
    └── BTB 和 TP 的更新在此刻生效
```

**代码对照** (`src/execution.py`)：

```python
# 计算分支目标
target_base = is_jalr.select(real_rs1, pc)
calc_target = (target_base_signed + imm_signed).bitcast(Bits(32))

# 计算分支条件
is_taken = (
    is_taken_eq | is_taken_ne | is_taken_lt | 
    is_taken_ge | is_taken_ltu | is_taken_geu |
    (ctrl.branch_type == BranchType.JAL) | is_jalr
)

# 检测预测错误
final_next_pc = is_branch.select(
    is_taken.select(calc_target, pc + 4),
    ctrl.next_pc_addr,
)
branch_miss = final_next_pc != ctrl.next_pc_addr

# 设置刷新信号
branch_target_reg[0] = branch_miss.select(final_next_pc, Bits(32)(0))

# 更新 BTB
should_update_btb = is_branch & is_taken & ~flush_if
btb_impl.update(pc, calc_target, should_update_btb, ...)

# 更新 Tournament Predictor
tp_impl.update(pc, is_taken, is_branch & ~flush_if, ...)
```

### 5.3 时序图：预测正确的情况

```
时钟     │  N   │ N+1  │ N+2  │ N+3  │ N+4  │
─────────┼──────┼──────┼──────┼──────┼──────┤
分支指令  │  IF  │  ID  │  EX  │  MEM │  WB  │
预测目标  │  IF  │  ID  │  EX  │  MEM │  WB  │
指令C    │      │  IF  │  ID  │  EX  │  MEM │
         │      │      │      │      │      │
─────────┴──────┴──────┴──────┴──────┴──────┘

BTB 查询  │  ✓   │      │      │      │      │
TP 查询   │  ✓   │      │      │      │      │
BTB 更新  │      │      │  ✓   │      │      │
TP 更新   │      │      │  ✓   │      │      │
```

**关键点**：
- 预测发生在 IF 阶段（周期 N）
- 更新发生在 EX 阶段（周期 N+2）
- 如果预测正确，流水线正常推进，没有惩罚

---

## 6. 分支预测失误的处理

### 6.1 预测错误的检测

在 EX 阶段，通过比较预测的 Next PC 和实际计算的 Next PC 来检测预测错误：

```python
branch_miss = final_next_pc != ctrl.next_pc_addr
```

### 6.2 流水线刷新机制

当检测到预测错误时，需要：
1. **刷新 IF 和 ID 阶段**的错误指令
2. **从正确的地址重新开始取指**

**代码对照** (`src/execution.py`)：

```python
# 如果预测错误，写入正确的目标地址；否则写 0
branch_target_reg[0] = branch_miss.select(
    final_next_pc,    # 预测错误：写入正确地址
    Bits(32)(0),      # 预测正确：写 0
)
```

**代码对照** (`src/fetch.py` - IF 阶段响应刷新)：

```python
# IF 阶段检查 branch_target_reg
flush_if = branch_target_reg[0] != Bits(32)(0)
target_pc = branch_target_reg[0]

# 如果需要刷新，使用正确的目标地址
final_current_pc = flush_if.select(target_pc, current_pc)
```

**代码对照** (`src/decoder.py` - ID 阶段响应刷新)：

```python
# ID 阶段检查 branch_target_reg
flush_if = branch_target_reg[0] != Bits(32)(0)
nop_if = flush_if | stall_if

# 如果需要刷新，当前指令变成 NOP
final_rd = nop_if.select(Bits(5)(0), wb_ctrl.rd_addr)
final_halt_if = nop_if.select(Bits(1)(0), wb_ctrl.halt_if)
final_alu_func = nop_if.select(ALUOp.NOP, pre.alu_func)
```

### 6.3 时序图：预测错误的情况

```
时钟     │  N   │ N+1  │ N+2  │ N+3  │ N+4  │ N+5  │
─────────┼──────┼──────┼──────┼──────┼──────┼──────┤
分支指令  │  IF  │  ID  │  EX  │  MEM │  WB  │      │
错误指令1 │      │  IF  │  ID  │ NOP  │      │      │  ← 被刷新
错误指令2 │      │      │  IF  │ NOP  │      │      │  ← 被刷新
正确指令  │      │      │      │  IF  │  ID  │  EX  │  ← 从正确地址开始
         │      │      │      │      │      │      │
─────────┴──────┴──────┴──────┴──────┴──────┴──────┘

预测结果  │ 错误 │      │      │      │      │      │
检测错误  │      │      │  ✓   │      │      │      │
刷新信号  │      │      │  ✓   │      │      │      │
重新取指  │      │      │      │  ✓   │      │      │
```

**预测错误的惩罚**：
- 2 条错误指令被刷新（IF 和 ID 阶段各 1 条）
- 加上 1 个周期重新取指
- 总共 **3 个周期的惩罚**

### 6.4 刷新机制的时序细节

```
周期 N+2（EX 阶段检测到错误）：
├── 组合逻辑计算出 branch_miss = 1
├── branch_target_reg[0] 被赋值为正确地址
└── [时钟上升沿] branch_target_reg 更新生效

周期 N+3（IF 和 ID 响应刷新）：
├── IF 阶段读取 branch_target_reg，发现不为 0
│   ├── 使用正确的目标地址作为 PC
│   └── 开始取正确的指令
├── ID 阶段读取 branch_target_reg，发现不为 0
│   └── 将当前指令转换为 NOP
└── EX 阶段
    ├── 将从 ID 收到的指令也转换为 NOP
    └── 将 branch_target_reg 清零
```

---

## 7. 性能影响分析

### 7.1 预测准确率的影响

| 预测结果 | 周期开销 |
|---------|---------|
| 预测正确 | 0 周期（流水线正常推进） |
| 预测错误 | 3 周期（刷新惩罚） |

### 7.2 实际性能数据

根据 `report/BTB性能分析报告.md` 的测试结果：

| 工作负载 | BTB 命中率 | 预测错误次数 | 惩罚周期 | 性能提升 |
|---------|-----------|------------|---------|---------|
| 0to100  | 99.0%     | 2          | 6       | 25.90%  |
| multiply| 78.77%    | 8          | 24      | 13.63%  |
| vvadd   | 98.68%    | 5          | 15      | 4.97%   |

### 7.3 分支预测对不同程序的影响

**循环密集型程序**（如 0to100）：
- 同一个分支会多次执行
- BTB 第一次 miss 后就能记住目标地址
- 后续预测几乎 100% 准确
- 只有循环结束时的最后一次跳转会预测错误

**计算密集型程序**（如 multiply）：
- 分支较多且模式复杂
- Tournament Predictor 能学习分支的行为模式
- 整体预测准确率仍然很高

### 7.4 为什么 Tournament Predictor 比单一预测器好？

Tournament Predictor 的优势在于它能**适应不同类型的分支**：

1. **简单循环分支**：Bimodal 预测器表现好
   - 例如：`for (i=0; i<100; i++)` 的循环检查
   - 几乎总是跳转，Bimodal 计数器会饱和在 "Strongly Taken"

2. **相关性分支**：Gshare 预测器表现好
   - 例如：嵌套条件判断
   - 当前分支的结果依赖于之前分支的结果
   - Gshare 通过全局历史能捕捉这种相关性

3. **选择器的作用**：
   - 自动学习哪个预测器对每个分支更准确
   - 不需要程序员或编译器干预

---

## 8. 总结

### 8.1 分支预测系统的组成

| 组件 | 功能 | 硬件资源 |
|------|------|---------|
| BTB | 存储分支目标地址 | 64 × (1 + 32 + 32) bits |
| Bimodal 预测器 | 局部方向预测 | 64 × 2 bits |
| Gshare 预测器 | 全局方向预测 | 64 × 2 bits |
| GHR | 全局历史 | 6 bits |
| Selector | 选择最佳预测器 | 64 × 2 bits |

### 8.2 时钟周期行为总结

| 周期 | 阶段 | 分支预测相关操作 |
|------|------|-----------------|
| N | IF | BTB 查询 + TP 查询 → 决定 Next PC |
| N+1 | ID | 无分支预测操作，指令译码 |
| N+2 | EX | 计算实际结果 + 检测预测错误 + 更新 BTB/TP |
| N+3 | MEM | 如果预测错误：刷新流水线 |

### 8.3 设计权衡

1. **空间 vs 准确率**：64 条目是一个平衡点，足够覆盖大多数工作负载的热点分支
2. **复杂度 vs 性能**：Tournament Predictor 增加了一些硬件复杂度，但显著提高了预测准确率
3. **延迟 vs 吞吐量**：所有预测都在 1 个周期内完成，不引入额外延迟

### 8.4 进一步阅读

- `src/btb.py` - BTB 实现代码
- `src/tournament_predictor.py` - Tournament Predictor 实现代码
- `src/fetch.py` - IF 阶段如何使用预测结果
- `src/execution.py` - EX 阶段如何验证和更新预测器
- `report/BTB性能分析报告.md` - 详细的性能测试报告（相对于仓库根目录）
