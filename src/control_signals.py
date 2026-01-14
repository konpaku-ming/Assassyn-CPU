from assassyn.frontend import Bits, Record

# 1. 基础物理常量
# 指令 Opcode (7-bit)
OP_R_TYPE = Bits(7)(0b0110011)  # ADD, SUB...
OP_I_TYPE = Bits(7)(0b0010011)  # ADDI...
OP_LOAD = Bits(7)(0b0000011)  # LB, LW...
OP_STORE = Bits(7)(0b0100011)  # SB, SW...
OP_BRANCH = Bits(7)(0b1100011)  # BEQ...
OP_JAL = Bits(7)(0b1101111)
OP_JALR = Bits(7)(0b1100111)
OP_LUI = Bits(7)(0b0110111)
OP_AUIPC = Bits(7)(0b0010111)
OP_SYSTEM = Bits(7)(0b1110011)  # ECALL, EBREAK


# 立即数类型 (用于生成器选择切片逻辑)
class ImmType:
    R = Bits(6)(0b000001)  # 无立即数
    I = Bits(6)(0b000010)
    S = Bits(6)(0b000100)
    B = Bits(6)(0b001000)
    U = Bits(6)(0b010000)
    J = Bits(6)(0b100000)


# 2. 执行阶段控制信号 (EX Control)
# ALU 功能码 (One-hot 映射, 假设 Bits(16))
# 顺序对应 alu_func[i]
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
    # 占位/直通/特殊用途
    SYS = Bits(16)(0b0000010000000000)
    # M-extension operations (multiply/divide)
    MUL = Bits(16)(0b0000100000000000)     # bit 11: MUL
    MULH = Bits(16)(0b0001000000000000)    # bit 12: MULH
    MULHSU = Bits(16)(0b0010000000000000)  # bit 13: MULHSU
    MULHU = Bits(16)(0b0100000000000000)   # bit 14: MULHU
    NOP = Bits(16)(0b1000000000000000)


# M-extension division operations (1-hot encoding for proper select1hot support)
class DivOp:
    NONE = Bits(5)(0b00001)   # No division operation
    DIV = Bits(5)(0b00010)    # Signed division
    DIVU = Bits(5)(0b00100)   # Unsigned division
    REM = Bits(5)(0b01000)    # Signed remainder
    REMU = Bits(5)(0b10000)   # Unsigned remainder


class BranchType:
    NO_BRANCH = Bits(16)(0b0000000000000001)
    BEQ = Bits(16)(0b0000000000000010)
    BNE = Bits(16)(0b0000000000000100)
    BLT = Bits(16)(0b0000000000001000)
    BGE = Bits(16)(0b0000000000010000)
    BLTU = Bits(16)(0b0000000000100000)
    BGEU = Bits(16)(0b0000000001000000)
    JAL = Bits(16)(0b0000000010000000)
    JALR = Bits(16)(0b0000000100000000)


class Rs1Sel:
    RS1 = Bits(4)(0b0001)
    EX_BYPASS = Bits(4)(0b0010)
    MEM_BYPASS = Bits(4)(0b0100)
    WB_BYPASS = Bits(4)(0b1000)


class Rs2Sel:
    RS2 = Bits(4)(0b0001)
    EX_BYPASS = Bits(4)(0b0010)
    MEM_BYPASS = Bits(4)(0b0100)
    WB_BYPASS = Bits(4)(0b1000)


# 操作数 1 选择 (One-hot, Bits(3))
# 对应: real_rs1, pc, 0
class Op1Sel:
    RS1 = Bits(3)(0b001)
    PC = Bits(3)(0b010)
    ZERO = Bits(3)(0b100)


# 操作数 2 选择 (One-hot, Bits(3))
# 对应: real_rs2, imm, 4
class Op2Sel:
    RS2 = Bits(3)(0b001)
    IMM = Bits(3)(0b010)
    CONST_4 = Bits(3)(0b100)


