# Assassyn CPU 总体架构文档

> **版本**：基于当前代码库
> **指令集**：RV32IM (RISC-V 32-bit Integer + M Extension)

## 1. 架构概述

Assassyn CPU 是一个基于 **Assassyn Framework** 实现的 5 级流水线 RISC-V 处理器，支持完整的 RV32IM 指令集。

### 1.1 流水线结构

```
┌────┐    ┌────┐    ┌────┐    ┌────┐    ┌────┐
│ IF │ -> │ ID │ -> │ EX │ -> │MEM │ -> │ WB │
└────┘    └────┘    └────┘    └────┘    └────┘
   │         │         │         │         │
   │         │         │         │         │
   ▼         ▼         ▼         ▼         ▼
 取指      译码      执行      访存      写回
```

### 1.2 主要特性

| 特性 | 描述 |
| :--- | :--- |
| 指令集 | RV32IM (Integer + M Extension) |
| 流水线深度 | 5 级 |
| 数据冒险处理 | 完全旁路 (Full Forwarding) |
| 控制冒险处理 | 分支预测 (BTB + Tournament Predictor) |
| 乘法器 | 3 周期 Wallace Tree |
| 除法器 | ~10 周期 Radix-16 |
| 内存模型 | 统一内存 (Unified Memory) |

## 2. 模块组成

### 2.1 核心流水线模块

| 模块 | 文件 | 描述 |
| :--- | :--- | :--- |
| Fetcher / FetcherImpl | `fetch.py` | 取指阶段，维护 PC，发起指令读取 |
| Decoder / DecoderImpl | `decoder.py` | 译码阶段，指令解析和控制信号生成 |
| Execution | `execution.py` | 执行阶段，ALU 运算和分支处理 |
| MemoryAccess | `memory.py` | 访存阶段，数据加载和存储 |
| WriteBack | `writeback.py` | 写回阶段，寄存器更新 |

### 2.2 辅助模块

| 模块 | 文件 | 描述 |
| :--- | :--- | :--- |
| DataHazardUnit | `data_hazard.py` | 数据冒险检测和旁路控制 |
| SingleMemory | `memory.py` | 统一内存访问控制器 |
| BTB / BTBImpl | `btb.py` | 分支目标缓冲 |
| TournamentPredictor | `tournament_predictor.py` | 方向预测器 |
| WallaceTreeMul | `multiplier.py` | Wallace Tree 乘法器 |
| Radix16Divider | `divider.py` | Radix-16 除法器 |

### 2.3 配置和常量

| 文件 | 描述 |
| :--- | :--- |
| `control_signals.py` | 控制信号定义和 Record 结构 |
| `instruction_table.py` | 指令真值表 |

## 3. 数据通路

### 3.1 主数据通路

```
                         ┌───────────────────────────────────────┐
                         │            Bypass Network             │
                         │  ┌─────────┐ ┌─────────┐ ┌─────────┐  │
                         │  │EX Bypass│ │MEM Bypass│ │WB Bypass│ │
                         │  └────┬────┘ └────┬────┘ └────┬────┘ │
                         │       │           │           │      │
┌──────┐   ┌──────┐   ┌──▼───┐   │    ┌──────▼───┐   ┌───▼──┐   │
│ SRAM │<->│  IF  │-->│  ID  │───┼───>│    EX    │-->│ MEM  │-->│ WB │
└──────┘   └──────┘   └──────┘   │    └──────────┘   └──────┘   └────┘
    ^                     │      │          │             │
    │                     │      │          │             │
    │                     ▼      │          ▼             │
    │              ┌────────────┐│   ┌────────────┐       │
    │              │HazardUnit  ││   │ MUL/DIV    │       │
    │              └────────────┘│   └────────────┘       │
    │                            │                        │
    └────────────────────────────┴────────────────────────┘
                     SingleMemory (统一内存访问)
```

### 3.2 旁路网络

```
                    ┌────────────┐
                    │  RegFile   │
                    └─────┬──────┘
                          │ RS1/RS2
                          ▼
                    ┌────────────┐
              ┌────>│  4:1 Mux   │<────┐
              │     └─────┬──────┘     │
              │           │            │
    ┌─────────┴───┐       │     ┌──────┴─────┐
    │  EX Bypass  │       │     │ MEM Bypass │
    │  (EX Result)│       │     │(MEM Result)│
    └─────────────┘       │     └────────────┘
                          │
                    ┌─────┴──────┐
                    │  WB Bypass │
                    │ (WB Result)│
                    └────────────┘
```

