from assassyn.frontend import *
from .control_signals import *
from .instruction_table import rv32i_table


# 辅助函数：生成填充位
def get_pad(width, hex_mask, sign):
    return sign.select(Bits(width)(hex_mask), Bits(width)(0))


class Decoder(Module):
    def __init__(self):
        super().__init__(
            ports={
                "pc": Port(Bits(32)),
                "next_pc": Port(Bits(32)),
            }
        )
        self.name = "Decoder"

    @module.combinational
    def build(self, icache_dout: Array, reg_file: Array):

        # 1. 获取基础输入
        pc_val, next_pc_val = self.pop_all_ports(False)
        # 从 SRAM 输出获取指令
        raw_inst = icache_dout[0].bitcast(Bits(32))
        # 将初始化时出现的 0b0 指令替换为 NOP
        inst = (raw_inst == Bits(32)(0)).select(Bits(32)(0x00000013), raw_inst)
        log("ID: Fetched Instruction=0x{:x} at PC=0x{:x}", inst, pc_val)

        # 2. 物理切片
        opcode = inst[0:6]
        rd = inst[7:11]
        funct3 = inst[12:14]
        rs1 = inst[15:19]
        rs2 = inst[20:24]
        bit30 = inst[30:30]

        # 3. 立即数并行生成
        sign = inst[31:31]

        # I-Type: [31]*20 | [31:20]
        pad_20 = get_pad(20, 0xFFFFF, sign)
        imm_i = concat(pad_20, inst[20:31])

        # S-Type: [31]*20 | [31:25] | [11:7]
        imm_s = concat(pad_20, inst[25:31], inst[7:11])

        # B-Type: [31]*19 | [31] | [7] | [30:25] | [11:8] | 0
        pad_19 = get_pad(19, 0x7FFFF, sign)
        imm_b = concat(
            pad_19, inst[31:31], inst[7:7], inst[25:30], inst[8:11], Bits(1)(0)
        )

        # U-Type: [31:12] | 0*12
        imm_u = concat(inst[12:31], Bits(12)(0))

        # J-Type: [31]*11 | [31] | [19:12] | [20] | [30:21] | 0
        pad_11 = get_pad(11, 0x7FF, sign)
        imm_j = concat(
            pad_11, inst[31:31], inst[12:19], inst[20:20], inst[21:30], Bits(1)(0)
        )

        # 4. 查表译码 (Signal Accumulation Loop)

        # 初始化累加器
        acc_alu_func = Bits(16)(0)
        acc_op1_sel = Bits(3)(0)
        acc_op2_sel = Bits(3)(0)
        acc_imm = Bits(32)(0)
        acc_br_type = Bits(16)(0)

        acc_mem_op = Bits(3)(0)
        acc_mem_wid = Bits(3)(0)
        acc_mem_uns = Bits(1)(0)
        acc_wb_en = Bits(1)(0)

        acc_rs1_used = Bits(1)(0)
        acc_rs2_used = Bits(1)(0)

        match_if = Bits(1)(0)

        for entry in rv32i_table:
            (
                _,
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
            match_if = opcode == t_op

            if t_f3 is not None:
                match_if &= funct3 == Bits(3)(t_f3)

            if t_b30 is not None:
                match_if &= bit30 == Bits(1)(t_b30)

            # --- B. 信号累加 (Mux Logic) ---
            # 使用 select 实现 OR 逻辑
            acc_alu_func |= match_if.select(t_alu, Bits(16)(0))
            acc_rs1_used |= match_if.select(Bits(1)(t_rs1_use), Bits(1)(0))
            acc_rs2_used |= match_if.select(Bits(1)(t_rs2_use), Bits(1)(0))
            acc_op1_sel |= match_if.select(t_op1, Bits(3)(0))
            acc_op2_sel |= match_if.select(t_op2, Bits(3)(0))
            acc_mem_op |= match_if.select(t_mem_op, Bits(3)(0))
            acc_mem_wid |= match_if.select(t_mem_wid, Bits(3)(0))
            acc_mem_uns |= match_if.select(t_mem_sgn, Bits(1)(0))
            acc_wb_en |= match_if.select(Bits(1)(t_wb), Bits(1)(0))
            acc_br_type |= match_if.select(t_br, Bits(16)(0))
            imm = t_imm_type.select1hot(
                Bits(32)(0),
                imm_i,
                imm_s,
                imm_b,
                imm_u,
                imm_j,
            )
            acc_imm |= match_if.select(imm, Bits(32)(0))

        # 5. 读取寄存器堆 & 打包
        raw_rs1_data = reg_file[rs1]
        raw_rs2_data = reg_file[rs2]

        # 处理 rd: 如果不需要写回，强制为 0 (Implicit Write Enable)
        final_rd = acc_wb_en.select(rd, Bits(5)(0))

        # 构造预解码包
        mem_ctrl_t = mem_ctrl_signals.bundle(
            mem_opcode=acc_mem_op,
            mem_width=acc_mem_wid,
            mem_unsigned=acc_mem_uns,
            rd_addr=final_rd,
        )

        pre = pre_decode_t.bundle(
            alu_func=acc_alu_func,
            op1_sel=acc_op1_sel,
            op2_sel=acc_op2_sel,
            branch_type=acc_br_type,
            next_pc_addr=next_pc_val,
            mem_ctrl=mem_ctrl_t,
            imm=acc_imm,
            pc=pc_val,
            rs1_data=raw_rs1_data,
            rs2_data=raw_rs2_data,
        )

        # 添加日志信息
        log(
            "Control signals: alu_func=0x{:x} op1_sel=0x{:x} op2_sel=0x{:x} branch_type=0x{:x} mem_op=0x{:x} mem_wid=0x{:x} mem_uns=0x{:x} rd=0x{:x} rs1_used=0x{:x} rs2_used=0x{:x}",
            acc_alu_func,
            acc_op1_sel,
            acc_op2_sel,
            acc_br_type,
            acc_mem_op,
            acc_mem_wid,
            acc_mem_uns,
            final_rd,
            acc_rs1_used,
            acc_rs2_used,
        )
        log(
            "Forwarding data: imm=0x{:x} pc=0x{:x} rs1_data=0x{:x} rs2_data=0x{:x}",
            acc_imm,
            pc_val,
            raw_rs1_data,
            raw_rs2_data,
        )

        # 返回: 预解码包, 冒险检测需要的原始信号
        return pre, rs1, rs2, acc_rs1_used, acc_rs2_used


class DecoderImpl(Downstream):
    def __init__(self):
        super().__init__()
        self.name = "Decoder_Impl"

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
        stall_if: Bits(1),
        branch_target_reg: Array,
    ):
        mem_ctrl = mem_ctrl_signals.view(pre.mem_ctrl)

        flush_if = branch_target_reg[0] != Bits(32)(0)
        nop_if = flush_if | stall_if

        final_rd = nop_if.select(Bits(5)(0), mem_ctrl.rd_addr)
        final_mem_opcode = nop_if.select(MemOp.NONE, mem_ctrl.mem_opcode)
        final_alu_func = nop_if.select(ALUOp.NOP, pre.alu_func)
        final_branch_type = nop_if.select(BranchType.NO_BRANCH, pre.branch_type)

        with Condition(nop_if == Bits(1)(1)):
            log(
                "ID: Inserting NOP (Stall={} Flush={})",
                stall_if == Bits(1)(1),
                flush_if == Bits(1)(1),
            )

        final_mem_ctrl = mem_ctrl_signals.bundle(
            mem_opcode=final_mem_opcode,
            mem_width=mem_ctrl.mem_width,
            mem_unsigned=mem_ctrl.mem_unsigned,
            rd_addr=final_rd,
        )
        final_ex_ctrl = ex_ctrl_signals.bundle(
            alu_func=final_alu_func,
            op1_sel=pre.op1_sel,
            op2_sel=pre.op2_sel,
            rs1_sel=rs1_sel,
            rs2_sel=rs2_sel,
            branch_type=final_branch_type,
            next_pc_addr=pre.next_pc_addr,
            mem_ctrl=final_mem_ctrl,
        )

        log(
            "Output: alu_func=0x{:x} rs1_sel=0x{:x} rs2_sel=0x{:x} branch_type=0x{:x} mem_op=0x{:x} rd=0x{:x}",
            pre.alu_func,
            rs1_sel,
            rs2_sel,
            pre.branch_type,
            mem_ctrl.mem_opcode,
            mem_ctrl.rd_addr,
        )

        # 无论是否 Stall，都向 EX 发送数据 (刚性流水线)
        # 如果是 NOP，数据线上的值(pc, imm等)是无意义的，EX 不会使用
        call = executor.async_called(
            ctrl=final_ex_ctrl,
            pc=pre.pc,
            rs1_data=pre.rs1_data,
            rs2_data=pre.rs2_data,
            imm=pre.imm,
        )
        call.bind.set_fifo_depth(ctrl=1, pc=1, rs1_data=1, rs2_data=1, imm=1)
