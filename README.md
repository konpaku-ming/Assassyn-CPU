# Assassyn-CPU

一个基于 Assassyn HDL 实现的 RISC-V 32位 CPU 设计项目

## 项目简介

本项目使用 Assassyn 硬件描述语言实现了一个支持 RV32I 指令集的五级流水线 CPU。Assassyn 是一种基于 Python 的新型硬件描述语言，提供了延迟不敏感（Latency-Insensitive）的设计抽象和自动化的流水线管理。

### 主要特性

- ✅ 完整的 RV32I 指令集支持
- ✅ 五级流水线架构（IF, ID, EX, MEM, WB）
- ✅ 数据冒险检测与前递（Forwarding）
- ✅ 控制冒险处理与分支预测
- ✅ 基于 Assassyn HDL 的模块化设计
- ✅ 完善的单元测试覆盖

## 仓库结构

```
Assassyn-CPU/
├── README.md                 # 项目说明文档（本文件）
├── requirements.txt          # Python 依赖包列表
├── Makefile                  # 常用命令快捷方式
├── .gitignore               # Git 忽略文件配置
│
├── docs/                     # 设计文档目录
│   ├── Assassyn.md          # Assassyn 语言学习笔记
│   ├── Agent.md             # AI Agent 开发指南
│   └── Module/              # 各模块详细设计文档
│       ├── IF.md            # 取指阶段 (Instruction Fetch)
│       ├── ID.md            # 译码阶段 (Instruction Decode)
│       ├── EX.md            # 执行阶段 (Execute)
│       ├── MEM.md           # 访存阶段 (Memory Access)
│       ├── WB.md            # 写回阶段 (Write Back)
│       ├── DataHazard.md    # 数据冒险处理单元
│       └── ControlHazard.md # 控制冒险处理单元
│
├── src/                      # 源代码目录
│   ├── main.py              # 顶层 CPU 构建入口
│   ├── control_signals.py   # 控制信号与常量定义
│   ├── instruction_table.py # RV32I 指令真值表
│   ├── fetch.py             # IF 阶段实现
│   ├── decoder.py           # ID 阶段实现
│   ├── data_hazard.py       # 数据冒险检测单元
│   ├── execution.py         # EX 阶段实现
│   ├── memory.py            # MEM 阶段实现
│   └── writeback.py         # WB 阶段实现
│
├── tests/                    # 测试代码目录
│   ├── common.py            # 测试工具和辅助函数
│   ├── test_fetch.py        # IF 阶段单元测试
│   ├── test_decoder.py      # ID 阶段单元测试
│   ├── test_decoder_impl.py # ID 阶段实现测试
│   ├── test_execute_part1.py # EX 阶段测试（第一部分）
│   ├── test_execute_part2.py # EX 阶段测试（第二部分）
│   ├── test_execute_part3.py # EX 阶段测试（第三部分）
│   ├── test_memory.py       # MEM 阶段单元测试
│   ├── test_writeback.py    # WB 阶段单元测试
│   ├── test_datahazard.py   # 数据冒险测试
│   └── test_mock.py         # 模拟测试
│
└── .workspace/               # 工作区（自动生成，包含仿真文件）
    ├── workload.init        # 初始化数据
    ├── workload_ins.exe     # 指令内存初始化文件
    └── workload_mem.exe     # 数据内存初始化文件
```

## 环境配置

### 系统要求

- **操作系统**: Linux / macOS / Windows (WSL2)
- **Python**: 3.10 或更高版本
- **Rust**: 最新稳定版（Assassyn 后端编译需要）
- **内存**: 建议 8GB 以上
- **磁盘空间**: 建议 2GB 以上

### 依赖安装

#### 1. 安装 Python 环境

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3 python3-pip python3-venv

# macOS
brew install python3

# 验证安装
python3 --version  # 应显示 3.10 或更高版本
```

#### 2. 安装 Rust 工具链

Assassyn 后端使用 Rust 编译，需要安装 Rust：

```bash
# 使用 rustup 安装 Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# 配置环境变量
source $HOME/.cargo/env

# 验证安装
rustc --version
cargo --version
```

#### 3. 克隆仓库

```bash
git clone https://github.com/konpaku-ming/Assassyn-CPU.git
cd Assassyn-CPU
```

#### 4. 创建 Python 虚拟环境

```bash
# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
# Linux/macOS:
source .venv/bin/activate

# Windows (Git Bash/WSL):
source .venv/Scripts/activate
```

#### 5. 安装 Python 依赖

```bash
# 升级 pip
pip install --upgrade pip

# 安装项目依赖
pip install -r requirements.txt
```

### Assassyn 框架安装

Assassyn HDL 需要单独安装。如果 requirements.txt 中包含了 Assassyn，它会自动安装。否则，请按照以下方式安装：

```bash
# 如果 Assassyn 是通过 pip 分发的
pip install assassyn

# 或者从源码安装（如果是私有仓库）
# git clone <assassyn-repo-url>
# cd assassyn
# pip install -e .
```

**注意**: 如果 Assassyn 是一个私有或内部框架，请确保您有访问权限并按照其官方文档进行安装。

## 快速开始

### 运行测试

本项目包含完整的单元测试套件，用于验证各个模块的功能：

```bash
# 确保虚拟环境已激活
source .venv/bin/activate  # Linux/macOS

# 运行所有测试
python -m pytest tests/ -v

# 运行特定模块的测试
python -m pytest tests/test_fetch.py -v
python -m pytest tests/test_decoder.py -v
python -m pytest tests/test_execute_part1.py -v

# 运行单个测试
python -m pytest tests/test_fetch.py::test_fetch_basic -v
```

### 使用 Makefile（推荐）

为了简化常用操作，项目提供了 Makefile：

```bash
# 安装依赖
make install

