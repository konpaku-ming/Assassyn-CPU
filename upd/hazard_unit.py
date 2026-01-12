from assassyn.frontend import *
from .control_signals import *


class HazardUnit(Downstream):
    def __init__(self):
        super().__init__()
        self.name = "HazardUnit"

    @downstream.combinational
    def build(
        self,
        # --- 1. 来自 ID 级 (当前指令需求) ---
        rs1_idx: Value,  # 源寄存器 1 索引 (Value)
        rs2_idx: Value,  # 源寄存器 2 索引 (Value)
        # --- 2. 来自流水线各级 (实时状态回传) ---
        # 各级 Module build() 的返回值
        ex_rd: Value,  # EX 级目标寄存器索引
        ex_is_load: Value,  # EX 级是否为 Load 指令
        ex_is_store: Value,  # EX 级是否为 Store 指令
        mem_is_store: Value,  # MEM 级是否为 Store 指令
        mem_rd: Value,  # MEM 级目标寄存器索引
        wb_rd: Value,  # WB 级目标寄存器索引
    ):
        # 使用 optional() 处理 Value 接口，如果无效则使用默认值 Bits(x)(0)
        rs1_idx_val = rs1_idx.optional(Bits(5)(0))
        rs2_idx_val = rs2_idx.optional(Bits(5)(0))
        ex_rd_val = ex_rd.optional(Bits(5)(0))
        ex_is_load_val = ex_is_load.optional(Bits(1)(0))
        ex_is_store_val = ex_is_store.optional(Bits(1)(0))
        mem_is_store_val = mem_is_store.optional(Bits(1)(0))
        mem_rd_val = mem_rd.optional(Bits(5)(0))
        wb_rd_val = wb_rd.optional(Bits(5)(0))

        log(
            "Input Signals: rs1_idx={} rs2_idx={} ex_rd={} ex_is_load={} ex_is_store={} mem_is_store={} mem_rd={} wb_rd={}",
            rs1_idx_val,
            rs2_idx_val,
            ex_rd_val,
            ex_is_load_val,
            ex_is_store_val,
            mem_is_store_val,
            mem_rd_val,
            wb_rd_val,
        )

        # 检查寄存器是否为零寄存器（x0），避免对零寄存器的冒险检测
        rs1_is_zero = rs1_idx_val == Bits(5)(0)
        rs2_is_zero = rs2_idx_val == Bits(5)(0)

        # 1. 检测 Load/Store 并生成 Stall 信号
        # 条件： ex_is_load == 1 || ex_is_store == 1 || mem_is_store == 1

        stall_if = ex_is_load_val | ex_is_store_val | mem_is_store_val

        # 2. 检测 Forwarding 并生成 Mux 选择码
        # 根据先前指令 rd 与当前指令 rs1、rs2 生成选择码 rs1_sel 与 rs2_sel

        # 对于 rs1 的旁路选择
        rs1_wb_pass = (rs1_idx_val == wb_rd_val).select(Rs1Sel.WB_BYPASS, Rs1Sel.RS1)
        rs1_mem_bypass = (rs1_idx_val == mem_rd_val).select(
            Rs1Sel.MEM_BYPASS, rs1_wb_pass
        )
        rs1_ex_bypass = (rs1_idx_val == ex_rd_val).select(
            Rs1Sel.EX_BYPASS, rs1_mem_bypass
        )
        rs1_sel = (~rs1_is_zero).select(rs1_ex_bypass, Rs1Sel.RS1)

        # 对于 rs2 的旁路选择
        rs2_wb_pass = (rs2_idx_val == wb_rd_val).select(Rs2Sel.WB_BYPASS, Rs2Sel.RS2)
        rs2_mem_bypass = (rs2_idx_val == mem_rd_val).select(
            Rs2Sel.MEM_BYPASS, rs2_wb_pass
        )
        rs2_ex_bypass = (rs2_idx_val == ex_rd_val).select(
            Rs2Sel.EX_BYPASS, rs2_mem_bypass
        )
        rs2_sel = (~rs2_is_zero).select(rs2_ex_bypass, Rs2Sel.RS2)

        log(
            "HazardUnit: rs1_sel={} rs2_sel={} stall_if={}",
            rs1_sel,
            rs2_sel,
            stall_if,
        )
        
        # 返回旁路选择信号和停顿信号
        return rs1_sel, rs2_sel, stall_if
