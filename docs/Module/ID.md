# RV32I ID (Instruction Decode) 模块设计文档

> **依赖**：Assassyn Framework
> **组成**：`ID.py` (主流水线模块), `control_signals.py` (包含 Record 定义)

## 1. 模块概述

ID 模块是流水线的**控制中心**。它的核心职责是将从取指阶段（IF）获取的原始二进制指令流，翻译为后续流水线阶段（EX, MEM, WB）所需的结构化控制信号和数据操作数。

该设计采用 **解耦（Decoupled）** 思想，将复杂的指令解析逻辑收敛在 ID 阶段，向后传递正交化的控制信号包，并采用嵌套 Record 结构实现信号在流水线各级的逐层剥离。

## 2. 数据结构：控制信号包 (Control Packets)

采用 **嵌套 Record** 结构，实现控制信号的分层管理。以下定义置于 `control_signals.py`。

### 2.1 写回域 (`WbCtrl`)

Record至少需要包含两个字段，因此 `rd_addr` 不定义为 `Record`

```python
rd_addr    = Bits(5)       # 目标寄存器索引，如果是0拒绝写入。
```

### 2.2 访存域 (`MemCtrl`)
```python
mem_ctrl_signals = Record(
    mem_opcode   = Bits(3), # 内存操作，使用 Bits(3) 静态定义 (NONE:Bits(3)(0b001), LOAD:Bits(3)(0b010), STORE:Bits(3)(0b100))
    mem_width    = Bits(3), # 访问宽度，使用 Bits(3) 静态定义 (BYTE:Bits(3)(0b001), HALF:Bits(3)(0b010), WORD:Bits(3)(0b100))
    mem_unsigned = Bits(1), # 是否无符号扩展 (LBU/LHU)
    rd_addr = Bits(5)       # 【嵌套】携带 WB 级信号
)
```

### 2.3 执行域 (`ExCtrl`)
```python
ex_ctrl_signals = Record(
    alu_func = Bits(16),   # ALU 功能码，使用 Bits(16) 静态定义 (ADD:Bits(16)(0b0000000000000001), SUB:Bits(16)(0b0000000000000010), ...)
    rs1_sel  = Bits(3),    # rs1结果来源，使用 Bits(3) 静态定义 (RS1:Bits(3)(0b001), EX_MEM_BYPASS:Bits(3)(0b010), MEM_WB_BYPASS:Bits(3)(0b100))
    rs2_sel  = Bits(3),    # rs2结果来源，使用 Bits(3) 静态定义 (RS2:Bits(3)(0b001), EX_MEM_BYPASS:Bits(3)(0b010), MEM_WB_BYPASS:Bits(3)(0b100))
    op1_sel  = Bits(3),    # 操作数1来源，使用 Bits(3) 静态定义 (RS1:Bits(3)(0b001), PC:Bits(3)(0b010), ZERO:Bits(3)(0b100))
    op2_sel  = Bits(3),    # 操作数2来源，使用 Bits(3) 静态定义 (RS2:Bits(3)(0b001), IMM:Bits(3)(0b010), CONST_4:Bits(3)(0b100))
    is_branch = Bits(1),    # 是否跳转 (Branch 指令)
    is_jtype = Bits(1),     # 是否直接跳转 (JAL/JALR 指令)
    is_jalr  = Bits(1),     # 是否是 JALR 指令
    next_pc_addr = Bits(32),  # 预测结果：下一条指令的地址
    mem_ctrl = mem_ctrl_signals  # 【嵌套】携带 MEM 级信号
)
```

## 3. 接口定义

### 3.1 类定义与端口 (`__init__`)

ID 模块作为标准的 `Module`，通过端口接收来自 IF 阶段的流式数据（主要是 PC，指令通常通过共享 SRAM 接口获取）。

```python
class Decoder(Module):
    def __init__(self):
        super().__init__(
            ports={
                # 来自 IF 阶段的 PC 值（用于 JAL/Branch 计算或传递给 EX 级）
                'pc': Port(Bits(32)),
            }
        )
        self.name = 'ID'
```

