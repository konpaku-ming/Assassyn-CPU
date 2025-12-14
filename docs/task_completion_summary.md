# 任务完成总结 / Task Completion Summary

## 概述 / Overview

本文档总结了针对 Assassyn CPU 项目的三个主要任务的完成情况：
1. SP（栈指针）初始化问题的说明
2. 工作负载生成工具的创建和配置
3. main.py 中 print(raw) 问题的诊断报告

This document summarizes the completion of three main tasks for the Assassyn CPU project:
1. Stack Pointer (SP) initialization explanation
2. Workload generation tool creation and configuration
3. Diagnostic report for the main.py print(raw) issue

---

## 任务 1：SP（栈指针）初始化说明 / Task 1: SP Initialization Explanation

### 状态 / Status
✅ **已完成 / COMPLETED**

### 位置 / Location
- 主文档：`main_test/INITIALIZATION_REPORT.md`
- 实现代码：`src/main.py` (行 109-117)

### 关键内容 / Key Content

#### 代码实现 / Code Implementation
在 `src/main.py` 中，SP 寄存器（x2）在 CPU 初始化时被设置为栈顶地址：

```python
# src/main.py, lines 109-117
# 初始化 SP (x2) 指向栈顶
# Initialize SP (x2) to point to the top of the stack
# RAM 大小: 2^depth_log 字节，栈顶在最高地址
# RAM size: 2^depth_log bytes, stack top at highest address
WORD_SIZE = 4  # RISC-V 字长 / RISC-V word size (bytes)
STACK_TOP = (1 << depth_log) - WORD_SIZE  # 栈顶地址（字对齐）/ Stack top (word-aligned)
reg_init = [0] * 32
reg_init[2] = STACK_TOP  # x2 = sp，初始化为栈顶 / x2 = sp, initialize to stack top
reg_file = RegArray(Bits(32), 32, initializer=reg_init)
```

#### 计算方法 / Calculation Method
- **RAM 大小 / RAM Size**: 2^depth_log 字节
- **栈顶地址 / Stack Top Address**: (2^depth_log - 4) 字节（4 字节对齐）
- **默认配置 / Default Config**: depth_log=16 → 栈顶 = 0xFFFC (65532)

#### 工作原理 / How It Works
1. CPU 复位时，所有通用寄存器被初始化为 reg_init 数组中的值
2. x2 (SP) 被设置为 STACK_TOP（RAM 最高可用地址）
3. 栈向下增长（从高地址向低地址），符合 RISC-V ABI 约定
4. 这确保了程序第一条指令（通常是 `addi sp, sp, -N`）能够正确执行

#### 文档详情 / Documentation Details
`main_test/INITIALIZATION_REPORT.md` 包含：
- 问题描述：为什么需要初始化 SP
- 三种解决方案的对比分析
- 内存映射参考
- RISC-V 寄存器约定
- 验证步骤

---

## 任务 2：工作负载生成工具 / Task 2: Workload Generation Tool

### 状态 / Status
✅ **已完成 / COMPLETED**

### 位置 / Location
- 工具脚本：`main_test/generate_workloads.py`
- 使用说明：`main_test/README.md`
- 详细文档：`main_test/INITIALIZATION_REPORT.md` (第 11-78 行)

### 功能特性 / Features

#### 输入文件 / Input Files
- `main_test/my0to100_text.bin` - 指令段二进制（88 字节）
- `main_test/my0to100_data.bin` - 数据段二进制（0 字节，空文件）

#### 输出文件 / Output Files
- `workloads/my0to100.exe` - 用于 icache 初始化（22 个 32-bit 字）
- `workloads/my0to100.data` - 用于 dcache 初始化（空文件）

#### 默认行为 / Default Behavior
```bash
cd main_test
python3 generate_workloads.py
```

**输出格式 / Output Format**:
- 文本文件，每行一个 32-bit 十六进制数（8 位十六进制字符）
- 小端序（Little-endian）
- 不含 `0x` 前缀
- 与 Verilog `$readmemh` 格式兼容

**示例输出 / Example Output** (`workloads/my0to100.exe`):
```
fe010113
00812e23
02010413
fe042423
00100793
...
```

#### 高级选项 / Advanced Options
```bash
# 输出原始二进制格式
python3 generate_workloads.py --binary

# 使用大端序
python3 generate_workloads.py --endian big

# 自定义输入/输出文件
python3 generate_workloads.py \
    --text-in custom_text.bin \
    --data-in custom_data.bin \
    --text-out ../workloads/custom.exe \
    --data-out ../workloads/custom.data
```

#### 关键更新 / Key Updates (Dec 14, 2025)
- ✅ 默认输出路径改为 `../workloads/` 而非当前目录
- ✅ 自动创建输出目录（如果不存在）
- ✅ 添加 `import os` 支持路径操作
- ✅ 更新文档以反映新的默认行为

