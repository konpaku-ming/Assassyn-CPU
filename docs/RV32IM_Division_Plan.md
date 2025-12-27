# RV32IM 除法与取模指令实现计划书

## 1. 项目概述

本计划书旨在详细说明如何在 Assassyn CPU 中实现 RV32IM 指令集扩展中的除法（DIV）和取模（REM）指令。我们将使用 SRT-4 除法算法，参考 `SRT4/` 目录下已有的 Verilog 实现，并将其集成到现有的流水线架构中。

### 1.1 目标指令

需要实现的 RV32IM 除法与取模指令共 4 条：

| 指令 | 编码 | 功能描述 |
|------|------|---------|
| `DIV` | opcode=0x33, funct3=0x4, funct7=0x01 | 有符号除法：rd = rs1 / rs2 (商) |
| `DIVU` | opcode=0x33, funct3=0x5, funct7=0x01 | 无符号除法：rd = rs1 / rs2 (商) |
| `REM` | opcode=0x33, funct3=0x6, funct7=0x01 | 有符号取模：rd = rs1 % rs2 (余数) |
| `REMU` | opcode=0x33, funct3=0x7, funct7=0x01 | 无符号取模：rd = rs1 % rs2 (余数) |

所有指令均为 R-Type 格式，与 RV32I 基本指令共享 opcode（0b0110011），通过 funct7=0x01 与基本算术指令区分。

### 1.2 特殊情况处理

根据 RISC-V 规范，除法指令需要处理以下特殊情况：

| 条件 | DIV | DIVU | REM | REMU |
|------|-----|------|-----|------|
| 除数为 0 | -1 | 2³²-1 | 被除数 | 被除数 |
| 有符号溢出 (-2³¹ / -1) | -2³¹ | N/A | 0 | N/A |

## 2. SRT-4 除法器分析

### 2.1 SRT-4 算法原理

SRT-4 是一种高基数除法算法，每个时钟周期计算 2 位商（基数 r=4）。相比传统的 SRT-2（每周期 1 位），SRT-4 能够减少约一半的迭代次数。

**核心特点：**
- **基数**：r = 4，每次迭代产生商位 q ∈ {-2, -1, 0, 1, 2}
- **冗余表示**：使用冗余商表示允许快速商选择
- **查找表驱动**：通过余数的高位和除数的高位快速选择下一个商位
- **迭代次数**：对于 32 位除法，需要 16 次迭代（32/2 = 16）

### 2.2 现有 Verilog 实现分析

位于 `SRT4/SRT4.v` 的除法器具有以下特征：

#### 2.2.1 接口定义
```verilog
module SRT4 #(parameter WID=8) (
    input           clk,
    input           rst,
    input[WID-1:0]  dividend,     // 被除数
    input[WID-1:0]  divisor,      // 除数
    input           sign,         // 1=有符号, 0=无符号
    input           valid,        // 启动信号
    output          ready,        // 完成信号
    output[WID-1:0] quotient,     // 商
    output[WID-1:0] remainder,    // 余数
    output          error         // 除数为0错误
);
```

#### 2.2.2 状态机设计
除法器采用有限状态机（FSM）控制：
- **IDLE**：等待启动信号 `valid`
- **DIV_PRE**：预处理阶段（1 周期）
- **DIV_WORKING**：迭代计算（WID/2 周期，对于 32 位是 16 周期）
- **DIV_END**：后处理与结果调整（1 周期）
- **DIV_1**：除数为 1 的快速路径（1 周期）
- **DIV_ERROR**：除数为 0 的错误处理（1 周期）

总延迟：**正常情况下 18 个周期**（1 预处理 + 16 迭代 + 1 后处理）

#### 2.2.3 关键模块

1. **find_1.v**：前导 1 检测器
   - 功能：找到除数的最高有效位位置
   - 用途：对齐除数，减少迭代次数

2. **q_sel.v**：商选择逻辑
   - 功能：基于部分余数和除数选择下一个商位 q ∈ {-2, -1, 0, 1, 2}
   - 实现：使用预计算查找表（PLA 逻辑）

3. **Wallace Tree 加法器**（隐含）：
   - 在每次迭代中计算：`新余数 = 旧余数 * 4 - q * 除数`

### 2.3 移植到 Assassyn 的考虑

由于 Assassyn 是高级硬件描述语言（Python DSL），而 SRT4 是 Verilog 实现，有以下两种移植策略：