### 3.2 构建参数 (`build`)

`build` 函数描述了 ID 模块与其他组件的物理连接。

| 参数名          | 类型         | 描述                                                |
| :-------------- | :----------- | :-------------------------------------------------- |
| **executor**    | `Module`     | 下一级流水线（EX），用于发送打包好的控制/数据包。   |
| **hazard_unit** | `Downstream` | 数据冒险检测单元，用于处理 Stall 和记分牌更新。     |
| **icache_data** | `Array`      | SRAM (ICache) 的输出端口 (`dout`)，即原始指令数据。 |
| **reg_file**    | `Array`      | 通用寄存器堆，用于读取 `rs1` 和 `rs2` 的源数据。    |

```python
@module.combinational
def build(self, executor: Module, hazard_unit: Downstream, icache_data: Array, reg_file: Array):
    # 实现逻辑见下文
```

## 4. 内部实现逻辑 (`build` 流程)

### 1. 切片与预处理 (Physical Slicing)

把 32 位 `inst` 拆解为所有可能的零件。

```python
# 1. 基础字段
opcode = inst[0:6]
rd     = inst[7:11]
funct3 = inst[12:14]
rs1    = inst[15:19]
rs2    = inst[20:24]
funct7 = inst[25:31]

# 2. 特殊位 (用于区分 SRAI/SRLI 等)
# 移位指令的区分位通常在 inst[30]
func7_bit30 = inst[30:30]

# 3. 立即数并行生成 (全部算好)
imm_i, imm_s, imm_b, imm_u, imm_j = gen_all_immediates(inst)
```

#### 2. 查表与控制包生成 (The Loop & `|=`)

利用预定义的指令真值表 `instructions_table`，对每条指令进行匹配，并累加生成控制信号包。这一步利用 Python 的循环来生成巨大的 Mux 逻辑。

```python
# 初始化累加器 (默认全 0)
alu_func_acc  = Bits(16)(0)
op1_sel_acc   = Bits(3)(0) # 使用 Bits(3) 静态定义
op2_sel_acc   = Bits(3)(0) # 使用 Bits(3) 静态定义
imm_val_acc   = Bits(32)(0)
is_load_acc   = Bits(1)(0)
# ... 其他信号 ...

# 遍历真值表
for entry in instructions_table:
    # A. 匹配逻辑
    # 依次进行 Opcode, Funct3, Bit30 的匹配
    match = (opcode == entry.op) & ... 
    
    # B. 信号累加 (你的核心思路)
    # 利用 Select + Or 实现 Mux
    alu_func_acc |= match.select(entry.alu_func, 0)
    op1_sel_acc  |= match.select(entry.op1_sel, 0)
    
    # C. 立即数选择
    # 如果匹配，把对应的立即数 (如 imm_i) 累加进来
    imm_val_acc  |= match.select(entry.imm_src, 0)
```

#### 3. 冒险检测 (Hazard Interaction)

在数据打包发送之前，先解决“能不能发”和“怎么发”的问题。

```python
# 1. 调用 Hazard Unit
# 输入：当前指令的 rs1, rs2 (物理切片得到的)
#      以及回传回来的 EX/MEM/WB 状态
stall_req, fwd_op1, fwd_op2 = hazard_unit.build(rs1, rs2, ...)

# 2. 执行流控 (Rigid Pipeline)
# 如果 stall_req 为真，冻结 ID 级 (不 pop FIFO，不更新内部状态)
wait_until(~stall_req)

# 3. 处理 NOP 注入
# 如果 Stall，向 EX 发送 NOP 包；否则发送正常包
packet_valid = ~stall_req
```

#### 4. 打包与分发 (Dispatch)
最后，将计算好的 **“控制语义”** 和 **“前瞻决策”** 一起发给 EX。