# 运行所有测试
make test

# 运行特定测试
make test-fetch
make test-decoder
make test-execute

# 清理生成的文件
make clean

# 查看所有可用命令
make help
```

### 构建和运行 CPU

```bash
# 运行主程序（构建完整 CPU）
python src/main.py

# 这将：
# 1. 构建 RV32I CPU 系统
# 2. 生成 Rust 仿真器代码
# 3. 编译二进制仿真器
# 4. 输出构建信息
```

生成的仿真器将保存在 `.workspace/` 目录中。

## 开发指南

### 代码结构说明

1. **流水线阶段模块**（`src/` 目录）
   - 每个模块继承自 `Module`（时序逻辑）或 `Downstream`（组合逻辑）
   - 使用 `@module.combinational` 装饰器定义构建逻辑
   - 通过 `Port` 定义模块间接口

2. **控制信号定义**（`control_signals.py`）
   - 包含所有指令的操作码、ALU 功能码等常量
   - 定义了各阶段间传递的 `Record` 结构

3. **测试驱动**（`tests/` 目录）
   - 使用 `common.py` 中的 `run_test_module` 函数
   - 每个测试包含：测试向量（输入）、DUT 构建、输出验证

### 添加新指令

1. 在 `instruction_table.py` 中添加指令定义
2. 更新 `decoder.py` 的译码逻辑（如需要）
3. 更新 `execution.py` 的 ALU 逻辑（如需要）
4. 在 `tests/` 中添加对应的单元测试

### Assassyn 语言学习

如果您是第一次接触 Assassyn HDL，请阅读：

- **[docs/Assassyn.md](docs/Assassyn.md)** - Assassyn 语言核心概念和语法详解
- **[docs/Agent.md](docs/Agent.md)** - AI Agent 开发指南
- **[docs/Module/](docs/Module/)** - 各模块详细设计文档

关键概念：
- `Bits/UInt/Int` - 基础数据类型
- `RegArray` - 寄存器数组
- `SRAM` - 存储器
- `Module/Downstream` - 模块类型
- `Port & async_called` - 模块间通信
- `Value & Optional` - 可选数据处理

## 测试说明

### 测试框架

本项目使用 Python 的 `pytest` 框架进行测试，结合 Assassyn 的仿真能力：

```python
from tests.common import run_test_module

def test_example():
    # 1. 构建测试系统
    sys = SysBuilder("test_system")
    
    # 2. 实例化模块
    with sys:
        dut = MyModule()
        driver = TestDriver()
        # ... 构建逻辑
    
    # 3. 定义验证函数
    def check(raw_output):
        # 解析仿真器输出
        # 验证正确性
        assert "expected" in raw_output
    
    # 4. 运行测试
    run_test_module(sys, check)
```

### 测试覆盖

- ✅ 取指阶段（IF）- `test_fetch.py`
- ✅ 译码阶段（ID）- `test_decoder.py`, `test_decoder_impl.py`
- ✅ 执行阶段（EX）- `test_execute_part1/2/3.py`
- ✅ 访存阶段（MEM）- `test_memory.py`
- ✅ 写回阶段（WB）- `test_writeback.py`
- ✅ 数据冒险 - `test_datahazard.py`

## 常见问题

### 1. 导入错误：`ModuleNotFoundError: No module named 'assassyn'`

**解决方案**:
```bash
# 确保虚拟环境已激活
source .venv/bin/activate

# 重新安装依赖
pip install -r requirements.txt

# 如果 Assassyn 需要从源码安装，请参考 Assassyn 官方文档
```

### 2. Rust 编译错误

**解决方案**:
```bash
# 更新 Rust 工具链
rustup update

# 如果遇到链接错误，可能需要安装系统依赖
# Ubuntu/Debian:
sudo apt install build-essential

# macOS:
xcode-select --install
```

### 3. 测试运行缓慢

**原因**: Assassyn 需要编译 Rust 仿真器，首次运行较慢。

**解决方案**:
- 后续运行会使用缓存，速度会明显提升
- 使用 `make test` 可以看到编译进度
- 增加系统内存可以加速编译

### 4. `.workspace/` 目录缺失

**解决方案**:
```bash
# 该目录会在首次运行测试或构建时自动创建
mkdir -p .workspace

# 如果需要手动创建初始化文件，请参考测试代码中的 SRAM 初始化逻辑
```

## 性能参数

- **指令集**: RV32I (32 条基础整数指令)
- **流水线级数**: 5 级（IF, ID, EX, MEM, WB）
- **数据位宽**: 32 位
- **通用寄存器**: 32 个（x0-x31）
- **地址空间**: 可配置（默认 2^16 = 64KB）

## 技术栈

- **HDL 语言**: Assassyn (基于 Python)
- **后端**: Rust (仿真器编译)
- **测试框架**: pytest
- **构建工具**: Make, Cargo
- **版本控制**: Git

## 贡献指南

欢迎贡献代码、文档或提出问题！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 开启 Pull Request

### 代码规范

- 遵循 Python PEP 8 风格指南
- 为新功能添加单元测试
- 更新相关文档
- 保持代码注释清晰（中文或英文）

## 许可证

本项目采用 MIT 许可证 - 详见 LICENSE 文件

## 联系方式

- **项目维护者**: konpaku-ming
- **项目主页**: https://github.com/konpaku-ming/Assassyn-CPU
- **问题反馈**: [GitHub Issues](https://github.com/konpaku-ming/Assassyn-CPU/issues)

## 致谢

- Assassyn HDL 框架开发团队
- RISC-V 基金会
- 所有贡献者

---

**最后更新**: 2025-12-12
