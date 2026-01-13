from assassyn.frontend import *
from .control_signals import *


def _resolve_optional(value, default):
    """Resolve optional Value by falling back to default when missing."""
    return value.optional(default) if value is not None else default


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
        self.name = "HazardUnit"

    @downstream.combinational
    def build(
            self,
            # --- 1. 来自 ID 级 (当前指令需求) ---
            rs1_idx: Value,  # 源寄存器 1 索引 (Value)
            rs2_idx: Value,  # 源寄存器 2 索引 (Value)
            rs1_used: Value = None,  # 是否需要读取 rs1 (Value，默认=1 兼容旧行为) - 避免 LUI 等指令的虚假冒险
            rs2_used: Value = None,  # 是否需要读取 rs2 (Value，默认=1 兼容旧行为)
            # --- 2. 来自流水线各级 (实时状态回传) ---
            # 各级 Module build() 的返回值
            ex_rd: Value,  # EX 级目标寄存器索引
            ex_is_load: Value,  # EX 级是否为 Load 指令
            ex_is_store: Value = None,  # EX 级是否为 Store 指令
            ex_mul_busy: Value = None,  # EX stage multiplier busy status (multi-cycle MUL instruction occupancy)
            ex_div_busy: Value = None,  # EX stage divider busy status (multi-cycle DIV instruction occupancy)
            mem_rd: Value = None,  # MEM 级目标寄存器索引
            mem_is_store: Value = None,  # MEM 级是否为 Store 指令
            wb_rd: Value = None,  # WB 级目标寄存器索引
            **kwargs,
    ):
        # 使用 optional() 处理 Value 接口，如果无效则使用默认值 Bits(x)(0)
        rs1_idx_val = _resolve_optional(rs1_idx, Bits(5)(0))
        rs2_idx_val = _resolve_optional(rs2_idx, Bits(5)(0))
        # 默认假设寄存器被使用（兼容旧 HazardUnit 行为），除非上游显式提供 usage 位
        rs1_used_val = _resolve_optional(rs1_used, Bits(1)(1))
        rs2_used_val = _resolve_optional(rs2_used, Bits(1)(1))
        ex_rd_val = _resolve_optional(ex_rd, Bits(5)(0))
        ex_is_load_val = _resolve_optional(ex_is_load, Bits(1)(0))
        ex_is_store_val = _resolve_optional(ex_is_store, Bits(1)(0))
        ex_mul_busy_val = _resolve_optional(ex_mul_busy, Bits(1)(0))
        ex_div_busy_val = _resolve_optional(ex_div_busy, Bits(1)(0))
        mem_rd_val = _resolve_optional(mem_rd, Bits(5)(0))
        mem_is_store_val = _resolve_optional(mem_is_store, Bits(1)(0))
        wb_rd_val = _resolve_optional(wb_rd, Bits(5)(0))

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
        mul_busy_hazard = ex_mul_busy_val

        # 3. Detect DIV multi-cycle occupancy - stall pipeline until divider completes
        div_busy_hazard = ex_div_busy_val

        # Combine all stall conditions
        stall_if = load_use_hazard_rs1 | load_use_hazard_rs2 | mul_busy_hazard | div_busy_hazard | ex_is_store_val | mem_is_store_val | ex_is_load_val

        # 4. Detect Forwarding (Generate Mux selection codes)
        # EX result is not ready if it's a Load (data from memory), MUL (multi-cycle operation), or DIV (multi-cycle operation)
        ex_result_not_ready = ex_is_load_val | ex_mul_busy_val | ex_div_busy_val

        rs1_wb_pass = (rs1_idx_val == wb_rd_val).select(Rs1Sel.WB_BYPASS, Rs1Sel.RS1)
        rs1_mem_bypass = (rs1_idx_val == mem_rd_val).select(Rs1Sel.MEM_BYPASS, rs1_wb_pass)
        rs1_ex_bypass = ((rs1_idx_val == ex_rd_val) & ~ex_result_not_ready).select(
            Rs1Sel.EX_BYPASS, rs1_mem_bypass
        )
        rs1_sel = (rs1_used_val & ~rs1_is_zero).select(rs1_ex_bypass, Rs1Sel.RS1)

        # For rs2 bypass selection
        rs2_wb_pass = (rs2_idx_val == wb_rd_val).select(Rs2Sel.WB_BYPASS, Rs2Sel.RS2)
        rs2_mem_bypass = (rs2_idx_val == mem_rd_val).select(Rs2Sel.MEM_BYPASS, rs2_wb_pass)
        rs2_ex_bypass = ((rs2_idx_val == ex_rd_val) & ~ex_result_not_ready).select(
            Rs2Sel.EX_BYPASS, rs2_mem_bypass
        )
        rs2_sel = (rs2_used_val & ~rs2_is_zero).select(rs2_ex_bypass, Rs2Sel.RS2)

        log_condition = stall_if | (rs1_sel != Rs1Sel.RS1) | (rs2_sel != Rs2Sel.RS2)
        with Condition(log_condition == Bits(1)(1)):
            log(
                "HazardUnit: rs1_sel={} rs2_sel={} stall_if={} mul_busy_hazard={} div_busy_hazard={} ex_is_store={} mem_is_store={} ex_is_load={}",
                rs1_sel,
                rs2_sel,
                stall_if,
                mul_busy_hazard,
                div_busy_hazard,
                ex_is_store_val,
                mem_is_store_val,
                ex_is_load_val,
            )
        # Return bypass selection signals and stall signal
        return rs1_sel, rs2_sel, stall_if