```python
# 构造发送给 EX 的控制包 (ex_ctrl_t)
ex_ctrl_payload = ex_ctrl_signals.bundle(
    # 语义控制
    alu_func = alu_func_acc,
    rs1_sel = fwd_op1,
    rs2_sel = fwd_op2,
    op1_sel = op1_sel_acc,
    op2_sel = op2_sel_acc,
    
    # 下级控制
    mem_ctrl = ...
)

# 物理发送 (接口分离)
executor.async_called(
    ctrl = packet_valid.select(ex_ctrl_payload, NOP_CTRL), # NOP 注入，对应一个常量控制包，对应指令 ADD，向x0写入。
    pc   = current_pc,
    rs1_data = reg_file[rs1],
    rs2_data = reg_file[rs2],
    imm  = imm_val_acc
)
```

## 指令表详细定义

> 助记符定义应当放置在`control_signals.py`中，指令真值表放置在`instructions_table.py`中。与`ID.py`同级目录，以形成逻辑分离。

### 第一部分：助记符与控制信号定义 (`control_signals.py`)

这里定义了所有控制信号的枚举值，对应于 `ex_ctrl_signals` 和 `mem_ctrl_signals` 中的位宽定义。

```python
from assassyn.frontend import Bits

# 1. 基础物理常量
# 指令 Opcode (7-bit)
OP_R_TYPE   = Bits(7)(0b0110011) # ADD, SUB...
OP_I_TYPE   = Bits(7)(0b0010011) # ADDI...
OP_LOAD     = Bits(7)(0b0000011) # LB, LW...
OP_STORE    = Bits(7)(0b0100011) # SB, SW...
OP_BRANCH   = Bits(7)(0b1100011) # BEQ...
OP_JAL      = Bits(7)(0b1101111)
OP_JALR     = Bits(7)(0b1100111)
OP_LUI      = Bits(7)(0b0110111)
OP_AUIPC    = Bits(7)(0b0010111)
OP_SYSTEM   = Bits(7)(0b1110011) # ECALL, EBREAK

# 立即数类型 (用于生成器选择切片逻辑)
class ImmType:
    R = Bits(6)(0b100000) # 无立即数
    I = Bits(6)(0b010000)
    S = Bits(6)(0b001000)
    B = Bits(6)(0b000100)
    U = Bits(6)(0b000010)
    J = Bits(6)(0b000001)

# 2. 执行阶段控制信号 (EX Control)
# ALU 功能码 (使用 Bits(16) 静态定义)
# 顺序对应 alu_func[i]
class ALUOp:
    ADD  = Bits(16)(0b0000000000000001)
    SUB  = Bits(16)(0b0000000000000010)
    SLL  = Bits(16)(0b0000000000000100)
    SLT  = Bits(16)(0b0000000000001000)
    SLTU = Bits(16)(0b0000000000010000)
    XOR  = Bits(16)(0b0000000000100000)
    SRL  = Bits(16)(0b0000000001000000)
    SRA  = Bits(16)(0b0000000010000000)
    OR   = Bits(16)(0b0000000100000000)
    AND  = Bits(16)(0b0000001000000000)
    # 占位/直通/特殊用途
    NOP    = Bits(16)(0b1000000000000000)

class Rs1Sel:
    RS1        = Bits(3)(0b001)
    EX_MEM_BYPASS = Bits(3)(0b010)
    MEM_WB_BYPASS = Bits(3)(0b100)

class Rs2Sel:
    RS2 = Bits(3)(0b001)
    EX_MEM_BYPASS = Bits(3)(0b010)
    MEM_WB_BYPASS = Bits(3)(0b100)

# 操作数 1 选择 (使用 Bits(3) 静态定义)
# 对应: real_rs1, pc, 0
class Op1Sel:
    RS1  = Bits(3)(0b001)
    PC   = Bits(3)(0b010)
    ZERO = Bits(3)(0b100)

# 操作数 2 选择 (使用 Bits(3) 静态定义)
# 对应: real_rs2, imm, 4
class Op2Sel:
    RS2  = Bits(3)(0b001)
    IMM  = Bits(3)(0b010)
    CONST_4 = Bits(3)(0b100)

# 3. 访存与写回控制信号 (MEM/WB Control)

# 访存操作 (Bits(3))
class MemOp:
    NONE  = Bits(3)(0b001)
    LOAD  = Bits(3)(0b010)
    STORE = Bits(3)(0b100)

# 访存宽度 (Bits(3))
class MemWidth:
    BYTE = Bits(3)(0b001)
    HALF = Bits(3)(0b010)
    WORD = Bits(3)(0b100)

# 符号扩展 (Bits(1))
class MemSign:
    SIGNED   = 0
    UNSIGNED = 1

# 写回使能 (隐式：通过将 RD 设为 0 来禁用写回，这里仅作逻辑标记)
class WB:
    YES = 1
    NO  = 0

# Rs 使用标志 (用于判断是否使用 Rs 寄存器，防止虚假冒险)
class RsUse:
    NO  = 0  # 不使用
    YES = 1  # 使用
```

