from assassyn.frontend import *
from .control_signals import *


class Fetcher(Module):
    def __init__(self):
        super().__init__(
            ports={}, # Fetcher 是起点，通常不需要被别人 async_called
            no_arbiter=True
        )
        self.name = 'F'

    @module.combinational
    def build(self):
        # 1. PC 寄存器
        # 初始化为 0 (Reset Vector)
        pc_reg = RegArray(Bits(32), 1, initializer=[0])
        
        # 暴露寄存器引用供 Impl 使用
        return pc_reg


class FetcherImpl(Downstream):
    @downstream.combinational
    def build(self,
        # --- 资源引用 ---
        pc_reg: Array,        # 引用 Fetcher 的 PC
        icache: SRAM,         # 引用 ICache
        decoder: Module,      # 下一级模块 (用于发送指令)

        # --- 反馈控制信号 (来自 DataHazardUnit/ControlHazardUnit) ---
        stall_if: Value,      # 暂停取指 (保持当前 PC)
        branch_target: Array, # 不为0时，根据目标地址冲刷流水线
    ):
        # 读取当前 PC
        current_pc = pc_reg[0]
        
        # --- 1. 计算 Next PC (时序逻辑输入) ---
        # 默认：PC + 4
        pc_next_normal = current_pc + 4
        
        # 处理 Stall：保持原值
        pc_next_stall = stall_if.optional(Bits(1)(0)).select(current_pc, pc_next_normal)
        
        # 处理 Flush：跳转目标 (优先级最高，覆盖 Stall)
        flush_if = branch_target[0] != Bits(32)(0)
        target_pc = branch_target[0]
        final_next_pc = flush_if.select(target_pc, pc_next_stall)
        
        # 更新 PC 寄存器
        pc_reg[0] <= final_next_pc

        # --- 2. 驱动 SRAM (组合逻辑输出) ---
        # 决定给 SRAM 喂什么地址
        # 如果 Flush，为了让下一拍 ID 能拿到新指令，必须立刻喂 Target
        # 如果 Stall，必须喂 Current 稳住输出
        # 如果 Normal，喂 Current (读取当前指令)
        # 综上：只有 Flush 时喂 Target，否则喂 Current
        sram_addr = flush_if.select(target_pc, current_pc)
        
        icache.build(we=Bits(1)(0), re=Bits(1)(1), addr=sram_addr, wdata=Bits(32)(0))

        # --- 3. 驱动下游 Decoder (流控) ---
        # 构造数据包
        # 注意：这里需要根据实际的控制信号包结构来定义
        # 由于IF阶段还没有解码，我们只需要传递PC和指令
        # 指令将从icache的输出获取
        
        # 获取指令数据
        inst_data = icache.dout
        
        # 只有在不stall时才发送数据
        with Condition(~stall_if.optional(Bits(1)(0))):
            # 如果是flush，发送NOP包；否则发送正常包
            is_flush = flush_if
            nop_inst = Bits(32)(0x00000013)  # ADDI x0, x0, 0 (NOP指令)
            final_inst = is_flush.select(nop_inst, inst_data)
            
            # 记录日志
            log("IF: PC=0x{:x} Inst=0x{:x} Stall={} Flush={}", 
                current_pc, final_inst, 
                stall_if.optional(Bits(1)(0)) == Bits(1)(1),
                is_flush == Bits(1)(1))
            
            # 发送到下一级
            decoder.async_called(pc=current_pc, inst=final_inst)