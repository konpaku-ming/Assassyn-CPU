# 安装指南

本文档提供详细的安装步骤，适用于不同操作系统和环境。

## 目录

- [系统要求](#系统要求)
- [Linux 安装](#linux-安装)
- [macOS 安装](#macos-安装)
- [Windows 安装](#windows-安装)
- [Docker 安装（可选）](#docker-安装可选)
- [验证安装](#验证安装)
- [常见问题](#常见问题)

## 系统要求

### 最低要求

- **CPU**: 双核处理器
- **内存**: 4GB RAM
- **磁盘**: 2GB 可用空间
- **操作系统**: 
  - Linux: Ubuntu 20.04+ / Debian 11+ / Fedora 35+
  - macOS: 11.0 (Big Sur) 或更高
  - Windows: Windows 10/11 with WSL2

### 推荐配置

- **CPU**: 四核或更多核心
- **内存**: 8GB RAM 或更多
- **磁盘**: 5GB 可用空间（SSD 推荐）

## Linux 安装

### Ubuntu / Debian

#### 1. 更新系统

```bash
sudo apt update
sudo apt upgrade -y
```

#### 2. 安装系统依赖

```bash
# 安装编译工具和开发库
sudo apt install -y \
    build-essential \
    git \
    curl \
    wget \
    python3 \
    python3-pip \
    python3-venv \
    pkg-config \
    libssl-dev
```

#### 3. 安装 Rust

```bash
# 使用 rustup 安装 Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# 选择默认安装选项 (1)
# 安装完成后，配置环境变量
source $HOME/.cargo/env

# 验证安装
rustc --version
cargo --version
```

#### 4. 克隆项目

```bash
git clone https://github.com/konpaku-ming/Assassyn-CPU.git
cd Assassyn-CPU
```

#### 5. 设置 Python 环境

```bash
# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate

# 升级 pip
pip install --upgrade pip

# 安装项目依赖
pip install -r requirements.txt
```

#### 6. 安装 Assassyn（如需要）

如果 Assassyn 框架需要单独安装：

```bash
# 方法 1: 如果 Assassyn 在 PyPI 上
pip install assassyn

# 方法 2: 从源码安装
# git clone <assassyn-repository-url>
# cd assassyn
# pip install -e .
```

### Fedora / CentOS / RHEL

```bash
# 安装系统依赖
sudo dnf install -y \
    gcc \
    gcc-c++ \
    make \
    git \
    curl \
    python3 \
    python3-pip \
    openssl-devel

# 后续步骤同 Ubuntu
```

## macOS 安装

### 使用 Homebrew（推荐）

#### 1. 安装 Homebrew

如果还没有安装 Homebrew：

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

#### 2. 安装依赖

```bash
# 安装 Python 3
brew install python3

# 安装 Git（如果还没有）
brew install git

# 安装其他工具
brew install wget curl
```

#### 3. 安装 Rust

```bash
# 使用 rustup 安装 Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# 配置环境变量
source $HOME/.cargo/env

# 或者使用 Homebrew 安装
# brew install rust
```

#### 4. 克隆和设置项目

```bash
# 克隆项目
git clone https://github.com/konpaku-ming/Assassyn-CPU.git
cd Assassyn-CPU

# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate

# 安装依赖
pip install --upgrade pip
pip install -r requirements.txt
```

### 使用 MacPorts

```bash
# 安装 Python 和 Rust
sudo port install python311 rust

# 后续步骤同上
```

## Windows 安装

### 使用 WSL2（推荐）

#### 1. 启用 WSL2

在管理员 PowerShell 中运行：

```powershell
# 启用 WSL
wsl --install

# 重启计算机
```

#### 2. 安装 Ubuntu

```powershell
# 安装 Ubuntu（默认最新 LTS 版本）
wsl --install -d Ubuntu

# 或者从 Microsoft Store 安装 Ubuntu
```

#### 3. 在 WSL2 Ubuntu 中安装

进入 WSL2 Ubuntu 终端后，按照 [Linux 安装](#linux-安装) 步骤操作。

### 使用原生 Windows（不推荐）

如果必须在原生 Windows 上运行：

#### 1. 安装 Python

从 [python.org](https://www.python.org/downloads/) 下载并安装 Python 3.10+

#### 2. 安装 Rust

从 [rustup.rs](https://rustup.rs/) 下载并安装 Rust

#### 3. 安装 Git

从 [git-scm.com](https://git-scm.com/download/win) 下载并安装 Git

#### 4. 安装 Visual Studio Build Tools

Rust 编译需要 C++ 编译器：

从 [Visual Studio](https://visualstudio.microsoft.com/downloads/) 下载 "Build Tools for Visual Studio"，安装时选择 "C++ build tools"。

#### 5. 克隆和设置项目

```powershell
# 使用 Git Bash 或 PowerShell
git clone https://github.com/konpaku-ming/Assassyn-CPU.git
cd Assassyn-CPU

# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 安装依赖
pip install --upgrade pip
pip install -r requirements.txt
```

## Docker 安装（可选）

如果您熟悉 Docker，可以使用容器化环境：

### 创建 Dockerfile

```dockerfile
FROM ubuntu:22.04

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# 安装 Rust
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# 设置工作目录
WORKDIR /workspace

# 复制项目文件
COPY . .

# 安装 Python 依赖
RUN pip3 install --upgrade pip && \
    pip3 install -r requirements.txt

# 默认命令
CMD ["/bin/bash"]
```

### 构建和运行

```bash
# 构建镜像
docker build -t assassyn-cpu:latest .

# 运行容器
docker run -it --rm -v $(pwd):/workspace assassyn-cpu:latest

# 在容器中运行测试
docker run -it --rm -v $(pwd):/workspace assassyn-cpu:latest make test
```

## 验证安装

完成安装后，运行以下命令验证：

### 1. 检查 Python 环境

```bash
# 确保虚拟环境已激活
source .venv/bin/activate  # Linux/macOS
# 或
.\.venv\Scripts\Activate.ps1  # Windows

# 检查 Python 版本
python --version  # 应显示 3.10 或更高

# 检查已安装的包
pip list
```

### 2. 检查 Rust 环境

```bash
# 检查 Rust 版本
rustc --version
cargo --version
```

### 3. 运行测试

```bash
# 运行简单测试
make test-fetch

# 如果成功，应看到类似输出：
# 🚀 Compiling system: test_fetch...
# 🔨 Building binary...
# 🏃 Running simulation...
# ✅ test_fetch Passed!
```

### 4. 构建 CPU

```bash
# 尝试构建完整 CPU
python src/main.py

# 应看到：
# Building System: rv32i_cpu
# Building Simulator Binary...
# Binary Built: ...
```

## 常见问题

### Q1: `assassyn` 模块找不到

**问题**: `ModuleNotFoundError: No module named 'assassyn'`

**解决方案**:

```bash
# 检查 Assassyn 是否已安装
pip list | grep assassyn

# 如果没有，尝试安装
pip install assassyn

# 或者从源码安装（如果是私有框架）
# 请联系项目维护者获取 Assassyn 安装方法
```

### Q2: Rust 编译失败

**问题**: `error: linker 'cc' not found`

**解决方案**:

```bash
# Ubuntu/Debian
sudo apt install build-essential

# macOS
xcode-select --install

# Fedora
sudo dnf install gcc gcc-c++
```

### Q3: 权限错误

**问题**: `Permission denied` 错误

**解决方案**:

```bash
# 不要使用 sudo pip install
# 而是使用虚拟环境
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Q4: 虚拟环境激活失败（Windows）

**问题**: PowerShell 执行策略阻止脚本运行

**解决方案**:

```powershell
# 以管理员身份运行 PowerShell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 然后重试激活虚拟环境
.\.venv\Scripts\Activate.ps1
```

### Q5: 内存不足

**问题**: 编译时系统卡顿或崩溃

**解决方案**:

```bash
# 限制并行编译任务数
export CARGO_BUILD_JOBS=1

# 或者增加系统 swap 空间
# Ubuntu/Debian:
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### Q6: Makefile 命令无法识别（Windows）

**问题**: `make: command not found`

**解决方案**:

```powershell
# 方法 1: 使用 WSL2（推荐）

# 方法 2: 安装 Make for Windows
# 从 http://gnuwin32.sourceforge.net/packages/make.htm 下载

# 方法 3: 使用 Chocolatey
choco install make

# 方法 4: 直接运行 Python 命令，不使用 Makefile
python -m pytest tests/ -v
```

## 获取帮助

如果遇到其他问题：

1. 查看主 [README.md](README.md) 中的常见问题部分
2. 查看 [docs/](docs/) 目录中的详细文档
3. 在 [GitHub Issues](https://github.com/konpaku-ming/Assassyn-CPU/issues) 中搜索或提交问题
4. 联系项目维护者

---

**祝您安装顺利！** 🎉
