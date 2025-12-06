from assassyn.frontend import *
from .control_signals import *
from .instruction_table import rv32i_table


class Decoder(Module):
    def __init__(self):
        super().__init__(ports={"pc": Port(Bits(32))})
        self.name = "ID_Shell"

    @module.combinational
    def build(self, icache_dout: Array, reg_file: Array):

        # 1. 获取基础输入
        pc_val = self.pc.pop()
        # 从 SRAM 输出获取指令
        inst = icache_dout[0].bitcast(Bits(32))

        # 2. 物理切片
        opcode = inst[0:6]
        rd = inst[7:11]
        funct3 = inst[12:14]
        rs1 = inst[15:19]
        rs2 = inst[20:24]
        bit30 = inst[30:30]

        # 3. 立即数并行生成
        sign = inst[31:31]

        # 辅助函数：生成填充位
        def get_pad(width, hex_mask):
            return sign.select(Bits(width)(hex_mask), Bits(width)(0))

        # I-Type: [31]*20 | [31:20]
        pad_20 = get_pad(20, 0xFFFFF)
        imm_i = pad_20.concat(inst[20:31])

        # S-Type: [31]*20 | [31:25] | [11:7]
        imm_s = pad_20.concat(inst[25:31], inst[7:11])

        # B-Type: [31]*19 | [31] | [7] | [30:25] | [11:8] | 0
        pad_19 = get_pad(19, 0x7FFFF)
        imm_b = pad_19.concat(
            inst[31:31], inst[7:7], inst[25:30], inst[8:11], Bits(1)(0)
        )

        # U-Type: [31:12] | 0*12
        imm_u = inst[12:31].concat(Bits(12)(0))

        # J-Type: [31]*11 | [31] | [19:12] | [20] | [30:21] | 0
        pad_11 = get_pad(11, 0x7FF)
        imm_j = pad_11.concat(
            inst[31:31], inst[12:19], inst[20:20], inst[21:30], Bits(1)(0)
        )

        # 立即数映射表
        imm_map = {
            ImmType.R: Bits(32)(0),
            ImmType.I: imm_i,
            ImmType.S: imm_s,
            ImmType.B: imm_b,
            ImmType.U: imm_u,
            ImmType.J: imm_j,
        }

        # 4. 查表译码 (Signal Accumulation Loop)

        # 初始化累加器
        acc_alu_func = Bits(16)(0)
        acc_op1_sel = Bits(3)(0)
        acc_op2_sel = Bits(3)(0)
        acc_tgt_sel = Bits(1)(0)
        acc_br_type = Bits(16)(0)

        acc_mem_op = Bits(3)(0)
        acc_mem_wid = Bits(3)(0)
        acc_mem_uns = Bits(1)(0)
        acc_wb_en = Bits(1)(0)

        acc_rs1_used = Bits(1)(0)
        acc_rs2_used = Bits(1)(0)

        acc_imm = Bits(32)(0)

        for entry in rv32i_table:
            (
                mn,
                t_op,
                t_f3,
                t_b30,
                t_imm_type,
                t_alu,
                t_rs1_use,
                t_rs2_use,
                t_op1,
                t_op2,
                t_mem_op,
                t_mem_wid,
                t_mem_sgn,
                t_wb,
                t_br,
            ) = entry

            # --- A. 匹配逻辑 ---
            match = opcode == t_op

            if t_f3 is not None:
                match &= funct3 == t_f3

            if t_b30 is not None:
                match &= bit30 == Bits(1)(t_b30)

            # --- B. 信号累加 (Mux Logic) ---
            # 使用 select 实现 OR 逻辑
            acc_alu_func |= match.select(t_alu, 0)
            acc_rs1_used |= match.select(Bits(1)(t_rs1_use), 0)
            acc_rs2_used |= match.select(Bits(1)(t_rs2_use), 0)
            acc_op1_sel |= match.select(t_op1, 0)
            acc_op2_sel |= match.select(t_op2, 0)
            acc_mem_op |= match.select(t_mem_op, 0)
            acc_mem_wid |= match.select(t_mem_wid, 0)
            acc_mem_uns |= match.select(Bits(1)(t_mem_sgn), 0)
            acc_wb_en |= match.select(Bits(1)(t_wb), 0)
            acc_br_type |= match.select(t_br, 0)
            # 立即数选择
            current_imm_wire = imm_map[t_imm_type]
            acc_imm |= match.select(current_imm_wire, 0)

        # 5. 读取寄存器堆 & 打包
        raw_rs1_data = reg_file[rs1]
        raw_rs2_data = reg_file[rs2]

        # 处理 rd: 如果不需要写回，强制为 0 (Implicit Write Enable)
        final_rd = acc_wb_en.select(rd, Bits(5)(0))

        # 构造预解码包
        pre_pkt = pre_decode_t.bundle(
            alu_func=acc_alu_func,
            op1_sel=acc_op1_sel,
            op2_sel=acc_op2_sel,
            tgt_sel=acc_tgt_sel,
            branch_type=acc_br_type,
            mem_ctrl=mem_ctrl_signals.bundle(
                mem_opcode=acc_mem_op,
                mem_width=acc_mem_wid,
                mem_unsigned=acc_mem_uns,
                rd_addr=final_rd,
            ),
            imm=acc_imm,
            pc=pc_val,
            # 传递原始数据 (Impl 负责修补)
            rs1_data=raw_rs1_data,
            rs2_data=raw_rs2_data,
        )

        # 返回: 预解码包, 冒险检测需要的原始信号
        return pre_pkt, rs1, rs2, acc_rs1_used, acc_rs2_used


