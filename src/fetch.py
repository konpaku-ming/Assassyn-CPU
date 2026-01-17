from assassyn.frontend import *

from .btb import BTBImpl
from .control_signals import *
from .debug_utils import debug_log
from .tournament_predictor import TournamentPredictorImpl


class Fetcher(Module):
    def __init__(self):
        super().__init__(
            ports={}, no_arbiter=True  # Fetcher 是起点，通常不需要被别人 async_called
        )
        self.name = "Fetcher"

    @module.combinational
    def build(self):
        # 1. PC 寄存器
        # 初始化为 0 (Reset Vector)
        pc_reg = RegArray(Bits(32), 1, initializer=[0])
        # 用于驱动 FetcherImpl（Assassyn特性）
        pc_addr = pc_reg[0]
        # 记录上一个周期的PC，用于在 Stall 时稳住输入（Assassyn不允许"不输入"）
        last_pc_reg = RegArray(Bits(32), 1, initializer=[0])

        # 暴露寄存器引用供 Impl 使用
        return pc_reg, pc_addr, last_pc_reg


class FetcherImpl(Downstream):

    def __init__(self):
        super().__init__()
        self.name = "Fetcher_Impl"

    @downstream.combinational
    def build(
        self,
        # --- 资源引用 ---
        pc_reg: Array,  # 引用 Fetcher 的 PC
        pc_addr: Bits(32),  # 引用 Fetcher 的 PC 地址
        last_pc_reg: Array,  # 引用 Fetcher 的 Last PC
        decoder: Module,  # 下一级模块 (用于发送指令)
        # --- 反馈控制信号 (来自 DataHazardUnit/ControlHazardReg) ---
        stall_if: Value,  # 暂停取指 (保持当前 PC)
        branch_target: Array,  # 不为0时，根据目标地址冲刷流水线
        # --- BTB 分支预测 (可选, SRAM-based) ---
        btb_impl: "BTBImpl" = None,  # BTB 实现逻辑
        btb_sram: SRAM = None,  # BTB SRAM instance
        # --- Tournament Predictor (方向预测，可选) ---
        tp_impl: "TournamentPredictorImpl" = None,  # Tournament Predictor 实现逻辑
        tp_bimodal: Array = None,  # Bimodal 计数器数组
        tp_gshare: Array = None,  # Gshare 计数器数组
        tp_ghr: Array = None,  # 全局历史寄存器
        tp_selector: Array = None,  # 选择器计数器数组
    ):
        current_stall_if = stall_if.optional(Bits(1)(0))

        with Condition(current_stall_if == Bits(1)(1)):
            debug_log("IF: Stall")

        # 读取当前 PC
        current_pc = current_stall_if.select(last_pc_reg[0], pc_addr)

        flush_if = branch_target[0] != Bits(32)(0)
        target_pc = branch_target[0]

        with Condition(flush_if == Bits(1)(1)):
            debug_log("IF: Flush to 0x{:x}", target_pc)

        final_current_pc = flush_if.select(target_pc, current_pc)
        debug_log("IF: Final Current PC=0x{:x}", final_current_pc)

        # --- 1. 计算 Next PC (时序逻辑输入) ---
        # 默认下一个 PC 是当前 PC + 4
        default_next_pc = (final_current_pc.bitcast(UInt(32)) + UInt(32)(4)).bitcast(
            Bits(32)
        )

        # 使用 BTB 进行分支目标预测（如果提供了 BTB SRAM）
        # Note: SRAM has 1-cycle read latency.
        # - In cycle T-1: BTB SRAM was read with final_current_pc_{T-1}
        # - In cycle T: BTB output contains entry for final_current_pc_{T-1}, which is last_pc_reg[0]
        # - We check if the current PC matches what we read from BTB
        #
        # This means BTB prediction is only valid when:
        # 1. We're in a stall (current PC same as last PC)
        # 2. We correctly predicted a branch and came back to same PC
        # 3. We're in a loop and this is not the first iteration
        if btb_impl is not None and btb_sram is not None:
            # Read BTB output and check if it matches the PC used for read (last_pc)
            btb_hit_raw, btb_predicted_target = btb_impl.predict(
                pc=last_pc_reg[0],  # Check if BTB entry tag matches the PC that was used for read
                btb_sram=btb_sram,
            )
            
            # BTB prediction is only valid if current PC equals the PC we read BTB for
            # This handles SRAM's 1-cycle read latency
            pc_matches_btb_read = (final_current_pc == last_pc_reg[0])
            btb_hit = btb_hit_raw & pc_matches_btb_read

            # --- Tournament Predictor 方向预测 ---
            # 当 BTB 命中时，使用 Tournament Predictor 决定是否跳转
            if tp_impl is not None and tp_bimodal is not None:
                # 使用 Tournament Predictor 预测跳转方向
                tp_predict_taken = tp_impl.predict(
                    pc=final_current_pc,
                    bimodal_counters=tp_bimodal,
                    gshare_counters=tp_gshare,
                    global_history=tp_ghr,
                    selector_counters=tp_selector,
                )
                # BTB 命中 + TP 预测跳转 → 使用 BTB 目标
                # BTB 命中 + TP 预测不跳转 → PC + 4
                # BTB 未命中 → PC + 4
                predicted_next_pc = btb_hit.select(
                    tp_predict_taken.select(btb_predicted_target, default_next_pc),
                    default_next_pc,
                )
                debug_log(
                    "IF: BTB hit={}, TP predict_taken={}", btb_hit, tp_predict_taken
                )
            else:
                # 无 Tournament Predictor，使用原有逻辑：BTB 命中即跳转
                predicted_next_pc = btb_hit.select(btb_predicted_target, default_next_pc)
        else:
            # 无 BTB，使用简单的 PC + 4 逻辑
            predicted_next_pc = default_next_pc
    
        # 最终的 Next PC
        final_next_pc = predicted_next_pc

        # 更新 PC 寄存器
        pc_reg[0] <= final_next_pc
        last_pc_reg[0] <= final_current_pc
        debug_log(
            "IF: Next PC=0x{:x}  Next Last PC={:x}",
            final_next_pc,
            final_current_pc,
        )

        # --- 2. 驱动下游 Decoder (流控) ---
        # 发送到下一级，传递 PC 值与 Stall 信号（使用上一周期指令信号）
        call = decoder.async_called(
            pc=final_current_pc,
            next_pc=final_next_pc,
            stall=current_stall_if,
        )
        call.bind.set_fifo_depth(pc=1)

        return final_current_pc
