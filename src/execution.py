from assassyn.frontend import *
from .control_signals import *


class Execution(Module):
    def __init__(self):
        super().__init__(
            ports={
                # --- [1] 控制通道 (Control Plane) ---
                # 包含 alu_func, op1_sel, op2_sel, is_branch, is_write
                # 以及嵌套的 mem_ctrl
                "ctrl": Port(ex_ctrl_signals),
                # --- [2] 数据通道群 (Data Plane) ---
                # 当前指令地址 (用于 Branch/AUIPC/JAL)
                "pc": Port(Bits(32)),
                # 源寄存器 1 数据 (来自 RegFile)
                "rs1_data": Port(Bits(32)),
                # 源寄存器 2 数据 (来自 RegFile)
                "rs2_data": Port(Bits(32)),
                # 立即数 (在 ID 级已完成符号扩展)
                "imm": Port(Bits(32)),
            }
        )
        self.name = "EX"

    @module.combinational
    def build(
        self,
        mem_module: Module,  # 下一级流水线 (MEM)
        # --- 旁路数据源 (Forwarding Sources) ---
        ex_mem_bypass: Array,  # 来自 EX-MEM 旁路寄存器的数据（上条指令结果）
        mem_wb_bypass: Array,  # 来自 MEM-WB 旁路寄存器的数据 (上上条指令结果)
        # --- 分支反馈 ---
        branch_target_reg: Array,  # 用于通知 IF 跳转目标的全局寄存器
        dcache: SRAM,  # SRAM 模块引用 (用于Store操作)
    ):
        # 1. 弹出所有端口数据
        # 根据 __init__ 定义顺序解包
        ctrl = self.ctrl.pop()
        pc = self.pc.pop()
        rs1 = self.rs1_data.pop()
        rs2 = self.rs2_data.pop()
        imm = self.imm.pop()

        # 获取旁路数据
        fwd_from_mem = ex_mem_bypass[0]
        fwd_from_wb = mem_wb_bypass[0]

        # --- rs1 旁路处理 ---
        real_rs1 = ctrl.rs1_sel.select1hot(rs1, fwd_from_mem, fwd_from_wb)

        # --- rs2 旁路处理 ---
        real_rs2 = ctrl.rs2_sel.select1hot(rs2, fwd_from_mem, fwd_from_wb)

        # --- 操作数 1 选择 ---
        alu_op1 = ctrl.op1_sel.select1hot(
            real_rs1, pc, Bits(32)(0)  # 0  # 1 (AUIPC/JAL/Branch)  # 2 (LUI Link)
        )

        # --- 操作数 2 选择 ---
        alu_op2 = ctrl.op2_sel.select1hot(
            real_rs2, imm, Bits(32)(4)  # 0  # 1  # 2 (JAL/JALR Link)
        )

        # --- ALU 计算 ---
        # 1. 基础运算
        # 转换为有符号数进行加减法运算
        op1_signed = alu_op1.bitcast(SInt(32))
        op2_signed = alu_op2.bitcast(SInt(32))

        # 加法
        add_res = (op1_signed + op2_signed).bitcast(Bits(32))

        # 减法
        sub_res = (op1_signed - op2_signed).bitcast(Bits(32))

        # 逻辑与
        and_res = alu_op1 & alu_op2

        # 逻辑或
        or_res = alu_op1 | alu_op2

        # 逻辑异或
        xor_res = alu_op1 ^ alu_op2

        # 逻辑左移 (使用低5位作为移位位数)
        sll_res = alu_op1 << alu_op2[4:0]

        # 逻辑右移 (使用低5位作为移位位数)
        srl_res = alu_op1 >> alu_op2[4:0]

        # 算术右移 (使用低5位作为移位位数)
        sra_res = op1_signed >> alu_op2[4:0]
        sra_res = sra_res.bitcast(Bits(32))

        # 有符号比较小于
        slt_res = (op1_signed < op2_signed).bitcast(Bits(32))

        # 无符号比较小于
        sltu_res = (alu_op1 < alu_op2).bitcast(Bits(32))

        # 2. 结果选择
        alu_result = ctrl.alu_func.select1hot(
            add_res,  # ADD
            sub_res,  # SUB
            sll_res,  # SLL
            slt_res,  # SLT
            sltu_res,  # SLTU
            xor_res,  # XOR
            srl_res,  # SRL
            sra_res,  # SRA
            or_res,  # OR
            and_res,  # AND
            alu_op2,  # NOP (直接输出操作数2)
            alu_op2,  # 占位
            alu_op2,  # 占位
            alu_op2,  # 占位
            alu_op2,  # 占位
            alu_op2,  # 占位
        )

        # 3. 驱动本级 Bypass 寄存器 (向 ID 级提供数据)
        # 这样下一拍 ID 级就能看到这条指令的结果了
        ex_mem_bypass[0] = alu_result

        # --- 访存操作 (Store Handling) ---
        # 仅在 is_write (Store) 为真时驱动 SRAM 的 WE
        # 地址是 ALU 计算结果，数据是经过 Forwarding 的 rs2
        is_store = ctrl.mem_ctrl.mem_opcode == MemOp.STORE
        is_load = ctrl.mem_ctrl.mem_opcode == MemOp.LOAD

        # 直接调用 dcache.build 处理 SRAM 操作
        dcache.build(
            we=is_store,  # 写使能信号（对于Store指令）
            wdata=real_rs2,  # 写入数据（经过Forwarding的rs2）
            addr=alu_result,  # 地址（ALU计算结果）
            re=is_load,  # 读使能信号（对于Load指令）
        )

        # --- 分支处理 (Branch Handling) ---
        # 1. 使用专用加法器计算跳转地址，对于 JALR，基址是 rs1；对于 JAL/Branch，基址是 PC
        is_jalr = ctrl.branch_type == BranchType.JALR
        target_base = is_jalr.select(pc, real_rs1)  # 0: Branch / JAL  # 1: JALR

        # 专用加法器永远做 Base + Imm
        calc_target = target_base + imm

        # 2. 计算分支条件
        # 对于 BEQ: alu_result == 0
        # 对于 BNE: alu_result != 0
        # 对于 BLT: alu_result[0] == 1
        # 对于 BGE: alu_result[0] == 0
        # 对于 BLTU: alu_result[0] == 1
        # 对于 BGEU: alu_result[0] == 0
        is_taken = Bits(1)(0)
        is_branch = (
            (ctrl.branch_type == BranchType.BEQ)
            | (ctrl.branch_type == BranchType.BNE)
            | (ctrl.branch_type == BranchType.BLT)
            | (ctrl.branch_type == BranchType.BGE)
            | (ctrl.branch_type == BranchType.BLTU)
            | (ctrl.branch_type == BranchType.BGEU)
        )

        with Condition(is_branch):
            # 根据不同的分支类型判断分支条件
            is_eq = alu_result == Bits(32)(0)
            is_lt = alu_result[31:31] == Bits(1)(1)  # 符号位为1表示小于

            # BEQ, BNE 使用等于判断
            is_taken_eq = (ctrl.branch_type == BranchType.BEQ) & is_eq
            is_taken_ne = (ctrl.branch_type == BranchType.BNE) & ~is_eq

            # BLT, BGE 使用小于判断
            is_taken_lt = (ctrl.branch_type == BranchType.BLT) & is_lt
            is_taken_ge = (ctrl.branch_type == BranchType.BGE) & ~is_lt

            # BLTU, BGEU 使用无符号小于判断
            is_taken_ltu = (ctrl.branch_type == BranchType.BLTU) & is_lt
            is_taken_geu = (ctrl.branch_type == BranchType.BGEU) & ~is_lt

            is_taken = (
                is_taken_eq
                | is_taken_ne
                | is_taken_lt
                | is_taken_ge
                | is_taken_ltu
                | is_taken_geu
            )

        # 3. 根据指令类型决定最终的下一 PC 地址
        is_branch_or_jump = (
            (ctrl.branch_type == BranchType.BEQ)
            | (ctrl.branch_type == BranchType.BNE)
            | (ctrl.branch_type == BranchType.BLT)
            | (ctrl.branch_type == BranchType.BGE)
            | (ctrl.branch_type == BranchType.BLTU)
            | (ctrl.branch_type == BranchType.BGEU)
            | (ctrl.branch_type == BranchType.JAL)
            | (ctrl.branch_type == BranchType.JALR)
        )

        final_next_pc = is_branch_or_jump.select(
            is_taken.select(
                calc_target,  # Taken
                pc + Bits(32)(4),  # Not Taken
            ),
            ctrl.next_pc_addr,
        )

        # 4. 写入分支目标寄存器，供 IF 级使用
        branch_miss = final_next_pc != ctrl.next_pc_addr
        branch_target_reg[0] = branch_miss.select(
            final_next_pc,  # 跳转，写入目标地址
            Bits(32)(0),  # 不跳转，写 0 表示顺序执行
        )

        # --- 下一级绑定与状态反馈 ---
        # 构造发送给 MEM 的包
        # 只有两个参数：控制 + 统一数据
        mem_call = mem_module.async_called(ctrl=ctrl.mem_ctrl, alu_result=alu_result)
        mem_call.bind.set_fifo_depth(ctrl=1, alu_result=1)

        # 3. 返回状态 (供 HazardUnit 窃听)
        # rd_addr 用于记分牌/依赖检测
        # is_load 用于检测 Load-Use 冒险
        return ctrl.mem_ctrl.rd_addr, is_load