## 4. 控制信号流

### 4.1 控制信号包层次

```
ex_ctrl_signals
├── alu_func (16-bit)      # ALU 操作码
├── div_op (5-bit)         # 除法操作码
├── rs1_sel (4-bit)        # RS1 旁路选择
├── rs2_sel (4-bit)        # RS2 旁路选择
├── op1_sel (3-bit)        # 操作数 1 来源
├── op2_sel (3-bit)        # 操作数 2 来源
├── branch_type (16-bit)   # 分支类型
├── next_pc_addr (32-bit)  # 预测的下一 PC
└── mem_ctrl_signals       # MEM 级控制
    ├── mem_opcode (3-bit)  # 内存操作
    ├── mem_width (3-bit)   # 访问宽度
    ├── mem_unsigned (1-bit)# 无符号标志
    └── wb_ctrl_signals     # WB 级控制
        ├── rd_addr (5-bit)  # 目标寄存器
        └── halt_if (1-bit)  # 停机标志
```

### 4.2 控制信号传递

```
IF --> ID: pc, next_pc, stall
ID --> EX: ctrl (ex_ctrl_signals), pc, rs1_data, rs2_data, imm
EX --> MEM: ctrl (mem_ctrl_signals), alu_result
MEM --> WB: ctrl (wb_ctrl_signals), wdata
```

## 5. 内存架构

### 5.1 统一内存模型

本 CPU 使用统一内存模型，取指和数据访存共享同一个 SRAM：

```
             ┌─────────────────────────────────────┐
             │           SingleMemory              │
             │                                     │
  IF Addr ──>│  ┌─────────────┐                   │
             │  │ Address     │                   │
  MEM Addr ─>│  │ Arbiter     │───> SRAM Addr    │
             │  └─────────────┘                   │
             │                                     │
  MEM Data ─>│  ┌─────────────┐                   │
             │  │ Write       │───> SRAM WData   │
  MEM Width ─>│  │ Handler    │                   │
             │  │ (RMW for    │                   │
             │  │  sub-word)  │                   │
             │  └─────────────┘                   │
             │                                     │
             │  SRAM DOut ─────────────────────>  │
             └─────────────────────────────────────┘
```

### 5.2 访存优先级

| 优先级 | 操作 | 描述 |
| :---: | :--- | :--- |
| 1 | Store (Phase 2) | 完成 RMW 写入 |
| 2 | Load | 数据读取 |
| 3 | Store (Phase 1) | 开始 RMW 读取 |
| 4 | IF | 取指 |

### 5.3 Store 操作 (Read-Modify-Write)

```
Cycle 1: 读取目标地址的整字
Cycle 2: 修改相应字节/半字，写回
```

## 6. 分支预测

### 6.1 预测器组成

```
                    ┌─────────────────────────────────────┐
                    │         Branch Prediction           │
                    │                                     │
  PC ──────────────>│  ┌─────────┐    ┌───────────────┐  │
                    │  │   BTB   │    │   Tournament   │  │
                    │  │ (Target)│    │   Predictor    │  │
                    │  │         │    │  (Direction)   │  │
                    │  └────┬────┘    └───────┬───────┘  │
                    │       │                 │          │
                    │       ▼                 ▼          │
                    │  ┌─────────────────────────┐       │
                    │  │    Decision Logic       │       │
                    │  │                         │       │
                    │  │ BTB Hit & TP Taken:     │       │
                    │  │   -> BTB Target         │       │
                    │  │ Otherwise:              │       │
                    │  │   -> PC + 4             │       │
                    │  └─────────────────────────┘       │
                    │              │                     │
                    │              ▼                     │
                    │        Next PC                     │
                    └─────────────────────────────────────┘
```

### 6.2 更新时机

| 事件 | BTB 更新 | Tournament 更新 |
| :--- | :---: | :---: |
| 分支 Taken | ✓ | ✓ |
| 分支 Not-Taken | ✗ | ✓ |
| 非分支指令 | ✗ | ✗ |

