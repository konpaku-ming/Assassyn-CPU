# RV32I ID (Instruction Decode) 模块设计文档

> **依赖**：Assassyn Framework, `control_signals.py`, `instruction_table.py`
> **组成**：`decoder.py` (主流水线模块)

## 1. 模块概述

ID 模块是流水线的**控制中心**。它的核心职责是将从取指阶段（IF）获取的原始二进制指令流，翻译为后续流水线阶段（EX, MEM, WB）所需的结构化控制信号和数据操作数。

该设计采用 **解耦（Decoupled）** 思想，将复杂的指令解析逻辑收敛在 ID 阶段，向后传递正交化的控制信号包，并采用嵌套 Record 结构实现信号在流水线各级的逐层剥离。

由于 Assassyn 对 Module 接收信号的限制，该设计将 ID 模块拆分成两部分：

*   **Decoder (Module)**：
    *   **职责**：物理切片 (Slicing) + 真值表查表 (Look-up) + 读取寄存器堆。
    *   **产出**：`alu_func`, `div_op`, `op_sel`, `imm`, `rs1_data`, `rs2_data` 等预解码包。

*   **DecoderImpl (Downstream)**：
    *   **职责**：接收 Hazard Unit 反馈 + NOP Mux + 发送控制包到 EX 级。
    *   **输入**：接收 Decoder 产出 + Hazard Unit 反馈。
    *   **输出**：将所有控制信息打包并发送给 EX 级。

## 2. 数据结构：控制信号包 (Control Packets)

采用 **嵌套 Record** 结构，实现控制信号的分层管理。以下定义置于 `control_signals.py`。

### 2.1 写回域 (`wb_ctrl_signals`)

```python
wb_ctrl_signals = Record(
    rd_addr=Bits(5),    # 目标寄存器索引，如果是0拒绝写入。
    halt_if=Bits(1),    # 是否触发仿真终止 (ECALL/EBREAK/sb x0, (-1)x0)
)
```

### 2.2 访存域 (`mem_ctrl_signals`)

```python
mem_ctrl_signals = Record(
    mem_opcode=Bits(3),    # 内存操作，独热码 (NONE:0b001, LOAD:0b010, STORE:0b100)
    mem_width=Bits(3),     # 访问宽度，独热码 (BYTE:0b001, HALF:0b010, WORD:0b100)
    mem_unsigned=Bits(1),  # 是否无符号扩展 (LBU/LHU)
    wb_ctrl=wb_ctrl_signals,  # 【嵌套】携带 WB 级信号
)
```

### 2.3 执行域 (`ex_ctrl_signals`)

```python
ex_ctrl_signals = Record(
    alu_func=Bits(16),     # ALU 功能码 (独热码)
    div_op=Bits(5),        # M扩展除法操作 (独热码：NONE/DIV/DIVU/REM/REMU)
    rs1_sel=Bits(4),       # rs1结果来源 (RS1/EX_BYPASS/MEM_BYPASS/WB_BYPASS)
    rs2_sel=Bits(4),       # rs2结果来源 (RS2/EX_BYPASS/MEM_BYPASS/WB_BYPASS)
    op1_sel=Bits(3),       # 操作数1来源 (RS1/PC/ZERO)
    op2_sel=Bits(3),       # 操作数2来源 (RS2/IMM/CONST_4)
    branch_type=Bits(16),  # Branch 指令功能码 (独热码)
    next_pc_addr=Bits(32), # 预测结果：下一条指令的地址
    mem_ctrl=mem_ctrl_signals,  # 【嵌套】携带 MEM 级信号
)
```

### 2.4 ID 阶段内部信号包 (`pre_decode_t`)

```python
pre_decode_t = Record(
    # 原始控制信号
    alu_func=Bits(16),
    div_op=Bits(5),        # M扩展除法操作 (独热码)
    op1_sel=Bits(3),
    op2_sel=Bits(3),
    branch_type=Bits(16),
    next_pc_addr=Bits(32),
    # 嵌套的后续阶段控制
    mem_ctrl=mem_ctrl_signals,
    # 原始数据需求
    pc=Bits(32),
    rs1_data=Bits(32),
    rs2_data=Bits(32),
    imm=Bits(32),
)
```

