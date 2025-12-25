# Codegen - RV32IM 代码生成工具

[English](#english) | [中文](#中文)

---

## 中文

### 概述

这个目录包含了用于生成 RV32IM 指令的工具和测试代码。它将 C 代码编译为 RISC-V 32位指令（包含乘法扩展），并生成可在 Assassyn-CPU 上运行的二进制文件。

### 前置要求

在运行 codegen.sh 之前，你需要安装 RISC-V 裸机交叉编译工具链。

#### Ubuntu/Debian 系统安装方法

```bash
sudo apt-get update
sudo apt-get install -y gcc-riscv64-unknown-elf binutils-riscv64-unknown-elf
```

#### 其他系统

请参考 [RISC-V GNU Toolchain](https://github.com/riscv-collab/riscv-gnu-toolchain) 仓库进行源码编译安装。

### 文件说明

- **codegen.sh**: 主编译脚本，执行完整的编译流程
- **code.c**: C 源代码文件（示例：计算阶乘）
- **start.S**: RISC-V 汇编启动代码
- **harvard.ld**: 链接脚本（Harvard 架构，指令和数据分离）
- **cpu.elf**: 生成的 ELF 可执行文件
- **icache.bin**: 指令缓存二进制文件
- **icache.hex**: 指令缓存十六进制文件
- **memory.bin**: 数据存储器二进制文件
- **memory.hex**: 数据存储器十六进制文件
- **obj.exe**: 反汇编文件

### 使用方法

1. 确保已安装 RISC-V 工具链（见"前置要求"）

2. 编辑 `code.c` 文件，编写你的 C 代码

3. 运行编译脚本：
   ```bash
   bash codegen.sh
   ```

4. 检查生成的文件：
   ```bash
   # 查看反汇编代码
   cat obj.exe
   
   # 查看指令十六进制
   cat icache.hex
   
   # 查看数据十六进制
   cat memory.hex
   ```

### 编译流程

`codegen.sh` 脚本执行以下步骤：

1. **编译和链接**
   ```bash
   riscv64-unknown-elf-gcc -march=rv32im -mabi=ilp32 -nostdlib \
       -Wl,--no-check-sections -T harvard.ld start.S code.c -o cpu.elf
   ```
   - `-march=rv32im`: 目标架构为 RV32IM（基本指令集 + 乘法扩展）
   - `-mabi=ilp32`: 使用 ILP32 ABI（整型、长整型、指针都是32位）
   - `-nostdlib`: 不链接标准库（裸机环境）
   - `-T harvard.ld`: 使用自定义链接脚本

2. **提取指令段**
   ```bash
   riscv64-unknown-elf-objcopy -j .text -O binary cpu.elf icache.bin
   ```

3. **提取数据段**
   ```bash
   riscv64-unknown-elf-objcopy -j .data -j .bss -O binary cpu.elf memory.bin
   ```

4. **生成反汇编**
   ```bash
   riscv64-linux-gnu-objdump -D cpu.elf > obj.exe
   ```

5. **转换为十六进制格式**
   ```bash
   hexdump -v -e '1/4 "%08x" "\n"' icache.bin > icache.hex
   hexdump -v -e '1/4 "%08x" "\n"' memory.bin > memory.hex
   ```

### 验证 RV32IM 指令生成

要验证是否正确生成了 M 扩展（乘法）指令，可以查看反汇编文件：

```bash
cat obj.exe | grep -E "mul|div|rem"
```

你应该能看到类似以下的指令：
- `mul` - 乘法（低32位）
- `mulh` - 有符号乘法（高32位）
- `mulhsu` - 有符号×无符号乘法（高32位）
- `mulhu` - 无符号乘法（高32位）
- `div` - 有符号除法
- `divu` - 无符号除法
- `rem` - 有符号取余
- `remu` - 无符号取余

### 示例代码

当前的 `code.c` 包含一个计算阶乘的示例：

```c
#define DATA_SIZE 100

int result = 1;

int main() {
    int i;
    for (i = 1; i <= DATA_SIZE; i++) {
        result = result * i;
    }
    return result;
}
```

这个代码会生成 `mul` 指令，证明 RV32IM 扩展正在工作。

### 故障排除

#### 错误: `riscv64-unknown-elf-gcc: command not found`

**原因**: 未安装 RISC-V 工具链

**解决方案**: 按照"前置要求"部分的说明安装工具链

#### 错误: 链接失败或内存溢出

**原因**: 代码或数据超出了链接脚本定义的内存大小

**解决方案**: 
1. 编辑 `harvard.ld`，增加 IMEM 或 DMEM 的 LENGTH
2. 优化你的 C 代码，减少内存使用

#### 问题: 编译成功但没有生成乘法指令

**症状**: 运行 `cat obj.exe | grep mul` 没有找到 `mul` 指令

**可能原因和解决方案**:

1. **编译器优化消除了乘法**
   - GCC 可能会将常量乘法优化掉（常量折叠）
   - 将乘数改为变量而不是常量
   
   ```c
   // 不好：编译器可能优化掉
   int x = 5 * 10;  // 编译时直接计算为 50
   
   // 好：强制运行时计算
   volatile int a = 5;
   int x = a * 10;  // 生成 mul 指令
   ```

2. **乘法被优化为移位操作**
   - 当乘数是 2 的幂时，GCC 会用左移代替乘法（更快）
   - 使用非 2 的幂的乘数来强制生成 `mul` 指令
   
   ```c
   // 不好：会被优化为左移
   int x = a * 4;   // 优化为 a << 2
   int y = a * 16;  // 优化为 a << 4
   
   // 好：无法优化为移位
   int x = a * 3;   // 生成 mul 指令
   int y = a * 7;   // 生成 mul 指令
   ```

3. **代码中没有实际的乘法运算**
   - 检查你的 C 代码是否真的包含乘法运算符 `*`
   - 确保乘法操作没有被条件语句跳过

4. **使用了错误的编译标志**
   - 确保使用 `-march=rv32im`（包含 M 扩展）
   - 不要使用 `-march=rv32i`（不包含 M 扩展）
   - 检查 `codegen.sh` 中的编译命令

**验证方法**:

```bash
# 1. 检查 ELF 文件的架构属性
riscv64-unknown-elf-readelf -A cpu.elf
# 应该显示: Tag_RISCV_arch: "rv32i2p1_m2p0_zmmul1p0"

# 2. 查看完整的反汇编
cat obj.exe | less
# 在 main 函数中查找 mul 指令

# 3. 使用示例代码测试
# 将 code.c 内容替换为：
#define DATA_SIZE 100
int result = 1;
int main() {
    int i;
    for (i = 1; i <= DATA_SIZE; i++) {
        result = result * i;
    }
    return result;
}
# 然后运行 bash codegen.sh
# 应该在 obj.exe 中看到 mul 指令
```

**调试技巧**:

如果仍然看不到 `mul` 指令，尝试添加优化级别标志：

```bash
# 修改 codegen.sh 第一行，添加 -O0 禁用优化
riscv64-unknown-elf-gcc -march=rv32im -mabi=ilp32 -O0 -nostdlib -Wl,--no-check-sections -T harvard.ld start.S code.c -o cpu.elf
```

或者添加 -O2 启用优化（有时反而会生成更多 mul 指令）：

```bash
riscv64-unknown-elf-gcc -march=rv32im -mabi=ilp32 -O2 -nostdlib -Wl,--no-check-sections -T harvard.ld start.S code.c -o cpu.elf
```

---

## English

### Overview

This directory contains tools for generating RV32IM instructions. It compiles C code into RISC-V 32-bit instructions (with multiplication extension) and generates binary files that can run on Assassyn-CPU.

### Prerequisites

Before running codegen.sh, you need to install the RISC-V bare-metal cross-compilation toolchain.

#### Installation on Ubuntu/Debian

```bash
sudo apt-get update
sudo apt-get install -y gcc-riscv64-unknown-elf binutils-riscv64-unknown-elf
```

#### Other Systems

Please refer to the [RISC-V GNU Toolchain](https://github.com/riscv-collab/riscv-gnu-toolchain) repository for building from source.

### File Descriptions

- **codegen.sh**: Main compilation script that executes the complete build process
- **code.c**: C source code file (example: factorial calculation)
- **start.S**: RISC-V assembly startup code
- **harvard.ld**: Linker script (Harvard architecture, separate instruction and data)
- **cpu.elf**: Generated ELF executable file
- **icache.bin**: Instruction cache binary file
- **icache.hex**: Instruction cache hexadecimal file
- **memory.bin**: Data memory binary file
- **memory.hex**: Data memory hexadecimal file
- **obj.exe**: Disassembly file

### Usage

1. Ensure the RISC-V toolchain is installed (see "Prerequisites")

2. Edit the `code.c` file with your C code

3. Run the compilation script:
   ```bash
   bash codegen.sh
   ```

4. Check the generated files:
   ```bash
   # View disassembly
   cat obj.exe
   
   # View instruction hexadecimal
   cat icache.hex
   
   # View data hexadecimal
   cat memory.hex
   ```

### Compilation Process

The `codegen.sh` script performs the following steps:

1. **Compile and Link**
   ```bash
   riscv64-unknown-elf-gcc -march=rv32im -mabi=ilp32 -nostdlib \
       -Wl,--no-check-sections -T harvard.ld start.S code.c -o cpu.elf
   ```
   - `-march=rv32im`: Target architecture RV32IM (base ISA + multiply extension)
   - `-mabi=ilp32`: Use ILP32 ABI (int, long, pointer are all 32-bit)
   - `-nostdlib`: Don't link standard library (bare-metal environment)
   - `-T harvard.ld`: Use custom linker script

2. **Extract Text Section**
   ```bash
   riscv64-unknown-elf-objcopy -j .text -O binary cpu.elf icache.bin
   ```

3. **Extract Data Section**
   ```bash
   riscv64-unknown-elf-objcopy -j .data -j .bss -O binary cpu.elf memory.bin
   ```

4. **Generate Disassembly**
   ```bash
   riscv64-linux-gnu-objdump -D cpu.elf > obj.exe
   ```

5. **Convert to Hexadecimal Format**
   ```bash
   hexdump -v -e '1/4 "%08x" "\n"' icache.bin > icache.hex
   hexdump -v -e '1/4 "%08x" "\n"' memory.bin > memory.hex
   ```

### Verifying RV32IM Instruction Generation

To verify that M extension (multiplication) instructions are correctly generated, check the disassembly:

```bash
cat obj.exe | grep -E "mul|div|rem"
```

You should see instructions like:
- `mul` - Multiply (lower 32 bits)
- `mulh` - Multiply High Signed×Signed (upper 32 bits)
- `mulhsu` - Multiply High Signed×Unsigned (upper 32 bits)
- `mulhu` - Multiply High Unsigned×Unsigned (upper 32 bits)
- `div` - Signed Division
- `divu` - Unsigned Division
- `rem` - Signed Remainder
- `remu` - Unsigned Remainder

### Example Code

The current `code.c` contains a factorial calculation example:

```c
#define DATA_SIZE 100

int result = 1;

int main() {
    int i;
    for (i = 1; i <= DATA_SIZE; i++) {
        result = result * i;
    }
    return result;
}
```

This code will generate `mul` instructions, proving that the RV32IM extension is working.

### Troubleshooting

#### Error: `riscv64-unknown-elf-gcc: command not found`

**Cause**: RISC-V toolchain not installed

**Solution**: Follow the installation instructions in the "Prerequisites" section

#### Error: Link failure or memory overflow

**Cause**: Code or data exceeds the memory size defined in the linker script

**Solution**: 
1. Edit `harvard.ld` and increase the LENGTH of IMEM or DMEM
2. Optimize your C code to reduce memory usage

#### Issue: Compilation succeeds but no multiplication instructions generated

**Symptom**: Running `cat obj.exe | grep mul` finds no `mul` instruction

**Possible causes and solutions**:

1. **Compiler optimization eliminated multiplication**
   - GCC may optimize away constant multiplication (constant folding)
   - Change the multiplier to a variable instead of a constant
   
   ```c
   // Bad: compiler may optimize away
   int x = 5 * 10;  // Computed at compile time as 50
   
   // Good: forces runtime calculation
   volatile int a = 5;
   int x = a * 10;  // Generates mul instruction
   ```

2. **Multiplication optimized to shift operation**
   - When the multiplier is a power of 2, GCC uses left shift instead of multiplication (faster)
   - Use non-power-of-2 multipliers to force `mul` instruction generation
   
   ```c
   // Bad: optimized to left shift
   int x = a * 4;   // Optimized to a << 2
   int y = a * 16;  // Optimized to a << 4
   
   // Good: cannot be optimized to shift
   int x = a * 3;   // Generates mul instruction
   int y = a * 7;   // Generates mul instruction
   ```

3. **No actual multiplication in the code**
   - Check if your C code actually contains multiplication operator `*`
   - Ensure multiplication operation is not skipped by conditional statements

4. **Wrong compilation flags used**
   - Ensure you're using `-march=rv32im` (includes M extension)
   - Don't use `-march=rv32i` (excludes M extension)
   - Check the compile command in `codegen.sh`

**Verification methods**:

```bash
# 1. Check ELF file architecture attributes
riscv64-unknown-elf-readelf -A cpu.elf
# Should show: Tag_RISCV_arch: "rv32i2p1_m2p0_zmmul1p0"

# 2. View complete disassembly
cat obj.exe | less
# Look for mul instruction in the main function

# 3. Test with example code
# Replace code.c content with:
#define DATA_SIZE 100
int result = 1;
int main() {
    int i;
    for (i = 1; i <= DATA_SIZE; i++) {
        result = result * i;
    }
    return result;
}
# Then run bash codegen.sh
# Should see mul instruction in obj.exe
```

**Debug tips**:

If you still don't see `mul` instructions, try adding optimization level flags:

```bash
# Modify codegen.sh line 1, add -O0 to disable optimization
riscv64-unknown-elf-gcc -march=rv32im -mabi=ilp32 -O0 -nostdlib -Wl,--no-check-sections -T harvard.ld start.S code.c -o cpu.elf
```

Or add -O2 to enable optimization (sometimes generates more mul instructions):

```bash
riscv64-unknown-elf-gcc -march=rv32im -mabi=ilp32 -O2 -nostdlib -Wl,--no-check-sections -T harvard.ld start.S code.c -o cpu.elf
```
