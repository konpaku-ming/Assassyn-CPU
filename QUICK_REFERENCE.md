# 快速参考指南 / Quick Reference Guide

## 运行 CPU 构建 / Running CPU Build

### 推荐方式 / Recommended Ways

```bash
# 方法 1: 使用便捷脚本（自动检查环境）
python run_cpu.py

# 方法 2: 使用 Python 模块方式
python -m src.main

# 方法 3: 使用 Makefile
make build
```

### 平台特定脚本 / Platform-Specific Scripts

```bash
# Linux/macOS
./run_cpu.sh

# Windows
run_cpu.bat

# 或直接运行（兼容方式）
python src/main.py
```

## 运行测试 / Running Tests

```bash
# 所有测试
make test
# 或
pytest tests/ -v

# 特定模块测试
make test-fetch      # IF 阶段
make test-decoder    # ID 阶段
make test-execute    # EX 阶段
make test-memory     # MEM 阶段
make test-wb         # WB 阶段

# 验证导入修复
python main_test/test_import_fix.py
```

## 环境设置 / Environment Setup

```bash
# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate      # Linux/macOS
.venv\Scripts\activate         # Windows

# 安装依赖
pip install -r requirements.txt
```

## 常用命令 / Common Commands

```bash
make help          # 显示所有可用命令
make install       # 安装依赖
make test          # 运行所有测试
make build         # 构建 CPU
make clean         # 清理构建文件
make format        # 代码格式化
make lint          # 代码检查
```

## 故障排除 / Troubleshooting

### ImportError: attempted relative import with no known parent package

**解决方案:**
```bash
# 使用模块运行方式
python -m src.main

# 或使用便捷脚本
python run_cpu.py
```

### ModuleNotFoundError: No module named 'assassyn'

**解决方案:**
```bash
# 确保虚拟环境已激活
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 虚拟环境激活失败

**Linux/macOS:**
```bash
source .venv/bin/activate
```

**Windows PowerShell:**
```powershell
# 可能需要修改执行策略
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.venv\Scripts\Activate.ps1
```

**Windows CMD:**
```cmd
.venv\Scripts\activate.bat
```

## 项目结构 / Project Structure

```
Assassyn-CPU/
├── src/              # 源代码
│   ├── __init__.py   # 包标识文件（新增）
│   ├── main.py       # CPU 构建入口
│   ├── fetch.py      # IF 阶段
│   ├── decoder.py    # ID 阶段
│   ├── execution.py  # EX 阶段
│   ├── memory.py     # MEM 阶段
│   └── writeback.py  # WB 阶段
│
├── tests/            # 测试代码
├── docs/             # 文档
├── main_test/        # 主要测试工具
│
├── run_cpu.py        # Python 运行脚本（新增）
├── run_cpu.sh        # Shell 运行脚本（新增）
├── run_cpu.bat       # Batch 运行脚本（新增）
│
├── Makefile          # 构建命令
├── requirements.txt  # Python 依赖
├── README.md         # 项目说明
├── QUICKSTART.md     # 快速开始
└── CHANGELOG.md      # 变更日志（新增）
```

## 文件快速索引 / Quick File Index

- **CPU 构建**: `src/main.py`
- **运行脚本**: `run_cpu.py`, `run_cpu.sh`, `run_cpu.bat`
- **测试框架**: `tests/common.py`
- **导入修复说明**: `docs/ImportError修复说明.md`
- **变更日志**: `CHANGELOG.md`
- **快速开始**: `QUICKSTART.md`
- **详细文档**: `README.md`

## 重要链接 / Important Links

- **GitHub 仓库**: https://github.com/konpaku-ming/Assassyn-CPU
- **问题反馈**: https://github.com/konpaku-ming/Assassyn-CPU/issues
- **贡献指南**: 见 README.md

## 版本要求 / Version Requirements

- Python: 3.10+
- Rust: 最新稳定版
- OS: Linux / macOS / Windows (WSL2)

---

**提示**: 如需详细信息，请查阅 [README.md](README.md) 或 [QUICKSTART.md](QUICKSTART.md)