# 3. 访存与写回控制信号 (MEM/WB Control)


# 访存操作 (Bits(3))
class MemOp:
    NONE = Bits(3)(0b001)
    LOAD = Bits(3)(0b010)
    STORE = Bits(3)(0b100)


# 访存宽度 (Bits(3))
class MemWidth:
    BYTE = Bits(3)(0b001)
    HALF = Bits(3)(0b010)
    WORD = Bits(3)(0b100)


# 符号扩展 (Bits(1))
class MemSign:
    SIGNED = Bits(1)(0b0)
    UNSIGNED = Bits(1)(0b1)


# 写回使能 (隐式：通过将 RD 设为 0 来禁用写回，这里仅作逻辑标记)
class WB:
    YES = 1
    NO = 0


# 4. 控制信号结构定义

# 写回域 (WB Ctrl)
wb_ctrl_signals = Record(
    rd_addr=Bits(5),  # 目标寄存器索引，如果是0拒绝写入。
    halt_if=Bits(1),  # 是否触发仿真终止 (ECALL/EBREAK/sb x0, (-1)x0)
)

# 访存域 (MEM Ctrl)
mem_ctrl_signals = Record(
    mem_opcode=Bits(3),  # 内存操作，独热码 (0:None, 1:Load, 2:Store)
    mem_width=Bits(3),  # 访问宽度，独热码 (0:Byte, 1:Half, 2:Word)
    mem_unsigned=Bits(1),  # 是否无符号扩展 (LBU/LHU)
    wb_ctrl=wb_ctrl_signals,  # 【嵌套】携带 WB 级信号
)

# 执行域 (EX Ctrl)
ex_ctrl_signals = Record(
    # ALU 功能码，使用 Bits(16) 静态定义 (ADD:Bits(16)(0b0000000000000001), SUB:Bits(16)(0b0000000000000010), ...)
    alu_func=Bits(16),
    # M-extension division operation (DIV/DIVU/REM/REMU) - 1-hot encoding with 5 bits
    div_op=Bits(5),
    # rs1结果来源，使用 Bits(4) 静态定义 (RS1:Bits(4)(0b0001), EX_BYPASS:Bits(4)(0b0010), MEM_BYPASS:Bits(4)(0b0100), WB_BYPASS: Bits(4)(0b1000))
    rs1_sel=Bits(4),
    # rs2结果来源，使用 Bits(4) 静态定义 (RS2:Bits(4)(0b0001), EX_BYPASS:Bits(4)(0b0010), MEM_BYPASS:Bits(4)(0b0100), WB_BYPASS:Bits(4)(0b1000))
    rs2_sel=Bits(4),
    # 操作数1来源，使用 Bits(3) 静态定义 (RS1:Bits(3)(0b001), PC:Bits(3)(0b010), ZERO:Bits(3)(0b100))
    op1_sel=Bits(3),
    # 操作数2来源，使用 Bits(3) 静态定义 (RS2:Bits(3)(0b001), IMM:Bits(3)(0b010), CONST_4:Bits(3)(0b100))
    op2_sel=Bits(3),
    branch_type=Bits(16),  # Branch 指令功能码，使用 Bits(16) 静态定义
    next_pc_addr=Bits(32),  # 预测结果：下一条指令的地址
    mem_ctrl=mem_ctrl_signals,  # 【嵌套】携带 MEM 级信号
)

pre_decode_t = Record(
    # 原始控制信号
    alu_func=Bits(16),
    div_op=Bits(5),  # M-extension division operation (1-hot encoding)
    op1_sel=Bits(3),
    op2_sel=Bits(3),
    branch_type=Bits(16),  # Branch 指令功能码
    next_pc_addr=Bits(32),  # IF 预测结果
    # 嵌套的后续阶段控制
    mem_ctrl=mem_ctrl_signals,
    # 原始数据需求
    pc=Bits(32),
    rs1_data=Bits(32),
    rs2_data=Bits(32),
    imm=Bits(32),
)
