from assassyn.frontend import *
from .control_signals import *


class Execution(Module):
    def __init__(self):
        super().__init__(
            ports={
                # --- [1] 控制通道 (Control Plane) ---
                # 包含 alu_func, op1_sel, op2_sel, is_branch, is_write 以及嵌套的 mem_ctrl
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
        self.name = "Executor"

    @module.combinational
    def build(
            self,
            mem_module: Module,  # 下一级流水线 (MEM)
            # --- 旁路数据源 (Forwarding Sources) ---
            ex_bypass: Array,  # 来自 EX-MEM 旁路寄存器的数据（上条指令结果）
            mem_bypass: Array,  # 来自 MEM-WB 旁路寄存器的数据 (上上条指令结果)
            wb_bypass: Array,  # 来自 WB 旁路寄存器的数据 (当前写回数据)
            # --- 分支反馈 ---
            branch_target_reg: Array,  # 用于通知 IF 跳转目标的全局寄存器
            dcache: SRAM,  # SRAM 模块引用 (用于Store操作)
            # --- BTB 更新 (可选) ---
            btb_impl: "BTBImpl" = None,  # BTB 实现逻辑
            btb_valid: Array = None,  # BTB 有效位数组
            btb_tags: Array = None,  # BTB 标签数组
            btb_targets: Array = None,  # BTB 目标地址数组
    ):
        # 1. 弹出所有端口数据
        # 根据 __init__ 定义顺序解包
        ctrl, pc, rs1, rs2, imm = self.pop_all_ports(False)
        mem_ctrl = mem_ctrl_signals.view(ctrl.mem_ctrl)

        log(
            "Input: pc=0x{:x} rs1_data=0x{:x} rs2_data=0x{:x} Imm=0x{:x}",
            pc,
            rs1,
            rs2,
            imm,
        )

        # 确定是否要 Flush 指令
        flush_if = branch_target_reg[0] != Bits(32)(0)

        with Condition(flush_if == Bits(1)(1)):
            log("EX: Flush")

        final_rd = flush_if.select(Bits(5)(0), mem_ctrl.rd_addr)
        final_mem_opcode = flush_if.select(Bits(3)(0), mem_ctrl.mem_opcode)

        log(
            "Memory Control after Flush Check: mem_opcode=0x{:x} rd=0x{:x}",
            final_mem_opcode,
            final_rd,
        )

        final_mem_ctrl = mem_ctrl_signals.bundle(
            mem_opcode=final_mem_opcode,
            mem_width=mem_ctrl.mem_width,
            mem_unsigned=mem_ctrl.mem_unsigned,
            rd_addr=final_rd,
        )

        # 获取旁路数据
        fwd_from_mem = ex_bypass[0]
        fwd_from_wb = mem_bypass[0]
        fwd_from_wb_stage = wb_bypass[0]

        # --- rs1 旁路处理 ---
        real_rs1 = ctrl.rs1_sel.select1hot(
            rs1, fwd_from_mem, fwd_from_wb, fwd_from_wb_stage
        )

        # --- rs2 旁路处理 ---
        real_rs2 = ctrl.rs2_sel.select1hot(
            rs2, fwd_from_mem, fwd_from_wb, fwd_from_wb_stage
        )

        # 输出旁路选择日志
        with Condition(ctrl.rs1_sel == Rs1Sel.RS1):
            log("EX: RS1 source: No Bypass")
        with Condition(ctrl.rs1_sel == Rs1Sel.EX_BYPASS):
            log("EX: RS1 source: EX-MEM Bypass (0x{:x})", fwd_from_mem)
        with Condition(ctrl.rs1_sel == Rs1Sel.MEM_BYPASS):
            log("EX: RS1 source: MEM-WB Bypass (0x{:x})", fwd_from_wb)
        with Condition(ctrl.rs1_sel == Rs1Sel.WB_BYPASS):
            log("EX: RS1 source: WB Bypass (0x{:x})", fwd_from_wb_stage)

        with Condition(ctrl.rs2_sel == Rs2Sel.RS2):
            log("EX: RS2 source: No Bypass")
        with Condition(ctrl.rs2_sel == Rs2Sel.EX_BYPASS):
            log("EX: RS2 source: EX-MEM Bypass (0x{:x})", fwd_from_mem)
        with Condition(ctrl.rs2_sel == Rs2Sel.MEM_BYPASS):
            log("EX: RS2 source: MEM-WB Bypass (0x{:x})", fwd_from_wb)
        with Condition(ctrl.rs2_sel == Rs2Sel.WB_BYPASS):
            log("EX: RS2 source: WB Bypass (0x{:x})", fwd_from_wb_stage)

        # --- 操作数 1 选择 ---
        alu_op1 = ctrl.op1_sel.select1hot(
            real_rs1, pc, Bits(32)(0)  # 0  # 1 (AUIPC/JAL/Branch)  # 2 (LUI Link)
        )

        with Condition(ctrl.op1_sel == Op1Sel.RS1):
            log("EX: ALU Op1 source: RS1 (0x{:x})", real_rs1)
        with Condition(ctrl.op1_sel == Op1Sel.PC):
            log("EX: ALU Op1 source: PC (0x{:x})", pc)
        with Condition(ctrl.op1_sel == Op1Sel.ZERO):
            log("EX: ALU Op1 source: ZERO (0x0)")

        # --- 操作数 2 选择 ---
        alu_op2 = ctrl.op2_sel.select1hot(
            real_rs2, imm, Bits(32)(4)  # 0  # 1  # 2 (JAL/JALR Link)
        )

        with Condition(ctrl.op2_sel == Op2Sel.RS2):
            log("EX: ALU Op2 source: RS2 (0x{:x})", real_rs2)
        with Condition(ctrl.op2_sel == Op2Sel.IMM):
            log("EX: ALU Op2 source: IMM (0x{:x})", imm)
        with Condition(ctrl.op2_sel == Op2Sel.CONST_4):
            log("EX: ALU Op2 source: CONST_4 (0x4)")

        # --- ALU 计算 ---
        # 1. 基础运算
        # 转换为有符号数进行加减法运算
        op1_signed = alu_op1.bitcast(Int(32))
        op2_signed = alu_op2.bitcast(Int(32))

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
        sll_res = alu_op1 << alu_op2[0:4]

        # 逻辑右移 (使用低5位作为移位位数)
        srl_res = alu_op1 >> alu_op2[0:4]

        # 算术右移 (使用低5位作为移位位数)
        sra_res = op1_signed >> alu_op2[0:4]
        sra_res = sra_res.bitcast(Bits(32))

        # 有符号比较小于
        slt_res = (op1_signed < op2_signed).bitcast(Bits(32))

        # 无符号比较小于
        sltu_res = (alu_op1 < alu_op2).bitcast(Bits(32))

        # ebreak 停机
        with Condition((ctrl.alu_func == ALUOp.SYS) & ~flush_if):
            log("EBREAK encountered at PC=0x{:x}, halting simulation.", pc)
            finish()

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
            alu_op2,  # SYS
            alu_op2,  # 占位
            alu_op2,  # 占位
            alu_op2,  # 占位
            alu_op2,  # 占位
            alu_op2,  # 占位
        )

        with Condition(ctrl.alu_func == ALUOp.ADD):
            log("EX: ALU Operation: ADD")
        with Condition(ctrl.alu_func == ALUOp.SUB):
            log("EX: ALU Operation: SUB")
        with Condition(ctrl.alu_func == ALUOp.SLL):
            log("EX: ALU Operation: SLL")
        with Condition(ctrl.alu_func == ALUOp.SLT):
            log("EX: ALU Operation: SLT")
        with Condition(ctrl.alu_func == ALUOp.SLTU):
            log("EX: ALU Operation: SLTU")
        with Condition(ctrl.alu_func == ALUOp.XOR):
            log("EX: ALU Operation: XOR")
        with Condition(ctrl.alu_func == ALUOp.SRL):
            log("EX: ALU Operation: SRL")
        with Condition(ctrl.alu_func == ALUOp.SRA):
            log("EX: ALU Operation: SRA")
        with Condition(ctrl.alu_func == ALUOp.OR):
            log("EX: ALU Operation: OR")
        with Condition(ctrl.alu_func == ALUOp.AND):
            log("EX: ALU Operation: AND")
        with Condition(ctrl.alu_func == ALUOp.SYS):
            log("EX: ALU Operation: SYS")
        with Condition(ctrl.alu_func == ALUOp.NOP):
            log("EX: ALU Operation: NOP or Reserved")

        # 3. 更新本级 Bypass 寄存器
        ex_bypass[0] = alu_result
        log("EX: ALU Result: 0x{:x}", alu_result)
        log("EX: Bypass Update: 0x{:x}", alu_result)

        # --- 访存操作 (Store Handling) ---
        # 仅在 is_write (Store) 为真时驱动 SRAM 的 WE
        # 地址是 ALU 计算结果，数据是经过 Forwarding 的 rs2
        is_store = final_mem_ctrl.mem_opcode == MemOp.STORE
        is_load = final_mem_ctrl.mem_opcode == MemOp.LOAD

        with Condition(is_store):
            log("EX: Memory Operation: STORE")
            log("EX: Store Address: 0x{:x}", alu_result)
            log("EX: Store Data: 0x{:x}", real_rs2)
        with Condition(is_load):
            log("EX: Memory Operation: LOAD")
            log("EX: Load Address: 0x{:x}", alu_result)

        # 直接调用 dcache.build 处理 SRAM 操作
        dcache.build(
            we=is_store,  # 写使能信号（对于Store指令）
            wdata=real_rs2,  # 写入数据（经过Forwarding的rs2）
            addr=alu_result[0:15],  # 地址（ALU计算结果转换为字地址）
            re=is_load,  # 读使能信号（对于Load指令）
        )

        # --- 分支处理 (Branch Handling) ---
        # 1. 使用专用加法器计算跳转地址，对于 JALR，基址是 rs1；对于 JAL/Branch，基址是 PC
        is_jalr = ctrl.branch_type == BranchType.JALR
        target_base = is_jalr.select(real_rs1, pc)  # 0: Branch / JAL  # 1: JALR

        # 专用加法器永远做 Base + Imm
        imm_signed = imm.bitcast(Int(32))
        log("EX: Branch Immediate: 0x{:x}", imm)
        target_base_signed = target_base.bitcast(Int(32))
        log("EX: Branch Target Base: 0x{:x}", target_base)
        raw_calc_target = (target_base_signed + imm_signed).bitcast(Bits(32))
        calc_target = is_jalr.select(
            concat(raw_calc_target[1:31], Bits(1)(0)),  # JALR: 目标地址最低位清0
            raw_calc_target,  # Branch / JAL: 直接使用计算结果
        )

        # 2. 计算分支条件
        # 对于 BEQ: alu_result == 0
        # 对于 BNE: alu_result != 0
        # 对于 BLT: alu_result[0] == 1
        # 对于 BGE: alu_result[0] == 0
        # 对于 BLTU: alu_result[0] == 1
        # 对于 BGEU: alu_result[0] == 0
        is_taken = Bits(1)(0)
        is_branch = ctrl.branch_type != BranchType.NO_BRANCH

        # 输出分支类型日志
        with Condition(ctrl.branch_type == BranchType.BEQ):
            log("EX: Branch Type: BEQ")
        with Condition(ctrl.branch_type == BranchType.BNE):
            log("EX: Branch Type: BNE")
        with Condition(ctrl.branch_type == BranchType.BLT):
            log("EX: Branch Type: BLT")
        with Condition(ctrl.branch_type == BranchType.BGE):
            log("EX: Branch Type: BGE")
        with Condition(ctrl.branch_type == BranchType.BLTU):
            log("EX: Branch Type: BLTU")
        with Condition(ctrl.branch_type == BranchType.BGEU):
            log("EX: Branch Type: BGEU")
        with Condition(ctrl.branch_type == BranchType.JAL):
            log("EX: Branch Type: JAL")
        with Condition(ctrl.branch_type == BranchType.JALR):
            log("EX: Branch Type: JALR")
        with Condition(ctrl.branch_type == BranchType.NO_BRANCH):
            log("EX: Branch Type: NO_BRANCH")

        # 根据不同的分支类型判断分支条件
        is_eq = alu_result == Bits(32)(0)
        is_lt = alu_result[0:0] == Bits(1)(1)  # 符号位为1表示小于

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
                | (ctrl.branch_type == BranchType.JAL)
                | is_jalr
        )

        final_next_pc = flush_if.select(
            Bits(32)(0),
            is_branch.select(
                is_taken.select(
                    calc_target,  # Taken
                    (pc.bitcast(UInt(32)) + UInt(32)(4)).bitcast(Bits(32)),  # Not Taken
                ),
                ctrl.next_pc_addr,
            ),
        )

        # 4. 写入分支目标寄存器，供 IF 级使用
        branch_miss = final_next_pc != ctrl.next_pc_addr
        branch_target_reg[0] = branch_miss.select(
            final_next_pc,  # 跳转，写入目标地址
            Bits(32)(0),  # 不跳转，写 0 表示顺序执行
        )

        # 输出分支目标和分支是否跳转的日志
        with Condition(is_branch):
            log("EX: Branch Target: 0x{:x}", calc_target)
            log("EX: Branch Taken: {}", is_taken == Bits(1)(1))

        # 5. 更新 BTB (如果提供了 BTB 引用)
        # 当分支指令 taken 时，更新 BTB 存储 PC -> Target 的映射
        if btb_impl is not None and btb_valid is not None:
            should_update_btb = is_branch & is_taken & ~flush_if
            btb_impl.update(
                pc=pc,
                target=calc_target,
                should_update=should_update_btb,
                btb_valid=btb_valid,
                btb_tags=btb_tags,
                btb_targets=btb_targets,
            )

        # --- 下一级绑定与状态反馈 ---
        # 构造发送给 MEM 的包
        # 只有两个参数：控制 + 统一数据
        mem_call = mem_module.async_called(ctrl=final_mem_ctrl, alu_result=alu_result)
        mem_call.bind.set_fifo_depth(ctrl=1, alu_result=1)

        # 3. 返回状态 (供 HazardUnit 窃听)
        # rd_addr 用于记分牌/依赖检测
        # is_load 用于检测 Load-Use 冒险
        return final_mem_ctrl.rd_addr, is_load
