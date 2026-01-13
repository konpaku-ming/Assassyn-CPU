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
        # 1. 弹出并解包，提取需要的控制信号
        ctrl, alu_result = self.pop_all_ports(False)
        mem_opcode = ctrl.mem_opcode
        mem_width = ctrl.mem_width
        mem_unsigned = ctrl.mem_unsigned
        wb_ctrl = wb_ctrl_signals.view(ctrl.wb_ctrl)

        with Condition(mem_opcode == MemOp.NONE):
            log("MEM: OP NONE.")
        with Condition(mem_opcode == MemOp.LOAD):
            log("MEM: OP LOAD.")
        with Condition(mem_opcode == MemOp.STORE):
            log("MEM: OP STORE.")

        with Condition(mem_width == MemWidth.BYTE):
            log("MEM: WIDTH BYTE.")
        with Condition(mem_width == MemWidth.HALF):
            log("MEM: WIDTH HALF.")
        with Condition(mem_width == MemWidth.WORD):
            log("MEM: WIDTH WORD.")

        with Condition(mem_unsigned == Bits(1)(1)):
            log("MEM: UNSIGNED.")
        with Condition(mem_unsigned == Bits(1)(0)):
            log("MEM: SIGNED.")

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
        is_store = mem_opcode == MemOp.STORE  # 检查是否为 Store 指令
        final_data = is_load.select(processed_mem_result, alu_result)

        # 4. 输出驱动 (Output Driver)
        # 驱动级间 Bypass 寄存器
        # 注意：如果当前是气泡 (rd=0)，写入 0 也是安全的
        mem_bypass_reg[0] = final_data

        log("MEM: Bypass <= 0x{:x}", final_data)

        # 驱动下一级 WB (Main Channel)
        wb_call = wb_module.async_called(ctrl=wb_ctrl, wdata=final_data)
        wb_call.bind.set_fifo_depth(ctrl=1, wdata=1)

        # 引脚暴露 (供 HazardUnit 使用)
        return wb_ctrl.rd_addr, is_store


class SingleMemory(Downstream):
    def __init__(self):
        super().__init__()
        self.name = "SingleMEM"

    @downstream.combinational
    def build(
        self,
        # --- 来自 IF 阶段的接口 ---
        if_addr: Value,  # 取指地址 (PC)
        # --- 来自 EX 阶段的接口 (优先) ---
        mem_addr: Value,  # 访存地址 (ALU Result)
        re: Value,  # 读使能 (Load)
        we: Value,  # 写使能 (Store)
        wdata: Value,  # 写数据 (Store Value)
        width: Value,  # 访存宽度 (Byte/Half/Word)
        sram: SRAM,  # 物理 SRAM 资源引用
    ):
        # 0. 使用 optional 弹出端口
        if_addr_val = if_addr.optional(Bits(32)(0))
        mem_addr_val = mem_addr.optional(Bits(32)(0))
        re_val = re.optional(Bits(1)(0))
        we_val = we.optional(Bits(1)(0))
        wdata_val = wdata.optional(Bits(32)(0))
        width_val = width.optional(Bits(3)(1))

        # 1. 定义状态寄存器
        # 0: IDLE/READ Phase; 1: WRITE Phase
        store_state = RegArray(Bits(1), 1, initializer=[0])
        # 定义锁存器，用于跨周期传递 Store 信息)
        store_addr = RegArray(Bits(32), 1)
        store_data = RegArray(Bits(32), 1)
        store_width = RegArray(Bits(3), 1)

        # 2. 状态迁移逻辑
        # store_state 更新
        store_reg_refresh = we_val & ~store_state[0]
        store_state[0] <= store_reg_refresh.select(Bits(1)(1), Bits(1)(0))
        # 地址寄存器更新
        store_addr[0] <= store_reg_refresh.select(mem_addr_val, Bits(32)(0))
        # 长度独热码寄存器更新
        store_width[0] <= store_reg_refresh.select(width_val, Bits(3)(1))
        # 写数据寄存器更新
        store_data[0] <= store_reg_refresh.select(wdata_val, Bits(32)(0))

        # 3. SRAM 输入计算
        # 读使能/写使能确定
        SRAM_we = store_state[0]
        SRAM_re = ~store_state[0]
        # 地址计算与仲裁
        final_mem_addr = store_state[0].select(store_addr[0], mem_addr_val)
        ex_request = we_val | re_val | store_state[0]
        SRAM_addr = ex_request.select(final_mem_addr, if_addr_val)

        # 写数据计算
        final_wdata = store_state[0].select(store_data[0], Bits(32)(0))
        final_width = store_state[0].select(store_width[0], Bits(3)(1))
        # 计算位偏移 (addr[0:1] * 8)
        shamt = (final_mem_addr[0:1].concat(Bits(3)(0))).bitcast(UInt(5))
        # 生成基础掩码
        raw_mask = final_width.select1hot(
            Bits(32)(0x000000FF),  # Byte (bit 0)
            Bits(32)(0x0000FFFF),  # Half (bit 1)
            Bits(32)(0xFFFFFFFF),  # Word (bit 2)
        ).bitcast(UInt(32))
        # 移位到目标位置
        shifted_mask = raw_mask << shamt
        shifted_data = final_wdata << shamt
        # 利用掩码进行拼接，得到结果
        SRAM_wdata = (sram.dout[0] & (~shifted_mask)) | (shifted_data & shifted_mask)

        # 4. 驱动 SRAM 端口
        SRAM_trunc_addr = (SRAM_addr >> Bits(32)(2))[0:15]
        sram.build(
            addr=SRAM_trunc_addr,
            re=SRAM_re,
            we=SRAM_we,
            wdata=SRAM_wdata,
        )

        MMIO_if = SRAM_addr.bitcast(UInt(32)) >= Bits(32)(0xFFFF0000)
        with Condition(MMIO_if & (SRAM_we == Bits(1)(1))):
            log("MMIO 0x{:x} at address 0x{:x}", SRAM_wdata, SRAM_addr)
