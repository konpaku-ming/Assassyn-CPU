# RISC-V 32I-M 扩展可行性分析与实施计划

> **🚨 重要更新 (2025-12-25)**: 在深入审查当前实现后，发现译码器存在关键限制（只检查bit30而非完整funct7），这会导致M扩展指令与基础指令冲突。详见[关键更正文档](./RV32M_Critical_Update.md)。可行性结论不变，但实施复杂度略有增加（+1小时）。

## 一、可行性分析

### 1.1 当前CPU架构概述

**Assassyn-CPU** 是一个基于 Assassyn HDL（使用Python描述硬件）实现的五级流水线RISC-V处理器，目前完整支持 **RV32I 基础整数指令集**。

#### 架构特点：
- **流水线结构**: IF (取指) → ID (译码) → EX (执行) → MEM (访存) → WB (写回)
- **数据冒险处理**: 完整的前递（Forwarding/Bypass）机制，支持 EX-MEM, MEM-WB, WB 三级旁路
- **控制冒险处理**: 分支预测 (BTB) + 冲刷机制
- **ALU功能**: 当前支持10种基础运算（ADD, SUB, SLL, SLT, SLTU, XOR, SRL, SRA, OR, AND）
- **模块化设计**: 清晰的模块分离，控制信号与数据路径分离

#### 当前指令集覆盖：
```
✅ R-Type:  ADD, SUB, SLL, SLT, SLTU, XOR, SRL, SRA, OR, AND
✅ I-Type:  ADDI, SLTI, SLTIU, XORI, ORI, ANDI, SLLI, SRLI, SRAI
✅ Load:    LB, LH, LW, LBU, LHU
✅ Store:   SB, SH, SW
✅ Branch:  BEQ, BNE, BLT, BGE, BLTU, BGEU
✅ Jump:    JAL, JALR
✅ U-Type:  LUI, AUIPC
✅ System:  ECALL, EBREAK
```

### 1.2 RISC-V M Extension 规范

M扩展（整数乘法和除法扩展）定义了**8条新指令**：

| 指令   | 操作码 | funct3 | funct7  | 功能描述                            |
|--------|--------|--------|---------|-------------------------------------|
| MUL    | 0110011| 000    | 0000001 | rd = (rs1 × rs2)[31:0]              |
| MULH   | 0110011| 001    | 0000001 | rd = (rs1 × rs2)[63:32] (有符号×有符号) |
| MULHSU | 0110011| 010    | 0000001 | rd = (rs1 × rs2)[63:32] (有符号×无符号) |
| MULHU  | 0110011| 011    | 0000001 | rd = (rs1 × rs2)[63:32] (无符号×无符号) |
| DIV    | 0110011| 100    | 0000001 | rd = rs1 ÷ rs2 (有符号，向零舍入)    |
| DIVU   | 0110011| 101    | 0000001 | rd = rs1 ÷ rs2 (无符号)              |
| REM    | 0110011| 110    | 0000001 | rd = rs1 % rs2 (有符号余数)          |
| REMU   | 0110011| 111    | 0000001 | rd = rs1 % rs2 (无符号余数)          |

**关键特性**：
- 所有指令均为 **R-Type** 格式（与ADD/SUB同类型）
- 共享操作码 `0110011` (OP_R_TYPE)
- 通过 `funct7=0000001` 区分M扩展与基础整数指令
- 需要64位乘法器和32位除法器

### 1.3 兼容性评估

#### ✅ **架构层面完全兼容**

1. **指令格式兼容**: M扩展使用R-Type格式，现有译码器已支持此格式
2. **操作码空间充足**: 当前 `ALUOp` 使用 Bits(16) 独热码，仅使用了11位，剩余5位足够扩展
3. **数据通路无需修改**: M扩展指令的数据流与ADD/SUB完全一致（rs1, rs2 → ALU → rd）
4. **旁路机制通用**: M扩展结果写回rd，可复用现有Forwarding逻辑
5. **流水线兼容**: 乘除法可视为单周期操作（或通过多周期暂停实现）

