# Quick Start Guide - dcache/icache Initialization

## 快速开始 / Quick Start

### 文件位置 / File Locations

```
Assassyn-CPU/
├── main_test/                          # 测试文件目录 / Test files directory
│   ├── 0to100_text.bin                # 指令段（输入）/ Text segment (input)
│   ├── 0to100_data.bin                # 数据段（输入）/ Data segment (input)
│   └── test_initialization.py          # 验证脚本 / Verification script
├── src/
│   ├── main.py                        # CPU 主程序 / Main CPU program
│   └── .workspace/                    # 自动生成 / Auto-generated
│       ├── workload.exe               # 指令缓存初始化 / icache initialization
│       └── workload.data              # 数据缓存初始化 / dcache initialization
└── docs/
    ├── Initialization_Report.md        # 详细报告 / Detailed report
    └── Quick_Start_Guide.md            # 本文档 / This guide
```

## 使用方法 / Usage

### 1. 运行验证测试 / Run Verification Test

```bash
cd Assassyn-CPU
python3 main_test/test_initialization.py
```

预期输出 / Expected output:
```
✅ ALL TESTS PASSED!
```

### 2. 运行 CPU（需要 assassyn 环境）/ Run CPU (requires assassyn environment)

```bash
cd Assassyn-CPU
python src/main.py
```

## 工作原理 / How It Works

### 文件转换 / File Conversion

1. **输入 / Input**: 二进制文件 `.bin` (raw binary)
2. **处理 / Process**: `convert_bin_to_hex()` 函数转换为十六进制文本
3. **输出 / Output**: 文本文件 `.exe` / `.data` (hex text, 8 chars per line)

```
Binary: [0x13, 0x01, 0x01, 0xfe]  →  Hex Text: "fe010113"
```

### 堆栈初始化 / Stack Initialization

```python
# 在 build_cpu() 中 / In build_cpu()
WORD_SIZE = 4
STACK_TOP = (1 << depth_log) - WORD_SIZE  # 0xFFFC for 64KB RAM
reg_init[2] = STACK_TOP  # x2 = sp
```

- **RAM 大小 / RAM Size**: 64KB (65536 bytes)
- **栈顶地址 / Stack Top**: 0xFFFC (65532)
- **SP 初始值 / Initial SP**: 0xFFFC

### 程序执行流程 / Program Execution Flow

```
1. CPU Reset
   ├─ SP = 0xFFFC (initialized by RegArray)
   └─ PC = 0x0000
   
2. First Instruction: ADDI sp, sp, -32
   └─ SP = 0xFFFC - 32 = 0xFFDC (create stack frame)
   
3. Program Execution
   ├─ Load/Store operations use stack
   ├─ Calculate sum = 1+2+3+...+100
   └─ Return value: 5050 (0x13BA)
   
4. Last Instruction: ADDI sp, sp, 32
   └─ SP = 0xFFDC + 32 = 0xFFFC (restore stack)
```

## 文件格式规范 / File Format Specification

### 十六进制文本格式 / Hex Text Format

- **每行一个字 / One word per line**: 32 bits (4 bytes)
- **十六进制字符 / Hex characters**: 8 characters, lowercase
- **无前缀 / No prefix**: No "0x"
- **字节序 / Byte order**: Little-endian

示例 / Example:
```
fe010113    # ADDI sp, sp, -32
00812e23    # SW s0, 28(sp)
02010413    # ADDI s0, sp, 32
```

## 测试程序信息 / Test Program Information

### 0to100 程序 / 0to100 Program

**功能 / Function**: 计算 1+2+3+...+100 = 5050

**规模 / Size**:
- 指令数 / Instructions: 22
- 指令大小 / Text size: 88 bytes
- 数据大小 / Data size: 0 bytes (uses stack only)
- 栈帧大小 / Stack frame: 32 bytes

**汇编代码结构 / Assembly Structure**:
```c
int accumulate() {
    int sum = 0;           // Stack: s0-24
    for (int i = 1; i <= 100; i++) {  // Stack: s0-20
        sum += i;
    }
    return sum;  // Expected: 5050
}
```

## 故障排除 / Troubleshooting

### 问题：找不到二进制文件 / Problem: Binary files not found

```bash
# 检查文件是否存在 / Check if files exist
ls -l main_test/*.bin
```

解决方案 / Solution: 确保 `main_test/` 目录包含 `0to100_text.bin` 和 `0to100_data.bin`

### 问题：转换失败 / Problem: Conversion fails

```bash
# 检查文件权限 / Check file permissions
chmod +x main_test/test_initialization.py
```

### 问题：CPU 运行失败 / Problem: CPU execution fails

可能原因 / Possible causes:
1. ❌ assassyn 框架未安装 / assassyn framework not installed
2. ❌ SP 未正确初始化 / SP not properly initialized
3. ❌ 指令文件格式错误 / Instruction file format incorrect

解决方案 / Solution:
```bash
# 运行验证测试 / Run verification test
python3 main_test/test_initialization.py

# 检查输出是否全部 ✅ / Check if all outputs show ✅
```

## 技术细节 / Technical Details

### 内存映射 / Memory Map

```
0x00000000 - 0x00000057  : 指令段 (22 instructions * 4 bytes = 88 bytes)
                          Text segment
0x00000058 - 0x0000FFDB  : 未使用 / Unused
0x0000FFDC - 0x0000FFFB  : 栈空间 (32 bytes)
                          Stack space  
0x0000FFFC               : 栈顶 / Stack top (initial SP)
```

### 寄存器初始化 / Register Initialization

```python
reg_init = [0] * 32
reg_init[2] = 0xFFFC    # x2 = sp (Stack Pointer)
# All other registers = 0
```

### SRAM 初始化 / SRAM Initialization

```python
# 指令缓存 / Instruction cache
icache = SRAM(width=32, depth=65536, init_file="workload.exe")

# 数据缓存 / Data cache  
dcache = SRAM(width=32, depth=65536, init_file="workload.data")
```

## 相关文档 / Related Documentation

- **详细报告 / Detailed Report**: `docs/Initialization_Report.md`
- **Assassyn 框架文档 / Framework Docs**: `docs/Assassyn.md`
- **模块文档 / Module Docs**: `docs/Module/`

## 更新历史 / Update History

- **2025-12-14**: 
  - ✅ 实现二进制到十六进制转换 / Implemented binary to hex conversion
  - ✅ 添加 SP 初始化 / Added SP initialization
  - ✅ 创建验证测试脚本 / Created verification test script
  - ✅ 编写完整文档 / Wrote comprehensive documentation

---

**版本 / Version**: 1.0  
**状态 / Status**: ✅ 完成 / Complete
