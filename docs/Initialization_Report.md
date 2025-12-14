# Assassyn CPU - Memory Initialization Report

## 概述 (Overview)

本报告说明了如何从二进制文件初始化 dcache (数据缓存) 和 icache (指令缓存)，以及如何正确初始化堆栈指针 (SP) 以运行测试程序。

This report describes how to initialize dcache (data cache) and icache (instruction cache) from binary files, and how to properly initialize the stack pointer (SP) to run test programs.

## 文件格式 (File Format)

### 输入文件 (Input Files)
- **0to100_text.bin**: 程序的指令段 (二进制格式)
- **0to100_data.bin**: 程序的数据段 (二进制格式)

### 输出文件 (Output Files)
- **.workspace/0to100.exe**: 指令缓存初始化文件 (文本格式)
- **.workspace/0to100.data**: 数据缓存初始化文件 (文本格式)
- **.workspace/workload.exe**: icache 加载文件 (main.py 使用)
- **.workspace/workload.data**: dcache 加载文件 (main.py 使用)

### 文本格式规范 (Text Format Specification)
```
- 每行一个 32 位字 (word)
- 8 个十六进制字符 (小写)
- 无 "0x" 前缀
- 小端序 (little-endian)

示例 (Example):
fe010113
00812e23
02010413
```

## 转换过程 (Conversion Process)

### 实现 (Implementation)

在 `src/main.py` 中添加了 `convert_bin_to_hex()` 函数：

```python
def convert_bin_to_hex(bin_path, hex_path):
    """
    将二进制文件转换为 hex 文本格式
    每行一个 32 位字 (8 个十六进制字符, 小写, 无 0x 前缀)
    """
    with open(bin_path, 'rb') as f_in, open(hex_path, 'w') as f_out:
        while True:
            # 每次读取 4 字节 (32 位)
            chunk = f_in.read(4)
            if not chunk:
                break
            
            # 如果不足 4 字节，补 0
            if len(chunk) < 4:
                chunk = chunk + b'\x00' * (4 - len(chunk))
            
            # 转换为小端序的 32 位整数，然后转为 8 位十六进制字符串
            word = int.from_bytes(chunk, byteorder='little')
            f_out.write(f"{word:08x}\n")
```

### 转换结果 (Conversion Results)

- **指令文件 (Instruction File)**: 22 条指令 (88 字节)
- **数据文件 (Data File)**: 0 字节 (空文件，程序只使用栈)

## 0to100 程序分析 (Program Analysis)

### 程序功能 (Program Function)
计算 1 + 2 + 3 + ... + 100 = **5050** (0x13BA)

### 指令分解 (Instruction Breakdown)

```asm
0: ADDI sp, sp, -32      # 创建栈帧，分配 32 字节空间
1: SW s0, 28(sp)         # 保存旧的帧指针
2: ADDI s0, sp, 32       # 设置新的帧指针
3: SW zero, -24(s0)      # sum = 0
4: ADDI a5, zero, 1      # i = 1
5: SW a5, -20(s0)        # 存储 i
6: JAL zero, 32          # 跳转到循环条件检查
7: LW a4, -24(s0)        # 加载 sum
8: LW a5, -20(s0)        # 加载 i
9: ADD a5, a4, a5        # sum = sum + i
10: SW a5, -24(s0)       # 存储 sum
11: LW a5, -20(s0)       # 加载 i
12: ADDI a5, a5, 1       # i++
13: SW a5, -20(s0)       # 存储 i
14: LW a4, -20(s0)       # 加载 i
15: ADDI a5, zero, 100   # 常量 100
16: BGE a5, a4, -36      # if (100 >= i) 跳转到循环体
17: ADDI a5, zero, 0     # 返回值 = 0
18: ADDI a0, a5, 0       # 设置返回寄存器
19: LW s0, 28(sp)        # 恢复帧指针
20: ADDI sp, sp, 32      # 恢复栈指针
21: JALR zero, ra, 0     # 返回
```

### 内存布局 (Memory Layout)

```
栈帧结构 (Stack Frame):
s0 + 0:  (栈顶，指向调用者的 SP)
s0 - 4:  (未使用)
s0 - 8:  (未使用)
s0 - 12: (未使用)
s0 - 16: (未使用)
s0 - 20: 变量 i (loop counter)
s0 - 24: 变量 sum (accumulator)
s0 - 28: 保存的 s0
```

## 堆栈指针初始化问题 (Stack Pointer Initialization Issue)

### 问题描述 (Problem Description)

**原始问题**: CPU 运行 accumulate 测试时，堆栈指针 (SP) 未被初始化。

**症状 (Symptoms)**:
- 第一条指令 `ADDI sp, sp, -32` 期望 SP 已经指向有效的栈地址
- 如果 SP = 0 或未初始化，则会导致：
  - 栈帧创建在无效地址
  - 内存访问违规或数据损坏
  - 程序无法正常执行

### 解决方案 (Solution)

#### 方法 1: 在 CPU 复位时初始化 SP (推荐)

在 `src/main.py` 的 `Driver` 模块或 CPU 初始化代码中，在复位时设置 SP 寄存器：

