from assassyn.frontend import *
from .control_signals import *


class DataHazardUnit(Downstream):
    """
    DataHazardUnit 是一个纯组合逻辑 (Downstream) 模块。

    职责：
    1. 前瞻控制 (Forwarding Logic)：检测 RAW 冒险，生成多路选择信号，控制 EX 阶段 ALU 的操作数来源。
    2. 阻塞控制 (Stall Logic)：检测 Load-Use 冒险，生成流水线停顿（Stall）和气泡（Flush）信号。

    特性：无内部状态（Stateless）。它依赖流水线各级"回传"的实时控制信号包作为真值来源。
    """

    def __init__(self):
        super().__init__()
        self.name = "DataHazardUnit"

    @downstream.combinational
    def build(
            self,
            # --- 1. 来自 ID 级 (当前指令需求) ---
            rs1_idx: Value,  # 源寄存器 1 索引 (Value)
            rs2_idx: Value,  # 源寄存器 2 索引 (Value)
            rs1_used: Value,  # 是否需要读取 rs1 (Value) - 避免 LUI 等指令的虚假冒险
            rs2_used: Value,  # 是否需要读取 rs2 (Value)
            # --- 2. 来自流水线各级 (实时状态回传) ---
            # 各级 Module build() 的返回值
            ex_rd: Value,  # EX 级目标寄存器索引
            ex_is_load: Value,  # EX 级是否为 Load 指令
            ex_mul_busy: Value,  # EX stage multiplier busy status (multi-cycle MUL instruction occupancy)
            mem_rd: Value,  # MEM 级目标寄存器索引
            wb_rd: Value,  # WB 级目标寄存器索引
    ):
        # 使用 optional() 处理 Value 接口，如果无效则使用默认值 Bits(x)(0)
        rs1_idx_val = rs1_idx.optional(Bits(5)(0))
        rs2_idx_val = rs2_idx.optional(Bits(5)(0))
        rs1_used_val = rs1_used.optional(Bits(1)(0))
        rs2_used_val = rs2_used.optional(Bits(1)(0))
        ex_rd_val = ex_rd.optional(Bits(5)(0))
        ex_is_load_val = ex_is_load.optional(Bits(1)(0))
        ex_mul_busy_val = ex_mul_busy.optional(Bits(1)(0))
        mem_rd_val = mem_rd.optional(Bits(5)(0))
        wb_rd_val = wb_rd.optional(Bits(5)(0))

        log(
            "Input Signals: rs1_idx={} rs2_idx={} rs1_used={} rs2_used={} ex_rd={} ex_is_load={} ex_mul_busy={} mem_rd={} wb_rd={}",
            rs1_idx_val,
            rs2_idx_val,
            rs1_used_val,
            rs2_used_val,
            ex_rd_val,
            ex_is_load_val,
            ex_mul_busy_val,
            mem_rd_val,
            wb_rd_val,
        )
        # 默认值：不旁路，直接使用寄存器值
        rs1_sel = Rs1Sel.RS1
        rs2_sel = Rs2Sel.RS2

        # 检查寄存器是否为零寄存器（x0），避免对零寄存器的冒险检测
        rs1_is_zero = rs1_idx_val == Bits(5)(0)
        rs2_is_zero = rs2_idx_val == Bits(5)(0)

        # 1. 检测 Load-Use 冒险 (必须 Stall)
        # 条件：当前指令需要的源寄存器与 EX 级的 Load 指令的目标寄存器相同
        # 这种情况下必须停顿，因为 Load 指令的数据在 MEM 阶段才能获取
        load_use_hazard_rs1 = rs1_used_val & ~rs1_is_zero & ex_is_load_val & (rs1_idx_val == ex_rd_val)
        load_use_hazard_rs2 = rs2_used_val & ~rs2_is_zero & ex_is_load_val & (rs2_idx_val == ex_rd_val)

        # 2. Detect MUL multi-cycle occupancy - stall pipeline until multiplier completes
        # If Load-Use hazard or MUL occupancy exists, stall pipeline
        stall_if = load_use_hazard_rs1 | load_use_hazard_rs2 | ex_mul_busy_val

        # 2. Detect Forwarding (Generate Mux selection codes)
        # If no Load-Use hazard, generate rs1_sel and rs2_sel selection codes

        rs1_wb_pass = (rs1_idx_val == wb_rd_val).select(Rs1Sel.WB_BYPASS, Rs1Sel.RS1)
        rs1_mem_bypass = (rs1_idx_val == mem_rd_val).select(Rs1Sel.MEM_BYPASS, rs1_wb_pass)
        rs1_ex_bypass = ((rs1_idx_val == ex_rd_val) & ~ex_is_load_val).select(
            Rs1Sel.EX_BYPASS, rs1_mem_bypass
        )
        rs1_sel = (rs1_used_val & ~rs1_is_zero).select(rs1_ex_bypass, Rs1Sel.RS1)

        # For rs2 bypass selection
        rs2_wb_pass = (rs2_idx_val == wb_rd_val).select(Rs2Sel.WB_BYPASS, Rs2Sel.RS2)
        rs2_mem_bypass = (rs2_idx_val == mem_rd_val).select(Rs2Sel.MEM_BYPASS, rs2_wb_pass)
        rs2_ex_bypass = ((rs2_idx_val == ex_rd_val) & ~ex_is_load_val).select(
            Rs2Sel.EX_BYPASS, rs2_mem_bypass
        )
        rs2_sel = (rs2_used_val & ~rs2_is_zero).select(rs2_ex_bypass, Rs2Sel.RS2)

        log(
            "DataHazardUnit: rs1_sel={} rs2_sel={} stall_if={} ex_mul_busy={}",
            rs1_sel,
            rs2_sel,
            stall_if,
            ex_mul_busy_val,
        )
        # Return bypass selection signals and stall signal
        return rs1_sel, rs2_sel, stall_if
