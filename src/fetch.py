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
        sram_addr = (final_current_pc) >> UInt(32)(2)
        icache.build(we=Bits(1)(0), re=Bits(1)(1), addr=sram_addr, wdata=Bits(32)(0))
        log("IF: SRAM Addr=0x{:x}", sram_addr)

        # --- 2. 计算 Next PC (时序逻辑输入) ---
        # 默认：PC + 4
        final_next_pc = final_current_pc + UInt(32)(4)

        # 更新 PC 寄存器
        pc_reg[0] <= final_next_pc
        last_pc_reg[0] <= final_current_pc
        log("IF: Next PC=0x{:x} Next Last PC={:x}", final_next_pc, final_current_pc)

        # --- 3. 驱动下游 Decoder (流控) ---
        # 发送到下一级，只传递 PC 值
        call = decoder.async_called(pc=final_current_pc, next_pc=final_next_pc)
        call.bind.set_fifo_depth(pc=1)
