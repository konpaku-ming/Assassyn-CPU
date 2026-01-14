from assassyn.frontend import *
from .control_signals import *
from .debug_utils import debug_log
from .multiplier import WallaceTreeMul
from .divider import SRT4Divider


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
        
        # M-extension functional units
        self.multiplier = WallaceTreeMul()
        self.divider = SRT4Divider()

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
        wb_ctrl = wb_ctrl_signals.view(mem_ctrl.wb_ctrl)

        debug_log(
            "Input: pc=0x{:x} rs1_data=0x{:x} rs2_data=0x{:x} Imm=0x{:x}",
            pc,
            rs1,
            rs2,
            imm,
        )

        # 确定是否要 Flush 指令
        flush_if = branch_target_reg[0] != Bits(32)(0)
        with Condition(flush_if == Bits(1)(1)):
            debug_log("EX: Flush")

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
            debug_log("EX: RS1 source: No Bypass")
        with Condition(ctrl.rs1_sel == Rs1Sel.EX_BYPASS):
            debug_log("EX: RS1 source: EX-MEM Bypass (0x{:x})", fwd_from_mem)
        with Condition(ctrl.rs1_sel == Rs1Sel.MEM_BYPASS):
            debug_log("EX: RS1 source: MEM-WB Bypass (0x{:x})", fwd_from_wb)
        with Condition(ctrl.rs1_sel == Rs1Sel.WB_BYPASS):
            debug_log("EX: RS1 source: WB Bypass (0x{:x})", fwd_from_wb_stage)

        with Condition(ctrl.rs2_sel == Rs2Sel.RS2):
            debug_log("EX: RS2 source: No Bypass")
        with Condition(ctrl.rs2_sel == Rs2Sel.EX_BYPASS):
            debug_log("EX: RS2 source: EX-MEM Bypass (0x{:x})", fwd_from_mem)
        with Condition(ctrl.rs2_sel == Rs2Sel.MEM_BYPASS):
            debug_log("EX: RS2 source: MEM-WB Bypass (0x{:x})", fwd_from_wb)
        with Condition(ctrl.rs2_sel == Rs2Sel.WB_BYPASS):
            debug_log("EX: RS2 source: WB Bypass (0x{:x})", fwd_from_wb_stage)

        # --- 操作数 1 选择 ---
        alu_op1 = ctrl.op1_sel.select1hot(
            real_rs1, pc, Bits(32)(0)  # 0  # 1 (AUIPC/JAL/Branch)  # 2 (LUI Link)
        )

        with Condition(ctrl.op1_sel == Op1Sel.RS1):
            debug_log("EX: ALU Op1 source: RS1 (0x{:x})", real_rs1)
        with Condition(ctrl.op1_sel == Op1Sel.PC):
            debug_log("EX: ALU Op1 source: PC (0x{:x})", pc)
        with Condition(ctrl.op1_sel == Op1Sel.ZERO):
            debug_log("EX: ALU Op1 source: ZERO (0x0)")

        # --- 操作数 2 选择 ---
        alu_op2 = ctrl.op2_sel.select1hot(
            real_rs2, imm, Bits(32)(4)  # 0  # 1  # 2 (JAL/JALR Link)
        )

        with Condition(ctrl.op2_sel == Op2Sel.RS2):
            debug_log("EX: ALU Op2 source: RS2 (0x{:x})", real_rs2)
        with Condition(ctrl.op2_sel == Op2Sel.IMM):
            debug_log("EX: ALU Op2 source: IMM (0x{:x})", imm)
        with Condition(ctrl.op2_sel == Op2Sel.CONST_4):
            debug_log("EX: ALU Op2 source: CONST_4 (0x4)")

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
        shamt = alu_op2[0:4].bitcast(UInt(5))
        sll_res = alu_op1 << shamt
        # 逻辑右移 (使用低5位作为移位位数)
        srl_res = alu_op1 >> shamt
        # 算术右移 (使用低5位作为移位位数)
        sra_res = op1_signed >> shamt
        sra_res = sra_res.bitcast(Bits(32))
        # 有符号比较小于
        slt_res = (op1_signed < op2_signed).bitcast(Bits(32))
        # 无符号比较小于
        sltu_res = (alu_op1 < alu_op2).bitcast(Bits(32))

        # ============================================================
        # M-Extension: Multiplication
        # ============================================================
        
        # Check if this is a multiplication instruction
        is_mul = ctrl.alu_func == ALUOp.MUL
        is_mulh = ctrl.alu_func == ALUOp.MULH
        is_mulhsu = ctrl.alu_func == ALUOp.MULHSU
        is_mulhu = ctrl.alu_func == ALUOp.MULHU
        is_mul_op = is_mul | is_mulh | is_mulhsu | is_mulhu
        
        # Check if this is a division instruction
        is_div_op = ctrl.div_op != DivOp.NONE
        
        # Get multiplier busy status
        mul_busy = self.multiplier.is_busy()
        div_busy = self.divider.is_busy()
        
        # Start multiplier if this is a new MUL instruction and multiplier is not busy
        with Condition((is_mul_op == Bits(1)(1)) & (mul_busy == Bits(1)(0)) & (flush_if == Bits(1)(0))):
            # Determine sign configuration based on operation:
            # MUL: signed x signed (returns low 32 bits)
            # MULH: signed x signed (returns high 32 bits)
            # MULHSU: signed x unsigned (returns high 32 bits)
            # MULHU: unsigned x unsigned (returns high 32 bits)
            op1_signed_flag = is_mul | is_mulh | is_mulhsu  # signed for MUL, MULH, MULHSU
            op2_signed_flag = is_mul | is_mulh  # signed for MUL, MULH only
            result_high_flag = is_mulh | is_mulhsu | is_mulhu  # high 32 bits for MULH, MULHSU, MULHU
            
            self.multiplier.start_multiply(
                op1=real_rs1,
                op2=real_rs2,
                op1_signed=op1_signed_flag,
                op2_signed=op2_signed_flag,
                result_high=result_high_flag,
                rd=wb_ctrl.rd_addr
            )
            debug_log("EX: Starting MUL operation, op1=0x{:x}, op2=0x{:x}", real_rs1, real_rs2)
        
        # Start divider if this is a new DIV instruction and divider is not busy
        with Condition((is_div_op == Bits(1)(1)) & (div_busy == Bits(1)(0)) & (flush_if == Bits(1)(0))):
            is_signed_div = (ctrl.div_op == DivOp.DIV) | (ctrl.div_op == DivOp.REM)
            is_rem_op = (ctrl.div_op == DivOp.REM) | (ctrl.div_op == DivOp.REMU)
            
            self.divider.start_divide(
                dividend=real_rs1,
                divisor=real_rs2,
                is_signed=is_signed_div,
                is_rem=is_rem_op,
                rd=wb_ctrl.rd_addr
            )
            debug_log("EX: Starting DIV operation, dividend=0x{:x}, divisor=0x{:x}", real_rs1, real_rs2)
        
        # Run multiplier pipeline stages
        self.multiplier.cycle_m1()
        self.multiplier.cycle_m2()
        self.multiplier.cycle_m3()
        
        # Run divider state machine
        self.divider.tick()
        
        # Get results from multiplier and divider
        mul_ready, mul_result, mul_rd = self.multiplier.get_result_if_ready()
        div_ready, div_result, div_rd, _ = self.divider.get_result_if_ready()
        
        # Clear results when consumed
        with Condition(mul_ready == Bits(1)(1)):
            self.multiplier.clear_result()
            debug_log("EX: MUL result ready: 0x{:x}", mul_result)
        
        with Condition(div_ready == Bits(1)(1)):
            self.divider.clear_result()
            debug_log("EX: DIV result ready: 0x{:x}", div_result)
        
        # 2. 结果选择
        # First, select from basic ALU operations
        alu_result = ctrl.alu_func.select1hot(
            add_res,  # ADD (bit 0)
            sub_res,  # SUB (bit 1)
            sll_res,  # SLL (bit 2)
            slt_res,  # SLT (bit 3)
            sltu_res,  # SLTU (bit 4)
            xor_res,  # XOR (bit 5)
            srl_res,  # SRL (bit 6)
            sra_res,  # SRA (bit 7)
            or_res,  # OR (bit 8)
            and_res,  # AND (bit 9)
            alu_op2,  # SYS (bit 10)
            Bits(32)(0),  # MUL placeholder (bit 11) - actual result from multiplier
            Bits(32)(0),  # MULH placeholder (bit 12)
            Bits(32)(0),  # MULHSU placeholder (bit 13)
            Bits(32)(0),  # MULHU placeholder (bit 14)
            Bits(32)(0),  # NOP (bit 15)
        )
        
        # Select final result: prioritize mul/div results when ready
        # Note: mul and div are mutually exclusive (different instructions), so only one can be ready
        final_result = mul_ready.select(
            mul_result,
            div_ready.select(
                div_result,
                alu_result
            )
        )

        with Condition(ctrl.alu_func == ALUOp.ADD):
            debug_log("EX: ALU Operation: ADD")
        with Condition(ctrl.alu_func == ALUOp.SUB):
            debug_log("EX: ALU Operation: SUB")
        with Condition(ctrl.alu_func == ALUOp.SLL):
            debug_log("EX: ALU Operation: SLL")
        with Condition(ctrl.alu_func == ALUOp.SLT):
            debug_log("EX: ALU Operation: SLT")
        with Condition(ctrl.alu_func == ALUOp.SLTU):
            debug_log("EX: ALU Operation: SLTU")
        with Condition(ctrl.alu_func == ALUOp.XOR):
            debug_log("EX: ALU Operation: XOR")
        with Condition(ctrl.alu_func == ALUOp.SRL):
            debug_log("EX: ALU Operation: SRL")
        with Condition(ctrl.alu_func == ALUOp.SRA):
            debug_log("EX: ALU Operation: SRA")
        with Condition(ctrl.alu_func == ALUOp.OR):
            debug_log("EX: ALU Operation: OR")
        with Condition(ctrl.alu_func == ALUOp.AND):
            debug_log("EX: ALU Operation: AND")
        with Condition(ctrl.alu_func == ALUOp.SYS):
            debug_log("EX: ALU Operation: SYS")
        with Condition(ctrl.alu_func == ALUOp.MUL):
            debug_log("EX: ALU Operation: MUL")
        with Condition(ctrl.alu_func == ALUOp.MULH):
            debug_log("EX: ALU Operation: MULH")
        with Condition(ctrl.alu_func == ALUOp.MULHSU):
            debug_log("EX: ALU Operation: MULHSU")
        with Condition(ctrl.alu_func == ALUOp.MULHU):
            debug_log("EX: ALU Operation: MULHU")
        with Condition(ctrl.alu_func == ALUOp.NOP):
            debug_log("EX: ALU Operation: NOP or Reserved")
        with Condition(ctrl.div_op == DivOp.DIV):
            debug_log("EX: DIV Operation: DIV")
        with Condition(ctrl.div_op == DivOp.DIVU):
            debug_log("EX: DIV Operation: DIVU")
        with Condition(ctrl.div_op == DivOp.REM):
            debug_log("EX: DIV Operation: REM")
        with Condition(ctrl.div_op == DivOp.REMU):
            debug_log("EX: DIV Operation: REMU")

        # 3. 更新本级 Bypass 寄存器
        ex_bypass[0] = final_result
        debug_log("EX: ALU Result: 0x{:x}", final_result)
        debug_log("EX: Bypass Update: 0x{:x}", final_result)

        # --- 分支处理 (Branch Handling) ---
        # 1. 使用专用加法器计算跳转地址，对于 JALR，基址是 rs1；对于 JAL/Branch，基址是 PC
        is_jalr = ctrl.branch_type == BranchType.JALR
        target_base = is_jalr.select(real_rs1, pc)  # 0: Branch / JAL  # 1: JALR

        # 专用加法器永远做 Base + Imm
        imm_signed = imm.bitcast(Int(32))
        debug_log("EX: Branch Immediate: 0x{:x}", imm)
        target_base_signed = target_base.bitcast(Int(32))
        debug_log("EX: Branch Target Base: 0x{:x}", target_base)
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

        with Condition(ctrl.branch_type == BranchType.BEQ):
            debug_log("EX: Branch Type: BEQ")
        with Condition(ctrl.branch_type == BranchType.BNE):
            debug_log("EX: Branch Type: BNE")
        with Condition(ctrl.branch_type == BranchType.BLT):
            debug_log("EX: Branch Type: BLT")
        with Condition(ctrl.branch_type == BranchType.BGE):
            debug_log("EX: Branch Type: BGE")
        with Condition(ctrl.branch_type == BranchType.BLTU):
            debug_log("EX: Branch Type: BLTU")
        with Condition(ctrl.branch_type == BranchType.BGEU):
            debug_log("EX: Branch Type: BGEU")
        with Condition(ctrl.branch_type == BranchType.JAL):
            debug_log("EX: Branch Type: JAL")
        with Condition(ctrl.branch_type == BranchType.JALR):
            debug_log("EX: Branch Type: JALR")
        with Condition(ctrl.branch_type == BranchType.NO_BRANCH):
            debug_log("EX: Branch Type: NO_BRANCH")

        # 3. 根据不同的分支类型判断分支条件
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

        # 4. 写入分支目标寄存器，供 IF 与 ID 级使用
        branch_miss = final_next_pc != ctrl.next_pc_addr
        branch_target_reg[0] = branch_miss.select(
            final_next_pc,  # 跳转，写入目标地址
            Bits(32)(0),  # 不跳转，写 0 表示顺序执行
        )

        with Condition(is_branch):
            debug_log("EX: Branch Target: 0x{:x}", calc_target)
            debug_log("EX: Branch Taken: {}", is_taken == Bits(1)(1))

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
        # 构造控制信号包
        # When MUL/DIV result is ready, use the saved rd from the multiplier/divider
        # Otherwise, use the normal rd from the current instruction
        # NOTE: We do NOT modify halt_if - it must pass through normally for halt to work
        effective_rd = mul_ready.select(
            mul_rd,
            div_ready.select(
                div_rd,
                wb_ctrl.rd_addr
            )
        )
        final_rd = flush_if.select(Bits(5)(0), effective_rd)
        final_halt_if = flush_if.select(Bits(1)(0), wb_ctrl.halt_if)
        final_mem_opcode = flush_if.select(MemOp.NONE, mem_ctrl.mem_opcode)

        debug_log(
            "Control after Flush Check: mem_opcode=0x{:x} rd=0x{:x}",
            final_mem_opcode,
            final_rd,
        )

        final_wb_ctrl = wb_ctrl_signals.bundle(
            rd_addr=final_rd,
            halt_if=final_halt_if,
        )

        final_mem_ctrl = mem_ctrl_signals.bundle(
            mem_opcode=final_mem_opcode,
            mem_width=mem_ctrl.mem_width,
            mem_unsigned=mem_ctrl.mem_unsigned,
            wb_ctrl=final_wb_ctrl,
        )

        # 级间信号：控制 + 数据
        mem_call = mem_module.async_called(ctrl=final_mem_ctrl, alu_result=final_result)
        mem_call.bind.set_fifo_depth(ctrl=1, alu_result=1)

        # --- 访存操作 (Store Handling) ---
        # 将所需的信号作为引脚给出，交给 SingleMemory 处理
        is_store = (final_mem_ctrl.mem_opcode == MemOp.STORE) & (~final_halt_if)
        is_load = final_mem_ctrl.mem_opcode == MemOp.LOAD
        mem_width = final_mem_ctrl.mem_width

        with Condition(is_store):
            debug_log("EX: Memory Operation: STORE")
            debug_log("EX: Store Address: 0x{:x}", final_result)
            debug_log("EX: Store Data: 0x{:x}", real_rs2)
        with Condition(is_load):
            debug_log("EX: Memory Operation: LOAD")
            debug_log("EX: Load Address: 0x{:x}", final_result)

        # 返回引脚 (供 HazardUnit 与 SingleMemory 使用)
        # Including mul_busy and div_busy for hazard detection
        return final_rd, final_result, is_load, is_store, mem_width, real_rs2, mul_busy, div_busy
