# Assassyn CPU 初始化报告

## 目录
1. [工具脚本使用说明](#工具脚本使用说明)
2. [文件格式说明](#文件格式说明)
3. [SP（栈指针）初始化问题分析与解决方案](#sp栈指针初始化问题分析与解决方案)
4. [验证步骤](#验证步骤)

---

## 工具脚本使用说明

### 脚本位置
`main_test/generate_workloads.py`

### 功能描述
该脚本用于从二进制文件生成 dcache 和 icache 的初始化文件：
- **输入**：
  - `*_text.bin`（指令段二进制文件）
  - `*_data.bin`（数据段二进制文件）
  - 支持三个程序：0to100、multiply、vvadd
- **输出**：
  - `*.exe`（用于 icache 初始化）
  - `*.data`（用于 dcache 初始化）

### 基本用法

#### 1. 生成默认格式文件（推荐）
```bash
cd main_test
python3 generate_workloads.py
```

**输出格式**：
- 文本文件，每行一个 32-bit 十六进制数（8 位十六进制字符）
- 小端序（Little-endian）
- 自动填充到 32-bit 字对齐
- 不含 `0x` 前缀

**示例输出** (`0to100.exe` 的前几行)：
```
fe010113
00812e23
02010413
fe042423
```

#### 2. 其他用法选项

**输出原始二进制格式**（如果 main.py 需要二进制镜像）：
```bash
python3 generate_workloads.py --binary
```

**指定大端序**：
```bash
python3 generate_workloads.py --endian big
```

**指定 16-bit 字宽**：
```bash
python3 generate_workloads.py --word-size 2
```

**使用自定义输入/输出文件名**：
```bash
python3 generate_workloads.py \
    --text-in custom_text.bin \
    --data-in custom_data.bin \
    --text-out custom.exe \
    --data-out custom.data
```

**查看帮助**：
```bash
python3 generate_workloads.py --help
```

---

## 文件格式说明

### 输出格式详解

#### 文本十六进制格式（默认）
- **每行格式**：一个 32-bit 无符号整数的十六进制表示（8 个十六进制字符）
- **字节序**：小端序（Little-endian），与 RISC-V 指令编码一致
- **对齐**：自动填充 `0x00` 到 32-bit 字边界
- **换行符**：Unix 风格 (`\n`)

**示例**：
```
原始二进制（16 字节）：
  13 01 01 fe 23 2e 81 00 13 04 01 02 23 24 04 fe

转换为文本格式（4 行）：
  fe010113  <- 字节 0-3：小端序表示 0xfe010113
  00812e23  <- 字节 4-7：小端序表示 0x00812e23
  02010413  <- 字节 8-11：小端序表示 0x02010413
  fe042423  <- 字节 12-15：小端序表示 0xfe042423
```

#### 二进制格式（`--binary` 选项）
- 直接复制原始二进制文件
- 适用于硬件直接映射内存镜像的场景

### 与 main.py 的集成

根据 `src/main.py` 的代码分析：

```python
# main.py 第 103-106 行
dcache = SRAM(width=32, depth=1 << depth_log, init_file=data_path)
icache = SRAM(width=32, depth=1 << depth_log, init_file=ins_path)
```

`SRAM` 类来自 `assassyn.frontend` 模块，其 `init_file` 参数通常支持：
- **Verilog `$readmemh` 格式**：文本文件，每行一个十六进制数（不带 `0x` 前缀）
- **Verilog `$readmemb` 格式**：文本文件，每行一个二进制数

**本工具默认输出格式与 `$readmemh` 兼容**，适用于大多数 FPGA/仿真器工具链。

---

## SP（栈指针）初始化问题分析与解决方案

### 问题描述

在运行 `accumulate` 程序（累加 0 到 100）时，如果栈指针（SP，x2 寄存器）未正确初始化，会导致以下问题：

1. **栈操作异常**：
   - 函数调用时的 `push`/`pop` 操作访问非法内存地址
   - 局部变量存储位置不可预测
   
2. **程序崩溃或错误结果**：
   - 栈溢出或下溢
   - 数据被意外覆盖
   - 寄存器保存/恢复失败

### 问题根源

从反汇编可以看到，程序使用标准的 RISC-V 函数调用约定：

```assembly
fe010113    # addi sp, sp, -32      ; 分配栈帧（需要 SP 已初始化）
00812e23    # sw   s0, 28(sp)       ; 保存寄存器到栈
02010413    # addi s0, sp, 32       ; 设置帧指针
```

**第一条指令就需要有效的 SP 值**，但硬件复位后所有寄存器默认为 0，导致栈操作访问地址 0xFFFFFFE0（0x00000000 - 32），这通常不是合法的内存区域。

### 解决方案

根据 Assassyn CPU 的架构特点，提供以下三种解决方案（**按推荐优先级排序**）：

---

#### 方案 1：在启动代码中初始化 SP（推荐）

**原理**：在程序入口点添加启动代码，在执行主程序前设置 SP。

**实施步骤**：

1. **修改链接脚本和启动汇编**（如果有源码访问权限）：
   ```assembly
   # boot.S - 启动代码
   .section .text.init
   .global _start
   _start:
       # 设置栈指针到 RAM 顶部（假设 RAM 为 0x80000000 - 0x80010000，64KB）
       li sp, 0x80010000       # sp = RAM 基地址 + RAM 大小
       
       # 跳转到主程序
       j main
   ```

2. **重新编译程序**，确保 `_start` 是入口点：
   ```bash
   riscv32-unknown-elf-gcc -T link.ld boot.S main.c -o program.elf
   riscv32-unknown-elf-objcopy -O binary program.elf program.bin
   ```

3. **更新二进制文件**，使其包含启动代码。

**优点**：
- ✅ 符合标准实践，程序自包含
- ✅ 不依赖外部仿真器配置
- ✅ 可移植性好

**缺点**：
- ❌ 需要修改原始程序（但用户要求不改 main.py，未禁止改程序本身）

---

#### 方案 2：在仿真器/硬件初始化时设置寄存器（次优）

**原理**：在 CPU 启动前通过外部配置初始化寄存器状态。

**实施步骤**：

1. **检查 Assassyn 框架是否支持初始寄存器配置**：
   - 查看 `assassyn.backend.elaborate` 或 `assassyn.utils.run_simulator` 是否接受初始寄存器状态参数
   - 查找配置文件（如 `.toml` 或 `.json`）中的寄存器初始化选项

2. **如果支持，创建寄存器初始化配置文件**（假设格式）：
   ```json
   // main_test/init_regs.json
   {
       "x2": "0x80010000",  // SP: 栈顶地址
       "x3": "0x00000000",  // GP: 全局指针（如果需要）
       "x8": "0x00000000"   // FP: 帧指针初始化为 0
   }
   ```

3. **修改 main.py 调用方式**（注意：这违反了"不修改 main.py"的约束）：
   ```python
   # 如果框架支持，在 utils.run_simulator 调用时传递初始状态
   raw = utils.run_simulator(
       binary_path=binary_path,
       init_regs="main_test/init_regs.json"  # 假设支持此参数
   )
   ```

4. **替代方案**：如果不能改 main.py，可以：
   - 在生成的 Rust 仿真器代码中手动修改初始化逻辑（在 `.workspace` 目录中）
   - 使用调试器（如 GDB）设置断点并在程序启动前修改寄存器

**优点**：
- ✅ 不修改程序代码本身
- ✅ 灵活，适合快速测试

**缺点**：
- ❌ 依赖外部配置，可移植性差
- ❌ 可能需要修改 main.py 或生成的代码（违反约束）

---

#### 方案 3：在 dcache 初始化文件中预设栈数据（备选）

**原理**：利用 `.data` 文件预先填充栈区域，避免非法访问。

**实施步骤**：

1. **确定内存布局**：
   - 假设 dcache 地址空间为 0x00000000 - 0x0000FFFF（64KB）
   - 将栈区域设在高地址，如 0x0000F000 - 0x0000FFFF（4KB）

2. **修改 SP 初始化方案**：
   - 在程序中将 SP 初始化为 `0x0000F000`（栈向下增长）
   - 或在 dcache 的高地址预填充全零（避免访问未初始化内存）

3. **生成包含栈区域的 `.data` 文件**：
   ```python
   # 在 generate_workloads.py 中添加选项
   python3 generate_workloads.py --stack-base 0xF000 --stack-size 4096
   ```

   脚本修改示例：
   ```python
   # 在输出 .data 时，填充高地址区域
   with open(args.data_out, 'a') as f:
       # 填充到栈基地址
       for addr in range(data_end, stack_base, word_size):
           f.write("00000000\n")
   ```

**优点**：
- ✅ 确保栈区域可访问

**缺点**：
- ❌ 仍需程序中初始化 SP 值
- ❌ 浪费初始化文件空间
- ❌ 不是标准做法

---

### 推荐的实施方案

**综合考虑用户约束（不修改 main.py）和最佳实践，推荐采用方案 1**：

1. **添加启动代码到程序**：
   - 在源程序中添加 `_start` 标签
   - 设置 SP 为 `0x80010000`（或根据实际内存映射调整）
   - 跳转到原始的主函数

2. **确定 SP 初始值**：
   根据 `src/main.py` 中的 SRAM 配置：
   ```python
   dcache = SRAM(width=32, depth=1 << 16)  # 64K words = 256KB
   ```
   
   推荐 SP 值：
   - **选项 A**：`0x00010000`（dcache 顶部，如果 dcache 从地址 0 开始）
   - **选项 B**：`0x80010000`（如果使用标准 RISC-V 内存映射，RAM 从 0x80000000 开始）
   
   **建议与硬件实际内存映射对齐**，可以在 Assassyn CPU 文档或测试中确认。

3. **验证 SP 值**：
   - 运行仿真器，检查 SP 是否在合法范围内
   - 确认栈操作（`sw`/`lw` 指令）不触发访问异常

---

### 具体代码示例

假设使用 RISC-V 汇编和 C 混合编程：

```c
// accumulate.c
int accumulate(int n) {
    int sum = 0;
    for (int i = 1; i <= n; i++) {
        sum += i;
    }
    return sum;
}

int main() {
    int result = accumulate(100);
    return result;
}
```

```assembly
# boot.S
.section .text.init
.global _start

_start:
    # 初始化栈指针（假设 RAM 为 0x80000000 - 0x80010000）
    li sp, 0x80010000
    
    # 初始化全局指针（如果需要）
    # la gp, __global_pointer$
    
    # 跳转到 C 运行时启动
    call main
    
    # 程序结束后进入死循环
_halt:
    j _halt
```

**编译命令**：
```bash
riscv32-unknown-elf-gcc -march=rv32i -mabi=ilp32 -nostdlib -T link.ld \
    -o program.elf boot.S accumulate.c

riscv32-unknown-elf-objcopy -O binary -j .text program.elf program_text.bin
riscv32-unknown-elf-objcopy -O binary -j .data program.elf program_data.bin
```

**链接脚本示例** (`link.ld`)：
```ld
MEMORY {
    RAM : ORIGIN = 0x80000000, LENGTH = 64K
}

SECTIONS {
    .text : {
        *(.text.init)   /* 启动代码放在最前面 */
        *(.text)
    } > RAM
    
    .data : {
        *(.data)
    } > RAM
}
```

---

## 验证步骤

### 1. 生成初始化文件

```bash
cd main_test
python3 generate_workloads.py
```

**预期输出**：
```
============================================================
批量生成工作负载文件
============================================================

脚本目录: /home/runner/work/Assassyn-CPU/Assassyn-CPU/main_test
输出目录: ../workloads

发现 3 个工作负载需要生成

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[1/3] 正在生成: 0to100
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[SUCCESS] Wrote 22 words to ../workloads/0to100.exe
          Format: 32-bit hex, little-endian
[INFO] Input file 0to100_data.bin is empty, created empty ../workloads/0to100.data
✅ 成功生成 0to100
   → ../workloads/0to100.exe (22 words)
   → ../workloads/0to100.data (0 words)

成功: 3 / 3
============================================================
✅ 生成完成！
============================================================
```

### 2. 检查文件内容

```bash
# 查看指令文件前几行
head -5 ../workloads/0to100.exe
```

**预期输出**（示例）：
```
fe010113
00812e23
02010413
fe042423
00100793
```

### 3. 验证字节序正确性

```bash
# 对比原始二进制和生成的十六进制
xxd -l 16 0to100_text.bin
head -4 ../workloads/0to100.exe
```

**验证方法**：
- 原始字节 `13 01 01 fe` 应对应十六进制行 `fe010113`（小端序）
- 确认每 4 个字节形成一个 32-bit 字

### 4. 在 workloads 目录中使用

将生成的文件复制到 `workloads` 目录（或 main.py 期望的位置）：

```bash
# 如果 workloads 目录不存在，创建它
mkdir -p ../workloads

# 文件已自动生成到 workloads 目录
# 无需手动复制
```

### 5. 运行仿真器

```bash
cd ../src
python3 main.py
```

**检查点**：
1. **文件加载成功**：
   ```
   [*] Source Dir: /path/to/workloads
   [*] Data Path: /path/to/.workspace/workload.data
   [*] Ins Path: /path/to/.workspace/workload.exe
     -> Copied Instruction: 0to100.exe ==> workload_ins.exe
     -> Copied Memory Data: 0to100.data ==> workload_mem.exe
   ```

2. **仿真运行无错误**：
   - 无非法内存访问
   - 无栈溢出/下溢
   - 程序正常退出

3. **结果验证**：
   - 累加 0 到 100 的正确结果为 **5050**
   - 检查寄存器 x10（a0，返回值寄存器）= 5050 = 0x13BA

**示例成功输出**：
```
🏃 Running simulation (Direct Output Mode)...
Cycle 1000: PC = 0x80000050
Register x10 (a0) = 0x000013BA (5050)
Program halted successfully.
```

### 6. 调试 SP 初始化问题

如果遇到栈相关错误：

```bash
# 使用 objdump 反汇编检查程序
riscv32-unknown-elf-objdump -d program.elf > program.asm

# 确认第一条指令是否为 SP 初始化
head -20 program.asm
```

**检查第一条指令**：
- ✅ 正确：`li sp, 0x80010000` 或 `addi sp, x0, ...`
- ❌ 错误：直接是 `addi sp, sp, -32`（SP 未初始化）

如果 SP 未初始化，回到 [方案 1](#方案-1在启动代码中初始化-sp推荐) 添加启动代码。

---

## 附录

### A. 内存映射参考

根据 Assassyn CPU 的配置（`depth_log=16`）：

| 区域    | 起始地址   | 大小      | 说明                |
|---------|-----------|-----------|---------------------|
| icache  | 0x00000000 | 256KB     | 指令缓存（64K words）|
| dcache  | 0x00000000 | 256KB     | 数据缓存（64K words）|
| 栈建议  | 0x0003F000 | 向下增长  | 栈顶从高地址开始     |

**注意**：实际内存映射可能不同，请根据硬件文档调整。

### B. RISC-V 寄存器约定

| 寄存器 | ABI 名称 | 用途                  | 调用者/被调用者保存 |
|--------|----------|-----------------------|--------------------|
| x0     | zero     | 硬连线为 0            | -                  |
| x1     | ra       | 返回地址              | 调用者             |
| x2     | sp       | **栈指针**            | 被调用者           |
| x3     | gp       | 全局指针              | -                  |
| x4     | tp       | 线程指针              | -                  |
| x5-x7  | t0-t2    | 临时寄存器            | 调用者             |
| x8-x9  | s0-s1    | 保存寄存器/帧指针     | 被调用者           |
| x10-x17| a0-a7    | 函数参数/返回值       | 调用者             |

**SP（x2）必须在第一条指令执行前初始化**，否则任何栈操作都会失败。

### C. 相关工具和文档

- **RISC-V 规范**：https://riscv.org/specifications/
- **GNU RISC-V 工具链**：https://github.com/riscv-collab/riscv-gnu-toolchain
- **Assassyn 框架文档**：`docs/Assassyn.md`
- **本项目仓库**：https://github.com/konpaku-ming/Assassyn-CPU

---

## 总结

1. **使用 `generate_workloads.py` 生成初始化文件**，默认格式与 Verilog `$readmemh` 兼容。
2. **解决 SP 初始化问题的最佳方案**：在程序启动代码中显式设置 SP 为 RAM 顶部地址。
3. **验证步骤**：确保文件格式正确，程序能正确加载并运行 `accumulate` 测试。

如有疑问或需要进一步调整，请参考本报告的各部分详细说明。