#### ⚠️ **需要解决的挑战**

1. **译码器限制（关键）**:
   - **当前问题**: 译码器只提取并检查 `bit30`，不检查完整的 `funct7` 字段
   - **冲突示例**: ADD (funct7=0x00, bit30=0) 与 MUL (funct7=0x01, bit30=0) 无法区分
   - **解决方案**: 必须修改译码器以支持完整的 funct7 匹配
   - **影响**: 需要先修改译码器，然后更新所有现有指令表条目
   - **详细分析**: 参见 [RV32M_Critical_Update.md](./RV32M_Critical_Update.md)

2. **运算复杂度**:
   - 乘法需要32×32=64位乘法器
   - 除法通常需要多周期迭代（32周期）
   - 可能影响时序性能（最大频率降低）

2. **资源消耗**:
   - 硬件乘法器和除法器会显著增加逻辑资源
   - Assassyn编译后的Verilog可能需要更多LUT/DSP

3. **除零处理**:
   - 除法和取模指令需要特殊处理除数为0的情况
   - RISC-V规范: DIV(x, 0) = -1, REM(x, 0) = x

### 1.4 可行性结论

✅ **技术上完全可行**

- 现有架构设计优秀，模块化程度高，易于扩展
- M扩展与现有指令集完美兼容，无需重构流水线
- 控制信号机制灵活，仅需增量修改
- Python/Assassyn的高层次抽象大大简化了硬件设计

📊 **预期工作量**: 中等（约2-3天开发 + 1天测试）

---

## 二、详细实施计划

### 阶段一：控制信号扩展（1小时）

#### 目标
在 `src/control_signals.py` 中为M扩展添加ALU操作码定义。

#### 修改内容
```python
# 在 ALUOp 类中添加（扩展为 Bits(32) 以容纳更多操作）
class ALUOp:
    # ... 现有10种操作 (Bits 0-10) ...
    
    # M Extension (新增8种，每个使用唯一的位)
    MUL    = Bits(32)(0b00000000000000000000100000000000)  # Bit 11
    MULH   = Bits(32)(0b00000000000000000001000000000000)  # Bit 12
    MULHSU = Bits(32)(0b00000000000000000010000000000000)  # Bit 13
    MULHU  = Bits(32)(0b00000000000000000100000000000000)  # Bit 14
    DIV    = Bits(32)(0b00000000000000001000000000000000)  # Bit 15
    DIVU   = Bits(32)(0b00000000000000010000000000000000)  # Bit 16
    REM    = Bits(32)(0b00000000000000100000000000000000)  # Bit 17
    REMU   = Bits(32)(0b00000000000001000000000000000000)  # Bit 18
```

**关键修改**: 扩展为 `Bits(32)`，为每个操作分配唯一的位，确保独热码特性。这也为未来指令集扩展（如F/D扩展）预留了空间。

---

### 阶段二：指令真值表更新（30分钟）

#### 目标
在 `src/instruction_table.py` 的 `rv32i_table` 中添加M扩展指令条目。

#### 修改内容
```python
rv32i_table = [
    # ... 现有RV32I指令 ...
    
    # --- M Extension (Multiply/Divide) ---
    ('mul', OP_R_TYPE, 0x0, None, ImmType.R, ALUOp.MUL, 
     RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH),
    
    ('mulh', OP_R_TYPE, 0x1, None, ImmType.R, ALUOp.MULH, 
     RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH),
    
    ('mulhsu', OP_R_TYPE, 0x2, None, ImmType.R, ALUOp.MULHSU, 
     RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH),
    
    ('mulhu', OP_R_TYPE, 0x3, None, ImmType.R, ALUOp.MULHU, 
     RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH),
    
    ('div', OP_R_TYPE, 0x4, None, ImmType.R, ALUOp.DIV, 
     RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH),
    
    ('divu', OP_R_TYPE, 0x5, None, ImmType.R, ALUOp.DIVU, 
     RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH),
    
    ('rem', OP_R_TYPE, 0x6, None, ImmType.R, ALUOp.REM, 
     RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH),
    
    ('remu', OP_R_TYPE, 0x7, None, ImmType.R, ALUOp.REMU, 
     RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH),
]
```