```python
# 在 Driver.build() 或类似的初始化逻辑中
# 假设 RAM 大小为 64KB (2^16 字节)
STACK_TOP = (1 << 16) - 4  # 0xFFFC (栈顶，字对齐)

# 方法 A: 通过 RegArray 直接初始化
# reg_file[2] = Bits(32)(STACK_TOP)  # x2 = sp

# 方法 B: 在第一个时钟周期写入
# 需要在 CPU 的复位逻辑中添加：
# if reset:
#     reg_file.write(addr=2, data=STACK_TOP)
```

#### 方法 2: 在程序开头添加启动代码

在 `_start` 标签或程序入口处添加：

```asm
_start:
    lui sp, 0x10      # SP = 0x10000 (64KB)
    addi sp, sp, -4   # SP = 0xFFFC
    jal ra, main      # 调用 main 函数
```

#### 推荐配置 (Recommended Configuration)

对于 Assassyn CPU 的配置：
- **RAM 大小**: 64KB (depth_log = 16)
- **栈顶地址**: 0xFFFC (最高可用字地址)
- **栈增长方向**: 向下 (从高地址向低地址)

```python
# 在 build_cpu() 中
MEMORY_SIZE = 1 << 16  # 64KB
STACK_TOP = MEMORY_SIZE - 4  # 0xFFFC
```

### 实现状态 (Implementation Status)

**当前状态**: ✅ 已实现 SP 初始化

**实际实现**: 在 `src/main.py` 的 `build_cpu()` 函数中，通过 `RegArray` 的 `initializer` 参数初始化 SP：

```python
# 寄存器堆
# 初始化 SP (x2) 指向栈顶
# RAM 大小: 2^depth_log 字节，栈顶在最高地址
STACK_TOP = (1 << depth_log) - 4  # 栈顶地址（字对齐）
reg_init = [0] * 32
reg_init[2] = STACK_TOP  # x2 = sp，初始化为栈顶
reg_file = RegArray(Bits(32), 32, initializer=reg_init)
```

**配置详情**:
- **RAM 大小**: 64KB (depth_log = 16, 即 2^16 = 65536 字节)
- **栈顶地址**: 0xFFFC (65532, 最高可用字对齐地址)
- **SP 初始值**: 0xFFFC
- **第一条指令执行后**: SP = 0xFFFC - 32 = 0xFFDC

**验证方法**:
1. 运行 CPU 模拟器
2. 检查第一条指令执行前 SP 的值应为 0xFFFC
3. 检查栈帧创建后 SP 的值应为 0xFFDC
4. 验证程序能够正常执行并返回正确结果 (5050)

## 文件清单 (File Checklist)

✅ **main_test/0to100_text.bin** - 输入的指令二进制文件 (88 字节)
✅ **main_test/0to100_data.bin** - 输入的数据二进制文件 (0 字节)
✅ **.workspace/0to100.exe** - 转换后的指令文件 (22 行)
✅ **.workspace/0to100.data** - 转换后的数据文件 (空)
✅ **.workspace/workload.exe** - CPU 加载的指令文件
✅ **.workspace/workload.data** - CPU 加载的数据文件

## 验证 (Verification)

### 转换验证 (Conversion Verification)
```bash
# 运行验证脚本
python3 /tmp/verify_conversion.py

# 预期输出:
# ✅ All 22 words verified correctly
# ✅ Both files are empty (correct)
# ✅ ALL VERIFICATIONS PASSED!
```

### 指令验证 (Instruction Verification)
```bash
# 解码指令
python3 /tmp/decode_instructions.py

# 验证第一条指令是 ADDI sp, sp, -32
# 验证程序结构正确
```

## 下一步 (Next Steps)

1. ✅ 完成二进制到十六进制的转换
2. ✅ 生成 .workspace 文件
3. ✅ 验证转换正确性
4. ✅ 在 CPU 代码中实现 SP 初始化
5. ⏳ 运行完整的 CPU 模拟测试（需要 assassyn 框架环境）
6. ⏳ 验证程序输出正确 (sum = 5050)

## 总结 (Summary)

本次修改成功实现了：
1. **文件转换**: 从 .bin 格式到 .exe/.data 文本格式
2. **格式兼容**: 符合 SRAM 初始化文件要求
3. **问题识别**: 明确了 SP 初始化的必要性
4. **SP 初始化**: 在寄存器堆创建时通过 initializer 设置 SP = 0xFFFC
5. **代码更新**: 修改 main.py 以适应新的外部接口

**关键代码变更**:

1. **新增函数**: `convert_bin_to_hex()` - 将二进制文件转换为十六进制文本格式
2. **修改函数**: `load_test_case()` - 改为从 `main_test` 目录读取 `*_text.bin` 和 `*_data.bin` 文件
3. **SP 初始化**: 在 `build_cpu()` 中通过 `RegArray` 的 `initializer` 参数设置 SP

**接口变更**: 
- **旧接口**: 从 `workloads` 目录读取 `.exe` 和 `.data` 文件（已生成的文本格式）
- **新接口**: 从 `main_test` 目录读取 `_text.bin` 和 `_data.bin` 文件（原始二进制）

**技术细节**:
- 转换采用小端序 (little-endian)
- 每行一个 32 位字，8 个十六进制字符
- 自动处理不足 4 字节的情况（补零）
- 空数据文件生成空的文本文件

---

**日期**: 2025-12-14  
**版本**: 1.0  
**状态**: ✅ 实现完成，代码已更新
