# Assassyn-CPU

[![RISC-V](https://img.shields.io/badge/RISC--V-RV32IM-brightgreen.svg)](https://riscv.org/)
[![Assassyn](https://img.shields.io/badge/Assassyn-HDL-orange.svg)](https://github.com/were/assassyn)

一个基于 **Assassyn 硬件描述语言** 实现的 **RISC-V RV32IM** 五级流水线 CPU 仿真项目。

---

## 🎯 项目概述

本项目使用 [Assassyn](https://github.com/were/assassyn) 框架实现了一个功能完整的 RISC-V 32 位整数指令集处理器（RV32IM），支持标准整数指令（I）和乘除法扩展指令（M）。

### 主要特性

- **五级流水线架构**：IF → ID → EX → MEM → WB
- **完整的 RV32IM 指令集支持**：包括所有整数指令和 M 扩展（乘法/除法）
- **高级分支预测**：BTB（分支目标缓冲）+ Tournament Predictor（竞争预测器）
- **数据冒险处理**：完整的旁路（Forwarding）和流水线暂停（Stall）机制
- **多周期功能单元**：Wallace Tree 乘法器（3 周期）和 Radix-16 除法器（~10 周期）
- **统一内存架构**：单端口 SRAM，支持字节/半字/字访问

---

## 📁 项目结构

```
Assassyn-CPU/
├── src/                          # 核心源代码
│   ├── main.py                   # CPU 顶层模块与系统构建
│   ├── control_signals.py        # 控制信号定义与 Record 结构
│   ├── instruction_table.py      # RV32IM 指令真值表
│   ├── fetch.py                  # IF（取指）阶段模块
│   ├── decoder.py                # ID（译码）阶段模块
│   ├── execution.py              # EX（执行）阶段模块
│   ├── memory.py                 # MEM（访存）阶段模块
│   ├── writeback.py              # WB（写回）阶段模块
│   ├── hazard_unit.py            # 冒险检测单元入口
│   ├── data_hazard.py            # 数据冒险检测与旁路逻辑
│   ├── btb.py                    # 分支目标缓冲（BTB）
│   ├── tournament_predictor.py   # Tournament 分支预测器
│   ├── multiplier.py             # Wallace Tree 乘法器
│   ├── divider.py                # Radix-16 除法器
│   └── debug_utils.py            # 调试日志工具
│
├── docs/                         # 设计文档
│   ├── Assassyn.md               # Assassyn 语言学习笔记
│   ├── Assassyn_语言完整说明书.md  # Assassyn 完整语法参考
│   ├── Agent.md                  # AI Agent 开发指导
│   └── Module/                   # 各模块设计文档
│       ├── IF.md                 # 取指阶段设计
│       ├── ID.md                 # 译码阶段设计
│       ├── EX.md                 # 执行阶段设计
│       ├── MEM.md                # 访存阶段设计
│       ├── WB.md                 # 写回阶段设计
│       ├── DataHazard.md         # 数据冒险处理设计
│       ├── ControlHazard.md      # 控制冒险处理设计
│       └── BranchPrediction.md   # 分支预测详细原理
│
├── tests/                        # 单元测试
│   ├── common.py                 # 通用测试框架
│   ├── test_fetch.py             # 取指模块测试
│   ├── test_decoder.py           # 译码模块测试
│   ├── test_execute_*.py         # 执行模块测试
│   ├── test_memory.py            # 访存模块测试
│   └── test_writeback.py         # 写回模块测试
│
├── testcases/                    # 测试用例源码
│   ├── *.c                       # C 语言测试程序 (gcd, qsort, hanoi 等)
│   ├── *.data                    # 数据文件
│   └── *.dump                    # 反汇编文件
│
├── workloads/                    # 编译后的测试程序 (*.exe)
├── logs/                         # 运行日志
├── report/                       # 性能报告
└── verilog_hex_converter.py      # Verilog Hex 格式转换工具
```

---

## 🏗️ 架构设计

### 流水线架构

```
┌────────────────────────────────────────────────────────────────────────┐
│                        五级流水线处理器架构                              │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│   ┌──────┐    ┌──────┐    ┌──────┐    ┌──────┐    ┌──────┐           │
│   │  IF  │───►│  ID  │───►│  EX  │───►│ MEM  │───►│  WB  │           │
│   │ 取指  │    │ 译码  │    │ 执行  │    │ 访存  │    │ 写回  │           │
│   └──┬───┘    └──┬───┘    └──┬───┘    └──────┘    └──────┘           │
│      │           │           │                                        │
│      │  ┌────────┴───────────┴────────┐                              │
│      │  │      Hazard Unit            │  ◄─── 旁路 & Stall 控制      │
│      │  │   (数据冒险检测单元)          │                              │
│      │  └─────────────────────────────┘                              │
│      │                                                                │
│      │  ┌─────────────────────────────┐                              │
│      └──┤   Branch Prediction Unit    │  ◄─── BTB + Tournament       │
│         │   (分支预测单元)              │                              │
│         └─────────────────────────────┘                              │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### 各阶段功能

| 阶段 | 模块文件 | 主要功能 |
|------|---------|---------|
| **IF** | `fetch.py` | PC 管理、指令缓存读取、分支预测查询 |
| **ID** | `decoder.py` | 指令译码、立即数生成、寄存器读取、控制信号生成 |
| **EX** | `execution.py` | ALU 运算、分支判断、地址计算、旁路数据选择 |
| **MEM** | `memory.py` | 数据缓存读写、数据对齐、Load/Store 处理 |
| **WB** | `writeback.py` | 寄存器写回、停机检测 |

### 支持的指令集

#### 基础整数指令 (RV32I)

| 类型 | 指令 |
|------|-----|
| **算术运算** | ADD, SUB, ADDI |
| **逻辑运算** | AND, OR, XOR, ANDI, ORI, XORI |
| **移位运算** | SLL, SRL, SRA, SLLI, SRLI, SRAI |
| **比较运算** | SLT, SLTU, SLTI, SLTIU |
| **加载指令** | LB, LH, LW, LBU, LHU |
| **存储指令** | SB, SH, SW |
| **分支指令** | BEQ, BNE, BLT, BGE, BLTU, BGEU |
| **跳转指令** | JAL, JALR |
| **立即数指令** | LUI, AUIPC |
| **系统指令** | ECALL, EBREAK |

#### 乘除法扩展 (RV32M)

| 指令 | 功能 | 实现方式 |
|------|-----|---------|
| MUL | 乘法（低32位） | 3 周期 Wallace Tree |
| MULH | 有符号乘法（高32位） | 3 周期 Wallace Tree |
| MULHSU | 有符号×无符号（高32位） | 3 周期 Wallace Tree |
| MULHU | 无符号乘法（高32位） | 3 周期 Wallace Tree |
| DIV | 有符号除法 | ~10 周期 Radix-16 |
| DIVU | 无符号除法 | ~10 周期 Radix-16 |
| REM | 有符号取余 | ~10 周期 Radix-16 |
| REMU | 无符号取余 | ~10 周期 Radix-16 |

### 分支预测系统

本项目实现了先进的分支预测系统，包含两个核心组件：

#### BTB（Branch Target Buffer）

- 64 条目直接映射缓存
- 存储分支目标地址
- 仅在分支跳转时更新

#### Tournament Predictor

- **Bimodal 预测器**：基于 2-bit 饱和计数器的局部预测
- **Gshare 预测器**：基于全局历史寄存器的相关性预测
- **选择器**：动态选择更准确的预测器

```
预测逻辑流程:
1. BTB 查询 → 是否有缓存的目标地址？
2. Tournament Predictor 预测 → 分支是否跳转？
3. 如果 BTB 命中 且 预测跳转 → 使用 BTB 目标地址
4. 否则 → 使用 PC+4
```

### 数据冒险处理

#### 旁路（Forwarding）路径

```
EX 阶段结果  ──┬──► EX 阶段 ALU 输入 (EX-EX 旁路)
              │
MEM 阶段结果 ──┼──► EX 阶段 ALU 输入 (MEM-EX 旁路)
              │
WB 阶段结果  ──┘──► EX 阶段 ALU 输入 (WB-EX 旁路)
```

#### 流水线暂停情况

| 冒险类型 | 检测条件 | 处理方式 |
|---------|---------|---------|
| Load-Use | EX 级是 Load 且 rd 匹配 | 暂停 1 周期 |
| MUL 占用 | 乘法器正在工作 | 暂停直到完成 |
| DIV 占用 | 除法器正在工作 | 暂停直到完成 |
| Store-Load | EX/MEM 级有 Store/Load | 暂停 1 周期 |

---

## 🚀 快速开始

### 环境要求

- **Python 3.8+**
- **Assassyn 框架**（需要 Rust 编译器）
- **可选**：Verilator（用于 Verilog 仿真）

### 安装依赖

```bash
# 克隆仓库
git clone https://github.com/konpaku-ming/Assassyn-CPU.git
cd Assassyn-CPU

# 安装 Assassyn 框架（参考 Assassyn 官方文档）
# https://github.com/were/assassyn
```

### 运行仿真

```bash
# 运行默认测试程序
cd src
python -m main

# 运行特定测试用例
python -c "
from main import load_test_case, build_cpu
from assassyn import utils
from assassyn.backend import elaborate, config

# 加载测试用例
load_test_case('gcd')  # 或其他 workloads 中的测试

# 构建 CPU
sys = build_cpu(depth_log=16, enable_branch_prediction=True)

# 编译并运行
cfg = config(verilog=False, sim_threshold=1000000)
simulator_path, _ = elaborate(sys, **cfg)
binary_path = utils.build_simulator(simulator_path)
output = utils.run_simulator(binary_path=binary_path)
print(output)
"
```

### 运行单元测试

```bash
# 运行所有测试
python -m pytest tests/

# 运行特定模块测试
python -m pytest tests/test_decoder.py
python -m pytest tests/test_execute_part1.py
```

---

## 📖 文档

详细的设计文档位于 `docs/` 目录：

| 文档 | 描述 |
|-----|------|
| [Assassyn.md](docs/Assassyn.md) | Assassyn 语言核心概念笔记 |
| [Assassyn_语言完整说明书.md](docs/Assassyn_语言完整说明书.md) | 完整的语法参考手册 |
| [Module/IF.md](docs/Module/IF.md) | 取指阶段设计文档 |
| [Module/ID.md](docs/Module/ID.md) | 译码阶段设计文档 |
| [Module/EX.md](docs/Module/EX.md) | 执行阶段设计文档 |
| [Module/DataHazard.md](docs/Module/DataHazard.md) | 数据冒险处理设计 |
| [Module/BranchPrediction.md](docs/Module/BranchPrediction.md) | 分支预测详细原理 |

---

## 🔧 关键技术

### Assassyn 框架

[Assassyn](https://github.com/were/assassyn) 是一种基于 Python 的硬件描述语言，本项目使用的核心特性包括：

```python
# 数据类型
Bits(32)              # 32 位无符号位向量
Int(32), UInt(32)     # 有符号/无符号整数
Record(...)           # 硬件结构体

# 架构单元
Module                # 时序逻辑模块（有端口和状态）
Downstream            # 纯组合逻辑模块

# 存储单元
RegArray(type, depth) # 寄存器/寄存器堆
SRAM(width, depth)    # 大容量存储器

# 控制流
Condition(cond)       # 硬件条件控制
select()              # 二路选择器
select1hot()          # 独热码选择器
```

### 模块间通信

```python
# 异步调用（自动生成 FIFO）
call = executor.async_called(ctrl=signals, data=value)
call.bind.set_fifo_depth(ctrl=1, data=1)

# 端口数据消费
ctrl, data = self.pop_all_ports(False)  # 非阻塞读取
```

---

## 📊 测试用例

`testcases/` 目录包含多种测试程序：

| 测试用例 | 描述 |
|---------|------|
| `gcd.c` | 最大公约数算法 |
| `qsort.c` | 快速排序算法 |
| `hanoi.c` | 汉诺塔问题 |
| `pi.c` | 圆周率计算 |
| `queens.c` | N 皇后问题 |
| `bulgarian.c` | 保加利亚纸牌游戏 |
| `magic.c` | 魔方阵生成 |
| `tak.c` | Tak 函数递归测试 |
| `expr.c` | 表达式求值 |
| `array_test*.c` | 数组操作测试 |
| `multiarray.c` | 多维数组测试 |
| `superloop.c` | 循环性能测试 |
| `vector_mul.c` | 向量乘法（测试 M 扩展） |
| `vector_div.c` | 向量除法（测试 M 扩展） |

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

---

## 🙏 致谢

- [Assassyn](https://github.com/were/assassyn) - 硬件描述语言框架
- [RISC-V](https://riscv.org/) - 开源指令集架构
- [riscv-tests](https://github.com/riscv/riscv-tests) - RISC-V 测试用例参考

---

## 📬 联系方式

如有问题或建议，欢迎通过以下方式联系：

- 提交 [Issue](https://github.com/konpaku-ming/Assassyn-CPU/issues)
- 发起 [Discussion](https://github.com/konpaku-ming/Assassyn-CPU/discussions)