## 7. 冒险处理

### 7.1 数据冒险

| 冒险类型 | 处理方式 | 周期惩罚 |
| :--- | :--- | :---: |
| RAW (EX->ID) | EX Bypass | 0 |
| RAW (MEM->ID) | MEM Bypass | 0 |
| RAW (WB->ID) | WB Bypass | 0 |
| Load-Use | Stall | 1 |
| MUL Busy | Stall | 3 |
| DIV Busy | Stall | ~10 |

### 7.2 控制冒险

| 情况 | 周期惩罚 |
| :--- | :---: |
| 预测正确 | 0 |
| 预测错误 | 2 |

## 8. 性能分析

### 8.1 CPI 分析

**理想 CPI**: 1.0

**实际 CPI 影响因素**:

| 因素 | 惩罚周期 | 频率估计 | CPI 影响 |
| :--- | :---: | :---: | :---: |
| Load-Use | 1 | ~15% | +0.15 |
| 分支预测错误 | 2 | ~5% | +0.10 |
| MUL 指令 | 3 | ~3% | +0.09 |
| DIV 指令 | 10 | ~1% | +0.10 |
| Store RMW | 1 | ~10% | +0.10 |

**典型 CPI**: 1.5 ~ 2.0

### 8.2 IPC 计算

$$IPC = \frac{1}{CPI} \approx 0.5 \sim 0.67$$

### 8.3 性能优化建议

1. **减少 Load-Use 冒险**: 编译器调度，将 Load 指令提前
2. **提高分支预测准确率**: 
   - 增加 BTB 大小
   - 增加历史位数
3. **减少 MUL/DIV 影响**:
   - 使用乘法展开替代小常数乘法
   - 避免除法，使用移位替代 2 的幂除法

### 8.4 循环性能示例

考虑一个简单的累加循环：

```assembly
loop:
    lw   a0, 0(a1)     # Load
    add  a2, a2, a0    # Add (Load-Use stall)
    addi a1, a1, 4     # Increment
    bne  a1, a3, loop  # Branch
```

| 周期 | IF | ID | EX | MEM | WB | 说明 |
| :---: | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | lw | - | - | - | - | |
| 2 | add | lw | - | - | - | |
| 3 | addi | **stall** | lw | - | - | Load-Use |
| 4 | bne | add | **nop** | lw | - | |
| 5 | lw | addi | add | nop | lw | BTB 预测 |
| 6 | add | bne | addi | add | nop | |
| 7 | addi | **stall** | bne | addi | add | Load-Use |
| ... | | | | | | |

**每次迭代周期**: 4 + 1 (Load-Use) = 5 周期
**每次迭代指令**: 4 条
**循环 CPI**: 5/4 = 1.25 (分支预测正确)

如果分支预测错误：
**循环 CPI**: (5 + 2)/4 = 1.75

## 9. 配置选项

### 9.1 CPU 构建参数

```python
def build_cpu(depth_log, enable_branch_prediction=True):
    """
    Args:
        depth_log: SRAM 深度的对数 (depth = 2^depth_log)
        enable_branch_prediction: 分支预测开关
            - True: BTB + Tournament Predictor
            - False: 默认 PC+4
    """
```

### 9.2 分支预测配置

| 参数 | 默认值 | 描述 |
| :--- | :---: | :--- |
| `num_entries` | 64 | BTB/预测器表项数 |
| `index_bits` | 6 | 索引位数 |
| `history_bits` | 6 | GHR 位数 |

## 10. 文件结构

```
src/
├── main.py              # 系统构建入口
├── fetch.py             # IF 阶段
├── decoder.py           # ID 阶段
├── execution.py         # EX 阶段
├── memory.py            # MEM 阶段 + SingleMemory
├── writeback.py         # WB 阶段
├── data_hazard.py       # 数据冒险检测
├── hazard_unit.py       # 冒险单元导出
├── control_signals.py   # 控制信号定义
├── instruction_table.py # 指令真值表
├── btb.py               # 分支目标缓冲
├── tournament_predictor.py # 方向预测器
├── multiplier.py        # Wallace Tree 乘法器
├── divider.py           # Radix-16 除法器
└── debug_utils.py       # 调试工具
```