**策略 A：直接实例化 Verilog 模块（推荐）**
- 优点：复用已验证的实现，减少错误
- 缺点：需要 Assassyn 支持外部 Verilog 模块实例化
- 实现：使用 `ExternalModule` 或类似机制

**策略 B：用 Assassyn/Python 重写**
- 优点：完全使用 Assassyn 语言，便于调试
- 缺点：需要重新实现和验证，工作量大
- 实现：参考 `multiplier.py` 的实现风格

**本计划采用策略 A**，通过外部模块实例化的方式集成 SRT4 除法器。

## 3. 流水线集成方案

### 3.1 与现有乘法器的对比

参考 `src/multiplier.py` 中的 `WallaceTreeMul` 实现：
- **乘法器**：3 级流水线（M1, M2, M3），3 周期延迟
- **除法器**：单阶段多周期，约 18 周期延迟

由于除法器延迟远长于乘法器，需要采用不同的流水线策略。

### 3.2 除法器集成架构

#### 3.2.1 多周期执行单元

除法器作为**独立的多周期功能单元**集成到 EX 阶段：

```
EX Stage:
  ├── ALU (组合逻辑，1 周期)
  ├── Multiplier (流水线，3 周期)
  └── Divider (多周期，~18 周期)  ← 新增
```

#### 3.2.2 流水线停顿机制

当除法指令进入 EX 阶段时：
1. 除法器启动（valid 信号置高）
2. **流水线全局停顿**（stall IF/ID/EX）
3. 等待除法器完成（ready 信号置高）
4. 读取结果并写入寄存器
5. 解除停顿，继续执行

**停顿控制逻辑**：
```python
# 在 execution.py 中
divider_busy = divider.is_busy()  # 除法器正在工作
stall_signal = divider_busy       # 停顿整个流水线
```

#### 3.2.3 与旁路网络的交互

除法结果需要支持旁路转发：
- **EX-MEM 旁路**：除法结果在完成周期可以旁路到下一条指令
- **MEM-WB 旁路**：除法结果写回后可旁路

这与乘法器的旁路机制一致，无需额外修改。

### 3.3 性能影响分析

#### 3.3.1 延迟
- **除法/取模指令**：~18 周期（最坏情况）
- **其他指令**：受除法指令阻塞，等待除法完成

#### 3.3.2 吞吐量
- 除法期间流水线完全停顿，CPI（每指令周期数）显著增加
- 对于除法密集型程序，性能影响较大

#### 3.3.3 优化方向（可选）
1. **早期完成检测**：某些情况下（如除数为 1）可以更早完成
2. **专用除法队列**：允许除法在后台执行，流水线继续（out-of-order 执行）
3. **多周期 ALU**：将除法器与其他多周期指令共享控制逻辑

**本期实现：采用最简单的全局停顿方案**

## 4. 实现步骤

### 4.1 阶段一：指令表更新

**文件**：`src/instruction_table.py`

在 `rv32i_table` 中添加 4 条除法/取模指令：

```python
# --- M Extension (Division & Remainder) ---
# 所有除法指令共享 OP_R_TYPE (0b0110011), funct7=0x01

('div', OP_R_TYPE, 0x4, 0x01, ImmType.R, ALUOp.DIV, 
 RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
 MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH),

('divu', OP_R_TYPE, 0x5, 0x01, ImmType.R, ALUOp.DIVU, 
 RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
 MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH),

('rem', OP_R_TYPE, 0x6, 0x01, ImmType.R, ALUOp.REM, 
 RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
 MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH),

('remu', OP_R_TYPE, 0x7, 0x01, ImmType.R, ALUOp.REMU, 
 RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
 MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH),
```

### 4.2 阶段二：ALU 操作码扩展

**文件**：`src/control_signals.py`

在 `ALUOp` 枚举中添加除法操作：

```python
class ALUOp(Enum):
    # ... 现有操作码 ...
    MUL    = 12  # 已存在
    MULH   = 13
    MULHSU = 14
    MULHU  = 15
    DIV    = 16  # 新增
    DIVU   = 17
    REM    = 18
    REMU   = 19
```

### 4.3 阶段三：创建除法器模块

**文件**：`src/divider.py`（新建）

#### 4.3.1 模块封装

创建 `SRT4Divider` 类，封装 Verilog 除法器：

