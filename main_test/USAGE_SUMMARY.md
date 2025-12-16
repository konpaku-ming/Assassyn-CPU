# 工具使用总结 / Tool Usage Summary

## 概述 / Overview

本目录包含用于将二进制程序文件（`*_text.bin` 和 `*_data.bin`）转换为 CPU 初始化文件（`.exe` 和 `.data`）的工具。

This directory contains tools to convert binary program files (`*_text.bin` and `*_data.bin`) into CPU initialization files (`.exe` and `.data`).

## 支持的程序 / Supported Programs

工具支持转换以下三个程序：

The tools support converting the following three programs:

1. **0to100** - 0到100累加程序 / Sum from 0 to 100
2. **multiply** - 乘法测试程序 / Multiplication test
3. **vvadd** - 向量加法测试程序 / Vector addition test

## 快速开始 / Quick Start

### 方法 1：批量生成所有程序（推荐）/ Method 1: Batch Generate All Programs (Recommended)

```bash
cd main_test
bash generate_all_workloads.sh
```

**输出 / Output:**
- `../workloads/0to100.exe` 和 `../workloads/0to100.data`
- `../workloads/multiply.exe` 和 `../workloads/multiply.data`
- `../workloads/vvadd.exe` 和 `../workloads/vvadd.data`

### 方法 2：生成单个程序 / Method 2: Generate Single Program

```bash
cd main_test

# 生成 0to100 (默认)
python3 generate_workloads.py

# 生成 multiply
python3 generate_workloads.py \
    --text-in multiply_text.bin \
    --data-in multiply_data.bin \
    --text-out ../workloads/multiply.exe \
    --data-out ../workloads/multiply.data

# 生成 vvadd
python3 generate_workloads.py \
    --text-in vvadd_text.bin \
    --data-in vvadd_data.bin \
    --text-out ../workloads/vvadd.exe \
    --data-out ../workloads/vvadd.data
```

## 输出格式 / Output Format

生成的文件采用以下格式：

The generated files use the following format:

- **格式类型 / Format Type**: 文本十六进制 / Text hexadecimal
- **每行内容 / Each Line**: 一个 32-bit 字（8位十六进制字符）/ One 32-bit word (8 hex characters)
- **字节序 / Byte Order**: 小端序（Little-endian）
- **前缀 / Prefix**: 无 `0x` 前缀 / No `0x` prefix
- **字母 / Case**: 小写 / Lowercase
- **对齐 / Alignment**: 自动填充到 32-bit 边界 / Auto-padded to 32-bit boundary

**示例 / Example:**
```
fe010113
00812e23
02010413
fe042423
```

## 与 CPU 的集成 / Integration with CPU

生成的文件可直接用于初始化 Assassyn CPU：

The generated files can be directly used to initialize the Assassyn CPU:

- **`.exe` 文件**: 用于初始化 icache（指令缓存）
- **`.data` 文件**: 用于初始化 dcache（数据缓存）

- **`.exe` files**: Used to initialize icache (instruction cache)
- **`.data` files**: Used to initialize dcache (data cache)

**兼容性 / Compatibility:**
- 与 Verilog `$readmemh` 格式兼容
- Compatible with Verilog `$readmemh` format

## 文件清单 / File List

### 输入文件（main_test 目录）/ Input Files (in main_test)

| 文件名 | 大小 | 说明 |
|--------|------|------|
| `0to100_text.bin` | 88 bytes | 0to100 指令段 |
| `0to100_data.bin` | 0 bytes | 0to100 数据段（空）|
| `multiply_text.bin` | 2.6 KB | multiply 指令段 |
| `multiply_data.bin` | 1.2 KB | multiply 数据段 |
| `vvadd_text.bin` | 2.5 KB | vvadd 指令段 |
| `vvadd_data.bin` | 3.6 KB | vvadd 数据段 |

### 输出文件（workloads 目录）/ Output Files (in workloads)

