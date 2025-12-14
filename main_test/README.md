# main_test 目录说明

本目录包含用于生成 dcache/icache 初始化文件的工具和测试文件。

## 文件清单

- `my0to100_text.bin` - 指令段二进制文件（输入）
- `my0to100_data.bin` - 数据段二进制文件（输入）
- `generate_workloads.py` - 生成工具脚本
- `INITIALIZATION_REPORT.md` - 完整的初始化报告和 SP 问题解决方案
- `README.md` - 本文件（快速参考）

## 快速开始

### 生成初始化文件

```bash
cd main_test
python3 generate_workloads.py
```

这将生成：
- `my0to100.exe` - 用于 icache 初始化
- `my0to100.data` - 用于 dcache 初始化

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

生成的文件需要放在 `workloads` 目录下（或 `main.py` 指定的位置）：

```bash
# 如果 workloads 目录不存在，创建它
mkdir -p ../workloads

# 复制生成的文件
cp my0to100.exe ../workloads/
cp my0to100.data ../workloads/
```

然后在 `src/main.py` 中加载：
```python
load_test_case("my0to100")  # 不含 .exe/.data 后缀
```

## 验证

运行仿真器：
```bash
cd ../src
python3 main.py
```

期望结果：累加 0 到 100 的结果为 **5050** (0x13BA)。

## 更多信息

完整的技术文档、问题分析和验证步骤，请参阅：
- **[INITIALIZATION_REPORT.md](INITIALIZATION_REPORT.md)** - 完整初始化报告
- `../docs/Assassyn.md` - Assassyn 框架文档
- `../src/main.py` - CPU 主程序
