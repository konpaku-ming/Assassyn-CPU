# 快速开始指南

本指南将帮助您在 5 分钟内启动并运行 Assassyn-CPU 项目。

## 前提条件检查

在开始之前，请确保您的系统已安装：

- ✅ Python 3.10 或更高版本
- ✅ Rust 工具链（rustc, cargo）
- ✅ Git

### 快速检查

```bash
python3 --version  # 应显示 3.10+
rustc --version    # 应显示 Rust 版本
git --version      # 应显示 Git 版本
```

如果缺少任何工具，请参考 [INSTALL.md](INSTALL.md) 进行安装。

## 三步启动

### 步骤 1: 克隆并进入项目

```bash
git clone https://github.com/konpaku-ming/Assassyn-CPU.git
cd Assassyn-CPU
```

### 步骤 2: 设置环境

```bash
# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate  # Linux/macOS
# 或
.\.venv\Scripts\Activate.ps1  # Windows PowerShell

# 安装依赖
pip install --upgrade pip
pip install -r requirements.txt
```

### 步骤 3: 运行测试

```bash
# 使用 Makefile（推荐）
make test-fetch

# 或直接使用 pytest
pytest tests/test_fetch.py -v
```

## 期望输出

如果一切正常，您应该看到类似以下的输出：

```
🚀 Compiling system: test_fetch_basic...
🔨 Building binary from: /path/to/binary
🏃 Running simulation (Direct Output Mode)...
🔍 Verifying output...
✅ test_fetch_basic Passed!
```

## 下一步

### 探索更多测试

```bash
# 运行所有测试
make test

# 运行特定模块测试
make test-decoder   # 译码器测试
make test-execute   # 执行单元测试
make test-memory    # 存储器访问测试
```

### 构建完整 CPU

```bash
# 构建 RV32I CPU 系统
python src/main.py

# 或使用 Makefile
make build
```

### 学习 Assassyn 语言

阅读文档了解 Assassyn HDL：

```bash
# 在浏览器中查看文档
# Linux/macOS
open docs/Assassyn.md

# Windows
start docs/Assassyn.md
```

## 使用 Makefile 的常用命令

```bash
# 查看所有可用命令
make help

# 代码格式化
make format

# 代码检查
make lint

# 清理构建文件
make clean
```

## 常见问题速查

### Q: 虚拟环境激活失败

**症状**: 提示权限错误或命令未找到

**解决**:
```bash
# Linux/macOS: 确保使用正确的激活命令
source .venv/bin/activate

# Windows: 可能需要修改执行策略
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Q: 找不到 `assassyn` 模块

**症状**: `ModuleNotFoundError: No module named 'assassyn'`

**解决**:

Assassyn 框架可能需要单独安装。请查看项目文档或联系维护者获取安装方法。

如果 Assassyn 已开源：
```bash
pip install assassyn
```

如果需要从源码安装，请参考 Assassyn 的官方文档。

### Q: Rust 编译错误

**症状**: `error: linker 'cc' not found`

**解决**:
```bash
# Ubuntu/Debian
sudo apt install build-essential

# macOS
xcode-select --install

# Fedora/RHEL
sudo dnf install gcc gcc-c++
```

### Q: 测试运行很慢

**原因**: 首次运行需要编译 Rust 仿真器

**说明**: 
- 首次运行每个测试会编译对应的仿真器（约 30-60 秒）
- 后续运行会使用缓存，速度显著提升（< 5 秒）
- 这是正常现象，耐心等待即可

## 项目结构速览

```
Assassyn-CPU/
├── README.md           # 项目主文档
├── INSTALL.md          # 详细安装指南
├── CONTRIBUTING.md     # 贡献指南
├── Makefile            # 常用命令快捷方式
├── requirements.txt    # Python 依赖
│
├── src/                # 源代码
│   ├── main.py        # CPU 构建入口
│   ├── fetch.py       # 取指阶段
│   ├── decoder.py     # 译码阶段
│   ├── execution.py   # 执行阶段
│   ├── memory.py      # 访存阶段
│   └── writeback.py   # 写回阶段
│
├── tests/              # 测试代码
│   ├── common.py      # 测试工具
│   └── test_*.py      # 各模块测试
│
└── docs/               # 设计文档
    ├── Assassyn.md    # Assassyn 语言教程
    └── Module/        # 模块设计文档
```

## 学习路径建议

### 初学者路径

1. **了解项目** (15 分钟)
   - 阅读 [README.md](README.md)
   - 浏览项目结构

2. **学习 Assassyn** (1-2 小时)
   - 阅读 [docs/Assassyn.md](docs/Assassyn.md)
   - 理解基本概念：Module, Bits, RegArray, Port

3. **运行示例** (30 分钟)
   - 运行所有测试：`make test`
   - 查看测试代码了解使用方式

4. **阅读源码** (2-3 小时)
   - 从简单模块开始：`src/fetch.py`
   - 理解流水线结构
   - 查看模块间通信

### 进阶开发者路径

1. **深入理解架构** (1 小时)
   - 阅读 [docs/Module/](docs/Module/) 中的设计文档
   - 理解数据冒险和控制冒险处理

2. **修改和扩展** (实践)
   - 添加新指令
   - 优化流水线
   - 改进测试

3. **贡献代码**
   - 阅读 [CONTRIBUTING.md](CONTRIBUTING.md)
   - 提交 Pull Request

## 获取帮助

遇到问题？您可以：

1. 📖 查看 [README.md](README.md) 中的常见问题部分
2. 📚 阅读 [INSTALL.md](INSTALL.md) 获取详细安装指导
3. 💬 在 [GitHub Issues](https://github.com/konpaku-ming/Assassyn-CPU/issues) 中搜索或提问
4. 📧 联系项目维护者

## 快捷参考

### 重要文件

- `src/main.py` - CPU 构建入口
- `tests/common.py` - 测试框架工具
- `docs/Assassyn.md` - Assassyn 语言教程
- `Makefile` - 所有常用命令

### 重要命令

```bash
make help          # 查看所有命令
make test          # 运行测试
make build         # 构建 CPU
make clean         # 清理文件
```

### 重要概念

- **Module**: Assassyn 中的硬件模块基类
- **Port**: 模块间的通信接口
- **RegArray**: 寄存器数组（状态存储）
- **SRAM**: 存储器（指令和数据）
- **async_called**: 模块间异步调用机制

---

**祝您使用愉快！** 🚀

如有问题，随时查阅文档或提出 Issue。