```python
"""
SRT-4 Divider Module for RV32IM Division Instructions

This module wraps the SRT-4 divider implemented in Verilog (SRT4/SRT4.v)
and provides a Python interface compatible with the Assassyn CPU pipeline.
"""

from assassyn.frontend import *

class SRT4Divider:
    """
    Wrapper class for SRT-4 32-bit divider.
    
    The divider is a multi-cycle functional unit that takes ~18 cycles:
    - 1 cycle: Preprocessing (alignment)
    - 16 cycles: Iterative calculation (2 bits per cycle)
    - 1 cycle: Post-processing (sign correction)
    
    Pipeline Integration:
    - When a division instruction enters EX stage, the divider is started
    - The pipeline stalls (IF/ID/EX) until divider completes
    - Result is written back to register file through normal WB path
    """
    
    def __init__(self):
        # Control and status registers
        self.busy = RegArray(Bits(1), 1, initializer=[0])
        self.start = RegArray(Bits(1), 1, initializer=[0])
        
        # Input operands
        self.dividend = RegArray(Bits(32), 1, initializer=[0])
        self.divisor = RegArray(Bits(32), 1, initializer=[0])
        self.is_signed = RegArray(Bits(1), 1, initializer=[0])
        self.is_rem = RegArray(Bits(1), 1, initializer=[0])  # 1=remainder, 0=quotient
        
        # Output results
        self.result = RegArray(Bits(32), 1, initializer=[0])
        self.ready = RegArray(Bits(1), 1, initializer=[0])
        self.error = RegArray(Bits(1), 1, initializer=[0])  # Division by zero
        
        # TODO: Instantiate Verilog module or implement in Python
        # Option A: self.srt4_instance = ExternalModule("SRT4", ...)
        # Option B: Implement SRT-4 algorithm in Python/Assassyn
    
    def is_busy(self):
        """Check if divider is currently processing"""
        return self.busy[0]
    
    def start_divide(self, dividend, divisor, is_signed, is_rem):
        """
        Start a division operation.
        
        Args:
            dividend: 32-bit dividend (rs1)
            divisor: 32-bit divisor (rs2)
            is_signed: 1 for signed (DIV/REM), 0 for unsigned (DIVU/REMU)
            is_rem: 1 to return remainder, 0 to return quotient
        """
        self.dividend[0] = dividend
        self.divisor[0] = divisor
        self.is_signed[0] = is_signed
        self.is_rem[0] = is_rem
        self.start[0] = Bits(1)(1)
        self.busy[0] = Bits(1)(1)
        
        log("Divider: Start {} division, dividend=0x{:x}, divisor=0x{:x}",
            "signed" if is_signed else "unsigned",
            dividend,
            divisor)
    
    def tick(self):
        """
        Execute one cycle of division.
        Should be called every clock cycle when busy.
        """
        with Condition(self.busy[0] == Bits(1)(1)):
            # TODO: Drive SRT4 module or implement algorithm
            # For now, placeholder logic
            pass
    
    def get_result_if_ready(self):
        """
        Get result if division is complete.
        Returns: (ready, result, error)
        """
        return (self.ready[0], self.result[0], self.error[0])
    
    def clear_result(self):
        """Clear result and reset busy flag"""
        self.ready[0] = Bits(1)(0)
        self.busy[0] = Bits(1)(0)
        self.start[0] = Bits(1)(0)
```

#### 4.3.2 特殊情况处理

在 `tick()` 方法中添加边界情况检测：

