# main_test 目录说明

本目录包含用于生成 dcache/icache 初始化文件的工具和测试文件。

## 文件清单

### 输入文件（二进制格式）
- `0to100_text.bin` / `0to100_data.bin` - 0到100累加程序
- `multiply_text.bin` / `multiply_data.bin` - 乘法测试程序
- `vvadd_text.bin` / `vvadd_data.bin` - 向量加法测试程序

### 工具脚本
- `generate_workloads.py` - 工作负载生成工具
- `generate_all_workloads.sh` - 批量生成脚本

### 文档
- `INITIALIZATION_REPORT.md` - 完整的初始化报告和 SP 问题解决方案
- `README.md` - 本文件（快速参考）

## 快速开始

### 生成所有工作负载（推荐）

```bash
cd main_test
bash generate_all_workloads.sh
```

这将一次性生成所有工作负载文件到 `../workloads/` 目录：
- `0to100.exe` / `0to100.data` - 0到100累加程序
- `multiply.exe` / `multiply.data` - 乘法测试程序
- `vvadd.exe` / `vvadd.data` - 向量加法测试程序

### 生成单个工作负载

```bash
# 生成 0to100 工作负载
python3 generate_workloads.py \
    --text-in 0to100_text.bin \
    --data-in 0to100_data.bin \
    --text-out ../workloads/0to100.exe \
    --data-out ../workloads/0to100.data

# 生成 multiply 工作负载
python3 generate_workloads.py \
    --text-in multiply_text.bin \
    --data-in multiply_data.bin \
    --text-out ../workloads/multiply.exe \
    --data-out ../workloads/multiply.data

# 生成 vvadd 工作负载
python3 generate_workloads.py \
    --text-in vvadd_text.bin \
    --data-in vvadd_data.bin \
    --text-out ../workloads/vvadd.exe \
    --data-out ../workloads/vvadd.data
```

### 输出格式

默认输出格式为**文本十六进制**：
- 每行一个 32-bit 十六进制数（8 位十六进制字符）
- 小端序（Little-endian）
- 不含 `0x` 前缀
- 与 Verilog `$readmemh` 格式兼容

示例：
```
fe010113
00812e23
02010413
fe042423
```

### 其他选项

查看所有选项：
```bash
python3 generate_workloads.py --help
```

常用选项：
- `--binary` - 输出原始二进制格式（而非文本十六进制）
- `--endian big` - 使用大端序
- `--word-size 2` - 使用 16-bit 字宽

## SP（栈指针）初始化问题

运行 `accumulate` 程序前，必须正确初始化栈指针（SP，x2 寄存器）。

**推荐解决方案**：在程序启动代码中设置 SP

```assembly
# boot.S
.global _start
_start:
    li sp, 0x80010000   # 设置 SP 为 RAM 顶部
    call main           # 跳转到主程序
```

详细说明和多种解决方案请参考 **[INITIALIZATION_REPORT.md](INITIALIZATION_REPORT.md)**。

## 集成到 main.py

生成的文件会自动放在 `workloads` 目录下，可以直接在 `src/main.py` 中加载：

```python
# 在 src/main.py 中选择要运行的测试用例
load_test_case("0to100")     # 0到100累加程序
load_test_case("multiply")   # 乘法测试程序
load_test_case("vvadd")      # 向量加法测试程序
```

注意：加载测试用例时不需要包含 `.exe` 或 `.data` 后缀。

## 验证

运行仿真器：
```bash
cd ../src
python3 main.py
```

期望结果（取决于加载的测试用例）：
- **0to100**: 累加 0 到 100 的结果为 **5050** (0x13BA)
- **multiply**: 执行乘法运算测试
- **vvadd**: 执行向量加法运算测试

## 更多信息

完整的技术文档、问题分析和验证步骤，请参阅：
- **[INITIALIZATION_REPORT.md](INITIALIZATION_REPORT.md)** - 完整初始化报告
- `../docs/Assassyn.md` - Assassyn 框架文档
- `../src/main.py` - CPU 主程序