### 集成到 main.py / Integration with main.py

```python
# src/main.py, line 215
load_test_case("my0to100")
```

该函数会：
1. 从 `workloads/` 目录读取 `my0to100.exe` 和 `my0to100.data`
2. 复制到 `src/.workspace/workload.exe` 和 `src/.workspace/workload.data`
3. 由 `SRAM` 类加载用于初始化 icache 和 dcache

---

## 任务 3：main.py print(raw) 问题诊断报告 / Task 3: main.py print(raw) Diagnostic Report

### 状态 / Status
✅ **已完成 / COMPLETED**

### 位置 / Location
- 诊断报告：`docs/print_raw_diagnostic_report.md`

### 问题描述 / Problem Description

#### 预期行为 / Expected Behavior
```python
# src/main.py, line 242-244
raw = utils.run_simulator(binary_path=binary_path)
print(raw)
```

**应输出 / Should Output**:
```
Cycle 0: PC = 0x00000000
Cycle 1: PC = 0x00000004
Register x10 (a0) = 0x00000064
...
Program halted successfully.
```

#### 实际行为 / Actual Behavior
**实际输出 / Actual Output**:
```python
['/home/ming/PythonProjects/cpu_test/workspace/rv32i_cpu/rv32i_cpu_simulator/target/release/rv32i_cpu_simulator']
```

这是一个 **Python 列表**，包含模拟器可执行文件的路径，而非预期的日志文本。

### 根本原因分析 / Root Cause Analysis

报告分析了三种可能的情况：

#### 情况 A：run_simulator 返回命令列表
```python
# 错误的实现
def run_simulator(binary_path):
    cmd = [binary_path]
    subprocess.run(cmd)
    return cmd  # 错误！应返回输出
```

#### 情况 B：未捕获 stdout
```python
# 不完整的实现
def run_simulator(binary_path):
    cmd = [binary_path]
    subprocess.run(cmd)  # 缺少 capture_output=True
    return cmd
```

#### 情况 C：捕获了但返回错误的字段
```python
# 返回值错误
def run_simulator(binary_path):
    cmd = [binary_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.args  # 错误！应返回 result.stdout
```

### 提供的解决方案 / Provided Solutions

报告提供了 **4 种修复方案**，每种都包含完整的代码示例：

1. **方案 1**：修改 `assassyn.utils.run_simulator` 源码（如果可访问）
2. **方案 2**：在 `main.py` 中添加包装函数（推荐，无需修改 main.py 约束）
3. **方案 3**：从日志文件读取输出（如果模拟器写入文件）
4. **方案 4**：验证模拟器配置和参数

### 推荐的诊断流程 / Recommended Diagnostic Procedure

报告提供了 4 步诊断流程：

1. **确认 raw 的类型和内容**
   ```python
   print(type(raw))
   print(repr(raw))
   ```

2. **手动运行模拟器**
   ```bash
   /path/to/simulator
   ```

3. **检查工作目录是否有日志文件**
   ```bash
   ls -la src/.workspace/*.log
   ```

4. **根据结果选择修复方案**（提供决策表）

### 包含的代码片段 / Included Code Snippets

- ✅ 完整的健壮包装函数实现（40+ 行）
- ✅ 调试版本的 main.py 修改
- ✅ 错误处理和日志记录示例
- ✅ Python 版本兼容性处理
- ✅ 类型检查和断言

---

## 文件清单 / File Inventory

### 新建文件 / New Files
1. `docs/print_raw_diagnostic_report.md` - 诊断报告（500+ 行）
2. `docs/task_completion_summary.md` - 本文档

### 修改的文件 / Modified Files
1. `main_test/generate_workloads.py` - 更新默认输出路径和目录创建逻辑
2. `main_test/README.md` - 更新文档以反映新的默认行为

### 现有文件（未修改但已验证）/ Existing Files (Verified)
1. `src/main.py` - SP 初始化代码已存在并正确
2. `main_test/INITIALIZATION_REPORT.md` - SP 初始化完整文档已存在
3. `main_test/my0to100_text.bin` - 输入二进制文件（88 字节）
4. `main_test/my0to100_data.bin` - 输入二进制文件（0 字节）
5. `workloads/my0to100.exe` - 生成的指令文件（22 words）
6. `workloads/my0to100.data` - 生成的数据文件（空）

---

## 验证结果 / Verification Results

### generate_workloads.py 测试 / Test Results

```bash
$ cd main_test
$ python3 generate_workloads.py
============================================================
生成 dcache/icache 初始化文件
============================================================
输入文件（指令段）: my0to100_text.bin
输入文件（数据段）: my0to100_data.bin
输出文件（指令段）: ../workloads/my0to100.exe
输出文件（数据段）: ../workloads/my0to100.data
输出格式: 文本十六进制 (32-bit, little-endian)
============================================================
[SUCCESS] Wrote 22 words to ../workloads/my0to100.exe
          Format: 32-bit hex, little-endian
[INFO] Input file my0to100_data.bin is empty, created empty ../workloads/my0to100.data
============================================================
✅ 生成完成！
============================================================
```

