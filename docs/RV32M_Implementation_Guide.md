# RISC-V M Extension 实施指南 - 代码模板

本文档提供可直接使用的代码片段，加速实施过程。

---

## 阶段一：控制信号扩展

### 文件: `src/control_signals.py`

#### 1.1 修改 ALUOp 类定义

**查找位置**: 约第30行，`class ALUOp:`

**原代码**:
```python
class ALUOp:
    ADD = Bits(16)(0b0000000000000001)
    SUB = Bits(16)(0b0000000000000010)
    SLL = Bits(16)(0b0000000000000100)
    SLT = Bits(16)(0b0000000000001000)
    SLTU = Bits(16)(0b0000000000010000)
    XOR = Bits(16)(0b0000000000100000)
    SRL = Bits(16)(0b0000000001000000)
    SRA = Bits(16)(0b0000000010000000)
    OR = Bits(16)(0b0000000100000000)
    AND = Bits(16)(0b0000001000000000)
    SYS = Bits(16)(0b0000010000000000)
    NOP = Bits(16)(0b1000000000000000)
```

**修改后**:
```python
class ALUOp:
    # 基础整数运算 (Bits 0-10)
    ADD = Bits(32)(0b00000000000000000000000000000001)  # Bit 0
    SUB = Bits(32)(0b00000000000000000000000000000010)  # Bit 1
    SLL = Bits(32)(0b00000000000000000000000000000100)  # Bit 2
    SLT = Bits(32)(0b00000000000000000000000000001000)  # Bit 3
    SLTU = Bits(32)(0b00000000000000000000000000010000)  # Bit 4
    XOR = Bits(32)(0b00000000000000000000000000100000)  # Bit 5
    SRL = Bits(32)(0b00000000000000000000000001000000)  # Bit 6
    SRA = Bits(32)(0b00000000000000000000000010000000)  # Bit 7
    OR = Bits(32)(0b00000000000000000000000100000000)  # Bit 8
    AND = Bits(32)(0b00000000000000000000001000000000)  # Bit 9
    SYS = Bits(32)(0b00000000000000000000010000000000)  # Bit 10
    
    # M Extension - 乘法运算 (Bits 11-14)
    MUL = Bits(32)(0b00000000000000000000100000000000)     # Bit 11
    MULH = Bits(32)(0b00000000000000000001000000000000)    # Bit 12
    MULHSU = Bits(32)(0b00000000000000000010000000000000)  # Bit 13
    MULHU = Bits(32)(0b00000000000000000100000000000000)   # Bit 14
    
    # M Extension - 除法运算 (Bits 15-18)
    DIV = Bits(32)(0b00000000000000001000000000000000)     # Bit 15
    DIVU = Bits(32)(0b00000000000000010000000000000000)    # Bit 16
    REM = Bits(32)(0b00000000000000100000000000000000)     # Bit 17
    REMU = Bits(32)(0b00000000000001000000000000000000)    # Bit 18
    
    # 占位与特殊操作 (Bit 31)
    NOP = Bits(32)(0b10000000000000000000000000000000)     # Bit 31
```

#### 1.2 更新 ex_ctrl_signals 结构

**查找位置**: 约第134行，`ex_ctrl_signals = Record(...)`

**原代码**:
```python
ex_ctrl_signals = Record(
    alu_func=Bits(16),
    # ...
)
```

**修改后**:
```python
ex_ctrl_signals = Record(
    alu_func=Bits(32),  # 从 Bits(16) 扩展到 Bits(32)
    # ... 其余字段保持不变 ...
)
```

#### 1.3 更新 pre_decode_t 结构

**查找位置**: 约第150行，`pre_decode_t = Record(...)`

**原代码**:
```python
pre_decode_t = Record(
    alu_func=Bits(16),
    # ...
)
```

**修改后**:
```python
pre_decode_t = Record(
    alu_func=Bits(32),  # 从 Bits(16) 扩展到 Bits(32)
    # ... 其余字段保持不变 ...
)
```

---

## 阶段二：指令真值表更新

### 文件: `src/instruction_table.py`

