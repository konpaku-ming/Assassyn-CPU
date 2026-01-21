# RV32I MEM (MemoryAccess) 模块设计文档

> **依赖**：Assassyn Framework, `control_signals.py`

## 1. 模块概述

**MemoryAccess** 是流水线的访存响应阶段。本 CPU 采用 **统一内存架构**，使用 `SingleMemory` 模块处理所有内存访问（包括取指和数据访存）。

MEM 阶段的职责如下：
1. **数据接收**：从 SRAM 寄存器端口读取原始数据
2. **数据整形**：根据地址低位和指令类型（LB/LH/LW/LBU/LHU），对数据进行移位、截断和符号扩展
3. **路由选择**：在"加工后的内存数据"和"EX 阶段传来的 ALU 结果"之间进行选择
4. **分发**：将最终结果同时发送给 **WB 模块（下一级）** 和 **Bypass 网络（回传）**

## 2. 接口定义

### 2.1 MemoryAccess 端口定义

```python
class MemoryAccess(Module):
    def __init__(self):
        super().__init__(
            ports={
                # 1. 控制通道：包含 mem_opcode, mem_width, mem_unsigned, wb_ctrl
                "ctrl": Port(mem_ctrl_signals),
                # 2. 统一数据通道：
                # - Load/Store 指令：SRAM 地址 (用于切割数据)
                # - ALU 指令：计算结果
                # - JAL/JALR 指令：PC+4
                "alu_result": Port(Bits(32)),
            }
        )
        self.name = "MEM"
```

### 2.2 构建函数

```python
@module.combinational
def build(
    self,
    wb_module: Module,      # 下一级流水线 (WriteBack)
    sram_dout: Array,       # SRAM 的输出端口
    mem_bypass_reg: Array,  # 全局 Bypass 寄存器
):
```

## 3. 内部实现

### 3.1 获取输入与拆包

```python
ctrl, alu_result = self.pop_all_ports(False)
mem_opcode = ctrl.mem_opcode
mem_width = ctrl.mem_width
mem_unsigned = ctrl.mem_unsigned
wb_ctrl = wb_ctrl_signals.view(ctrl.wb_ctrl)
```

### 3.2 SRAM 数据加工 (Data Aligner)

根据地址低位从 32 位字中提取正确的字节/半字：

```python
# 1. 读取 SRAM 原始数据 (32-bit)
raw_mem = sram_dout[0].bitcast(Bits(32))

# 2. 二分选择半字 (根据 alu_result[1:1])
# 0 -> 低16位 [15:0]
# 1 -> 高16位 [31:16]
half_selected = alu_result[1:1].select(raw_mem[16:31], raw_mem[0:15])

# 3. 二分选择字节 (根据 alu_result[0:0])
# 0 -> 低8位
# 1 -> 高8位
byte_selected = alu_result[0:0].select(half_selected[8:15], half_selected[0:7])
```

### 3.3 符号扩展

```python
# 对于 Byte：如果是无符号，填充0；否则填充最高位(第7位)
pad_bit_8 = mem_unsigned.select(Bits(1)(0), byte_selected[7:7])
padding_8 = pad_bit_8.select(Bits(24)(0xFFFFFF), Bits(24)(0))
byte_extended = concat(padding_8, byte_selected)

# 对于 Half：如果是无符号，填充0；否则填充最高位(第15位)
pad_bit_16 = mem_unsigned.select(Bits(1)(0), half_selected[15:15])
padding_16 = pad_bit_16.select(Bits(16)(0xFFFF), Bits(16)(0))
half_extended = concat(padding_16, half_selected)

# 根据位宽选择最终结果 (独热码)
processed_mem_result = mem_width.select1hot(
    byte_extended,  # MemWidth.BYTE
    half_extended,  # MemWidth.HALF
    raw_mem,        # MemWidth.WORD
)
```

### 3.4 最终数据选择

```python
# 如果是 Load 指令，用加工后的内存数据
# 否则 (ALU运算/JAL/LUI)，用 EX 传下来的 alu_result
is_load = mem_opcode == MemOp.LOAD
final_data = is_load.select(processed_mem_result, alu_result)
```

### 3.5 输出驱动

```python
# 1. 驱动全局 Bypass 寄存器
mem_bypass_reg[0] = final_data

# 2. 驱动下一级 WB
wb_call = wb_module.async_called(ctrl=wb_ctrl, wdata=final_data)
wb_call.bind.set_fifo_depth(ctrl=1, wdata=1)

# 3. 返回引脚供 HazardUnit 使用
return wb_ctrl.rd_addr, is_store
```

## 4. SingleMemory 模块

**SingleMemory** 是统一内存访问控制器，处理 IF 阶段的取指请求和 EX 阶段的数据访存请求。

### 4.1 接口定义

```python
class SingleMemory(Downstream):
    @downstream.combinational
    def build(
        self,
        if_addr: Value,    # 取指地址 (PC)
        mem_addr: Value,   # 访存地址 (ALU Result)
        re: Value,         # 读使能 (Load)
        we: Value,         # 写使能 (Store)
        wdata: Value,      # 写数据 (Store Value)
        width: Value,      # 访存宽度 (Byte/Half/Word)
        sram: SRAM,        # 物理 SRAM 资源引用
    ):
```

### 4.2 状态机设计

SingleMemory 使用两阶段状态机处理 Store 操作（读-修改-写）：

| 状态 | 行为 |
| :--- | :--- |
| `0` (IDLE/READ) | 处理 IF 取指或 Load 读取 |
| `1` (WRITE) | 执行 Store 写入（RMW 完成） |

### 4.3 地址仲裁

```python
# EX 阶段请求优先级高于 IF 阶段
ex_request = we_val | re_val | store_state[0]
final_mem_addr = store_state[0].select(store_addr[0], mem_addr_val)
SRAM_addr = ex_request.select(final_mem_addr, if_addr_val)
```

### 4.4 Store 数据处理

支持 Byte/Half/Word 粒度的写入：

```python
# 计算位偏移 (addr[0:1] * 8)
shamt = (final_mem_addr[0:1].concat(Bits(3)(0))).bitcast(UInt(5))

# 生成基础掩码
raw_mask = final_width.select1hot(
    Bits(32)(0x000000FF),  # Byte
    Bits(32)(0x0000FFFF),  # Half
    Bits(32)(0xFFFFFFFF),  # Word
)

# 移位到目标位置
shifted_mask = raw_mask << shamt
shifted_data = final_wdata << shamt

# 利用掩码进行读-修改-写
SRAM_wdata = (sram.dout[0] & (~shifted_mask)) | (shifted_data & shifted_mask)
```

### 4.5 MMIO 支持

支持 MMIO 地址空间（地址 >= 0xFFFF0000）的输出：

```python
MMIO_if = SRAM_addr.bitcast(UInt(32)) >= Bits(32)(0xFFFF0000)
with Condition(MMIO_if & (SRAM_we == Bits(1)(1))):
    debug_log("MMIO 0x{:x} at address 0x{:x}", SRAM_wdata, SRAM_addr)
```