### 文件完整性验证 / File Integrity

```bash
$ ls -lh workloads/my0to100.*
-rw-rw-r-- 1 runner runner   0 Dec 14 07:09 workloads/my0to100.data
-rw-rw-r-- 1 runner runner 198 Dec 14 07:09 workloads/my0to100.exe

$ head -5 workloads/my0to100.exe
fe010113
00812e23
02010413
fe042423
00100793
```

✅ 格式正确：每行 8 个十六进制字符（32-bit）  
✅ 字节序正确：与原始二进制的小端序一致  
✅ 内容正确：与 `my0to100_text.bin` 的反汇编匹配

---

## 约束遵守情况 / Constraint Compliance

### 用户约束 / User Constraints

| 约束 / Constraint | 状态 / Status | 说明 / Notes |
|------------------|--------------|-------------|
| 不修改 main.py / Do not modify main.py | ✅ 遵守 / COMPLIED | main.py 未被修改，只创建了诊断报告 |
| 在 docs/ 生成报告 / Generate report in docs/ | ✅ 完成 / COMPLETED | 创建了 `print_raw_diagnostic_report.md` |
| 工具在 main_test/ / Tool in main_test/ | ✅ 完成 / COMPLETED | `generate_workloads.py` 已存在并更新 |
| 输出到 workloads/ / Output to workloads/ | ✅ 完成 / COMPLETED | 默认路径改为 `../workloads/` |
| 说明 SP 初始化 / Explain SP init | ✅ 完成 / COMPLETED | 代码注释和文档已存在 |

---

## 使用指南 / Usage Guide

### 快速开始 / Quick Start

#### 1. 生成工作负载文件 / Generate Workload Files
```bash
cd main_test
python3 generate_workloads.py
```

#### 2. 运行 CPU 仿真 / Run CPU Simulation
```bash
cd ../src
python3 main.py
```

#### 3. 如果遇到 print(raw) 问题 / If print(raw) Issue Occurs
1. 阅读诊断报告：`docs/print_raw_diagnostic_report.md`
2. 按照"推荐的诊断流程"（第 5 节）操作
3. 实施合适的修复方案（第 4 节）

### 故障排查 / Troubleshooting

#### 问题：找不到 assassyn 模块 / Issue: assassyn module not found
```bash
ModuleNotFoundError: No module named 'assassyn'
```

**解决方案 / Solution**:
```bash
# 如果 assassyn 是本地开发包
cd /path/to/assassyn
pip install -e .

# 如果 assassyn 是发布包
pip install assassyn
```

#### 问题：工作负载文件未找到 / Issue: Workload files not found
```bash
FileNotFoundError: Test case not found: .../my0to100.exe
```

**解决方案 / Solution**:
```bash
cd main_test
python3 generate_workloads.py
ls -l ../workloads/my0to100.*
```

#### 问题：print(raw) 只显示路径 / Issue: print(raw) only shows path
**解决方案 / Solution**:
参考 `docs/print_raw_diagnostic_report.md` 的方案 2，在 main.py 中添加包装函数。

---

## 下一步行动 / Next Steps

### 立即行动 / Immediate Actions
1. ✅ 验证 `generate_workloads.py` 正常工作
2. ✅ 确认 SP 初始化文档完整
3. ✅ 创建 `print(raw)` 问题的诊断报告

### 后续建议 / Future Recommendations
1. 🔄 **修复 print(raw) 问题**：根据诊断报告实施修复方案
2. 📝 **添加单元测试**：为 `generate_workloads.py` 添加测试
3. 🔍 **验证仿真输出**：确认 accumulate(100) = 5050
4. 📚 **更新主 README**：添加快速开始指南链接

---

## 参考文档 / References

1. **SP 初始化**：`main_test/INITIALIZATION_REPORT.md`
2. **工具使用**：`main_test/README.md`
3. **print(raw) 诊断**：`docs/print_raw_diagnostic_report.md`
4. **Assassyn 框架**：`docs/Assassyn.md`
5. **源代码**：`src/main.py`

---

## 贡献者 / Contributors

- **GitHub Copilot Agent** - 代码分析、文档编写、工具更新
- **konpaku-ming** - 项目维护者

---

## 版本历史 / Version History

| 版本 / Version | 日期 / Date | 说明 / Notes |
|---------------|-------------|-------------|
| 1.0 | 2025-12-14 | 初始版本，完成所有三个任务 |

---

**报告生成时间 / Report Generated**: 2025-12-14 07:09 UTC  
**状态 / Status**: ✅ 所有任务已完成 / All Tasks Completed