### 第二部分：指令真值表 (`instructions_table.py`)

这张表是 Decoder 的核心。它包含了两部分：
1.  **Check Part (匹配键)**：Opcode, Func3, Func7_Bit30。
2.  **Info Part (控制值)**：所有后级流水线需要的控制信号。

**特殊说明**：
*   `Bit30`: 对于 `ADD/SUB` 和 `SRL/SRA`，Opcode 和 Funct3 是一样的，必须检查指令的第 30 位（即 `inst[30]`）。我们用 `0` 或 `1` 表示必须匹配该位，`None` 表示忽略。

```python
from ctrl_consts import *

# 表格列定义:
# Key, Opcode, Funct3, Bit30, ImmType | ALU_Func, Rs1_use, Rs2_use, Op1, Op2, Mem_Op, Width, Sign, WB, Branch, Jump, Jalr

rv32i_table = [
    
    # --- R-Type ---
    ('add',    OP_R_TYPE, 0x0,  0,    ImmType.R, ALUOp.ADD, RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,  0, 0, WB.YES, 0, 0, 0),
    ('sub',    OP_R_TYPE, 0x0,  1,    ImmType.R, ALUOp.SUB, RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,  0, 0, WB.YES, 0, 0, 0),
    ('sll',    OP_R_TYPE, 0x1,  0,    ImmType.R, ALUOp.SLL, RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,  0, 0, WB.YES, 0, 0, 0),
    ('slt',    OP_R_TYPE, 0x2,  0,    ImmType.R, ALUOp.SLT, RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,  0, 0, WB.YES, 0, 0, 0),
    ('sltu',   OP_R_TYPE, 0x3,  0,    ImmType.R, ALUOp.SLTU, RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,  0, 0, WB.YES, 0, 0, 0),
    ('xor',    OP_R_TYPE, 0x4,  0,    ImmType.R, ALUOp.XOR, RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,  0, 0, WB.YES, 0, 0, 0),
    ('srl',    OP_R_TYPE, 0x5,  0,    ImmType.R, ALUOp.SRL, RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,  0, 0, WB.YES, 0, 0, 0),
    ('sra',    OP_R_TYPE, 0x5,  1,    ImmType.R, ALUOp.SRA, RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,  0, 0, WB.YES, 0, 0, 0),
    ('or',     OP_R_TYPE, 0x6,  0,    ImmType.R, ALUOp.OR,  RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,  0, 0, WB.YES, 0, 0, 0),
    ('and',    OP_R_TYPE, 0x7,  0,    ImmType.R, ALUOp.AND, RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,  0, 0, WB.YES, 0, 0, 0),

    # --- I-Type (ALU) ---
    ('addi',   OP_I_TYPE, 0x0,  None, ImmType.I, ALUOp.ADD, RsUse.YES, RsUse.NO,  Op1Sel.RS1, Op2Sel.IMM, MemOp.NONE,  0, 0, WB.YES, 0, 0, 0),
    ('slti',   OP_I_TYPE, 0x2,  None, ImmType.I, ALUOp.SLT, RsUse.YES, RsUse.NO,  Op1Sel.RS1, Op2Sel.IMM, MemOp.NONE,  0, 0, WB.YES, 0, 0, 0),
    ('sltiu',  OP_I_TYPE, 0x3,  None, ImmType.I, ALUOp.SLTU, RsUse.YES, RsUse.NO,  Op1Sel.RS1, Op2Sel.IMM, MemOp.NONE,  0, 0, WB.YES, 0, 0, 0),
    ('xori',   OP_I_TYPE, 0x4,  None, ImmType.I, ALUOp.XOR, RsUse.YES, RsUse.NO,  Op1Sel.RS1, Op2Sel.IMM, MemOp.NONE,  0, 0, WB.YES, 0, 0, 0),
    ('ori',    OP_I_TYPE, 0x6,  None, ImmType.I, ALUOp.OR,  RsUse.YES, RsUse.NO,  Op1Sel.RS1, Op2Sel.IMM, MemOp.NONE,  0, 0, WB.YES, 0, 0, 0),
    ('andi',   OP_I_TYPE, 0x7,  None, ImmType.I, ALUOp.AND, RsUse.YES, RsUse.NO,  Op1Sel.RS1, Op2Sel.IMM, MemOp.NONE,  0, 0, WB.YES, 0, 0, 0),
    # Shift Imm (Bit30 distinguishes Logic/Arith shift)
    ('slli',   OP_I_TYPE, 0x1,  0,    ImmType.I, ALUOp.SLL, RsUse.YES, RsUse.NO,  Op1Sel.RS1, Op2Sel.IMM, MemOp.NONE,  0, 0, WB.YES, 0, 0, 0),
    ('srli',   OP_I_TYPE, 0x5,  0,    ImmType.I, ALUOp.SRL, RsUse.YES, RsUse.NO,  Op1Sel.RS1, Op2Sel.IMM, MemOp.NONE,  0, 0, WB.YES, 0, 0, 0),
    ('srai',   OP_I_TYPE, 0x5,  1,    ImmType.I, ALUOp.SRA, RsUse.YES, RsUse.NO,  Op1Sel.RS1, Op2Sel.IMM, MemOp.NONE,  0, 0, WB.YES, 0, 0, 0),

    # --- I-type (Load) ---
    # ALU 计算地址 (RS1 + Imm)，Mem 读取
    ('lb',     OP_LOAD,   0x0,  None, ImmType.I, ALUOp.ADD, RsUse.YES, RsUse.NO,  Op1Sel.RS1, Op2Sel.IMM, MemOp.LOAD,  MemWidth.BYTE, MemSign.SIGNED,   WB.YES, 0, 0, 0),
    ('lh',     OP_LOAD,   0x1,  None, ImmType.I, ALUOp.ADD, RsUse.YES, RsUse.NO,  Op1Sel.RS1, Op2Sel.IMM, MemOp.LOAD,  MemWidth.HALF, MemSign.SIGNED,   WB.YES, 0, 0, 0),
    ('lw',     OP_LOAD,   0x2,  None, ImmType.I, ALUOp.ADD, RsUse.YES, RsUse.NO,  Op1Sel.RS1, Op2Sel.IMM, MemOp.LOAD,  MemWidth.WORD, MemSign.SIGNED,   WB.YES, 0, 0, 0),
    ('lbu',    OP_LOAD,   0x4,  None, ImmType.I, ALUOp.ADD, RsUse.YES, RsUse.NO,  Op1Sel.RS1, Op2Sel.IMM, MemOp.LOAD,  MemWidth.BYTE, MemSign.UNSIGNED, WB.YES, 0, 0, 0),
    ('lhu',    OP_LOAD,   0x5,  None, ImmType.I, ALUOp.ADD, RsUse.YES, RsUse.NO,  Op1Sel.RS1, Op2Sel.IMM, MemOp.LOAD,  MemWidth.HALF, MemSign.UNSIGNED, WB.YES, 0, 0, 0),

    # --- S-type (Store) ---
    # ALU 计算地址 (RS1 + Imm)，Mem 写入
    ('sb',     OP_STORE,  0x0,  None, ImmType.S, ALUOp.ADD, RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.IMM, MemOp.STORE, MemWidth.BYTE, 0, WB.NO,  0, 0, 0),
    ('sh',     OP_STORE,  0x1,  None, ImmType.S, ALUOp.ADD, RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.IMM, MemOp.STORE, MemWidth.HALF, 0, WB.NO,  0, 0, 0),
    ('sw',     OP_STORE,  0x2,  None, ImmType.S, ALUOp.ADD, RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.IMM, MemOp.STORE, MemWidth.WORD, 0, WB.NO,  0, 0, 0),

    # --- Branch ---
    # ALU 做比较 (Sub/Cmp)，PC Adder 算目标 (PC+Imm)，不写回
    ('beq',    OP_BRANCH, 0x0,  None, ImmType.B, ALUOp.SUB, RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE, 0, 0, WB.NO, 1, 0, 0),
    ('bne',    OP_BRANCH, 0x1,  None, ImmType.B, ALUOp.SUB, RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE, 0, 0, WB.NO, 1, 0, 0),
    ('blt',    OP_BRANCH, 0x4,  None, ImmType.B, ALUOp.SLT, RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE, 0, 0, WB.NO, 1, 0, 0),
    ('bge',    OP_BRANCH, 0x5,  None, ImmType.B, ALUOp.SLT, RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE, 0, 0, WB.NO, 1, 0, 0),
    ('bltu',   OP_BRANCH, 0x6,  None, ImmType.B, ALUOp.SLTU, RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE, 0, 0, WB.NO, 1, 0, 0),
    ('bgeu',   OP_BRANCH, 0x7,  None, ImmType.B, ALUOp.SLTU, RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE, 0, 0, WB.NO, 1, 0, 0),

    # --- JAL ---
    # ALU: PC + 4 (Link Data -> WB)
    # Tgt: PC + Imm (Jump Target -> IF)
    ('jal',    OP_JAL,    None, None, ImmType.J, ALUOp.ADD, RsUse.NO,  RsUse.NO,  Op1Sel.PC,  Op2Sel.CONST_4, MemOp.NONE, 0, 0, WB.YES, 1, 1, 0),

    # --- JALR ---
    # ALU: PC + 4 (Link Data -> WB)
    # Tgt: RS1 + Imm (Jump Target -> IF)
    ('jalr',   OP_JALR,   0x0,  None, ImmType.I, ALUOp.ADD, RsUse.YES, RsUse.NO,  Op1Sel.PC,  Op2Sel.CONST_4, MemOp.NONE, 0, 0, WB.YES, 1, 1, 1),

    # --- U-Type ---
    # LUI:   ALU 算 0 + Imm
    ('lui',    OP_LUI,    None, None, ImmType.U, ALUOp.ADD, RsUse.NO,  RsUse.NO,  Op1Sel.ZERO, Op2Sel.IMM, MemOp.NONE, 0, 0, WB.YES, 0, 0, 0),
    # AUIPC: ALU 算 PC + Imm
    ('auipc',  OP_AUIPC,  None, None, ImmType.U, ALUOp.ADD, RsUse.NO,  RsUse.NO,  Op1Sel.PC,  Op2Sel.IMM, MemOp.NONE, 0, 0, WB.YES, 0, 0, 0),

    # --- Environment (ECALL/EBREAK) ---
    # 作为特殊 I-Type 处理，但这里只给基本信号，具体逻辑由 Decoder/Execution 中的 finish() 逻辑拦截，直接停止模拟。
    ('ecall',  OP_SYSTEM, 0x0,  None, ImmType.I, ALUOp.NOP, RsUse.NO,  RsUse.NO,  Op1Sel.RS1, Op2Sel.IMM, MemOp.NONE, 0, 0, WB.NO, 0, 0, 0),
    ('ebreak', OP_SYSTEM, 0x0,  None, ImmType.I, ALUOp.NOP, RsUse.NO,  RsUse.NO,  Op1Sel.RS1, Op2Sel.IMM, MemOp.NONE, 0, 0, WB.NO, 0, 0, 0),
]
```