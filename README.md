# Assassyn-CPU

RISC-V RV32IM 处理器设计与实现 | RISC-V RV32IM Processor Design and Implementation

[English](#english) | [中文](#中文)

---

## 中文

### 项目概述

Assassyn-CPU 是一个基于 RISC-V RV32IM 架构的处理器设计项目。该项目支持基本整数指令集（RV32I）以及乘法和除法扩展（M Extension）。

### 主要特性

- ✅ RV32I 基本整数指令集
- ✅ M 扩展（乘法和除法指令）
- ✅ Harvard 架构（指令和数据分离）
- ✅ 使用 Assassyn HDL 进行硬件描述
- ✅ 支持 C 语言代码生成和编译

### 快速开始

#### 1. 安装依赖

**Ubuntu/Debian 系统:**

```bash
# 安装 RISC-V 交叉编译工具链
sudo apt-get update
sudo apt-get install -y gcc-riscv64-unknown-elf binutils-riscv64-unknown-elf

# 安装 Python 依赖（如需要）
pip install -r requirements.txt  # 如果有此文件
```

#### 2. 代码生成和编译

```bash
cd codegen
bash codegen.sh
```

详细说明请参考 [codegen/README.md](codegen/README.md)

#### 3. 验证 RV32IM 指令

```bash
cd codegen
# 查看生成的汇编代码
cat obj.exe

# 查找乘法指令
cat obj.exe | grep -E "mul"
```

### 项目结构

```
.
├── codegen/          # 代码生成工具和测试代码
│   ├── README.md     # 详细的代码生成说明
│   ├── codegen.sh    # 编译脚本
│   ├── code.c        # C 源代码
│   ├── start.S       # 启动汇编代码
│   └── harvard.ld    # 链接脚本
├── docs/             # 项目文档
│   ├── RV32M_*.md    # M 扩展相关文档
│   └── ...
├── src/              # 源代码（HDL 实现）
├── tests/            # 测试代码
└── workloads/        # 工作负载和测试程序
```

### 文档

- [RV32M 扩展计划](docs/RV32M_Extension_Plan.md)
- [RV32M 快速总结](docs/RV32M_Quick_Summary.md)
- [RV32M 架构图](docs/RV32M_Architecture_Diagram.md)
- [实现指南](docs/RV32M_Implementation_Guide.md)
- [代码生成说明](codegen/README.md)

### 常见问题

#### Q: 运行 codegen.sh 时提示 "command not found"

**A**: 这是因为没有安装 RISC-V 工具链。请按照"快速开始"中的步骤安装 `gcc-riscv64-unknown-elf` 和 `binutils-riscv64-unknown-elf`。

#### Q: 如何验证是否正确生成了 RV32IM 指令？

**A**: 运行编译后，检查反汇编文件：
```bash
cd codegen
cat obj.exe | grep -E "mul|div|rem"
```
如果能看到 `mul`, `mulh`, `div` 等指令，说明 M 扩展正常工作。

#### Q: 如何修改测试代码？

**A**: 编辑 `codegen/code.c` 文件，编写你自己的 C 代码，然后重新运行 `codegen.sh`。

### 贡献

欢迎提交 Issue 和 Pull Request！

### 许可证

[待定]

---

## English

### Project Overview

Assassyn-CPU is a RISC-V RV32IM architecture processor design project. This project supports the base integer instruction set (RV32I) and the multiplication and division extension (M Extension).

### Key Features

- ✅ RV32I Base Integer Instruction Set
- ✅ M Extension (Multiplication and Division Instructions)
- ✅ Harvard Architecture (Separate Instruction and Data Memory)
- ✅ Hardware Description using Assassyn HDL
- ✅ C Language Code Generation and Compilation Support

### Quick Start

#### 1. Install Dependencies

**Ubuntu/Debian:**

```bash
# Install RISC-V cross-compilation toolchain
sudo apt-get update
sudo apt-get install -y gcc-riscv64-unknown-elf binutils-riscv64-unknown-elf

# Install Python dependencies (if needed)
pip install -r requirements.txt  # if this file exists
```

#### 2. Code Generation and Compilation

```bash
cd codegen
bash codegen.sh
```

For detailed instructions, see [codegen/README.md](codegen/README.md)

#### 3. Verify RV32IM Instructions

```bash
cd codegen
# View generated assembly code
cat obj.exe

# Search for multiplication instructions
cat obj.exe | grep -E "mul"
```

### Project Structure

```
.
├── codegen/          # Code generation tools and test code
│   ├── README.md     # Detailed code generation instructions
│   ├── codegen.sh    # Compilation script
│   ├── code.c        # C source code
│   ├── start.S       # Startup assembly code
│   └── harvard.ld    # Linker script
├── docs/             # Project documentation
│   ├── RV32M_*.md    # M extension related documentation
│   └── ...
├── src/              # Source code (HDL implementation)
├── tests/            # Test code
└── workloads/        # Workloads and test programs
```

### Documentation

- [RV32M Extension Plan (EN)](docs/RV32M_Extension_Plan_EN.md)
- [RV32M Extension Plan (中文)](docs/RV32M_Extension_Plan.md)
- [RV32M Quick Summary](docs/RV32M_Quick_Summary.md)
- [RV32M Architecture Diagram](docs/RV32M_Architecture_Diagram.md)
- [Implementation Guide](docs/RV32M_Implementation_Guide.md)
- [Code Generation Guide](codegen/README.md)

### FAQ

#### Q: Getting "command not found" when running codegen.sh

**A**: This is because the RISC-V toolchain is not installed. Please follow the "Quick Start" section to install `gcc-riscv64-unknown-elf` and `binutils-riscv64-unknown-elf`.

#### Q: How to verify that RV32IM instructions are correctly generated?

**A**: After compilation, check the disassembly file:
```bash
cd codegen
cat obj.exe | grep -E "mul|div|rem"
```
If you can see instructions like `mul`, `mulh`, `div`, the M extension is working correctly.

#### Q: How to modify the test code?

**A**: Edit the `codegen/code.c` file with your own C code, then re-run `codegen.sh`.

### Contributing

Issues and Pull Requests are welcome!

### License

[TBD]