```python
def tick(self):
    with Condition(self.busy[0] == Bits(1)(1)):
        # Check for division by zero
        div_by_zero = (self.divisor[0] == Bits(32)(0))
        
        # Check for signed overflow: (-2^31) / (-1)
        min_int = Bits(32)(0x80000000)
        neg_one = Bits(32)(0xFFFFFFFF)
        signed_overflow = (self.is_signed[0] == Bits(1)(1)) & \
                         (self.dividend[0] == min_int) & \
                         (self.divisor[0] == neg_one)
        
        # Handle special cases
        with Condition(div_by_zero):
            # Division by zero
            quotient_on_div0 = self.is_signed[0].select(
                Bits(32)(0xFFFFFFFF),  # -1 for signed
                Bits(32)(0xFFFFFFFF)   # 2^32-1 for unsigned (same value)
            )
            result = self.is_rem[0].select(
                self.dividend[0],      # Remainder = dividend
                quotient_on_div0       # Quotient = -1 or 2^32-1
            )
            self.result[0] = result
            self.error[0] = Bits(1)(1)
            self.ready[0] = Bits(1)(1)
            self.busy[0] = Bits(1)(0)
            log("Divider: Division by zero detected")
        
        with ElseCondition(signed_overflow):
            # Signed overflow: -2^31 / -1
            result = self.is_rem[0].select(
                Bits(32)(0),           # Remainder = 0
                Bits(32)(0x80000000)   # Quotient = -2^31
            )
            self.result[0] = result
            self.ready[0] = Bits(1)(1)
            self.busy[0] = Bits(1)(0)
            log("Divider: Signed overflow detected")
        
        with ElseCondition():
            # Normal division using SRT-4
            # TODO: Call SRT4 module or implement algorithm
            pass
```

### 4.4 阶段四：集成到 EX 阶段

**文件**：`src/execution.py`

#### 4.4.1 实例化除法器

在 `Execution` 类的 `__init__` 方法中：

```python
def __init__(self):
    super().__init__(...)
    
    # Existing multiplier
    self.multiplier = WallaceTreeMul()
    
    # New divider
    self.divider = SRT4Divider()  # 新增
```

#### 4.4.2 添加除法指令检测

在 `build()` 方法的 ALU 操作分发逻辑中：

```python
# Decode ALU operation
is_mul_op = (alu_func == ALUOp.MUL) | (alu_func == ALUOp.MULH) | \
            (alu_func == ALUOp.MULHSU) | (alu_func == ALUOp.MULHU)

is_div_op = (alu_func == ALUOp.DIV) | (alu_func == ALUOp.DIVU) | \
            (alu_func == ALUOp.REM) | (alu_func == ALUOp.REMU)  # 新增

# Operand selection
op1 = ...  # 根据 op1_sel 选择
op2 = ...  # 根据 op2_sel 选择

# Division operation
with Condition(is_div_op):
    is_signed = (alu_func == ALUOp.DIV) | (alu_func == ALUOp.REM)
    is_rem = (alu_func == ALUOp.REM) | (alu_func == ALUOp.REMU)
    
    # Start divider if not already busy
    with Condition(~self.divider.is_busy()):
        self.divider.start_divide(op1, op2, is_signed, is_rem)
```

#### 4.4.3 添加流水线停顿逻辑

在 `build()` 方法中生成停顿信号：

```python
# Stall detection
mul_stall = self.multiplier.is_busy()
div_stall = self.divider.is_busy()  # 新增
stall = mul_stall | div_stall       # 修改

# Send stall signal to IF/ID stages
# (需要在 top.py 中连接停顿信号到各级)
```

#### 4.4.4 结果选择逻辑

在结果多路选择器中添加除法结果：

```python
# Get divider result
(div_ready, div_result, div_error) = self.divider.get_result_if_ready()

# Result selection
alu_result = ...  # 现有 ALU 结果

with Condition(div_ready):
    final_result = div_result
    self.divider.clear_result()
with Condition(mul_ready):
    final_result = mul_result
    self.multiplier.clear_result()
with ElseCondition():
    final_result = alu_result

# Forward to MEM stage
mem_module.xxx.push(final_result)
```

### 4.5 阶段五：顶层停顿信号连接

**文件**：`src/main.py` 或 `src/top.py`

将 EX 阶段的停顿信号连接到 IF 和 ID 阶段：

```python
# In top-level build
ex_stall = execution.get_stall_signal()

# Connect to IF stage
fetch.build(..., stall=ex_stall)

# Connect to ID stage
decode.build(..., stall=ex_stall)
```

确保停顿信号能够阻止：
- IF：停止取指，保持 PC 不变
- ID：停止译码，保持 ID-EX 流水线寄存器不更新
- EX：保持当前操作继续执行

## 5. 测试方案

### 5.1 单元测试

**文件**：`tests/test_divider.py`（新建）

#### 5.1.1 基本功能测试