class DecoderImpl(Downstream):
    def __init__(self):
        super().__init__()
        self.name = "ID_Impl"

    @downstream.combinational
    def build(
        self,
        # --- 1. 来自 Decoder Shell 的静态数据 (Record) ---
        pre: Record,
        # --- 2. 外部模块引用 ---
        executor: Module,
        # --- 3. DataHazardUnit 反馈信号 ---
        rs1_sel: Bits(4),
        rs2_sel: Bits(4),
        stall_req: Bits(1),
    ):

        real_ctrl = ex_ctrl_signals.bundle(
            # --- 静态部分 (透传) ---
            alu_func=pre.alu_func,
            op1_sel=pre.op1_sel,
            op2_sel=pre.op2_sel,
            branch_type=pre.branch_type,
            # [关键] 透传 Next PC 预测值 (用于 EX 级 BTB 校验)
            next_pc_addr=pre.next_pc_addr,
            # --- 动态部分 (注入 DHU 决策) ---
            # EX 阶段将根据这两个信号控制 ALU 前端的 Mux
            rs1_sel=rs1_sel,
            rs2_sel=rs2_sel,
            # --- 下级控制 ---
            mem_ctrl=pre.mem_ctrl,
        )

        # ======================================================================
        # 4. 刚性流控与 NOP 注入 (Stall Logic)
        # ======================================================================

        # 构造 NOP 包 (气泡)
        # 关键是确保不写回 (rd=0, mem=NONE, branch=NO)
        nop_ctrl = ex_ctrl_signals.const(
            alu_func=ALUOp.NOP,
            rs1_sel=Rs1Sel.RS1,
            rs2_sel=Rs2Sel.RS2,
            op1_sel=Op1Sel.ZERO,
            op2_sel=Op2Sel.IMM,
            branch_type=BranchType.NO_BRANCH,
            next_pc_addr=Bits(32)(0),
            mem_ctrl=mem_ctrl_signals.const(
                mem_opcode=MemOp.NONE,
                mem_width=MemWidth.WORD,
                mem_unsigned=Bits(1)(0),
                rd_addr=Bits(5)(0),  # 核心安全保障
            ),
        )

        # 如果 Stall，发送 NOP；否则发送真实指令
        ctrl_to_send = stall_req.select(nop_ctrl, real_ctrl)

        # ======================================================================
        # 5. 发送与反馈 (Dispatch)
        # ======================================================================

        # 无论是否 Stall，都向 EX 发送数据 (刚性流水线)
        # 如果是 NOP，数据线上的值(pc, imm等)是无意义的，EX 不会使用
        executor.async_called(
            ctrl=ctrl_to_send,
            pc=pre.pc,
            rs1_data=final_rs1,  # 发送修补后的数据
            rs2_data=final_rs2,  # 发送修补后的数据
            imm=pre.imm,
        )

        # 返回 Stall 信号给 IF (FetcherImpl)，用于冻结 PC
        return stall_req
