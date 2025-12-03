# RV32I MEM (MemoryAccess) 模块设计文档

> **依赖**：Assassyn Framework, `control_signals.py`

## 1. 模块概述

**MemoryAccess** 是流水线的访存响应阶段。
由于 SRAM 的读/写请求已在 EXE 阶段发出，MEM 阶段的职责如下：
1.  **数据接收**：从 SRAM 寄存器端口读取原始数据。
2.  **数据整形**：根据地址低位和指令类型（LB/LH/LW/LBU/LHU），对数据进行移位、截断和符号扩展。
3.  **路由选择**：在“加工后的内存数据”和“EX 阶段传来的 ALU 结果”之间进行选择。
4.  **分发**：将最终结果同时发送给 **WB 模块（下一级）** 和 **Bypass 网络（回传）**。

## 2. 接口定义

### 2.1 端口定义 (`__init__`)

接收来自 EXE 阶段的控制信号包以及两条数据通道。

``` python
class MemoryAccess(Module):
    def __init__(self):
        super().__init__(
            ports={
                # 1. 控制通道：包含 is_load, mem_width, mem_unsigned, wb_ctrl(rd)
                'ctrl': Port(mem_ctrl_signals),

                # 2. 统一数据通道：
                # - Load/Store 指令：SRAM 地址 (用于切割数据)
                # - ALU 指令：计算结果
                # - JAL/JALR 指令：PC+4 (由 EXE 级 Mux 进来)
                'alu_result': Port(Bits(32)) 
            }
        )
        self.name = 'MEM'
```

### 2.2 构建函数 (`build`)

参数如下：

```python
@module.combinational
def build(self, 
          wb_module: Module,         # 下一级流水线
          sram_dout: Array,       # SRAM 的输出端口 (Ref)
          mem_bypass_reg: Array   # 全局 Bypass 寄存器 (数据)
          ):
    # 实现见下文
    pass
```

内部实现：

#### 2.2.1 获取输入与拆包

```python
    # 1. 弹出并解
    ctrl, alu_result = self.pop_all_ports(False)
    
    # 提取需要的控制信号
    is_load = ctrl.is_load
    mem_width = ctrl.mem_width
    mem_unsigned = ctrl.mem_unsigned
```

#### 2.2.2 SRAM 数据加工 (Data Aligner)

这是 MEM 阶段最繁琐的组合逻辑。我们需要根据地址的低 2 位 (`alu_result[1:0]`) 从 32 位字中切出正确的字节。

```python
    # 1. 读取 SRAM 原始数据 (32-bit)
    raw_mem = sram_dout[0].bitcast(Bits(32))
    
    # 2. 二分选择半字 (16-bit Candidates)
    # 根据 alu_result[1:1] (地址第1位) 选择高16位还是低16位
    # 0 -> 低16位 [15:0]
    # 1 -> 高16位 [31:16]
    half_selected = alu_result[1:1].select(raw_mem[16:32], raw_mem[0:16])

    # 3. 二分选择字节 (8-bit Candidates)
    # 在刚才选出的半字基础上，根据 alu_result[0:0] (地址第0位) 选择高8位还是低8位
    # 0 -> 低8位
    # 1 -> 高8位
    byte_selected = alu_result[0:0].select(half_selected[8:16], half_selected[0:8])

    # 此时我们有了三个维度的候选者：
    # A. byte_selected: 无论地址是多少，这里都是你要的那个字节 (8-bit)
    # B. half_selected: 无论地址是多少，这里都是你要的那个半字 (16-bit)
    # C. raw_mem:       原始字 (32-bit)

    # 4. 统一处理符号位
    # 技巧：无论是有符号还是无符号，先算出 "填充位 (Padding Bit)" 是 0 还是 1
    
    # 对于 Byte：如果是无符号，填充0；否则填充最高位(第7位)
    pad_bit_8 = mem_unsigned.select(Bits(1)(0), byte_selected[7:7])
    # 生成 24 位的填充掩码 (全0 或 全1)
    padding_8 = pad_bit_8.select(Bits(24)(0xffffff), Bits(24)(0))
    # 拼接
    byte_extended = concat(padding_8, byte_selected)

    # 对于 Half：如果是无符号，填充0；否则填充最高位(第15位)
    pad_bit_16 = mem_unsigned.select(Bits(1)(0), half_selected[15:15])
    # 生成 16 位的填充掩码
    padding_16 = pad_bit_16.select(Bits(16)(0xffff), Bits(16)(0))
    # 拼接
    half_extended = concat(padding_16, half_selected)

    # 5. 根据位宽指令选择最终结果
    # 使用 mem_width 作为选择信号 (独热码)
    processed_mem_result = mem_width.select1hot(
        byte_extended,  # 对应 is_byte 
        half_extended,  # 对应 is_half
        raw_mem         # 对应 is_word
    )
```

#### 2.2.3 最终数据选择 (Final Mux)

决定传递给 WB 的数据来自内存读取抑或 ALU 计算。

```python
    # 如果是 Load 指令，用加工后的内存数据
    # 否则 (ALU运算/JAL/LUI)，用 EX 传下来的 alu_result
    final_data = is_load.select(processed_mem_result, alu_result)
```

#### 2.2.4 输出驱动 (Output Driver)

同时将结果存入旁路寄存器和级间寄存器。

```python
    # 1. 驱动全局 Bypass 寄存器 (Side Channel)
    # 这使得下下条指令 (ID级) 能在当前周期看到结果
    # 注意：如果当前是气泡 (rd=0)，写入 0 也是安全的
    mem_bypass_reg[0] = final_data

    # 2. 驱动下一级 WB (Main Channel)
    # 剥离外层 mem_ctrl，只传 wb_ctrl
    wb_call = wb_module.async_called(
        ctrl = ctrl.wb_ctrl,
        wdata = final_data
    )
    
    # [关键]：设置 FIFO 深度为 1 (刚性流水线特征)
    wb_call.bind.set_fifo_depth(ctrl=1, wdata=1)

    # 3. 状态暴露
    # 将当前的控制包返回，供 DataHazardUnit 使用
    return ctrl
```