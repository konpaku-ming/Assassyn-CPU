from assassyn.frontend import *
from .control_signals import *


class MemoryAccess(Module):
    def __init__(self):
        super().__init__(
            ports={
                # 1. 控制通道：包含 mem_opcode, mem_width, mem_unsigned, rd_addr
                "ctrl": Port(mem_ctrl_signals),
                # 2. 统一数据通道：
                # - Load/Store 指令：SRAM 地址 (用于切割数据)
                # - ALU 指令：计算结果
                # - JAL/JALR 指令：PC+4 (由 EX 级 Mux 进来)
                "alu_result": Port(Bits(32)),
            }
        )
        self.name = "MEM"

    @module.combinational
    def build(
        self,
        wb_module: Module,  # 下一级流水线 (writeback.py)
        sram_dout: Array,  # SRAM 的输出端口 (Ref)
        mem_bypass_reg: Array,  # 全局 Bypass 寄存器 (数据)
    ):
        # 1. 弹出并解包
        ctrl, alu_result = self.pop_all_ports(False)

        # 提取需要的控制信号
        mem_opcode = ctrl.mem_opcode
        mem_width = ctrl.mem_width
        mem_unsigned = ctrl.mem_unsigned

        # 2. SRAM 数据加工 (Data Aligner)
        # 读取 SRAM 原始数据 (32-bit)
        raw_mem = sram_dout[0].bitcast(Bits(32))

        # 二分选择半字 (16-bit Candidates)
        # 根据 alu_result[1:1] (地址第1位) 选择高16位还是低16位
        # 0 -> 低16位 [15:0]
        # 1 -> 高16位 [31:16]
        half_selected = alu_result[1:1].select(raw_mem[16:31], raw_mem[0:15])

        # 二分选择字节 (8-bit Candidates)
        # 在刚才选出的半字基础上，根据 alu_result[0:0] (地址第0位) 选择高8位还是低8位
        # 0 -> 低8位
        # 1 -> 高8位
        byte_selected = alu_result[0:0].select(half_selected[8:15], half_selected[0:7])

        # 统一处理符号位
        # 对于 Byte：如果是无符号，填充0；否则填充最高位(第7位)
        pad_bit_8 = mem_unsigned.select(Bits(1)(0), byte_selected[7:7])
        # 生成 24 位的填充掩码 (全0 或 全1)
        padding_8 = pad_bit_8.select(Bits(24)(0xFFFFFF), Bits(24)(0))
        # 拼接
        byte_extended = concat(padding_8, byte_selected)

        # 对于 Half：如果是无符号，填充0；否则填充最高位(第15位)
        pad_bit_16 = mem_unsigned.select(Bits(1)(0), half_selected[15:15])
        # 生成 16 位的填充掩码
        padding_16 = pad_bit_16.select(Bits(16)(0xFFFF), Bits(16)(0))
        # 拼接
        half_extended = concat(padding_16, half_selected)

        # 根据位宽指令选择最终结果
        # 使用 mem_width 作为选择信号 (独热码)
        processed_mem_result = mem_width.select1hot(
            byte_extended,  # 对应 MemWidth.BYTE
            half_extended,  # 对应 MemWidth.HALF
            raw_mem,  # 对应 MemWidth.WORD
        )

        # 3. 最终数据选择 (Final Mux)
        # 如果是 Load 指令，用加工后的内存数据
        # 否则 (ALU运算/JAL/LUI)，用 EX 传下来的 alu_result
        is_load = mem_opcode == MemOp.LOAD  # 检查是否为 Load 指令
        final_data = is_load.select(processed_mem_result, alu_result)

        # 4. 输出驱动 (Output Driver)
        # 驱动全局 Bypass 寄存器 (Side Channel)
        # 这使得下下条指令 (ID级) 能在当前周期看到结果
        # 注意：如果当前是气泡 (rd=0)，写入 0 也是安全的
        mem_bypass_reg[0] = final_data

        # 添加日志输出，方便测试验证
        log("MEM: Bypass <= 0x{:x}", final_data)

        # 驱动下一级 WB (Main Channel)
        # 剥离外层 mem_ctrl，只传 wb_ctrl
        wb_call = wb_module.async_called(ctrl=ctrl.rd_addr, wdata=final_data)

        # 设置 FIFO 深度为 1 (刚性流水线特征)
        wb_call.bind.set_fifo_depth(ctrl=1, wdata=1)

        # 状态暴露
        # 将当前的控制包返回，供 DataHazardUnit 使用
        return ctrl.rd_addr