**关键点**：
- 所有指令共享 `OP_R_TYPE` 操作码
- 通过 `funct3` 区分不同指令（0x0-0x7）
- 需要添加 `funct7=0x01` 的匹配逻辑

**额外修改**：在译码器中添加funct7字段的解析和匹配。

---

### 阶段三：译码器增强（1小时）

#### 目标
修改 `src/decoder.py`，支持funct7字段的提取和匹配。

#### 当前译码器局限
```python
# 当前只解析了 bit30，没有完整的 funct7
bit30 = inst[30:30]
```

#### 修改方案
```python
# 2. 物理切片（扩展）
opcode = inst[0:6]
rd = inst[7:11]
funct3 = inst[12:14]
rs1 = inst[15:19]
rs2 = inst[20:24]
funct7 = inst[25:31]  # 新增：提取完整的funct7字段
bit30 = inst[30:30]   # 保留向后兼容

# 在查表匹配逻辑中添加funct7判断
for entry in rv32i_table:
    (name, t_op, t_f3, t_f7, t_imm_type, ...) = entry  # 添加t_f7参数
    
    match_if = opcode == t_op
    
    if t_f3 is not None:
        match_if &= funct3 == Bits(3)(t_f3)
    
    # 新增: funct7 匹配
    if t_f7 is not None:
        match_if &= funct7 == Bits(7)(t_f7)
    
    # ... 原有累加逻辑 ...
```

**影响范围**：
- `instruction_table.py` 的表格结构需调整（添加funct7列）
- 所有现有指令条目需添加 `None` 或实际funct7值

---

### 阶段四：执行单元扩展（2小时）

#### 目标
在 `src/execution.py` 的ALU计算部分添加乘法和除法逻辑。

#### 乘法实现
```python
# --- 乘法运算 (Multiplication) ---

# MUL: 返回 rs1 × rs2 的低32位
mul_res = (op1_signed * op2_signed).bitcast(Bits(64))[0:31]

# MULH: 有符号×有符号，返回高32位
mulh_full = op1_signed.bitcast(Int(32)) * op2_signed.bitcast(Int(32))
mulh_res = mulh_full.bitcast(Bits(64))[32:63]

# MULHSU: 有符号×无符号，返回高32位
op1_s = alu_op1.bitcast(Int(32))
op2_u = alu_op2.bitcast(UInt(32))
mulhsu_full = (op1_s.bitcast(Int(64)) * op2_u.bitcast(Int(64)))
mulhsu_res = mulhsu_full.bitcast(Bits(64))[32:63]

# MULHU: 无符号×无符号，返回高32位
mulhu_full = alu_op1.bitcast(UInt(32)) * alu_op2.bitcast(UInt(32))
mulhu_res = mulhu_full.bitcast(Bits(64))[32:63]
```

#### 除法实现（需处理除零）
```python
# --- 除法运算 (Division) ---

# 除零检测
is_div_zero = alu_op2 == Bits(32)(0)

# DIV: 有符号除法
div_normal = (op1_signed / op2_signed).bitcast(Bits(32))
div_res = is_div_zero.select(
    Bits(32)(0xFFFFFFFF),  # 除零返回-1
    div_normal
)

# DIVU: 无符号除法
divu_normal = (alu_op1.bitcast(UInt(32)) / alu_op2.bitcast(UInt(32))).bitcast(Bits(32))
divu_res = is_div_zero.select(
    Bits(32)(0xFFFFFFFF),  # 除零返回全1
    divu_normal
)

# REM: 有符号取余
rem_normal = (op1_signed % op2_signed).bitcast(Bits(32))
rem_res = is_div_zero.select(
    alu_op1,  # 除零时余数等于被除数
    rem_normal
)

# REMU: 无符号取余
remu_normal = (alu_op1.bitcast(UInt(32)) % alu_op2.bitcast(UInt(32))).bitcast(Bits(32))
remu_res = is_div_zero.select(
    alu_op1,  # 除零时余数等于被除数
    remu_normal
)
```