```python
def test_div_basic():
    """Test basic signed division"""
    # 10 / 3 = 3
    # 10 % 3 = 1
    pass

def test_divu_basic():
    """Test basic unsigned division"""
    # 0xFFFFFFFF / 2 = 0x7FFFFFFF
    pass

def test_div_by_zero():
    """Test division by zero returns correct values"""
    # DIV: should return -1
    # DIVU: should return 0xFFFFFFFF
    # REM/REMU: should return dividend
    pass

def test_signed_overflow():
    """Test signed overflow: (-2^31) / (-1)"""
    # DIV: should return -2^31 (no wrap)
    # REM: should return 0
    pass

def test_negative_numbers():
    """Test division with negative numbers"""
    # -10 / 3 = -3 (round toward zero)
    # -10 % 3 = -1
    # 10 / -3 = -3
    # 10 % -3 = 1
    pass
```

#### 5.1.2 边界情况测试

```python
def test_edge_cases():
    """Test edge cases"""
    # Division by 1
    # Division by -1
    # Division by itself
    # 0 / x = 0
    pass
```

### 5.2 集成测试

**文件**：`tests/test_integration.py`（修改）

添加使用除法指令的汇编程序测试：

```assembly
# Test program: division_test.s
.text
main:
    li a0, 100          # Load 100
    li a1, 7            # Load 7
    div a2, a0, a1      # a2 = 100 / 7 = 14
    rem a3, a0, a1      # a3 = 100 % 7 = 2
    
    li a0, -100         # Load -100
    li a1, 7            # Load 7
    div a4, a0, a1      # a4 = -100 / 7 = -14
    rem a5, a0, a1      # a5 = -100 % 7 = -2
    
    # Test division by zero
    li a0, 42
    li a1, 0
    div a6, a0, a1      # a6 = -1 (error case)
    rem a7, a0, a1      # a7 = 42 (error case)
    
    # Test signed overflow
    lui a0, 0x80000     # Load -2^31
    li a1, -1
    div t0, a0, a1      # t0 = -2^31 (overflow)
    rem t1, a0, a1      # t1 = 0
    
    ecall               # Exit
```

### 5.3 性能测试

**文件**：`tests/test_performance.py`（可选）

测量除法指令对 CPI 的影响：

```python
def test_division_latency():
    """Measure division instruction latency"""
    # Run program with many divisions
    # Count total cycles
    # Calculate CPI
    pass
```

## 6. 文档更新

### 6.1 模块文档

**文件**：`docs/Module/EX.md`（修改）

添加除法器相关章节：

- 除法器架构说明
- 流水线停顿机制
- 延迟和性能影响

### 6.2 指令集文档

如果存在指令集文档，需要添加 DIV/DIVU/REM/REMU 指令说明。

## 7. 实现优先级与时间估算

### 7.1 最小可行实现（MVP）

**目标**：实现基本功能，通过简单测试

1. **Phase 1**：指令表和控制信号（0.5 天）
   - 更新 `instruction_table.py`
   - 更新 `control_signals.py`

2. **Phase 2**：除法器 Python 实现（2 天）
   - 创建 `divider.py`
   - 实现简化版 SRT-4 或使用 Python 除法（功能验证）
   - 特殊情况处理

3. **Phase 3**：EX 阶段集成（1 天）
   - 修改 `execution.py`
   - 添加除法指令分发
   - 实现停顿逻辑

4. **Phase 4**：停顿信号传播（0.5 天）
   - 修改 `main.py`/`top.py`
   - 连接 IF/ID 停顿

5. **Phase 5**：基础测试（1 天）
   - 编写单元测试
   - 简单集成测试

**MVP 总计**：约 5 天

### 7.2 完整实现

在 MVP 基础上：

6. **Phase 6**：Verilog 集成（2 天）
   - 实例化 `SRT4.v` 模块
   - 如需支持外部模块，可能需要扩展 Assassyn 框架

7. **Phase 7**：完整测试（2 天）
   - 边界情况测试
   - 性能测试
   - 集成测试程序

8. **Phase 8**：文档与优化（1 天）
   - 更新文档
   - 代码审查与优化

**完整实现总计**：约 10 天

### 7.3 可选增强

- **性能优化**：早期完成检测，减少简单除法的延迟
- **并行执行**：允许除法在后台执行（复杂度高）
- **除法队列**：支持多个除法同时在队列中（out-of-order）

## 8. 风险与挑战

### 8.1 技术风险

1. **Verilog 集成**：Assassyn 可能不原生支持外部 Verilog 模块
   - **缓解**：先用 Python 实现功能验证，后续优化性能

