from assassyn.frontend import *
from .control_signals import wb_ctrl_signals
from .debug_utils import log_register_snapshot, debug_log

class WriteBack(Module):

    def __init__(self):
        super().__init__(
            ports={
                # 控制通路：包含 wb_ctrl 信号
                "ctrl": Port(wb_ctrl_signals),
                # 数据通路：来自 MEM 级的最终结果 (Mux 后的结果)
                "wdata": Port(Bits(32)),
            }
        )
        self.name = "WB"

    @module.combinational
    def build(self, reg_file: Array, wb_bypass_reg: Array):
        
        # 1. 获取输入
        wb_ctrl, wdata = self.pop_all_ports(False)
        rd = wb_ctrl.rd_addr
        halt_if = wb_ctrl.halt_if
        
        debug_log("Input: rd=x{} wdata=0x{:x}", rd, wdata)

        # 2. 写入逻辑 (Write Logic)
        # 当目标寄存器不是 x0 时写入指定寄存器
        with Condition(rd != Bits(5)(0)):
            debug_log("WB: Write x{} <= 0x{:x}", rd, wdata)
            
            # 驱动寄存器堆的 D 端和 WE 端
            reg_file[rd] = wdata
            wb_bypass_reg[0] = wdata
        
        # 3. 仿真终止检测 (Halt Detection)
        with Condition(halt_if == Bits(1)(1)):
            debug_log("WB: HALT triggered!")
            log_register_snapshot(reg_file)
            finish()

        # 4. 引脚暴露 (供 HazardUnit 使用)
        return rd