#### ALU结果选择器扩展
```python
# 当前select1hot有16个槽位，需扩展或替换为更大的Bits
alu_result = ctrl.alu_func.select1hot(
    add_res,     # 0:  ADD
    sub_res,     # 1:  SUB
    sll_res,     # 2:  SLL
    slt_res,     # 3:  SLT
    sltu_res,    # 4:  SLTU
    xor_res,     # 5:  XOR
    srl_res,     # 6:  SRL
    sra_res,     # 7:  SRA
    or_res,      # 8:  OR
    and_res,     # 9:  AND
    alu_op2,     # 10: SYS
    mul_res,     # 11: MUL
    mulh_res,    # 12: MULH
    mulhsu_res,  # 13: MULHSU
    mulhu_res,   # 14: MULHU
    div_res,     # 15: DIV (需扩展Bits)
    divu_res,    # 16: DIVU
    rem_res,     # 17: REM
    remu_res,    # 18: REMU
)
```

**注意**: 需将 `alu_func` 从 `Bits(16)` 扩展到 `Bits(32)`。

---

### 阶段五：测试用例开发（3小时）

#### 5.1 单元测试（tests/test_m_extension.py）

```python
"""
RV32M Extension 单元测试
测试乘法、除法和取模指令的正确性
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from assassyn.frontend import *
from src.execution import Execution
from src.control_signals import *
from tests.common import run_test_module

class Driver(Module):
    def __init__(self):
        super().__init__(ports={})

    @module.combinational
    def build(self, dut: Module, ...):
        # 测试向量
        test_vectors = [
            # (指令, rs1, rs2, 期望结果)
            ("MUL",    10, 20, 200),
            ("MUL",    -5, 3, -15),
            ("MULH",   0x80000000, 2, 1),  # 测试溢出
            ("MULHU",  0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFE),
            ("DIV",    100, 10, 10),
            ("DIV",    10, 0, -1),  # 除零
            ("DIVU",   100, 10, 10),
            ("REM",    105, 10, 5),
            ("REM",    10, 0, 10),  # 除零
            ("REMU",   105, 10, 5),
        ]
        
        # 测试逻辑实现...

def test_m_extension():
    sys = SysBuilder('test_m_ext')
    # ... 测试系统构建 ...
    run_test_module(sys, check_function)

if __name__ == '__main__':
    test_m_extension()
```

#### 5.2 集成测试（workloads/）

创建汇编测试程序：

**乘法测试** (`workloads/mul_test.s`):
```assembly
.globl _start
_start:
    li a0, 123
    li a1, 456
    mul a2, a0, a1      # a2 = 56088
    
    li a3, 0x80000000
    li a4, 2
    mulh a5, a3, a4     # a5 = 1 (高位)
    
    ebreak
```

**除法测试** (`workloads/div_test.s`):
```assembly
.globl _start
_start:
    li a0, 1000
    li a1, 7
    div a2, a0, a1      # a2 = 142
    rem a3, a0, a1      # a3 = 6
    
    li a4, 100
    li a5, 0
    div a6, a4, a5      # a6 = -1 (除零)
    rem a7, a4, a5      # a7 = 100 (除零)
    
    ebreak
```

#### 5.3 性能测试

复用现有的 `workloads/multiply.exe`（软件实现的乘法），对比M扩展的性能提升。

---

### 阶段六：文档更新（1小时）

#### 6.1 更新模块文档

- `docs/Module/EX.md`: 添加M扩展ALU操作说明
- `docs/Module/ID.md`: 说明funct7字段的译码逻辑

#### 6.2 创建M扩展专项文档

创建 `docs/RV32M_Extension.md`：
```markdown
# RV32M Extension 使用指南

## 支持的指令
- MUL, MULH, MULHSU, MULHU
- DIV, DIVU, REM, REMU

## 性能特性
- 单周期执行（理想情况）
- 除法可能需要多周期（实现依赖）

## 使用示例
...
```

