# print(raw) 问题调查文档索引

## 快速导航

### 🎯 立即开始
如果你想快速了解问题和解决方案，请阅读：
- **[SOLUTION_SUMMARY.md](SOLUTION_SUMMARY.md)** - 完整的解决方案总结

### 🔍 深入调查
如果你需要详细的技术分析和诊断步骤，请阅读：
- **[print_raw_investigation.md](print_raw_investigation.md)** - 详细的问题分析和解决方案

### 🛠️ 诊断工具
如果你想自己诊断问题，请运行：
- **[debug_run_simulator.py](debug_run_simulator.py)** - 自动化诊断脚本

### 📦 工作负载生成
如果你需要生成 dcache/icache 初始化文件，请参考：
- **[../main_test/README.md](../main_test/README.md)** - 快速参考
- **[../main_test/INITIALIZATION_REPORT.md](../main_test/INITIALIZATION_REPORT.md)** - 完整报告

---

## 文档结构

```
docs/
├── README_INVESTIGATION.md          # 本文件（导航索引）
├── SOLUTION_SUMMARY.md              # ⭐ 解决方案总结（推荐首先阅读）
├── print_raw_investigation.md       # 详细的技术分析
├── debug_run_simulator.py           # 诊断工具脚本
├── Assassyn.md                      # Assassyn 框架文档
└── Agent.md                         # Agent 相关文档

main_test/
├── README.md                        # 工具快速参考
├── INITIALIZATION_REPORT.md         # SP 初始化完整报告
├── generate_workloads.py            # ⭐ 工作负载生成工具
├── my0to100_text.bin               # 输入：指令段二进制
├── my0to100_data.bin               # 输入：数据段二进制
├── my0to100.exe                    # 输出：指令初始化文件
└── my0to100.data                   # 输出：数据初始化文件

workloads/
├── my0to100.exe                    # 已复制的指令文件
└── my0to100.data                   # 已复制的数据文件
```

---

## 问题描述

在 `src/main.py` 中，第 244 行的 `print(raw)` 只输出了：
```
['/home/ming/PythonProjects/cpu_test/workspace/rv32i_cpu/rv32i_cpu_simulator/target/release/rv32i_cpu_simulator']
```

而期望输出的是 CPU 运行过程中的所有日志，包括指令执行、寄存器状态等。

---

## 解决方案概览

### 推荐方案：修改函数调用方式

**文件**：`src/main.py` 第 242 行

**当前代码**：
```python
raw = utils.run_simulator(binary_path=binary_path)
```

**修改为**：
```python
raw = utils.run_simulator(binary_path)  # 使用位置参数
```

**原因**：根据 `docs/Assassyn.md` 文档，`utils.run_simulator` 应该使用位置参数而非关键字参数。

---

## 使用指南

### 1. 运行诊断（推荐第一步）

```bash
# 在有 assassyn 模块的环境中运行
cd /path/to/Assassyn-CPU
python3 docs/debug_run_simulator.py
```

**输出内容**：
- `utils.run_simulator` 的函数签名
- 源代码位置和文档
- 不同调用方式的测试结果

**根据输出确定**：
- 是否需要使用位置参数
- 返回值应该是什么类型（字符串 vs 列表）
- 是否存在版本不兼容问题

### 2. 生成工作负载文件

```bash
cd main_test
python3 generate_workloads.py
```

**输出**：
```
============================================================
生成 dcache/icache 初始化文件
============================================================
[SUCCESS] Wrote 22 words to my0to100.exe
[INFO] Input file my0to100_data.bin is empty, created empty my0to100.data
✅ 生成完成！
============================================================
```

**验证**：
```bash
# 查看生成的文件
head -5 my0to100.exe
# 应该输出 32-bit 十六进制数，每行一个

# 复制到 workloads 目录（如果需要）
mkdir -p ../workloads
cp my0to100.exe my0to100.data ../workloads/
```

### 3. 修改 main.py（根据诊断结果）

**选项 A：使用位置参数**（如果诊断显示这样可行）
```python
# src/main.py 第 242 行
raw = utils.run_simulator(binary_path)
```

**选项 B：使用 subprocess**（如果 utils.run_simulator 有问题）
```python
import subprocess

# src/main.py 第 240-244 行
print(f"🏃 Running simulation...")
result = subprocess.run(
    [binary_path],
    capture_output=True,
    text=True,
    timeout=600
)
raw = result.stdout
if result.stderr:
    raw += "\n=== STDERR ===\n" + result.stderr
print(raw)
```

### 4. 测试修复

```bash
cd src
python3 main.py
```

**期望输出**：
```
🚀 Compiling system: rv32i_cpu...
[*] Source Dir: /path/to/workloads
[*] Data Path: /path/to/.workspace/workload.data
[*] Ins Path: /path/to/.workspace/workload.exe
...
🏃 Running simulation (Direct Output Mode)...
Cycle 0: PC=0x00000000, Inst=0xfe010113
Cycle 1: PC=0x00000004, Inst=0x00812e23
...
Register x10 (a0) = 0x000013BA (5050)
🔍 Verifying output...
```

---

## 文档详细内容

### SOLUTION_SUMMARY.md
- ✅ 已完成的工作清单
- ⚠️ 待用户执行的任务
- 📝 关键修复建议
- ❓ 常见问题解答
- 🔧 技术细节

### print_raw_investigation.md
- 🔍 问题根源分析（3 种假设）
- 📊 诊断步骤（4 个阶段）
- 💡 解决方案（3 种方案对比）
- ✅ 验证清单
- 📝 调试信息收集方法
- 📎 相关文件清单

### debug_run_simulator.py
- 🔧 函数签名检查
- 📖 文档字符串显示
- 📂 源码位置定位
- 🧪 调用方式测试
- 📋 详细诊断输出

---

## 相关参考

### Assassyn 框架文档
- `docs/Assassyn.md` - 第 403-410 行有关于 `run_simulator` 的说明

### 测试代码参考
- `tests/common.py` - 第 28 行也使用了 `utils.run_simulator`

### 工具脚本
- `main_test/generate_workloads.py` - 完整的命令行参数和文档

---

## 联系与反馈

如果遇到问题或需要进一步的帮助：

1. **查看日志**：确保所有诊断输出已保存
2. **检查环境**：确认 assassyn 模块版本
3. **参考文档**：阅读相关的 md 文件
4. **运行诊断**：使用 `debug_run_simulator.py`

---

## 版本历史

- **2025-12-14**: 初始版本
  - 创建完整的调查文档
  - 实现诊断工具
  - 提供解决方案

---

**最后更新**：2025-12-14  
**维护者**：GitHub Copilot Agent  
**仓库**：konpaku-ming/Assassyn-CPU
