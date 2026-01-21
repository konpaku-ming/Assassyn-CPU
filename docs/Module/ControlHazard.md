# 控制冒险处理机制设计文档

> **依赖**：Assassyn Framework

## 1. 概述

控制冒险（Control Hazard）发生在分支和跳转指令中。当 CPU 无法在取指阶段确定下一条指令的地址时，就会产生控制冒险。

本 CPU 采用 **动态分支预测 + 延迟冲刷** 的策略来处理控制冒险。

## 2. 分支预测机制

### 2.1 无分支预测模式

当 `enable_branch_prediction=False` 时：
- IF 阶段默认预测 `next_pc = pc + 4`
- 所有分支/跳转指令都在 EX 阶段解析
- 分支预测错误（misprediction）导致 2 周期惩罚

### 2.2 分支预测模式

当 `enable_branch_prediction=True` 时：
- **BTB (Branch Target Buffer)**：预测分支目标地址
- **Tournament Predictor**：预测分支方向（taken/not-taken）
- 正确预测时无惩罚，错误预测时 2 周期惩罚

详见 [BranchPrediction.md](./BranchPrediction.md)。

## 3. 冲刷机制

### 3.1 核心组件：branch_target_reg

`branch_target_reg` 是一个全局寄存器，用于在 EX 阶段和 IF/ID 阶段之间传递分支解析结果：

```python
branch_target_reg = RegArray(Bits(32), 1)
```

### 3.2 EX 阶段行为

在 EX 阶段，计算实际的分支目标并检测预测错误：

```python
# 1. 计算实际的下一 PC
final_next_pc = is_branch.select(
    is_taken.select(calc_target, pc + 4),
    ctrl.next_pc_addr,
)

# 2. 检测预测错误
branch_miss = final_next_pc != ctrl.next_pc_addr

# 3. 写入 branch_target_reg
branch_target_reg[0] = branch_miss.select(
    final_next_pc,   # 预测错误：写入正确的目标地址
    Bits(32)(0),     # 预测正确：写 0 表示无需冲刷
)
```

### 3.3 IF 阶段响应

IF 阶段在每个周期开始时检查 `branch_target_reg`：

```python
flush_if = branch_target_reg[0] != Bits(32)(0)
target_pc = branch_target_reg[0]

# 如果需要冲刷，使用正确的目标地址
final_current_pc = flush_if.select(target_pc, current_pc)
```

### 3.4 ID 阶段响应

ID 阶段检测到冲刷信号时，将当前指令转换为 NOP：

```python
flush_if = branch_target_reg[0] != Bits(32)(0)
nop_if = flush_if | stall_if

# 将控制信号替换为无效值
final_rd = nop_if.select(Bits(5)(0), wb_ctrl.rd_addr)
final_mem_opcode = nop_if.select(MemOp.NONE, mem_ctrl.mem_opcode)
final_alu_func = nop_if.select(ALUOp.NOP, pre.alu_func)
final_branch_type = nop_if.select(BranchType.NO_BRANCH, pre.branch_type)
```

### 3.5 EX 阶段自身响应

EX 阶段在检测到冲刷时，也会使当前指令作废：

```python
flush_if = branch_target_reg[0] != Bits(32)(0)

final_rd = flush_if.select(Bits(5)(0), effective_rd)
final_halt_if = flush_if.select(Bits(1)(0), wb_ctrl.halt_if)
final_mem_opcode = flush_if.select(MemOp.NONE, mem_ctrl.mem_opcode)
```

## 4. 时序分析

### 4.1 分支预测正确

| Cycle | IF | ID | EX | MEM | WB |
| :---: | :--- | :--- | :--- | :--- | :--- |
| T | branch | - | - | - | - |
| T+1 | predicted | branch | - | - | - |
| T+2 | predicted+4 | predicted | branch | - | - |
| T+3 | ... | predicted+4 | predicted | branch | - |

无任何惩罚，流水线正常推进。

### 4.2 分支预测错误

| Cycle | IF | ID | EX | MEM | WB | branch_target_reg |
| :---: | :--- | :--- | :--- | :--- | :--- | :--- |
| T | branch | - | - | - | - | 0 |
| T+1 | wrong | branch | - | - | - | 0 |
| T+2 | wrong+4 | wrong | branch | - | - | **correct_addr** |
| T+3 | **correct** | NOP | NOP | branch | - | 0 |
| T+4 | correct+4 | correct | NOP | NOP | branch |

2 周期惩罚（T+2 和 T+3 的指令被冲刷）。

## 5. 分支类型处理

### 5.1 条件分支 (BEQ/BNE/BLT/BGE/BLTU/BGEU)

- 目标地址：`PC + Imm`
- 条件：ALU 比较结果
- 预测：由 Tournament Predictor 提供方向预测

### 5.2 直接跳转 (JAL)

- 目标地址：`PC + Imm`
- 总是 taken
- BTB 可以提供目标预测

### 5.3 间接跳转 (JALR)

- 目标地址：`rs1 + Imm`（最低位清 0）
- 总是 taken
- 目标地址依赖 rs1，难以预测

## 6. 设计权衡

### 6.1 为什么在 EX 阶段解析分支？

- **简化设计**：分支条件需要 ALU 计算，放在 EX 阶段自然
- **减少转发复杂度**：EX 阶段已经有完整的旁路网络
- **权衡**：2 周期的分支惩罚（从 ID 移到 EX 会增加 1 周期）

### 6.2 分支预测的收益

在典型的循环密集型代码中：
- 无预测：每次循环末尾都有 2 周期惩罚
- 有预测：预测正确时无惩罚，典型准确率 > 90%