---

## 三、实施时间表（更新）

> **注**: 由于发现译码器限制，实施计划已调整，增加了译码器增强阶段。

| 阶段                     | 预计时间 | 关键产出                              |
|--------------------------|----------|---------------------------------------|
| **阶段零：现状验证**     | 0.5小时  | 译码器行为测试，确认bit30匹配逻辑     |
| 阶段一：控制信号扩展     | 1小时    | `control_signals.py` 修改完成         |
| 阶段二：指令真值表更新   | 1小时    | `instruction_table.py` 更新所有条目+8条新指令 |
| 阶段三：译码器增强       | 1.5小时  | `decoder.py` 支持完整funct7匹配       |
| 阶段四：执行单元扩展     | 2小时    | `execution.py` 实现乘除法逻辑         |
| 阶段五：测试用例开发     | 3小时    | 单元测试 + 集成测试 + 性能测试        |
| 阶段六：文档更新         | 1小时    | 模块文档 + M扩展专项文档              |
| **总计**                 | **10小时** | 完整的RV32IM支持（原估计8.5小时）    |

**关键变化**：
- 新增阶段零（现状验证）: +0.5小时
- 阶段二时间增加: +0.5小时（需更新所有现有指令）
- 阶段三时间增加: +0.5小时（funct7匹配逻辑更复杂）
- **总计增加**: +1.5小时

---

## 四、风险评估与缓解策略

### 风险1：除法器延迟过大
**影响**: 可能降低CPU最大频率或需要暂停流水线  
**缓解**: 
- 方案A: 使用多周期除法器 + Stall机制
- 方案B: 使用快速除法算法（Newton-Raphson）
- 方案C: 初期实现可容忍较低频率

### 风险2：资源消耗超预期
**影响**: FPGA综合失败或仿真速度过慢  
**缓解**:
- 监控Assassyn生成的Verilog代码质量
- 使用共享的乘除法单元（时间复用）
- 考虑使用DSP原语（如果目标FPGA支持）

### 风险3：Assassyn语言限制
**影响**: 无法表达复杂的乘除法电路  
**缓解**:
- 依赖Python运算符映射到硬件
- 查阅Assassyn文档确认类型转换支持
- 必要时联系框架开发者

---

## 五、成功标准

✅ **功能正确性**
- [ ] 所有8条M扩展指令通过单元测试
- [ ] 除零处理符合RISC-V规范
- [ ] 边界值测试通过（如0x80000000 ÷ -1）

✅ **集成完整性**
- [ ] 与现有RV32I指令无冲突
- [ ] 前递机制正常工作（乘除法结果可旁路）
- [ ] BTB预测不受影响

✅ **性能指标**
- [ ] 乘法指令相比软件实现提速10倍以上
- [ ] 除法指令相比软件实现提速5倍以上

✅ **文档质量**
- [ ] 每个模块的修改都有对应文档更新
- [ ] 提供可运行的示例程序

---

## 六、后续优化方向

1. **多周期除法器**: 将除法操作扩展为32周期迭代，提升频率
2. **F/D扩展**: 在M扩展基础上进一步支持浮点运算
3. **性能计数器**: 添加指令统计，评估M扩展的实际使用率
4. **工具链支持**: 确保GCC/LLVM生成的RV32IM代码可正确执行

---

## 七、总结

RV32M扩展在Assassyn-CPU上的实现**完全可行**，得益于：
1. 清晰的模块化设计
2. 灵活的控制信号机制
3. Python/Assassyn的高表达能力

预计 **1-2个工作日** 即可完成从设计到测试的全流程，为CPU的实用化奠定基础。

建议按照本计划 **逐阶段推进**，每完成一阶段立即进行回归测试，确保增量开发的稳定性。

---

**文档版本**: v1.0  
**创建日期**: 2025-12-24  
**作者**: Copilot AI Assistant  
**审阅状态**: 待审阅
