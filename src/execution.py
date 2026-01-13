from assassyn.frontend import *

from .btb import TournamentPredictorImpl, BTBImpl
from .control_signals import *
from .multiplier import WallaceTreeMul, sign_zero_extend
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

    @module.combinational
    def build(
            self,
            mem_module: Module,  # 下一级流水线 (MEM)
            # --- 旁路数据源 (Forwarding Sources) ---
            ex_bypass: Array = None,  # 来自 EX-MEM 旁路寄存器的数据（上条指令结果）
            mem_bypass: Array = None,  # 来自 MEM-WB 旁路寄存器的数据 (上上条指令结果)
            wb_bypass: Array = None,  # 来自 WB 旁路寄存器的数据 (当前写回数据)
            # --- 分支反馈 ---
            branch_target_reg: Array = None,  # 用于通知 IF 跳转目标的全局寄存器
            reg_file: Array = None,  # 用于终止时打印寄存器快照
            dcache: SRAM = None,  # 保留参数以兼容旧接口
            # --- BTB 更新 (可选) ---
            btb_impl: "BTBImpl" = None,  # BTB 实现逻辑
            btb_valid: Array = None,  # BTB 有效位数组
            btb_tags: Array = None,  # BTB 标签数组
            btb_targets: Array = None,  # BTB 目标地址数组
            # --- Tournament Predictor 更新 (可选) ---
            tournament_impl: "TournamentPredictorImpl" = None,
            local_counters: Array = None,
            ghr: Array = None,
            global_counters: Array = None,
            chooser_counters: Array = None,
            **kwargs,
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

        # 兼容旧接口的别名参数
        if ex_bypass is None:
            ex_bypass = kwargs.get("ex_mem_bypass")
        if mem_bypass is None:
            mem_bypass = kwargs.get("mem_wb_bypass")
        if wb_bypass is None:
            wb_bypass = kwargs.get("wb_bypass")
        if ex_bypass is None:
            ex_bypass = RegArray(Bits(32), 1, initializer=[0])
        if mem_bypass is None:
            mem_bypass = RegArray(Bits(32), 1, initializer=[0])
        if wb_bypass is None:
            wb_bypass = RegArray(Bits(32), 1, initializer=[0])

        if mem_module is None or branch_target_reg is None:
            return (
                Bits(5)(0),
                Bits(32)(0),
                Bits(1)(0),
                Bits(1)(0),
                Bits(3)(0),
                Bits(32)(0),
                Bits(1)(0),
                Bits(1)(0),
            )

        with Condition(flush_if == Bits(1)(1)):
            log("EX: Flush")

        final_rd = flush_if.select(Bits(5)(0), mem_ctrl.rd_addr)
        final_mem_opcode = flush_if.select(Bits(3)(0), mem_ctrl.mem_opcode)
        final_halt_if = flush_if.select(Bits(1)(0), mem_ctrl.halt_if)

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
            halt_if=final_halt_if,
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

        # === Initialize 3-cycle Pure Wallace Tree Multiplier (No Booth Encoding) ===
        multiplier = WallaceTreeMul()

        # === Initialize SRT-4 Divider (~18-cycle multi-cycle unit) ===
        divider = SRT4Divider()

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
        sll_res = alu_op1 << alu_op2[0:4].bitcast(UInt(5))

        # 逻辑右移 (使用低5位作为移位位数)
        srl_res = alu_op1 >> alu_op2[0:4].bitcast(UInt(5))

        # 算术右移 (使用低5位作为移位位数)
        sra_res = op1_signed >> alu_op2[0:4].bitcast(UInt(5))
        sra_res = sra_res.bitcast(Bits(32))

        # 有符号比较小于
        slt_res = (op1_signed < op2_signed).bitcast(Bits(32))

        # 无符号比较小于
        sltu_res = (alu_op1 < alu_op2).bitcast(Bits(32))

        # ============== M Extension - Pure Wallace Tree Multiplier ==============
        #
        # Implementation: 3-cycle pipelined multiplier (NO Booth encoding)
        # Architecture:
        #   Cycle 1 (EX_M1): Partial product generation (32 partial products)
        #                    pp[i] = A & {32{B[i]}}, left-shifted by i positions
        #   Cycle 2 (EX_M2): Wallace Tree compression (reduce 32 → 6-8 rows)
        #   Cycle 3 (EX_M3): Wallace Tree final compression + CPA (produce 64-bit result)
        #
        # Supported Operations:
        #   MUL:    signed × signed → low 32 bits
        #   MULH:   signed × signed → high 32 bits
        #   MULHSU: signed × unsigned → high 32 bits
        #   MULHU:  unsigned × unsigned → high 32 bits
        #
        # This is the ONLY multiplication interface - all multiplication operations
        # use the 3-cycle Wallace Tree pipeline. Each multiplication takes exactly
        # 3 cycles to complete, from EX_M1 through EX_M3.

        # Detect if current operation is multiplication
        is_mul_op = (ctrl.alu_func == ALUOp.MUL) | (ctrl.alu_func == ALUOp.MULH) | \
                    (ctrl.alu_func == ALUOp.MULHSU) | (ctrl.alu_func == ALUOp.MULHU)

        # Determine signedness for each multiply operation type
        # MUL, MULH, MULHSU: op1 is treated as signed
        # MUL, MULH: op2 is treated as signed
        # MULHSU: op2 is treated as unsigned
        # MULHU: both operands are treated as unsigned
        op1_is_signed = (ctrl.alu_func == ALUOp.MUL) | (ctrl.alu_func == ALUOp.MULH) | \
                        (ctrl.alu_func == ALUOp.MULHSU)
        op2_is_signed = (ctrl.alu_func == ALUOp.MUL) | (ctrl.alu_func == ALUOp.MULH)

        # Determine which 32 bits of the 64-bit product to return
        # MUL returns low 32 bits, others return high 32 bits
        result_is_high = (ctrl.alu_func == ALUOp.MULH) | (ctrl.alu_func == ALUOp.MULHSU) | \
                         (ctrl.alu_func == ALUOp.MULHU)

        # === 方案A：MUL指令状态保持与延迟写回 ===
        #
        # 核心思路：
        # 1. 当MUL指令启动时，保存其rd到专用寄存器
        # 2. MUL未ready时，向MEM发送NOP (rd=0)
        # 3. MUL结果ready时，使用保存的rd发送结果到MEM
        # 4. 这样MUL结果能够正确地通过MEM→WB写回寄存器

        # MUL指令状态寄存器：保存正在执行的MUL的目标寄存器
        mul_pending_rd = RegArray(Bits(5), 1)
        mul_pending_valid = RegArray(Bits(1), 1)

        # Initiate multiplication in the 3-cycle pipeline
        # Only start if multiplier is not busy to avoid overwriting in-flight operations
        # Stage 1 (EX_M1): Start partial product generation
        # Note: MUL uses real_rs1 and real_rs2 directly (like ADD with register operands)
        # to ensure proper operand forwarding, not alu_op1/alu_op2 which are for general ALU ops
        mul_can_start = is_mul_op & ~flush_if & ~multiplier.is_busy()
        with Condition(mul_can_start):
            multiplier.start_multiply(real_rs1, real_rs2, op1_is_signed, op2_is_signed, result_is_high)
            # 保存MUL指令的目标寄存器
            mul_pending_rd[0] = mem_ctrl.rd_addr
            mul_pending_valid[0] = Bits(1)(1)
            log("EX: Starting 3-cycle multiplication (Pure Wallace Tree)")
            log("EX:   Op1=0x{:x} (signed={}), Op2=0x{:x} (signed={})",
                real_rs1, op1_is_signed, real_rs2, op2_is_signed)
            log("EX:   Saved pending MUL rd=x{}", mem_ctrl.rd_addr)

        # Advance multiplier pipeline stages every cycle
        multiplier.cycle_m1()  # Stage 1 -> Stage 2: Generate 32 partial products
        multiplier.cycle_m2()  # Stage 2 -> Stage 3: Wallace Tree compression (32 → 6-8 rows)
        multiplier.cycle_m3()  # Stage 3: Final compression + CPA, result ready

        # Get multiplication result if ready (after 3 cycles)
        mul_result_valid, mul_result_value = multiplier.get_result_if_ready()

        # 检测是否有pending的MUL结果需要写回
        # 这个变量需要在bypass更新逻辑之前定义，因为bypass更新需要用到它
        has_pending_mul_result = mul_pending_valid[0] & mul_result_valid

        # Clear result after reading to prevent consuming it multiple times
        with Condition(mul_result_valid == Bits(1)(1)):
            log("EX: 3-cycle multiplier result ready and consumed: 0x{:x}", mul_result_value)
            multiplier.clear_result()
            # MUL结果ready时，清除pending状态（结果将在本cycle发送到MEM）
            mul_pending_valid[0] = Bits(1)(0)

        # Wallace Tree multiplier is now the ONLY interface for multiplication
        # All MUL/MULH/MULHSU/MULHU operations use the 3-cycle pipeline result
        # No inline single-cycle computation is performed

        # ============== M Extension - SRT-4 Divider ==============
        #
        # Implementation: ~18-cycle multi-cycle divider (radix-4)
        # Architecture:
        #   Cycle 1: Preprocessing (DIV_PRE) - normalize divisor, find leading 1
        #   Cycles 2-17: Iterative calculation (DIV_WORKING) - 16 iterations, 2 bits per cycle
        #   Cycle 18: Post-processing (DIV_END) - sign correction and remainder adjustment
        #   Special: Fast paths for division by 0 (DIV_ERROR) or division by 1 (DIV_1)
        #
        # Supported Operations:
        #   DIV:  signed ÷ signed → quotient
        #   DIVU: unsigned ÷ unsigned → quotient
        #   REM:  signed % signed → remainder
        #   REMU: unsigned % unsigned → remainder
        #
        # Pipeline Integration:
        #   - Pipeline stalls while divider is busy
        #   - Result is written back when ready (similar to MUL pending result)

        # Detect if current operation is division
        is_div_op = (ctrl.alu_func == ALUOp.DIV) | (ctrl.alu_func == ALUOp.DIVU) | \
                    (ctrl.alu_func == ALUOp.REM) | (ctrl.alu_func == ALUOp.REMU)

        # Determine signedness and whether to return remainder
        div_is_signed = (ctrl.alu_func == ALUOp.DIV) | (ctrl.alu_func == ALUOp.REM)
        div_is_rem = (ctrl.alu_func == ALUOp.REM) | (ctrl.alu_func == ALUOp.REMU)

        # DIV instruction handling (similar to MUL)
        # Unlike the original pending result mechanism, we'll make DIV work exactly like MUL:
        # - When DIV starts, it stays in EX for the full duration
        # - Pipeline stalls (IF/ID send NOPs) while divider is busy
        # - When result is ready, DIV instruction proceeds to MEM with the result
        # - No separate "injection" mechanism needed

        # Note: We still need to track which DIV instruction started the operation
        # because the EX stage receives NOPs during stall, not the original DIV
        div_pending_rd = RegArray(Bits(5), 1)
        div_pending_valid = RegArray(Bits(1), 1)
        div_pending_is_rem = RegArray(Bits(1), 1)

        # Start division if not already busy
        div_can_start = is_div_op & ~flush_if & ~divider.is_busy()
        with Condition(div_can_start):
            divider.start_divide(real_rs1, real_rs2, div_is_signed, div_is_rem)
            # Save DIV instruction's context
            div_pending_rd[0] = mem_ctrl.rd_addr
            div_pending_valid[0] = Bits(1)(1)
            div_pending_is_rem[0] = div_is_rem
            log("EX: Starting ~18-cycle division (SRT-4)")
            log("EX:   Op1=0x{:x} (signed={}), Op2=0x{:x} (signed={}), is_rem={}",
                real_rs1, div_is_signed, real_rs2, div_is_signed, div_is_rem)
            log("EX:   Saved pending DIV rd=x{}", mem_ctrl.rd_addr)

        # Advance divider state machine every cycle
        divider.tick()

        # Get division result if ready
        div_result_valid, div_result_value, div_error = divider.get_result_if_ready()

        # Check if DIV result is ready for this cycle
        # When ready, we'll send the result to MEM (not as injection, but as normal flow)
        div_result_ready_this_cycle = div_pending_valid[0] & div_result_valid

        # Clear result after reading
        with Condition(div_result_valid == Bits(1)(1)):
            log("EX: SRT-4 divider result ready: 0x{:x}, error={}",
                div_result_value, div_error)
            divider.clear_result()
            # Clear pending status when result is sent to MEM
            div_pending_valid[0] = Bits(1)(0)

        # For bypass and ALU result selection, use div_result when ready
        has_div_result = div_result_ready_this_cycle

        # ebreak 停机
        with Condition((ctrl.alu_func == ALUOp.SYS) & ~flush_if):
            log("EBREAK encountered at PC=0x{:x}, halting simulation.", pc)
            if reg_file is not None:
                log("Final register file state:")
                for idx in range(32):
                    log("  x{} = 0x{:x}", idx, reg_file[idx])
            finish()

        # 2. 结果选择
        # For MUL/MULH/MULHSU/MULHU, use the Wallace Tree multiplier result
        # All multiplication operations use mul_result_value from the 3-cycle pipeline
        # For DIV/DIVU/REM/REMU, use the SRT-4 divider result
        alu_result = ctrl.alu_func.select1hot(
            add_res,  # 0:  ADD
            sub_res,  # 1:  SUB
            sll_res,  # 2:  SLL
            slt_res,  # 3:  SLT
            sltu_res,  # 4:  SLTU
            xor_res,  # 5:  XOR
            srl_res,  # 6:  SRL
            sra_res,  # 7:  SRA
            or_res,  # 8:  OR
            and_res,  # 9:  AND
            alu_op2,  # 10: SYS
            mul_result_value,  # 11: MUL - from Wallace Tree (3-cycle)
            mul_result_value,  # 12: MULH - from Wallace Tree (3-cycle)
            mul_result_value,  # 13: MULHSU - from Wallace Tree (3-cycle)
            mul_result_value,  # 14: MULHU - from Wallace Tree (3-cycle)
            div_result_value,  # 15: DIV - from SRT-4 Divider (~18-cycle)
            div_result_value,  # 16: DIVU - from SRT-4 Divider (~18-cycle)
            div_result_value,  # 17: REM - from SRT-4 Divider (~18-cycle)
            div_result_value,  # 18: REMU - from SRT-4 Divider (~18-cycle)
            alu_op2,  # 19-31: 占位（为未来扩展预留）
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

        # 3. 更新本级 Bypass 寄存器
        # 修复：对于MUL指令，只有当结果ready时才更新bypass
        # 同时也需要在pending MUL result注入时更新bypass
        # 对于DIV指令，也是同样的处理

        # 确定是否应该更新bypass：
        # - 有pending MUL/DIV结果需要注入：更新（使用MUL/DIV结果）
        # - 非MUL/DIV指令：总是更新
        # - MUL/DIV指令第一个周期：不更新（result_valid=0）
        # - MUL/DIV结果ready时：更新（result_valid=1）
        should_update_bypass = has_pending_mul_result | has_div_result | \
                               (~(is_mul_op | is_div_op) | mul_result_valid | div_result_valid)

        # 确定bypass的值：
        # - 如果有pending MUL结果或当前MUL结果ready，使用mul_result_value
        # - 否则如果有pending DIV结果或当前DIV结果ready，使用div_result_value
        # - 否则使用alu_result
        bypass_value = (has_pending_mul_result | mul_result_valid).select(
            mul_result_value,
            (has_div_result | div_result_valid).select(div_result_value, alu_result)
        )

        # 只在should_update_bypass为true时更新bypass
        with Condition(should_update_bypass):
            ex_bypass[0] = bypass_value
            log("EX: Bypass Update: 0x{:x}", bypass_value)
        with Condition(~should_update_bypass):
            log("EX: Bypass Update skipped for MUL/DIV (result not ready)")

        log("EX: ALU Result: 0x{:x}", alu_result)

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

        # 6. 更新 Tournament Predictor (如果提供了引用)
        # 对于条件分支指令，根据实际结果更新:
        # - Local predictor (PC-indexed counters)
        # - Global predictor (GHR-indexed counters)
        # - Chooser (when local and global disagree)
        # - Global History Register (shift in actual outcome)
        if tournament_impl is not None and local_counters is not None:
            # 对于条件分支指令，根据实际结果更新 Tournament Predictor
            # JAL/JALR 是无条件跳转，不需要预测
            is_conditional_branch = (
                    (ctrl.branch_type == BranchType.BEQ) |
                    (ctrl.branch_type == BranchType.BNE) |
                    (ctrl.branch_type == BranchType.BLT) |
                    (ctrl.branch_type == BranchType.BGE) |
                    (ctrl.branch_type == BranchType.BLTU) |
                    (ctrl.branch_type == BranchType.BGEU)
            )
            # 只对条件分支更新 Tournament Predictor
            should_update_tournament = is_conditional_branch & ~flush_if
            tournament_impl.update(
                pc=pc,
                branch_taken=is_taken,
                should_update=should_update_tournament,
                local_counters=local_counters,
                ghr=ghr,
                global_counters=global_counters,
                chooser_counters=chooser_counters,
            )

        # --- 下一级绑定与状态反馈 ---
        # 构造发送给 MEM 的包
        #
        # 方案A完整修复：MUL/DIV结果延迟注入
        #
        # 核心机制：
        # 1. 当MUL/DIV启动时：保存rd到pending_rd，发送NOP到MEM
        # 2. 后续周期：如果有pending的MUL/DIV result ready，优先发送结果
        # 3. 否则：发送当前指令到MEM
        #
        # 这样确保MUL/DIV结果一定能够到达WB并写回寄存器

        # 注意：has_pending_mul_result和has_div_result已在前面定义
        # 因为bypass更新逻辑需要在前面使用它

        # 决定本cycle发送到MEM的内容：
        # - 如果有pending MUL/DIV结果：发送写回操作
        # - 否则：发送当前指令（可能是NOP）

        # 当前指令是否是MUL/DIV且未ready（需要发送NOP）
        current_is_mul_not_ready = is_mul_op & ~mul_result_valid
        current_is_div_not_ready = is_div_op & ~div_result_valid

        # 确定发送到MEM的rd：
        # 优先级1: 如果有pending MUL结果，使用保存的mul_pending_rd
        # 优先级2: 如果有pending DIV结果，使用保存的div_pending_rd
        # 优先级3: 如果当前指令是MUL/DIV且未ready，发送rd=0 (NOP)
        # 优先级4: 否则使用final_rd（当前指令的rd）
        mem_rd_mux = has_pending_mul_result.select(
            mul_pending_rd[0],  # pending MUL result
            has_div_result.select(
                div_pending_rd[0],  # pending DIV result
                (current_is_mul_not_ready | current_is_div_not_ready).select(
                    Bits(5)(0),  # current MUL/DIV not ready -> NOP
                    final_rd  # normal instruction
                )
            )
        )

        # 确定发送到MEM的ALU结果：
        # 如果有pending MUL结果或当前是MUL，使用mul_result_value
        # 否则如果有pending DIV结果或当前是DIV，使用div_result_value
        # 否则使用alu_result
        use_mul_result = has_pending_mul_result | is_mul_op
        use_div_result = has_div_result | is_div_op
        mem_alu_result_mux = use_mul_result.select(
            mul_result_value,
            use_div_result.select(div_result_value, alu_result)
        )

        # 确定发送到MEM的mem_opcode：
        # 如果发送pending MUL/DIV结果，应该是NONE（只写回寄存器，不访存）
        # 如果当前MUL/DIV未ready，发送NONE (NOP)
        # 否则使用原始mem_opcode
        mem_opcode_mux = (has_pending_mul_result | has_div_result |
                          current_is_mul_not_ready | current_is_div_not_ready).select(
            MemOp.NONE,
            final_mem_opcode
        )

        # 重新构造发送给MEM的控制信号
        mem_ctrl_to_send = mem_ctrl_signals.bundle(
            mem_opcode=mem_opcode_mux,
            mem_width=final_mem_ctrl.mem_width,
            mem_unsigned=final_mem_ctrl.mem_unsigned,
            rd_addr=mem_rd_mux,
            halt_if=final_mem_ctrl.halt_if,
        )

        # 总是向MEM发送
        mem_call = mem_module.async_called(ctrl=mem_ctrl_to_send, alu_result=mem_alu_result_mux)
        mem_call.bind.set_fifo_depth(ctrl=1, alu_result=1)

        # 日志记录
        with Condition(has_pending_mul_result):
            log("EX: Injecting pending MUL result to MEM (rd=x{}, result=0x{:x})",
                mul_pending_rd[0], mul_result_value)
        with Condition(has_div_result & ~has_pending_mul_result):
            log("EX: Injecting pending DIV result to MEM (rd=x{}, result=0x{:x})",
                div_pending_rd[0], div_result_value)
        with Condition((current_is_mul_not_ready | current_is_div_not_ready) &
                       ~has_pending_mul_result & ~has_div_result):
            log("EX: Current MUL/DIV not ready, sending NOP to MEM")
        with Condition((is_mul_op & mul_result_valid) & ~has_pending_mul_result & ~has_div_result):
            log("EX: Current MUL ready, sending to MEM (rd=0x{:x}, result=0x{:x})",
                mem_rd_mux, mem_alu_result_mux)
        with Condition((is_div_op & div_result_valid) & ~has_pending_mul_result & ~has_div_result):
            log("EX: Current DIV ready, sending to MEM (rd=0x{:x}, result=0x{:x})",
                mem_rd_mux, mem_alu_result_mux)

        # 3. Return status (for HazardUnit to monitor)
        # rd_addr for scoreboarding/dependency detection
        # is_load for detecting Load-Use hazards
        # mul_busy for detecting MUL multi-cycle occupancy, requires pipeline stall
        # div_busy for detecting DIV multi-cycle occupancy, requires pipeline stall
        #
        # 返回实际发送到MEM的rd值
        # 这样DataHazardUnit能够正确识别：
        # - pending MUL result注入时：返回mul_pending_rd
        # - 当前MUL未ready时：返回0 (NOP)
        # - 正常情况：返回final_rd
        #
        # CRITICAL: Include mul_can_start/div_can_start to signal busy immediately
        # when a new MUL/DIV starts in the current cycle. Otherwise, there's a
        # one-cycle delay before the busy signal propagates, allowing the next
        # instruction to incorrectly enter EX.
        mul_busy = multiplier.is_busy() | mul_can_start
        div_busy = divider.is_busy() | div_can_start
        return mem_rd_mux, mem_alu_result_mux, is_load, is_store, final_mem_ctrl.mem_width, real_rs2, mul_busy, div_busy
