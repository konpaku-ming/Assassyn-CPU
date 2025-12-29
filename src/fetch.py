from assassyn.frontend import *
from .control_signals import *


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
        icache: SRAM,  # 引用 ICache
        decoder: Module,  # 下一级模块 (用于发送指令)
        # --- 反馈控制信号 (来自 DataHazardUnit/ControlHazardReg) ---
        stall_if: Value,  # 暂停取指 (保持当前 PC)
        branch_target: Array,  # 不为0时，根据目标地址冲刷流水线
        # --- BTB 分支预测 ---
        btb_impl: "BTBImpl",  # BTB 实现逻辑
        btb_valid: Array,  # BTB 有效位数组
        btb_tags: Array,  # BTB 标签数组
        btb_targets: Array,  # BTB 目标地址数组
        # --- BHT 分支方向预测 (2-bit saturating counter) ---
        bht_impl: "BHTImpl" = None,  # BHT 实现逻辑
        bht_counters: Array = None,  # BHT 计数器数组
    ):
        current_stall_if = stall_if.optional(Bits(1)(0))

        with Condition(current_stall_if == Bits(1)(1)):
            log("IF: Stall")

        # 读取当前 PC
        current_pc = current_stall_if.select(last_pc_reg[0], pc_addr)

        flush_if = branch_target[0] != Bits(32)(0)
        target_pc = branch_target[0]

        with Condition(flush_if == Bits(1)(1)):
            log("IF: Flush to 0x{:x}", target_pc)

        final_current_pc = flush_if.select(target_pc, current_pc)
        log("IF: Final Current PC=0x{:x}", final_current_pc)

        # --- 1. 驱动 SRAM (组合逻辑输出) ---
        # 决定是否给 SRAM 喂地址以及喂什么地址
        # 如果 Flush，为了让下一拍 ID 能拿到新指令，必须立刻喂 Target
        # 如果 Stall，必须输入上一周期地址以稳住输出
        # 如果 Normal，喂 Current 读取当前指令
        sram_addr = ((final_current_pc) >> UInt(32)(2))[0:15]
        icache.build(we=Bits(1)(0), re=Bits(1)(1), addr=sram_addr, wdata=Bits(32)(0))
        log("IF: SRAM Addr=0x{:x}", sram_addr)

        # --- 2. 计算 Next PC (时序逻辑输入) ---
        # 使用 BTB 进行分支目标预测
        btb_hit, btb_predicted_target = btb_impl.predict(
            pc=final_current_pc,
            btb_valid=btb_valid,
            btb_tags=btb_tags,
            btb_targets=btb_targets,
        )

        # 默认: PC + 4
        btb_miss_target = (final_current_pc.bitcast(UInt(32)) + UInt(32)(4)).bitcast(Bits(32))

        # 分支预测逻辑：
        # - BTB 命中时：使用 BHT 的 2-bit 饱和计数器判断是否跳转
        #   - 如果 BHT 预测跳转 (counter >= 2)：使用 BTB 预测的目标地址
        #   - 如果 BHT 预测不跳转：使用 PC + 4
        # - BTB 未命中时：使用 PC + 4（与之前行为相同）
        if bht_impl is not None and bht_counters is not None:
            # 使用 BHT 进行方向预测
            bht_predict_taken = bht_impl.predict(
                pc=final_current_pc,
                bht_counters=bht_counters,
            )

            # BTB 命中 + BHT 预测跳转：使用 BTB 目标
            # BTB 命中 + BHT 预测不跳转：使用 PC + 4
            # BTB 未命中：使用 PC + 4
            btb_hit_target = bht_predict_taken.select(btb_predicted_target, btb_miss_target)
            predicted_next_pc = btb_hit.select(btb_hit_target, btb_miss_target)

            with Condition(btb_hit == Bits(1)(1)):
                with Condition(bht_predict_taken == Bits(1)(1)):
                    log("IF: BTB HIT + BHT TAKEN -> Target=0x{:x}", btb_predicted_target)
                with Condition(bht_predict_taken == Bits(1)(0)):
                    log("IF: BTB HIT + BHT NOT TAKEN -> PC+4=0x{:x}", btb_miss_target)
        else:
            # 没有 BHT，使用原始逻辑：BTB 命中则使用目标，否则 PC + 4
            predicted_next_pc = btb_hit.select(btb_predicted_target, btb_miss_target)
    
        # 最终的 Next PC
        final_next_pc = predicted_next_pc

        # 更新 PC 寄存器
        pc_reg[0] <= final_next_pc
        last_pc_reg[0] <= final_current_pc
        log(
            "IF: Next PC=0x{:x}  Next Last PC={:x}",
            final_next_pc,
            # btb_hit,
            final_current_pc,
        )

        # --- 3. 驱动下游 Decoder (流控) ---
        # 发送到下一级，只传递 PC 值
        call = decoder.async_called(pc=final_current_pc, next_pc=final_next_pc)
        call.bind.set_fifo_depth(pc=1)
