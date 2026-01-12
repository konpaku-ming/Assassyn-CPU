from assassyn.frontend import *


class WriteBack(Module):

    def __init__(self):
        super().__init__(
            ports={
                # 控制通路：包含 rd_addr
                "ctrl": Port(Bits(5)),
                # 数据通路：来自 MEM 级的最终结果 (Mux 后的结果)
                "wdata": Port(Bits(32)),
            }
        )
        self.name = "WB"

    @module.combinational
    def build(self, reg_file: Array, wb_bypass_reg: Array):
        
        # 1. 获取输入 (Consume)
        rd, wdata = self.pop_all_ports(False)
        log("Input: rd=x{} wdata=0x{:x}", rd, wdata)

        # 2. 写入逻辑 (Write Logic)
        # 物理含义：生成寄存器堆的 Write Enable 信号
        # 只有当目标寄存器不是 x0 且 is_wb 为 1 时，才允许写入
        with Condition(rd != Bits(5)(0)):
            # 调试日志：打印写回操作
            log("WB: Write x{} <= 0x{:x}", rd, wdata)

            # 驱动寄存器堆的 D 端和 WE 端
            reg_file[rd] = wdata

            wb_bypass_reg[0] = wdata

        # 3. 状态反馈 (Feedback to Hazard Unit)
        # 将当前的 rd 返回，供 DataHazardUnit (Downstream) 使用
        return rd