| 文件名 | 大小 | 字数 | 说明 |
|--------|------|------|------|
| `0to100.exe` | 198 bytes | 22 words | 0to100 指令（icache）|
| `0to100.data` | 0 bytes | 0 words | 0to100 数据（dcache）|
| `multiply.exe` | 5.7 KB | 642 words | multiply 指令（icache）|
| `multiply.data` | 2.7 KB | 300 words | multiply 数据（dcache）|
| `vvadd.exe` | 5.5 KB | 625 words | vvadd 指令（icache）|
| `vvadd.data` | 8.0 KB | 900 words | vvadd 数据（dcache）|

## 高级选项 / Advanced Options

```bash
# 查看所有选项
python3 generate_workloads.py --help

# 输出原始二进制（而非文本十六进制）
python3 generate_workloads.py --binary

# 使用大端序
python3 generate_workloads.py --endian big

# 使用 16-bit 字宽
python3 generate_workloads.py --word-size 2
```

## 验证 / Verification

### 格式验证 / Format Verification

```bash
# 检查文件格式（每行应为 8 个十六进制字符）
head -5 ../workloads/0to100.exe
```

**预期输出 / Expected Output:**
```
fe010113
00812e23
02010413
fe042423
00100793
```

### 字节序验证 / Byte Order Verification

```bash
# 对比原始二进制和生成的十六进制
xxd -l 16 0to100_text.bin
head -4 ../workloads/0to100.exe
```

**验证规则 / Verification Rule:**
- 原始字节 `13 01 01 fe` → 十六进制行 `fe010113` ✓ (小端序)
- Raw bytes `13 01 01 fe` → Hex line `fe010113` ✓ (little-endian)

## 常见问题 / FAQ

### Q: 生成的文件与模板 0to100.exe 格式不同？

A: 模板文件 `workloads/0to100.exe` 包含反汇编注释（例如 `000007b7 //  0: lui a5, 0x00`），这是手动添加的注释，用于文档目的。工具生成的文件是纯十六进制格式（无注释），这是正确的初始化格式。

### Q: The generated files have different format than template 0to100.exe?

A: The template file `workloads/0to100.exe` contains disassembly comments (e.g., `000007b7 //  0: lui a5, 0x00`), which are manually added for documentation purposes. The tool-generated files are in pure hexadecimal format (without comments), which is the correct initialization format.

### Q: 为什么 0to100.data 是空文件？

A: 因为 `0to100_data.bin` 是空的（0 bytes）。这个程序不需要初始化数据段，所有数据都在代码中生成。

### Q: Why is 0to100.data empty?

A: Because `0to100_data.bin` is empty (0 bytes). This program doesn't require an initialized data segment; all data is generated in the code.

### Q: 如何添加新的测试程序？

A: 
1. 将二进制文件放在 `main_test` 目录：`<name>_text.bin` 和 `<name>_data.bin`
2. 编辑 `generate_all_workloads.sh`，在 `WORKLOADS` 数组中添加程序名
3. 运行 `bash generate_all_workloads.sh`

### Q: How to add a new test program?

A:
1. Place binary files in `main_test` directory: `<name>_text.bin` and `<name>_data.bin`
2. Edit `generate_all_workloads.sh` and add the program name to the `WORKLOADS` array
3. Run `bash generate_all_workloads.sh`

## 相关文档 / Related Documentation

- **[README.md](README.md)** - 快速参考指南 / Quick reference guide
- **[INITIALIZATION_REPORT.md](INITIALIZATION_REPORT.md)** - 完整技术报告 / Complete technical report
- **[../docs/Assassyn.md](../docs/Assassyn.md)** - Assassyn CPU 文档 / Assassyn CPU documentation

## 版本信息 / Version Information

- **工具版本 / Tool Version**: 1.0
- **支持的 CPU / Supported CPU**: Assassyn RISC-V CPU
- **生成格式 / Generated Format**: 32-bit hex, little-endian, $readmemh-compatible
- **最后更新 / Last Updated**: 2025-12-16
