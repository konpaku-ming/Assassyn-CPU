from .control_signals import *

# RV32I 指令真值表
# 表格列定义:
# Key, Opcode, Funct3, Bit30, Bit25, ImmType | ALU_Func, Op1, Op2, Mem_Op, Width, Sign, WB, branch_type, div_op

rv32i_table = [

    # --- R-Type ---
    # For R-type instructions, bit25=0 distinguishes them from M-extension (bit25=1)
    ('add', OP_R_TYPE, 0x0, 0, 0, ImmType.R, ALUOp.ADD, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    ('sub', OP_R_TYPE, 0x0, 1, 0, ImmType.R, ALUOp.SUB, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    ('sll', OP_R_TYPE, 0x1, 0, 0, ImmType.R, ALUOp.SLL, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    ('slt', OP_R_TYPE, 0x2, 0, 0, ImmType.R, ALUOp.SLT, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    ('sltu', OP_R_TYPE, 0x3, 0, 0, ImmType.R, ALUOp.SLTU, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    ('xor', OP_R_TYPE, 0x4, 0, 0, ImmType.R, ALUOp.XOR, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    ('srl', OP_R_TYPE, 0x5, 0, 0, ImmType.R, ALUOp.SRL, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    ('sra', OP_R_TYPE, 0x5, 1, 0, ImmType.R, ALUOp.SRA, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    ('or', OP_R_TYPE, 0x6, 0, 0, ImmType.R, ALUOp.OR, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    ('and', OP_R_TYPE, 0x7, 0, 0, ImmType.R, ALUOp.AND, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),

    # --- M-Extension (Multiply) ---
    # funct7 = 0x01 (bit25 = 1, bit30 = 0)
    ('mul', OP_R_TYPE, 0x0, 0, 1, ImmType.R, ALUOp.MUL, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    ('mulh', OP_R_TYPE, 0x1, 0, 1, ImmType.R, ALUOp.MULH, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    ('mulhsu', OP_R_TYPE, 0x2, 0, 1, ImmType.R, ALUOp.MULHSU, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    ('mulhu', OP_R_TYPE, 0x3, 0, 1, ImmType.R, ALUOp.MULHU, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),

    # --- M-Extension (Divide) ---
    # funct7 = 0x01 (bit25 = 1, bit30 = 0)
    ('div', OP_R_TYPE, 0x4, 0, 1, ImmType.R, ALUOp.ADD, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.DIV),
    ('divu', OP_R_TYPE, 0x5, 0, 1, ImmType.R, ALUOp.ADD, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.DIVU),
    ('rem', OP_R_TYPE, 0x6, 0, 1, ImmType.R, ALUOp.ADD, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.REM),
    ('remu', OP_R_TYPE, 0x7, 0, 1, ImmType.R, ALUOp.ADD, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.REMU),

    # --- I-Type (ALU) ---
    ('addi', OP_I_TYPE, 0x0, None, None, ImmType.I, ALUOp.ADD, Op1Sel.RS1, Op2Sel.IMM, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    ('slti', OP_I_TYPE, 0x2, None, None, ImmType.I, ALUOp.SLT, Op1Sel.RS1, Op2Sel.IMM, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    ('sltiu', OP_I_TYPE, 0x3, None, None, ImmType.I, ALUOp.SLTU, Op1Sel.RS1, Op2Sel.IMM, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    ('xori', OP_I_TYPE, 0x4, None, None, ImmType.I, ALUOp.XOR, Op1Sel.RS1, Op2Sel.IMM, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    ('ori', OP_I_TYPE, 0x6, None, None, ImmType.I, ALUOp.OR, Op1Sel.RS1, Op2Sel.IMM, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    ('andi', OP_I_TYPE, 0x7, None, None, ImmType.I, ALUOp.AND, Op1Sel.RS1, Op2Sel.IMM, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    # Shift Imm (Bit30 distinguishes Logic/Arith shift)
    ('slli', OP_I_TYPE, 0x1, None, None, ImmType.I, ALUOp.SLL, Op1Sel.RS1, Op2Sel.IMM, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    ('srli', OP_I_TYPE, 0x5, 0, None, ImmType.I, ALUOp.SRL, Op1Sel.RS1, Op2Sel.IMM, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    ('srai', OP_I_TYPE, 0x5, 1, None, ImmType.I, ALUOp.SRA, Op1Sel.RS1, Op2Sel.IMM, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),

    # --- I-type (Load) ---
    # ALU 计算地址 (RS1 + Imm)，Mem 读取
    ('lb', OP_LOAD, 0x0, None, None, ImmType.I, ALUOp.ADD, Op1Sel.RS1, Op2Sel.IMM, MemOp.LOAD,
     MemWidth.BYTE, MemSign.SIGNED, WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    ('lh', OP_LOAD, 0x1, None, None, ImmType.I, ALUOp.ADD, Op1Sel.RS1, Op2Sel.IMM, MemOp.LOAD,
     MemWidth.HALF, MemSign.SIGNED, WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    ('lw', OP_LOAD, 0x2, None, None, ImmType.I, ALUOp.ADD, Op1Sel.RS1, Op2Sel.IMM, MemOp.LOAD,
     MemWidth.WORD, MemSign.SIGNED, WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    ('lbu', OP_LOAD, 0x4, None, None, ImmType.I, ALUOp.ADD, Op1Sel.RS1, Op2Sel.IMM, MemOp.LOAD,
     MemWidth.BYTE, MemSign.UNSIGNED, WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    ('lhu', OP_LOAD, 0x5, None, None, ImmType.I, ALUOp.ADD, Op1Sel.RS1, Op2Sel.IMM, MemOp.LOAD,
     MemWidth.HALF, MemSign.UNSIGNED, WB.YES, BranchType.NO_BRANCH, DivOp.NONE),

    # --- S-type (Store) ---
    # ALU 计算地址 (RS1 + Imm)，Mem 写入
    ('sb', OP_STORE, 0x0, None, None, ImmType.S, ALUOp.ADD, Op1Sel.RS1, Op2Sel.IMM, MemOp.STORE,
     MemWidth.BYTE, Bits(1)(0), WB.NO, BranchType.NO_BRANCH, DivOp.NONE),
    ('sh', OP_STORE, 0x1, None, None, ImmType.S, ALUOp.ADD, Op1Sel.RS1, Op2Sel.IMM, MemOp.STORE,
     MemWidth.HALF, Bits(1)(0), WB.NO, BranchType.NO_BRANCH, DivOp.NONE),
    ('sw', OP_STORE, 0x2, None, None, ImmType.S, ALUOp.ADD, Op1Sel.RS1, Op2Sel.IMM, MemOp.STORE,
     MemWidth.WORD, Bits(1)(0), WB.NO, BranchType.NO_BRANCH, DivOp.NONE),

    # --- Branch ---
    # ALU 做比较 (Sub/Cmp)，PC Adder 算目标 (PC+Imm)，不写回
    ('beq', OP_BRANCH, 0x0, None, None, ImmType.B, ALUOp.SUB, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.NO, BranchType.BEQ, DivOp.NONE),
    ('bne', OP_BRANCH, 0x1, None, None, ImmType.B, ALUOp.SUB, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.NO, BranchType.BNE, DivOp.NONE),
    ('blt', OP_BRANCH, 0x4, None, None, ImmType.B, ALUOp.SLT, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.NO, BranchType.BLT, DivOp.NONE),
    ('bge', OP_BRANCH, 0x5, None, None, ImmType.B, ALUOp.SLT, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.NO, BranchType.BGE, DivOp.NONE),
    ('bltu', OP_BRANCH, 0x6, None, None, ImmType.B, ALUOp.SLTU, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.NO, BranchType.BLTU, DivOp.NONE),
    ('bgeu', OP_BRANCH, 0x7, None, None, ImmType.B, ALUOp.SLTU, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.NO, BranchType.BGEU, DivOp.NONE),

    # --- JAL ---
    # ALU: PC + 4 (Link Data -> WB)
    # Tgt: PC + Imm (Jump Target -> IF)
    ('jal', OP_JAL, None, None, None, ImmType.J, ALUOp.ADD, Op1Sel.PC, Op2Sel.CONST_4, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.JAL, DivOp.NONE),

    # --- JALR ---
    # ALU: PC + 4 (Link Data -> WB)
    # Tgt: RS1 + Imm (Jump Target -> IF)
    ('jalr', OP_JALR, 0x0, None, None, ImmType.I, ALUOp.ADD, Op1Sel.PC, Op2Sel.CONST_4, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.JALR, DivOp.NONE),

    # --- U-Type ---
    # LUI:   ALU 算 0 + Imm
    ('lui', OP_LUI, None, None, None, ImmType.U, ALUOp.ADD, Op1Sel.ZERO, Op2Sel.IMM, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),
    # AUIPC: ALU 算 PC + Imm
    ('auipc', OP_AUIPC, None, None, None, ImmType.U, ALUOp.ADD, Op1Sel.PC, Op2Sel.IMM, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH, DivOp.NONE),

    # --- Environment (ECALL/EBREAK) ---
    # 由 Execution 中的 finish() 逻辑拦截，直接停止模拟。
    ('ecall', OP_SYSTEM, 0x0, 0, None, ImmType.I, ALUOp.SYS, Op1Sel.RS1, Op2Sel.IMM, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.NO, BranchType.NO_BRANCH, DivOp.NONE),
    # ebreak 编码仅立即数字段不同，这里沿用相同的解码路径，便于 halt 处理
    ('ebreak', OP_SYSTEM, 0x0, 0, None, ImmType.I, ALUOp.SYS, Op1Sel.RS1, Op2Sel.IMM, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.NO, BranchType.NO_BRANCH, DivOp.NONE),
]
