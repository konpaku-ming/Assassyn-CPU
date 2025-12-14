from assassyn.frontend import *
from control_signals import *


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
            rs1_idx: Bits(5),  # 源寄存器 1 索引 (Bits 5)
            rs2_idx: Bits(5),  # 源寄存器 2 索引 (Bits 5)
            rs1_used: Bits(1),  # 是否需要读取 rs1 (Bits 1) - 避免 LUI 等指令的虚假冒险
            rs2_used: Bits(1),  # 是否需要读取 rs2 (Bits 1)
            # --- 2. 来自流水线各级 (实时状态回传) ---
            # 各级 Module build() 的返回值
            ex_rd: Bits(5),  # EX 级目标寄存器索引
            ex_is_load: Bits(1),  # EX 级是否为 Load 指令
            mem_rd: Bits(5),  # MEM 级目标寄存器索引
            wb_rd: Bits(5),  # WB 级目标寄存器索引
    ):
        log(
            "Input Signals: rs1_idx={} rs2_idx={} rs1_used={} rs2_used={} ex_rd={} ex_is_load={} mem_rd={} wb_rd={}",
            rs1_idx,
            rs2_idx,
            rs1_used,
            rs2_used,
            ex_rd,
            ex_is_load,
            mem_rd,
            wb_rd,
        )
        # 默认值：不旁路，直接使用寄存器值
        rs1_sel = Rs1Sel.RS1
        rs2_sel = Rs2Sel.RS2

        # 检查寄存器是否为零寄存器（x0），避免对零寄存器的冒险检测
        rs1_is_zero = rs1_idx == Bits(5)(0)
        rs2_is_zero = rs2_idx == Bits(5)(0)

        # 1. 检测 Load-Use 冒险 (必须 Stall)
        # 条件：当前指令需要的源寄存器与 EX 级的 Load 指令的目标寄存器相同
        # 这种情况下必须停顿，因为 Load 指令的数据在 MEM 阶段才能获取
        load_use_hazard_rs1 = rs1_used & ~rs1_is_zero & ex_is_load & (rs1_idx == ex_rd)
        load_use_hazard_rs2 = rs2_used & ~rs2_is_zero & ex_is_load & (rs2_idx == ex_rd)

        # 如果存在 Load-Use 冒险，需要停顿流水线
        stall_if = load_use_hazard_rs1 | load_use_hazard_rs2

        # 2. 检测 Forwarding (生成 Mux 选择码)
        # 如果没有 Load-Use 冒险，我们生成选择码 rs1_sel 与 rs2_sel

        rs1_wb_pass = (rs1_idx == wb_rd).select(Rs1Sel.WB_BYPASS, Rs1Sel.RS1)
        rs1_mem_bypass = (rs1_idx == mem_rd).select(Rs1Sel.MEM_WB_BYPASS, rs1_wb_pass)
        rs1_ex_bypass = ((rs1_idx == ex_rd) & ~ex_is_load).select(
            Rs1Sel.EX_MEM_BYPASS, rs1_mem_bypass
        )
        rs1_sel = (rs1_used & ~rs1_is_zero).select(rs1_ex_bypass, Rs1Sel.RS1)

        # 对于 rs2 的旁路选择
        rs2_wb_pass = (rs2_idx == wb_rd).select(Rs2Sel.WB_BYPASS, Rs2Sel.RS2)
        rs2_mem_bypass = (rs2_idx == mem_rd).select(Rs2Sel.MEM_WB_BYPASS, rs2_wb_pass)
        rs2_ex_bypass = ((rs2_idx == ex_rd) & ~ex_is_load).select(
            Rs2Sel.EX_MEM_BYPASS, rs2_mem_bypass
        )
        rs2_sel = (rs2_used & ~rs2_is_zero).select(rs2_ex_bypass, Rs2Sel.RS2)

        log(
            "DataHazardUnit: rs1_sel={} rs2_sel={} stall_if={}",
            rs1_sel,
            rs2_sel,
            stall_if,
        )
        # 返回旁路选择信号和停顿信号
        return rs1_sel, rs2_sel, stall_if
