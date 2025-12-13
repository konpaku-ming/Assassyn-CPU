#!/bin/bash
# Assassyn-CPU 构建脚本
# 用于构建 RV32I CPU 系统

set -e  # 遇到错误时退出

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}===================================${NC}"
echo -e "${BLUE}  Assassyn-CPU 构建工具${NC}"
echo -e "${BLUE}===================================${NC}"
echo ""

# 检查虚拟环境
if [[ -z "$VIRTUAL_ENV" ]] && [[ -z "$CONDA_DEFAULT_ENV" ]]; then
    echo -e "${YELLOW}⚠️  警告: 未检测到虚拟环境${NC}"
    echo -e "${YELLOW}   建议先激活虚拟环境: source .venv/bin/activate${NC}"
    echo ""
    
    # 检查是否存在 venv 虚拟环境
    if [[ -d ".venv" ]]; then
        echo -e "${BLUE}💡 提示: 发现 .venv 虚拟环境，尝试激活...${NC}"
        source .venv/bin/activate || {
            echo -e "${RED}❌ 激活虚拟环境失败${NC}"
            echo -e "${YELLOW}   如果您使用 conda 或其他虚拟环境管理工具，请手动激活${NC}"
            exit 1
        }
        echo -e "${GREEN}✓ 虚拟环境已激活${NC}"
        echo ""
    else
        echo -e "${YELLOW}   继续使用系统 Python 环境...${NC}"
        echo -e "${YELLOW}   如果您使用 conda、pipenv 或 poetry，请手动激活环境${NC}"
        echo ""
    fi
elif [[ -n "$CONDA_DEFAULT_ENV" ]]; then
    echo -e "${GREEN}✓ Conda 环境已激活: $CONDA_DEFAULT_ENV${NC}"
    echo ""
fi

# 检查 Python 版本
echo -e "${BLUE}🔍 检查 Python 版本...${NC}"
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}✓ Python 版本: ${PYTHON_VERSION}${NC}"
echo ""

# 检查依赖
echo -e "${BLUE}🔍 检查依赖包...${NC}"
if python3 -c "import assassyn" 2>/dev/null; then
    echo -e "${GREEN}✓ Assassyn 框架已安装${NC}"
else
    echo -e "${RED}❌ 未找到 Assassyn 框架${NC}"
    echo -e "${YELLOW}   请先安装 Assassyn 或参考文档安装依赖${NC}"
    echo ""
    echo -e "${BLUE}💡 提示:${NC}"
    echo "   1. 确保已安装所有依赖: pip install -r requirements.txt"
    echo "   2. 如果 Assassyn 是私有框架，请参考其官方文档安装"
    echo ""
    exit 1
fi
echo ""

# 创建工作目录
echo -e "${BLUE}📁 准备工作目录...${NC}"
mkdir -p .workspace
echo -e "${GREEN}✓ 工作目录已创建: .workspace/${NC}"
echo ""

# 运行构建
echo -e "${BLUE}🚀 开始构建 CPU 系统...${NC}"
echo ""

python3 -m src.main

echo ""
echo -e "${GREEN}===================================${NC}"
echo -e "${GREEN}  ✓ 构建完成！${NC}"
echo -e "${GREEN}===================================${NC}"
