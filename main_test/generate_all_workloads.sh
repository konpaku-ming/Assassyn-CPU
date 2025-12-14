#!/bin/bash
# ============================================================================
# 批量生成所有工作负载文件
# 
# 功能：
#   - 一次性生成所有测试用例的 .exe 和 .data 文件
#   - 输出到 ../workloads/ 目录供 main.py 使用
#
# 用法：
#   bash generate_all_workloads.sh
# ============================================================================

# 设置错误时退出
set -e

# 辅助函数：获取工作负载描述
function get_description() {
    case "$1" in
        my0to100)
            echo "0到100累加程序"
            ;;
        multiply)
            echo "乘法测试程序"
            ;;
        vvadd)
            echo "向量加法测试程序"
            ;;
        *)
            echo "测试程序"
            ;;
    esac
}

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 获取脚本所在目录（main_test）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 定义输出目录
OUTPUT_DIR="../workloads"

echo -e "${BLUE}============================================================================${NC}"
echo -e "${BLUE}批量生成工作负载文件${NC}"
echo -e "${BLUE}============================================================================${NC}"
echo ""
echo -e "${YELLOW}脚本目录:${NC} $SCRIPT_DIR"
echo -e "${YELLOW}输出目录:${NC} $OUTPUT_DIR"
echo ""

# 确保输出目录存在
mkdir -p "$OUTPUT_DIR"

# 定义所有工作负载（格式：名称）
# 脚本会自动查找 {name}_text.bin 和 {name}_data.bin
WORKLOADS=("my0to100" "multiply" "vvadd")

# 统计信息
TOTAL=${#WORKLOADS[@]}
SUCCESS=0
FAILED=0

echo -e "${BLUE}发现 $TOTAL 个工作负载需要生成${NC}"
echo ""

# 逐个生成工作负载
for name in "${WORKLOADS[@]}"; do
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}[$((SUCCESS + FAILED + 1))/$TOTAL] 正在生成: ${name}${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    # 定义输入和输出文件
    TEXT_IN="${name}_text.bin"
    DATA_IN="${name}_data.bin"
    TEXT_OUT="$OUTPUT_DIR/${name}.exe"
    DATA_OUT="$OUTPUT_DIR/${name}.data"
    
    # 检查输入文件是否存在
    if [ ! -f "$TEXT_IN" ]; then
        echo -e "${RED}❌ 错误: 找不到 $TEXT_IN${NC}"
        FAILED=$((FAILED + 1))
        echo ""
        continue
    fi
    
    if [ ! -f "$DATA_IN" ]; then
        echo -e "${YELLOW}⚠️  警告: 找不到 $DATA_IN，将创建空文件${NC}"
        touch "$DATA_IN"
    fi
    
    # 运行生成脚本
    if python3 generate_workloads.py \
        --text-in "$TEXT_IN" \
        --data-in "$DATA_IN" \
        --text-out "$TEXT_OUT" \
        --data-out "$DATA_OUT"; then
        
        echo -e "${GREEN}✅ 成功生成 ${name}${NC}"
        
        # 显示文件统计信息
        if [ -f "$TEXT_OUT" ] && [ -f "$DATA_OUT" ]; then
            TEXT_SIZE=$(wc -l < "$TEXT_OUT")
            DATA_SIZE=$(wc -l < "$DATA_OUT")
            echo -e "   ${GREEN}→${NC} $TEXT_OUT (${TEXT_SIZE} words)"
            echo -e "   ${GREEN}→${NC} $DATA_OUT (${DATA_SIZE} words)"
        fi
        
        SUCCESS=$((SUCCESS + 1))
    else
        echo -e "${RED}❌ 生成失败: ${name}${NC}"
        FAILED=$((FAILED + 1))
    fi
    
    echo ""
done

# 最终总结
echo -e "${BLUE}============================================================================${NC}"
echo -e "${BLUE}生成完成${NC}"
echo -e "${BLUE}============================================================================${NC}"
echo ""
echo -e "${GREEN}成功: $SUCCESS${NC} / $TOTAL"
if [ $FAILED -gt 0 ]; then
    echo -e "${RED}失败: $FAILED${NC} / $TOTAL"
fi
echo ""

# 列出所有生成的文件
if [ $SUCCESS -gt 0 ]; then
    echo -e "${YELLOW}生成的文件列表:${NC}"
    ls -lh "$OUTPUT_DIR"/*.{exe,data} 2>/dev/null || true
    echo ""
fi

# 使用提示
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}使用提示:${NC}"
echo ""
echo -e "在 ${BLUE}src/main.py${NC} 中加载测试用例："
echo ""
for name in "${WORKLOADS[@]}"; do
    echo -e "  load_test_case(\"${name}\")  ${GREEN}# $(get_description "$name")${NC}"
done
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# 退出代码
if [ $FAILED -gt 0 ]; then
    exit 1
else
    exit 0
fi