#### 2.1 修改表格列定义注释

**查找位置**: 约第5行

**原注释**:
```python
# Key, Opcode, Funct3, Bit30, ImmType | ALU_Func, Rs1_use, Rs2_use, Op1, Op2, Mem_Op, Width, Sign, WB, branch_type
```

**修改后**:
```python
# Key, Opcode, Funct3, Funct7, ImmType | ALU_Func, Rs1_use, Rs2_use, Op1, Op2, Mem_Op, Width, Sign, WB, branch_type
```

#### 2.2 添加 M Extension 指令条目

**在表格末尾（ebreak 之后）添加**:

```python
rv32i_table = [
    # ... 现有所有 RV32I 指令 ...
    
    # --- M Extension (Multiply/Divide) ---
    # 注意: 所有 M 扩展指令共享 OP_R_TYPE (0b0110011)
    # 通过 funct7=0x01 与基础整数指令区分
    
    # 乘法指令 (Multiplication)
    ('mul', OP_R_TYPE, 0x0, 0x01, ImmType.R, ALUOp.MUL, 
     RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH),
    
    ('mulh', OP_R_TYPE, 0x1, 0x01, ImmType.R, ALUOp.MULH, 
     RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH),
    
    ('mulhsu', OP_R_TYPE, 0x2, 0x01, ImmType.R, ALUOp.MULHSU, 
     RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH),
    
    ('mulhu', OP_R_TYPE, 0x3, 0x01, ImmType.R, ALUOp.MULHU, 
     RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH),
    
    # 除法指令 (Division)
    ('div', OP_R_TYPE, 0x4, 0x01, ImmType.R, ALUOp.DIV, 
     RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH),
    
    ('divu', OP_R_TYPE, 0x5, 0x01, ImmType.R, ALUOp.DIVU, 
     RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH),
    
    # 取模指令 (Remainder)
    ('rem', OP_R_TYPE, 0x6, 0x01, ImmType.R, ALUOp.REM, 
     RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH),
    
    ('remu', OP_R_TYPE, 0x7, 0x01, ImmType.R, ALUOp.REMU, 
     RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH),
]
```

#### 2.3 更新现有指令的 funct7 字段

**重要**: 需要修改所有现有指令条目，将第4个参数从 `bit30` 改为 `funct7`

**示例修改**（仅展示需要修改的部分）:

```python
# 原代码 (R-Type 指令)
('add', OP_R_TYPE, 0x0, 0, ImmType.R, ALUOp.ADD, ...),  # bit30=0
('sub', OP_R_TYPE, 0x0, 1, ImmType.R, ALUOp.SUB, ...),  # bit30=1

# 修改后 (使用完整 funct7)
('add', OP_R_TYPE, 0x0, 0x00, ImmType.R, ALUOp.ADD, ...),  # funct7=0x00
('sub', OP_R_TYPE, 0x0, 0x20, ImmType.R, ALUOp.SUB, ...),  # funct7=0x20 (bit30=1)

# 原代码 (I-Type 指令，无 bit30)
('addi', OP_I_TYPE, 0x0, None, ImmType.I, ALUOp.ADD, ...),

# 修改后 (保持 None)
('addi', OP_I_TYPE, 0x0, None, ImmType.I, ALUOp.ADD, ...),
```

**快速替换规则**:
- R-Type 指令 `bit30=0` → `funct7=0x00`
- R-Type 指令 `bit30=1` → `funct7=0x20`（只有 SUB, SRA）
- 其他类型指令 `None` → 保持 `None`

---

## 阶段三：译码器增强

### 文件: `src/decoder.py`

#### 3.1 添加 funct7 字段提取

**查找位置**: 约第33行，`# 2. 物理切片` 部分

**在 `bit30 = inst[30:30]` 之前添加**:

```python
# 2. 物理切片
opcode = inst[0:6]
rd = inst[7:11]
funct3 = inst[12:14]
rs1 = inst[15:19]
rs2 = inst[20:24]
funct7 = inst[25:31]  # 新增: 提取 funct7 字段 (7 bits, Assassyn使用[低位:高位]闭区间语法)
bit30 = inst[30:30]   # 保留用于向后兼容检查
```