## 3. 接口定义

### 3.1 Decoder 类定义与端口

```python
class Decoder(Module):
    def __init__(self):
        super().__init__(
            ports={
                "pc": Port(Bits(32)),       # 来自 IF 阶段的 PC 值
                "next_pc": Port(Bits(32)),  # 来自 IF 阶段的预测下一 PC
                "stall": Port(Bits(1)),     # 来自 IF 阶段的 Stall 信号
            }
        )
        self.name = "Decoder"
```

### 3.2 Decoder 构建参数

| 参数名 | 类型 | 描述 |
| :--- | :--- | :--- |
| **icache_dout** | `Array` | SRAM 的输出端口，即原始指令数据。 |
| **reg_file** | `Array` | 通用寄存器堆，用于读取 `rs1` 和 `rs2` 的源数据。 |

```python
@module.combinational
def build(self, icache_dout: Array, reg_file: Array):
    # 返回: 预解码包, rs1索引, rs2索引
    return pre, rs1, rs2
```

### 3.3 DecoderImpl 构建参数

```python
class DecoderImpl(Downstream):
    @downstream.combinational
    def build(
        self,
        pre: Record,              # 来自 Decoder Shell 的静态数据
        executor: Module,         # 下一级流水线 (EX)
        rs1_sel: Bits(4),         # DataHazardUnit 反馈的 rs1 旁路选择
        rs2_sel: Bits(4),         # DataHazardUnit 反馈的 rs2 旁路选择
        stall_if: Bits(1),        # 流水线 Stall 信号
        branch_target_reg: Array, # 分支目标寄存器 (用于 Flush 检测)
    ):
```

## 4. 内部实现逻辑

### 4.1 指令获取与预处理

```python
# 获取基础输入
pc_val, next_pc_val, stall_if = self.pop_all_ports(False)

# 从 SRAM 输出获取指令
icache_inst = icache_dout[0].bitcast(Bits(32))

# 使用寄存器保持 Stall 时的指令稳定
last_ins_reg = RegArray(Bits(32), 1, initializer=[0])
raw_inst = stall_if.select(last_ins_reg[0], icache_inst)
last_ins_reg[0] <= raw_inst

# 将初始化时出现的 0b0 指令替换为 NOP
inst = (raw_inst == Bits(32)(0)).select(Bits(32)(0x00000013), raw_inst)

# 检测停机指令 (ecall/ebreak/sb x0, -1(x0))
halt_if = (
    (inst == Bits(32)(0x00000073))
    | (inst == Bits(32)(0x00100073))
    | (inst == Bits(32)(0xFE000FA3))
)
```

### 4.2 切片与预处理 (Physical Slicing)

```python
# 基础字段
opcode = inst[0:6]
rd = inst[7:11]
funct3 = inst[12:14]
rs1 = inst[15:19]
rs2 = inst[20:24]
bit25 = inst[25:25]  # funct7[0] - 区分 M扩展和 R-type
bit30 = inst[30:30]

# 立即数并行生成
sign = inst[31:31]
imm_i = concat(pad_20, inst[20:31])
imm_s = concat(pad_20, inst[25:31], inst[7:11])
imm_b = concat(pad_19, inst[31:31], inst[7:7], inst[25:30], inst[8:11], Bits(1)(0))
imm_u = concat(inst[12:31], Bits(12)(0))
imm_j = concat(pad_11, inst[31:31], inst[12:19], inst[20:20], inst[21:30], Bits(1)(0))
```

### 4.3 查表与控制包生成

使用预定义的指令真值表 `rv32i_table` 进行匹配和信号累加：

```python
for entry in rv32i_table:
    (_, t_op, t_f3, t_b30, t_b25, t_imm_type, t_alu, t_op1, t_op2,
     t_mem_op, t_mem_wid, t_mem_sgn, t_wb, t_br, t_div_op) = entry

    # 匹配逻辑
    match_if = opcode == t_op
    if t_f3 is not None:
        match_if &= funct3 == Bits(3)(t_f3)
    if t_b30 is not None:
        match_if &= bit30 == Bits(1)(t_b30)
    if t_b25 is not None:
        match_if &= bit25 == Bits(1)(t_b25)

    # 信号累加 (使用 select + OR 实现 Mux)
    acc_alu_func |= match_if.select(t_alu, Bits(16)(0))
    acc_div_op |= match_if.select(t_div_op, Bits(5)(0))
    # ... 其他信号
```