2. **停顿信号传播**：流水线停顿可能影响分支预测、旁路等复杂逻辑
   - **缓解**：仔细测试停顿期间的流水线状态

3. **时序问题**：除法器延迟可能影响时钟频率
   - **缓解**：SRT-4 已经是分级设计，每级逻辑深度较小

### 8.2 验证风险

1. **边界情况覆盖不全**：除法有很多特殊情况
   - **缓解**：参考 RISC-V 官方测试套件（riscv-tests）

2. **有符号运算正确性**：符号处理容易出错
   - **缓解**：详细的单元测试，对比参考实现

### 8.3 性能风险

1. **CPI 增加显著**：18 周期延迟会严重影响性能
   - **缓解**：这是设计权衡，短期接受，长期可优化

## 9. 后续工作

### 9.1 短期（本期完成）

- 实现所有 4 条除法/取模指令
- 通过功能测试
- 基本文档

### 9.2 中期（下一迭代）

- 优化除法器性能（早期完成检测）
- 完善测试覆盖率
- 性能基准测试

### 9.3 长期（未来规划）

- 研究并行除法执行（乱序执行）
- 支持浮点除法（RV32F）
- 硬件加速除法（专用电路）

## 10. 参考资料

### 10.1 RISC-V 规范

- RISC-V Unprivileged Specification (版本 20191213)
  - 第 7 章："M" Standard Extension for Integer Multiplication and Division
  - 第 7.2 节：Division Operations

### 10.2 SRT 除法算法

- Ercegovac, M. D., & Lang, T. (2004). *Digital Arithmetic*. Morgan Kaufmann.
  - 第 5 章：High-Radix Division
- Oberman, S. F., & Flynn, M. J. (1997). "Design Issues in Division and Other Floating-Point Operations". *IEEE Transactions on Computers*.

### 10.3 现有实现参考

- `SRT4/SRT4.v`：本项目已有的 SRT-4 除法器实现
- `src/multiplier.py`：乘法器多周期流水线实现
- `src/execution.py`：EX 阶段现有架构

### 10.4 测试资源

- RISC-V Tests Repository: https://github.com/riscv/riscv-tests
  - `isa/rv32um-p-div.S`：除法指令测试
  - `isa/rv32um-p-divu.S`：无符号除法测试
  - `isa/rv32um-p-rem.S`：取模指令测试
  - `isa/rv32um-p-remu.S`：无符号取模测试

---

## 附录 A：指令编码详细信息

### A.1 R-Type 指令格式

```
 31        25 24    20 19    15 14     12 11     7 6      0
+------------+--------+--------+---------+--------+--------+
|   funct7   |   rs2  |   rs1  | funct3  |   rd   | opcode |
+------------+--------+--------+---------+--------+--------+
```

### A.2 除法指令编码

| 指令 | opcode | funct3 | funct7 |
|------|--------|--------|--------|
| DIV  | 0110011 | 100 | 0000001 |
| DIVU | 0110011 | 101 | 0000001 |
| REM  | 0110011 | 110 | 0000001 |
| REMU | 0110011 | 111 | 0000001 |

### A.3 机器码示例

```assembly
div  x1, x2, x3     # 0x023100B3
divu x4, x5, x6     # 0x026252B3
rem  x7, x8, x9     # 0x029463B3
remu x10, x11, x12  # 0x02C5F533
```

---

## 附录 B：RISC-V 除法语义

### B.1 有符号除法 (DIV)

- **商向零舍入**：-10 / 3 = -3（不是 -4）
- **余数符号**：余数与被除数同号
- **恒等式**：dividend = divisor × quotient + remainder

### B.2 无符号除法 (DIVU)

- 所有操作数视为无符号
- 商向零舍入（等价于截断）

### B.3 边界情况总结表

| Operation | Dividend | Divisor | Quotient | Remainder |
|-----------|----------|---------|----------|-----------|
| DIV       | x        | 0       | -1       | x         |
| DIV       | -2³¹     | -1      | -2³¹     | 0         |
| DIVU      | x        | 0       | 2³²-1    | x         |
| REM       | x        | 0       | x        | x         |
| REM       | -2³¹     | -1      | 0        | 0         |
| REMU      | x        | 0       | x        | x         |

---

**文档版本**：v1.0  
**创建日期**：2024-12-27  
**作者**：Assassyn CPU 开发团队  
**状态**：计划阶段 - 待评审