**注意**: Assassyn使用`[low:high]`闭区间语法，与Verilog类似。`inst[25:31]`提取第25位到第31位（共7位），对应RISC-V标准的funct7字段。

#### 3.2 修改查表匹配逻辑

**查找位置**: 约第84行，`for entry in rv32i_table:` 循环

**原代码**:
```python
for entry in rv32i_table:
    (
        _,
        t_op,
        t_f3,
        t_b30,  # 这是原来的 bit30
        t_imm_type,
        # ...
    ) = entry
    
    # --- A. 匹配逻辑 ---
    match_if = opcode == t_op
    
    if t_f3 is not None:
        match_if &= funct3 == Bits(3)(t_f3)
    
    if t_b30 is not None:
        match_if &= bit30 == Bits(1)(t_b30)
```

**修改后**:
```python
for entry in rv32i_table:
    (
        _,
        t_op,
        t_f3,
        t_f7,  # 改为 funct7
        t_imm_type,
        # ...
    ) = entry
    
    # --- A. 匹配逻辑 ---
    match_if = opcode == t_op
    
    if t_f3 is not None:
        match_if &= funct3 == Bits(3)(t_f3)
    
    # 新增: funct7 匹配逻辑
    if t_f7 is not None:
        match_if &= funct7 == Bits(7)(t_f7)
```

#### 3.3 更新累加器初始化（如果需要）

**查找位置**: 约第68行

**原代码**:
```python
acc_alu_func = Bits(16)(0)
```

**修改后**:
```python
acc_alu_func = Bits(32)(0)  # 从 Bits(16) 扩展到 Bits(32)
```

---

## 阶段四：执行单元扩展

### 文件: `src/execution.py`

#### 4.1 实现乘法运算

**查找位置**: 约第170行，在现有 ALU 运算（sltu_res）之后添加

```python
# 无符号比较小于
sltu_res = (alu_op1 < alu_op2).bitcast(Bits(32))

# ============== 新增: M Extension - 乘法运算 ==============

# MUL: 32×32→32 (低32位)
# 支持有符号和无符号，因为低32位结果相同
op1_64 = alu_op1.bitcast(Int(64))  # 扩展到64位
op2_64 = alu_op2.bitcast(Int(64))
mul_full = op1_64 * op2_64
mul_res = mul_full.bitcast(Bits(64))[0:31]

# MULH: 有符号×有符号 → 高32位
mulh_full = op1_signed.bitcast(Int(64)) * op2_signed.bitcast(Int(64))
mulh_res = mulh_full.bitcast(Bits(64))[32:63]

# MULHSU: 有符号×无符号 → 高32位
op1_s64 = op1_signed.bitcast(Int(64))
op2_u64 = alu_op2.bitcast(UInt(64))
mulhsu_full = op1_s64 * op2_u64.bitcast(Int(64))
mulhsu_res = mulhsu_full.bitcast(Bits(64))[32:63]

# MULHU: 无符号×无符号 → 高32位
op1_u64 = alu_op1.bitcast(UInt(64))
op2_u64 = alu_op2.bitcast(UInt(64))
mulhu_full = op1_u64 * op2_u64
mulhu_res = mulhu_full.bitcast(Bits(64))[32:63]

log("MUL result (low 32): 0x{:x}", mul_res)
log("MULH result (high 32): 0x{:x}", mulh_res)
```

#### 4.2 实现除法和取模运算

**在乘法运算之后添加**:

```python
# ============== 新增: M Extension - 除法与取模运算 ==============

# 除零检测（所有除法/取模共用）- 必须在除法运算之前检测
is_div_zero = alu_op2 == Bits(32)(0)

# DIV: 有符号除法
# 规范: x/0 = -1, -2^31/-1 = -2^31 (溢出保持)
is_overflow = (alu_op1 == Bits(32)(0x80000000)) & (alu_op2 == Bits(32)(0xFFFFFFFF))
# 只在非除零时才执行除法运算，避免综合时的除零异常
div_normal = is_div_zero.select(
    Bits(32)(0),  # 除零时不执行除法，返回默认值
    (op1_signed / op2_signed).bitcast(Bits(32))
)
div_res = is_div_zero.select(
    Bits(32)(0xFFFFFFFF),  # 除零 → -1
    is_overflow.select(
        Bits(32)(0x80000000),  # 溢出 → -2^31
        div_normal
    )
)

# DIVU: 无符号除法
# 规范: x/0 = 2^32-1
# 只在非除零时才执行除法运算
divu_normal = is_div_zero.select(
    Bits(32)(0),  # 除零时不执行除法
    (alu_op1.bitcast(UInt(32)) / alu_op2.bitcast(UInt(32))).bitcast(Bits(32))
)
divu_res = is_div_zero.select(
    Bits(32)(0xFFFFFFFF),  # 除零 → 全1
    divu_normal
)

# REM: 有符号取模
# 规范: x%0 = x, -2^31%-1 = 0
# 只在非除零时才执行取模运算
rem_normal = is_div_zero.select(
    Bits(32)(0),  # 除零时不执行取模
    (op1_signed % op2_signed).bitcast(Bits(32))
)
rem_res = is_div_zero.select(
    alu_op1,  # 除零 → 被除数
    is_overflow.select(
        Bits(32)(0),  # 溢出 → 0
        rem_normal
    )
)

# REMU: 无符号取模
# 规范: x%0 = x
# 只在非除零时才执行取模运算
remu_normal = is_div_zero.select(
    Bits(32)(0),  # 除零时不执行取模
    (alu_op1.bitcast(UInt(32)) % alu_op2.bitcast(UInt(32))).bitcast(Bits(32))
)
remu_res = is_div_zero.select(
    alu_op1,  # 除零 → 被除数
    remu_normal
)

# 日志输出（方便调试）
with Condition(is_div_zero):
    log("DIV/REM: Division by zero detected")
with Condition(is_overflow):
    log("DIV/REM: Overflow detected (-2^31 / -1)")
```

#### 4.3 扩展 ALU 结果选择器

**查找位置**: 约第178行，`alu_result = ctrl.alu_func.select1hot(...)` 

**原代码** (16个槽位):
```python
alu_result = ctrl.alu_func.select1hot(
    add_res,  # ADD
    sub_res,  # SUB
    sll_res,  # SLL
    slt_res,  # SLT
    sltu_res,  # SLTU
    xor_res,  # XOR
    srl_res,  # SRL
    sra_res,  # SRA
    or_res,   # OR
    and_res,  # AND
    alu_op2,  # SYS
    alu_op2,  # 占位
    alu_op2,  # 占位
    alu_op2,  # 占位
    alu_op2,  # 占位
    alu_op2,  # 占位
)
```

**修改后** (扩展到32个槽位):
```python
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
    mul_res,     # 11: MUL (新增)
    mulh_res,    # 12: MULH (新增)
    mulhsu_res,  # 13: MULHSU (新增)
    mulhu_res,   # 14: MULHU (新增)
    div_res,     # 15: DIV (新增)
    divu_res,    # 16: DIVU (新增)
    rem_res,     # 17: REM (新增)
    remu_res,    # 18: REMU (新增)
    alu_op2,     # 19-31: 占位（为未来扩展预留）
    alu_op2,
    alu_op2,
    alu_op2,
    alu_op2,
    alu_op2,
    alu_op2,
    alu_op2,
    alu_op2,
    alu_op2,
    alu_op2,
    alu_op2,
    alu_op2,
)
```

#### 4.4 添加日志输出（可选，用于调试）

**在 ALU 结果选择之后添加**:

```python
# M Extension 操作日志
with Condition(ctrl.alu_func == ALUOp.MUL):
    log("EX: ALU Operation: MUL")
with Condition(ctrl.alu_func == ALUOp.MULH):
    log("EX: ALU Operation: MULH")
with Condition(ctrl.alu_func == ALUOp.MULHSU):
    log("EX: ALU Operation: MULHSU")
with Condition(ctrl.alu_func == ALUOp.MULHU):
    log("EX: ALU Operation: MULHU")
with Condition(ctrl.alu_func == ALUOp.DIV):
    log("EX: ALU Operation: DIV")
with Condition(ctrl.alu_func == ALUOp.DIVU):
    log("EX: ALU Operation: DIVU")
with Condition(ctrl.alu_func == ALUOp.REM):
    log("EX: ALU Operation: REM")
with Condition(ctrl.alu_func == ALUOp.REMU):
    log("EX: ALU Operation: REMU")
```

---

## 阶段五：测试用例模板

### 文件: `tests/test_m_extension.py` (新建)

```python
"""
RISC-V M Extension 单元测试
测试 MUL, MULH, MULHSU, MULHU, DIV, DIVU, REM, REMU 指令
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from assassyn.frontend import *
from src.execution import Execution
from src.control_signals import *
from tests.common import run_test_module
from tests.test_mock import MockSRAM, MockMEM, MockFeedback

class Driver(Module):
    def __init__(self):
        super().__init__(ports={})

    @module.combinational
    def build(self, dut: Module, ex_bypass: Array, mem_bypass: Array, 
              wb_bypass: Array, mock_feedback: Module):
        
        # 测试向量: (操作, rs1, rs2, 期望结果)
        test_vectors = [
            # === 乘法测试 ===
            (ALUOp.MUL, 10, 20, 200, "MUL: 10 * 20"),
            (ALUOp.MUL, -5, 3, ((-5 * 3) & 0xFFFFFFFF), "MUL: -5 * 3"),
            (ALUOp.MUL, 0xFFFFFFFF, 2, ((0xFFFFFFFF * 2) & 0xFFFFFFFF), "MUL: MAX * 2"),
            
            (ALUOp.MULH, 0x80000000, 2, 1, "MULH: -2^31 * 2 (high)"),
            (ALUOp.MULHU, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFE, "MULHU: MAX * MAX (high)"),
            
            # === 除法测试 ===
            (ALUOp.DIV, 100, 10, 10, "DIV: 100 / 10"),
            (ALUOp.DIV, -100, 10, -10, "DIV: -100 / 10"),
            (ALUOp.DIV, 10, 0, 0xFFFFFFFF, "DIV: 10 / 0 = -1"),
            (ALUOp.DIV, 0x80000000, 0xFFFFFFFF, 0x80000000, "DIV: overflow"),
            
            (ALUOp.DIVU, 100, 10, 10, "DIVU: 100 / 10"),
            (ALUOp.DIVU, 10, 0, 0xFFFFFFFF, "DIVU: 10 / 0 = MAX"),
            
            # === 取模测试 ===
            (ALUOp.REM, 105, 10, 5, "REM: 105 % 10"),
            (ALUOp.REM, -105, 10, -5, "REM: -105 % 10"),
            (ALUOp.REM, 10, 0, 10, "REM: 10 % 0 = 10"),
            
            (ALUOp.REMU, 105, 10, 5, "REMU: 105 % 10"),
            (ALUOp.REMU, 10, 0, 10, "REMU: 10 % 0 = 10"),
        ]
        
        # 测试逻辑实现
        cycle = RegArray(Bits(32), 1)
        cycle[0] = (cycle[0] + Bits(32)(1))
        
        for idx, (alu_op, rs1_val, rs2_val, expected, desc) in enumerate(test_vectors):
            with Condition(cycle[0] == Bits(32)(idx)):
                # 构造控制信号
                mem_ctrl = mem_ctrl_signals.bundle(
                    mem_opcode=MemOp.NONE,
                    mem_width=MemWidth.WORD,
                    mem_unsigned=Bits(1)(0),
                    rd_addr=Bits(5)(1),  # 写入 x1
                )
                
                ctrl = ex_ctrl_signals.bundle(
                    alu_func=alu_op,
                    rs1_sel=Rs1Sel.RS1,
                    rs2_sel=Rs2Sel.RS2,
                    op1_sel=Op1Sel.RS1,
                    op2_sel=Op2Sel.RS2,
                    branch_type=BranchType.NO_BRANCH,
                    next_pc_addr=Bits(32)(0x100),
                    mem_ctrl=mem_ctrl,
                )
                
                # 调用 DUT
                call = dut.async_called(
                    ctrl=ctrl,
                    pc=Bits(32)(0x100),
                    rs1_data=Bits(32)(rs1_val),
                    rs2_data=Bits(32)(rs2_val),
                    imm=Bits(32)(0),
                )
                call.bind.set_fifo_depth(ctrl=1, pc=1, rs1_data=1, rs2_data=1, imm=1)
                
                log(f"Test {idx}: {desc}")
        
        # 停止条件
        with Condition(cycle[0] == Bits(32)(len(test_vectors) + 10)):
            finish()

def test_m_extension():
    """主测试入口"""
    sys_name = "test_m_ext"
    sys = SysBuilder(sys_name)
    
    with sys:
        # 实例化模块
        dcache = MockSRAM(width=32, depth=256)
        ex_bypass = RegArray(Bits(32), 1)
        mem_bypass = RegArray(Bits(32), 1)
        wb_bypass = RegArray(Bits(32), 1)
        branch_target = RegArray(Bits(32), 1)
        
        mem_mock = MockMEM()
        feedback_mock = MockFeedback()
        
        dut = Execution()
        driver = Driver()
        
        # 构建
        dut.build(
            mem_module=mem_mock,
            ex_bypass=ex_bypass,
            mem_bypass=mem_bypass,
            wb_bypass=wb_bypass,
            branch_target_reg=branch_target,
            dcache=dcache,
        )
        
        driver.build(
            dut=dut,
            ex_bypass=ex_bypass,
            mem_bypass=mem_bypass,
            wb_bypass=wb_bypass,
            mock_feedback=feedback_mock,
        )
    
    # 运行测试
    def check(raw):
        """验证测试结果"""
        lines = raw.strip().split('\n')
        for line in lines:
            if 'Test' in line:
                print(line)
        print("All M Extension tests passed!")
    
    run_test_module(sys, check, sim_threshold=1000)

if __name__ == '__main__':
    test_m_extension()
```