### 4.4 默认值处理

确保所有独热码信号在无匹配时有有效默认值：

```python
acc_alu_func = (acc_alu_func == Bits(16)(0)).select(ALUOp.NOP, acc_alu_func)
acc_op1_sel = (acc_op1_sel == Bits(3)(0)).select(Op1Sel.RS1, acc_op1_sel)
acc_div_op = (acc_div_op == Bits(5)(0)).select(DivOp.NONE, acc_div_op)
# ...
```

### 4.5 DecoderImpl: NOP 注入与分发

```python
# 检测 Flush 和 Stall 条件
flush_if = branch_target_reg[0] != Bits(32)(0)
nop_if = flush_if | stall_if

# NOP 注入：将控制信号替换为无效值
final_rd = nop_if.select(Bits(5)(0), wb_ctrl.rd_addr)
final_halt_if = nop_if.select(Bits(1)(0), wb_ctrl.halt_if)
final_mem_opcode = nop_if.select(MemOp.NONE, mem_ctrl.mem_opcode)
final_alu_func = nop_if.select(ALUOp.NOP, pre.alu_func)
final_div_op = nop_if.select(DivOp.NONE, pre.div_op)
final_branch_type = nop_if.select(BranchType.NO_BRANCH, pre.branch_type)

# 向 EX 发送数据 (刚性流水线)
call = executor.async_called(
    ctrl=final_ex_ctrl,
    pc=pre.pc,
    rs1_data=pre.rs1_data,
    rs2_data=pre.rs2_data,
    imm=pre.imm,
)
```

## 5. 支持的指令集

ID 模块支持完整的 **RV32IM** 指令集：

### 5.1 RV32I 基础指令

| 类型 | 指令 |
| :--- | :--- |
| R-Type | add, sub, sll, slt, sltu, xor, srl, sra, or, and |
| I-Type (ALU) | addi, slti, sltiu, xori, ori, andi, slli, srli, srai |
| I-Type (Load) | lb, lh, lw, lbu, lhu |
| S-Type (Store) | sb, sh, sw |
| B-Type (Branch) | beq, bne, blt, bge, bltu, bgeu |
| J-Type | jal |
| I-Type (JALR) | jalr |
| U-Type | lui, auipc |
| System | ecall, ebreak |

### 5.2 M扩展 (乘除法指令)

| 类型 | 指令 | 描述 |
| :--- | :--- | :--- |
| Multiply | mul | 有符号乘法，返回低32位 |
| Multiply | mulh | 有符号乘法，返回高32位 |
| Multiply | mulhsu | 有符号×无符号乘法，返回高32位 |
| Multiply | mulhu | 无符号乘法，返回高32位 |
| Divide | div | 有符号除法 |
| Divide | divu | 无符号除法 |
| Divide | rem | 有符号取余 |
| Divide | remu | 无符号取余 |

## 6. 指令表详细定义

指令真值表位于 `instruction_table.py`，格式如下：

```python
# 表格列定义:
# Key, Opcode, Funct3, Bit30, Bit25, ImmType | ALU_Func, Op1, Op2, Mem_Op, Width, Sign, WB, branch_type, div_op

rv32i_table = [
    # --- R-Type ---
    ('add', OP_R_TYPE, 0x0, 0, 0, ImmType.R, ALUOp.ADD, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    # ...

    # --- M-Extension (Multiply) ---
    ('mul', OP_R_TYPE, 0x0, 0, 1, ImmType.R, ALUOp.MUL, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    # ...

    # --- M-Extension (Divide) ---
    ('div', OP_R_TYPE, 0x4, 0, 1, ImmType.R, ALUOp.ADD, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.DIV),
    # ...
]
```

**特殊说明**：
*   `Bit30`: 用于区分 `ADD/SUB` 和 `SRL/SRA`。
*   `Bit25`: 用于区分 R-Type 基础指令和 M 扩展指令（funct7[0]）。
*   `DivOp`: M 扩展除法操作的独热码编码。