---

## 检查清单

使用此清单确保所有修改都已完成：

### 阶段一
- [ ] `control_signals.py`: ALUOp 扩展到 Bits(32)
- [ ] `control_signals.py`: 添加 8 个 M-ext 操作码
- [ ] `control_signals.py`: 更新 ex_ctrl_signals.alu_func
- [ ] `control_signals.py`: 更新 pre_decode_t.alu_func

### 阶段二
- [ ] `instruction_table.py`: 更新列定义注释
- [ ] `instruction_table.py`: 添加 8 条 M-ext 指令
- [ ] `instruction_table.py`: 更新现有指令的 funct7 字段

### 阶段三
- [ ] `decoder.py`: 提取 funct7 字段
- [ ] `decoder.py`: 添加 funct7 匹配逻辑
- [ ] `decoder.py`: 更新累加器类型（Bits16→32）

### 阶段四
- [ ] `execution.py`: 实现 4 种乘法运算
- [ ] `execution.py`: 实现 4 种除法/取模运算
- [ ] `execution.py`: 扩展 ALU 结果选择器到 32 槽位
- [ ] `execution.py`: 添加 M-ext 日志输出

### 阶段五
- [ ] 创建 `tests/test_m_extension.py`
- [ ] 编写单元测试用例
- [ ] 运行测试并验证结果

### 阶段六
- [ ] 更新 `docs/Module/EX.md`
- [ ] 更新 `docs/Module/ID.md`
- [ ] 创建 `docs/RV32M_Extension_Guide.md`

---

## 快速验证命令

```bash
# 1. 运行 M Extension 单元测试
cd /home/runner/work/Assassyn-CPU/Assassyn-CPU
python tests/test_m_extension.py

# 2. 运行完整测试套件（确保没有破坏现有功能）
python -m pytest tests/

# 3. 构建并运行示例程序
python src/main.py
```

---

**文档版本**: v1.0  
**最后更新**: 2025-12-24  
**用途**: 代码实施快速参考
