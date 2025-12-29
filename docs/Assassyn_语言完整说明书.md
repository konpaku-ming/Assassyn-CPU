# Assassyn 硬件描述语言完整说明书

## 目录

1. [概述](#1-概述)
2. [基础数据类型](#2-基础数据类型)
3. [数据包裹与结构](#3-数据包裹与结构)
4. [状态存储单元](#4-状态存储单元)
5. [架构单元](#5-架构单元)
6. [接口与控制](#6-接口与控制)
7. [运算符与操作函数](#7-运算符与操作函数)
8. [时序与通信模型](#8-时序与通信模型)
9. [仿真与测试](#9-仿真与测试)
10. [完整示例](#10-完整示例)

---

## 1. 概述

### 1.1 什么是 Assassyn

Assassyn 是一种基于 Python 的硬件描述语言 (HDL)，专门用于设计数字电路和处理器。它将硬件设计抽象为 Python 类和对象，使得硬件开发更加直观和高效。

### 1.2 核心特点

- **Python 原生语法**：使用熟悉的 Python 语法编写硬件
- **强类型系统**：严格的位宽和类型检查
- **延迟不敏感设计**：基于 FIFO 的弹性流水线
- **自动布线**：模块间通信自动生成连接逻辑
- **多后端支持**：可生成 Verilog 或直接仿真

### 1.3 导入方式

```python
from assassyn.frontend import *
from assassyn.backend import elaborate, config
from assassyn import utils
```

---

## 2. 基础数据类型

基础数据类型对应电路中的连线 (Wires)，其值为 0/1 位向量，对应线上的高低电平。

### 2.1 `Bits(width)` — 无符号位向量

**作用**：表示无符号位向量，用于不涉及算术运算的控制信号、操作码或原始数据。

**语法**：
```python
Bits(width)(value)  # 创建带初始值的位向量
Bits(width)         # 声明位向量类型
```

**示例**：
```python
# 定义 7 位宽的常量，二进制值为 0b0110111
LUI_OPCODE = Bits(7)(0b0110111)

# 定义 32 位宽的立即数
imm_value = Bits(32)(0x12345678)

# 定义 1 位宽的使能信号
enable = Bits(1)(1)

# 定义 5 位的寄存器地址
rd_addr = Bits(5)(3)  # 目标寄存器 x3
```

**使用场景**：
- 指令操作码 (opcode)
- 控制信号
- 地址
- 独热码选择信号

### 2.2 `UInt(width)` — 无符号整数

**作用**：表示无符号整数，用于需要算术运算的场景。

**语法**：
```python
UInt(width)(value)  # 创建带初始值的无符号整数
UInt(width)         # 声明无符号整数类型
```

**示例**：
```python
# 32 位无符号计数器
counter = UInt(32)(0)

# 无符号加法
result = counter + UInt(32)(1)

# 无符号比较
is_less = UInt(32)(5) < UInt(32)(10)

# PC 地址计算（无符号）
next_pc = (pc.bitcast(UInt(32)) + UInt(32)(4)).bitcast(Bits(32))
```

**使用场景**：
- 计数器
- 地址计算
- 无符号算术运算

### 2.3 `Int(width)` / `SInt(width)` — 有符号整数

**作用**：表示有符号整数（补码表示），用于需要有符号算术运算的场景。

**语法**：
```python
Int(width)(value)   # 创建带初始值的有符号整数
Int(width)          # 声明有符号整数类型
```

**示例**：
```python
# 将 Bits 转换为有符号整数进行算术运算
op1_signed = alu_op1.bitcast(Int(32))
op2_signed = alu_op2.bitcast(Int(32))

# 有符号加法
add_result = (op1_signed + op2_signed).bitcast(Bits(32))

# 有符号减法
sub_result = (op1_signed - op2_signed).bitcast(Bits(32))

# 有符号比较（小于）
slt_result = (op1_signed < op2_signed).bitcast(Bits(32))

# 算术右移（保持符号位）
sra_result = (op1_signed >> UInt(5)(5)).bitcast(Bits(32))
```

**使用场景**：
- 有符号算术运算
- 算术右移
- 有符号比较

### 2.4 类型转换：`bitcast()`

**作用**：重解释位向量的类型，不改变底层位模式。

**语法**：
```python
value.bitcast(target_type)
```

**示例**：
```python
# Bits -> Int (用于有符号运算)
bits_val = Bits(32)(0xFFFFFFFF)  # 二进制全 1
signed_val = bits_val.bitcast(Int(32))  # 解释为 -1

# Int -> Bits (运算后转回 Bits)
result = (a.bitcast(Int(32)) + b.bitcast(Int(32))).bitcast(Bits(32))

# UInt -> Bits
addr = pc.bitcast(UInt(32)) + UInt(32)(4)
next_pc = addr.bitcast(Bits(32))
```

**注意**：`bitcast()` 不生成任何逻辑门，只是告诉编译器换一种方式解释同一束线。

---

## 3. 数据包裹与结构

数据包裹与结构用于对连线进行逻辑分组，或处理数据有效性的元数据。

### 3.1 `Record(fields)` — 硬件结构体

**作用**：将多个信号打包成一个结构体，类似于 C 语言的 struct。

**语法**：
```python
# 定义结构体类型
my_record = Record(
    field1=Bits(width1),
    field2=Bits(width2),
    nested=another_record,  # 支持嵌套
)

# 创建结构体实例（打包）
instance = my_record.bundle(
    field1=value1,
    field2=value2,
    nested=nested_instance,
)

# 解析结构体（解包）
view = my_record.view(packed_data)
field1_value = view.field1
```

**示例**：
```python
# 定义内存控制信号结构体
mem_ctrl_signals = Record(
    mem_opcode=Bits(3),     # 内存操作类型
    mem_width=Bits(3),      # 访问宽度
    mem_unsigned=Bits(1),   # 是否无符号扩展
    rd_addr=Bits(5),        # 目标寄存器地址
)

# 定义执行阶段控制信号（包含嵌套 Record）
ex_ctrl_signals = Record(
    alu_func=Bits(32),      # ALU 功能码
    op1_sel=Bits(3),        # 操作数 1 选择
    op2_sel=Bits(3),        # 操作数 2 选择
    branch_type=Bits(16),   # 分支类型
    mem_ctrl=mem_ctrl_signals,  # 嵌套的内存控制
)

# 打包数据
mem_ctrl = mem_ctrl_signals.bundle(
    mem_opcode=MemOp.LOAD,
    mem_width=MemWidth.WORD,
    mem_unsigned=Bits(1)(0),
    rd_addr=Bits(5)(3),
)

# 解包数据
ctrl = ex_ctrl_signals.view(packed_ctrl)
alu_op = ctrl.alu_func
mem_op = mem_ctrl_signals.view(ctrl.mem_ctrl).mem_opcode
```

**使用场景**：
- 流水线级间信号传递
- 复杂控制信号打包
- 模块接口定义

### 3.2 `Value` — 可选数据容器

**作用**：包含 `{Data, Valid}` 的对象，用于处理可能无效的数据（如流水线气泡）。

**语法**：
```python
# Value 通常由框架自动生成，用于处理来自上游的可选数据
data = value.optional(default_value)  # 如果无效返回默认值
```

**示例**：
```python
class DataHazardUnit(Downstream):
    @downstream.combinational
    def build(
        self,
        rs1_idx: Value,      # 可能无效的源寄存器索引
        ex_rd: Value,        # 可能无效的 EX 级目标寄存器
        ex_is_load: Value,   # 可能无效的加载标志
    ):
        # 使用 optional() 处理无效数据
        rs1_idx_val = rs1_idx.optional(Bits(5)(0))  # 无效时返回 0
        ex_rd_val = ex_rd.optional(Bits(5)(0))
        ex_is_load_val = ex_is_load.optional(Bits(1)(0))
        
        # 现在可以安全使用这些值
        hazard = (rs1_idx_val == ex_rd_val) & ex_is_load_val
```

**使用场景**：
- 处理流水线气泡
- 处理可选的反馈信号
- 模块间数据传递的有效性检查

---

## 4. 状态存储单元

状态存储单元是具有记忆能力的电路单元，用于实现时序逻辑。

### 4.1 `RegArray(type, depth)` — 寄存器/寄存器堆

**作用**：创建寄存器或寄存器堆，支持时序赋值与时钟域绑定。

**语法**：
```python
# 创建寄存器数组
reg = RegArray(data_type, depth)
reg = RegArray(data_type, depth, initializer=[init_values])

# 读取
value = reg[index]

# 组合逻辑赋值（立即更新）
reg[index] = value

# 时序逻辑赋值（下一时钟沿更新）
reg[index] <= value

# 带时钟域的时序赋值
(reg & self)[index] <= value
```

**示例**：
```python
# 单个 32 位寄存器（PC）
pc_reg = RegArray(Bits(32), 1, initializer=[0])
current_pc = pc_reg[0]
pc_reg[0] <= next_pc  # 时序更新

# 32 个 32 位寄存器（寄存器堆）
reg_file = RegArray(Bits(32), 32)
rs1_data = reg_file[rs1_addr]  # 读取
reg_file[rd_addr] = write_data  # 组合写入

# 带初始值的计数器
counter = RegArray(UInt(32), 1, initializer=[0])
(counter & self)[0] <= counter[0] + UInt(32)(1)

# 状态机状态寄存器
state = RegArray(Bits(3), 1, initializer=[0])
IDLE = Bits(3)(0)
WORKING = Bits(3)(1)
DONE = Bits(3)(2)

# BTB 存储数组
btb_valid = RegArray(Bits(1), 64, initializer=[0] * 64)
btb_tags = RegArray(Bits(32), 64, initializer=[0] * 64)
btb_targets = RegArray(Bits(32), 64, initializer=[0] * 64)
```

**赋值语义**：
- `reg[i] = value`：组合逻辑赋值，当前周期立即生效
- `reg[i] <= value`：时序逻辑赋值，下一时钟上升沿生效
- `(reg & self)[i] <= value`：带时钟域绑定的时序赋值

### 4.2 `SRAM(width, depth)` — 大容量存储器

**作用**：创建 SRAM 存储器，支持读写操作，可从文件初始化。

**语法**：
```python
# 创建 SRAM
sram = SRAM(width=bit_width, depth=num_entries)
sram = SRAM(width=bit_width, depth=num_entries, init_file=file_path)

# 构建连接（必须调用）
sram.build(we=write_enable, re=read_enable, addr=address, wdata=write_data)

# 读取输出
read_data = sram.dout[0]
```

**示例**：
```python
# 创建指令缓存 (64KB)
icache = SRAM(width=32, depth=1 << 16, init_file="workload.exe")
icache.name = "icache"

# 创建数据缓存
dcache = SRAM(width=32, depth=1 << 16, init_file="workload.data")
dcache.name = "dcache"

# 指令读取（只读）
sram_addr = (pc >> UInt(32)(2))[0:15]  # 字地址
icache.build(
    we=Bits(1)(0),         # 不写入
    re=Bits(1)(1),         # 读使能
    addr=sram_addr,        # 地址
    wdata=Bits(32)(0)      # 写数据（不使用）
)
instruction = icache.dout[0].bitcast(Bits(32))

# 数据读写
dcache.build(
    we=is_store,           # Store 指令时写入
    re=is_load,            # Load 指令时读取
    addr=alu_result[0:15], # ALU 计算的地址
    wdata=rs2_data         # 写入数据
)
load_data = dcache.dout[0]
```

**注意事项**：
- SRAM 读取需要一个周期延迟
- 写入在当前周期完成
- 地址以字为单位（不是字节）

---

## 5. 架构单元

架构单元是电路板上的逻辑分区，用于组织和封装电路功能。

### 5.1 `Module` — 时序逻辑模块

**作用**：标准的时序逻辑容器，拥有端口和时钟域，可以包含状态。

**语法**：
```python
class MyModule(Module):
    def __init__(self):
        super().__init__(
            ports={
                'port_name': Port(data_type),
                ...
            },
            no_arbiter=False  # 是否禁用仲裁器
        )
        self.name = "ModuleName"
    
    @module.combinational
    def build(self, external_refs...):
        # 消费端口数据
        data1, data2 = self.pop_all_ports(blocking=False)
        
        # 实现逻辑
        ...
        
        # 返回状态供其他模块使用
        return outputs
```

**示例**：
```python
class Execution(Module):
    def __init__(self):
        super().__init__(
            ports={
                # 控制通道
                "ctrl": Port(ex_ctrl_signals),
                # 数据通道
                "pc": Port(Bits(32)),
                "rs1_data": Port(Bits(32)),
                "rs2_data": Port(Bits(32)),
                "imm": Port(Bits(32)),
            }
        )
        self.name = "Executor"

    @module.combinational
    def build(self, mem_module: Module, ex_bypass: Array, ...):
        # 1. 弹出端口数据
        ctrl, pc, rs1, rs2, imm = self.pop_all_ports(False)
        
        # 2. ALU 运算
        op1_signed = alu_op1.bitcast(Int(32))
        op2_signed = alu_op2.bitcast(Int(32))
        add_result = (op1_signed + op2_signed).bitcast(Bits(32))
        
        # 3. 更新旁路寄存器
        ex_bypass[0] = alu_result
        
        # 4. 发送到下一级
        mem_call = mem_module.async_called(
            ctrl=mem_ctrl,
            alu_result=alu_result
        )
        mem_call.bind.set_fifo_depth(ctrl=1, alu_result=1)
        
        # 5. 返回状态
        return rd_addr, is_load


class WriteBack(Module):
    def __init__(self):
        super().__init__(
            ports={
                "ctrl": Port(Bits(5)),   # rd 地址
                "wdata": Port(Bits(32)), # 写入数据
            }
        )
        self.name = "WB"

    @module.combinational
    def build(self, reg_file: Array, wb_bypass_reg: Array):
        rd, wdata = self.pop_all_ports(False)
        
        # 写回寄存器堆
        with Condition(rd != Bits(5)(0)):
            reg_file[rd] = wdata
            wb_bypass_reg[0] = wdata
            log("WB: Write x{} <= 0x{:x}", rd, wdata)
        
        return rd
```

### 5.2 `Downstream` — 纯组合逻辑模块

**作用**：纯组合逻辑容器，用于封装无状态的组合逻辑或反馈回路。

**语法**：
```python
class MyDownstream(Downstream):
    def __init__(self):
        super().__init__()
        self.name = "DownstreamName"
    
    @downstream.combinational
    def build(self, inputs...):
        # 纯组合逻辑
        ...
        return outputs
```

**示例**：
```python
class DataHazardUnit(Downstream):
    """数据冒险检测单元 - 纯组合逻辑"""
    
    def __init__(self):
        super().__init__()
        self.name = "DataHazardUnit"

    @downstream.combinational
    def build(
        self,
        rs1_idx: Value,
        rs2_idx: Value,
        rs1_used: Value,
        rs2_used: Value,
        ex_rd: Value,
        ex_is_load: Value,
        mem_rd: Value,
        wb_rd: Value,
    ):
        # 处理 Value 接口
        rs1_idx_val = rs1_idx.optional(Bits(5)(0))
        ex_rd_val = ex_rd.optional(Bits(5)(0))
        ex_is_load_val = ex_is_load.optional(Bits(1)(0))
        
        # Load-Use 冒险检测
        load_use_hazard = rs1_used.optional(Bits(1)(0)) & \
                          ex_is_load_val & \
                          (rs1_idx_val == ex_rd_val)
        
        # 旁路选择逻辑
        rs1_sel = (rs1_idx_val == ex_rd_val).select(
            Rs1Sel.EX_BYPASS,
            Rs1Sel.RS1
        )
        
        return rs1_sel, rs2_sel, stall_signal


class FetcherImpl(Downstream):
    """取指实现 - 纯组合逻辑"""
    
    def __init__(self):
        super().__init__()
        self.name = "Fetcher_Impl"

    @downstream.combinational
    def build(
        self,
        pc_reg: Array,
        icache: SRAM,
        decoder: Module,
        stall_if: Value,
        branch_target: Array,
    ):
        current_stall = stall_if.optional(Bits(1)(0))
        current_pc = current_stall.select(last_pc, pc_reg[0])
        
        # 驱动 SRAM
        sram_addr = (current_pc >> UInt(32)(2))[0:15]
        icache.build(we=Bits(1)(0), re=Bits(1)(1), addr=sram_addr, wdata=Bits(32)(0))
        
        # 计算下一 PC
        next_pc = (current_pc.bitcast(UInt(32)) + UInt(32)(4)).bitcast(Bits(32))
        
        # 更新 PC 寄存器
        pc_reg[0] <= next_pc
        
        # 发送到解码器
        call = decoder.async_called(pc=current_pc, next_pc=next_pc)
        call.bind.set_fifo_depth(pc=1)
```

### 5.3 `Module` vs `Downstream` 对比

| 特性 | Module | Downstream |
|------|--------|------------|
| 装饰器 | `@module.combinational` | `@downstream.combinational` |
| 端口 | 有 Port 定义 | 无 Port |
| 状态 | 可包含 RegArray | 无状态 |
| 时钟域 | 有独立时钟域 | 无时钟域 |
| 用途 | 流水线级 | 组合逻辑、反馈 |

---

## 6. 接口与控制

### 6.1 `Port` — 端口定义

**作用**：定义模块的输入端口，用于接收数据。

**语法**：
```python
ports={
    'port_name': Port(data_type),
}
```

**示例**：
```python
class Decoder(Module):
    def __init__(self):
        super().__init__(
            ports={
                "pc": Port(Bits(32)),           # 简单类型端口
                "next_pc": Port(Bits(32)),
            }
        )

class Execution(Module):
    def __init__(self):
        super().__init__(
            ports={
                "ctrl": Port(ex_ctrl_signals),  # Record 类型端口
                "pc": Port(Bits(32)),
                "rs1_data": Port(Bits(32)),
                "rs2_data": Port(Bits(32)),
                "imm": Port(Bits(32)),
            }
        )
```

### 6.2 `async_called()` — 异步调用/连接

**作用**：连接生产者和消费者模块，自动生成 FIFO 缓冲区。

**语法**：
```python
# 基本用法
call = consumer_module.async_called(port_name=data, ...)

# 配置 FIFO 深度
call.bind.set_fifo_depth(port_name=depth, ...)
```

**示例**：
```python
# 在 Decoder 中发送数据到 Executor
class DecoderImpl(Downstream):
    @downstream.combinational
    def build(self, pre: Record, executor: Module, ...):
        # 构造控制信号
        final_ex_ctrl = ex_ctrl_signals.bundle(
            alu_func=pre.alu_func,
            op1_sel=pre.op1_sel,
            ...
        )
        
        # 连接到 Executor
        call = executor.async_called(
            ctrl=final_ex_ctrl,
            pc=pre.pc,
            rs1_data=pre.rs1_data,
            rs2_data=pre.rs2_data,
            imm=pre.imm,
        )
        
        # 设置 FIFO 深度（1 = 刚性流水线）
        call.bind.set_fifo_depth(
            ctrl=1,
            pc=1,
            rs1_data=1,
            rs2_data=1,
            imm=1
        )
```

### 6.3 `pop_all_ports()` — 弹出端口数据

**作用**：从模块端口读取数据。

**语法**：
```python
# blocking=True: 如果 FIFO 为空则等待
# blocking=False: 无论 FIFO 是否为空都返回（返回 Value 类型）
data1, data2, ... = self.pop_all_ports(blocking)
```

**示例**：
```python
class Execution(Module):
    @module.combinational
    def build(self, ...):
        # 非阻塞读取
        ctrl, pc, rs1, rs2, imm = self.pop_all_ports(False)
        
        # ctrl 可能是 Value 类型，需要处理无效情况
        # 但通常在刚性流水线中，数据总是有效的
```

### 6.4 `Condition` — 条件控制

**作用**：硬件条件控制，控制代码块内的副作用是否生效。

**语法**：
```python
with Condition(condition):
    # 只有当 condition 为真时，这里的操作才会执行
    ...
```

**示例**：
```python
# 条件写回
with Condition(rd != Bits(5)(0)):
    reg_file[rd] = wdata
    log("WB: Write x{} <= 0x{:x}", rd, wdata)

# 条件日志
with Condition(is_branch == Bits(1)(1)):
    log("EX: Branch Target: 0x{:x}", target)
    log("EX: Branch Taken: {}", is_taken)

# 嵌套条件
with Condition(btb_hit == Bits(1)(1)):
    with Condition(predict_taken == Bits(1)(1)):
        log("BTB HIT + TAKEN")
    with Condition(predict_taken == Bits(1)(0)):
        log("BTB HIT + NOT TAKEN")

# 状态机转换
with Condition(state[0] == IDLE):
    with Condition(start_signal == Bits(1)(1)):
        state[0] = WORKING

# 停机控制
with Condition(ctrl.alu_func == ALUOp.SYS):
    log("EBREAK encountered, halting simulation.")
    finish()
```

### 6.5 `wait_until()` — 等待条件

**作用**：暂停模块执行，直到条件满足。

**语法**：
```python
wait_until(condition)
```

**示例**：
```python
# 等待数据有效
wait_until(data_valid == Bits(1)(1))

# 等待流水线不阻塞
wait_until(stall == Bits(1)(0))
```

---

## 7. 运算符与操作函数

### 7.1 位截取：`signal[high:low]`

**作用**：从位向量中提取指定范围的位。

**注意**：Assassyn 使用 **[低位:高位]** 的闭区间格式（类似 Verilog），与 Python 原生不同。

**示例**：
```python
word = Bits(32)(0x12345678)

# 提取低 8 位 [7:0]
byte = word[0:7]  # 0x78

# 提取高 8 位 [31:24]
high_byte = word[24:31]  # 0x12

# 提取第 31 位（符号位）
sign_bit = word[31:31]

# 提取 opcode (低 7 位)
opcode = instruction[0:6]

# 提取 funct3 (位 14:12)
funct3 = instruction[12:14]

# 提取 rs1 (位 19:15)
rs1 = instruction[15:19]
```

### 7.2 位拼接：`concat()`

**作用**：将多个位向量拼接成一个更宽的位向量。

**语法**：
```python
result = concat(high_bits, mid_bits, low_bits)
# 或
result = high_bits.concat(low_bits)
```

**示例**：
```python
# 符号扩展：将 8 位扩展到 32 位
sign = data[7:7]  # 符号位
sign_ext = sign.select(Bits(24)(0xFFFFFF), Bits(24)(0))
extended = concat(sign_ext, data[0:7])

# I 型立即数生成
# [31]*20 | [31:20]
sign = inst[31:31]
pad_20 = sign.select(Bits(20)(0xFFFFF), Bits(20)(0))
imm_i = concat(pad_20, inst[20:31])

# B 型立即数生成
# [31]*19 | [31] | [7] | [30:25] | [11:8] | 0
pad_19 = sign.select(Bits(19)(0x7FFFF), Bits(19)(0))
imm_b = concat(
    pad_19,
    inst[31:31],
    inst[7:7],
    inst[25:30],
    inst[8:11],
    Bits(1)(0)
)

# GHR 更新：左移并插入新位
new_ghr = concat(ghr[0:4], branch_taken)
```

### 7.3 二路选择：`select()`

**作用**：根据条件选择两个值之一（2-to-1 Mux）。

**语法**：
```python
result = condition.select(true_value, false_value)
```

**示例**：
```python
# 基本用法
result = is_negative.select(negated_value, positive_value)

# PC 选择
next_pc = is_branch.select(branch_target, pc_plus_4)

# 旁路数据选择
rs1_data = use_bypass.select(bypass_data, reg_data)

# 符号扩展
pad = sign_bit.select(Bits(24)(0xFFFFFF), Bits(24)(0))

# 嵌套选择
final_result = cond1.select(
    val1,
    cond2.select(
        val2,
        cond3.select(val3, val4)
    )
)
```

### 7.4 独热码选择：`select1hot()`

**作用**：根据独热码选择多个值之一（N-to-1 Mux）。

**语法**：
```python
result = onehot_signal.select1hot(option0, option1, option2, ...)
```

**示例**：
```python
# ALU 操作选择
result = alu_func.select1hot(
    add_result,   # bit 0: ADD
    sub_result,   # bit 1: SUB
    sll_result,   # bit 2: SLL
    slt_result,   # bit 3: SLT
    sltu_result,  # bit 4: SLTU
    xor_result,   # bit 5: XOR
    srl_result,   # bit 6: SRL
    sra_result,   # bit 7: SRA
    or_result,    # bit 8: OR
    and_result,   # bit 9: AND
)

# 立即数类型选择
imm = imm_type.select1hot(
    Bits(32)(0),  # R 型（无立即数）
    imm_i,        # I 型
    imm_s,        # S 型
    imm_b,        # B 型
    imm_u,        # U 型
    imm_j,        # J 型
)

# 操作数选择
alu_op1 = op1_sel.select1hot(
    real_rs1,     # 0: RS1
    pc,           # 1: PC
    Bits(32)(0),  # 2: ZERO
)

# 旁路数据选择
real_rs1 = rs1_sel.select1hot(
    rs1,          # 0: 原始值
    ex_bypass,    # 1: EX 旁路
    mem_bypass,   # 2: MEM 旁路
    wb_bypass,    # 3: WB 旁路
)
```

### 7.5 算术运算符

| 运算符 | 作用 | 示例 |
|--------|------|------|
| `+` | 加法 | `a + b` |
| `-` | 减法 | `a - b` |
| `*` | 乘法 | `a * b` |
| `/` | 除法 | `a / b` |
| `%` | 取模 | `a % b` |

**示例**：
```python
# 无符号加法
next_pc = (pc.bitcast(UInt(32)) + UInt(32)(4)).bitcast(Bits(32))

# 有符号运算
op1_signed = alu_op1.bitcast(Int(32))
op2_signed = alu_op2.bitcast(Int(32))
add_res = (op1_signed + op2_signed).bitcast(Bits(32))
sub_res = (op1_signed - op2_signed).bitcast(Bits(32))

# 64 位乘法
product = op1.bitcast(UInt(64)) * op2.bitcast(UInt(64))
```

### 7.6 位运算符

| 运算符 | 作用 | 示例 |
|--------|------|------|
| `&` | 按位与 | `a & b` |
| `\|` | 按位或 | `a \| b` |
| `^` | 按位异或 | `a ^ b` |
| `~` | 按位取反 | `~a` |
| `<<` | 左移 | `a << shift` |
| `>>` | 右移 | `a >> shift` |

**示例**：
```python
# 逻辑运算
and_res = alu_op1 & alu_op2
or_res = alu_op1 | alu_op2
xor_res = alu_op1 ^ alu_op2

# 移位运算
sll_res = alu_op1 << alu_op2[0:4].bitcast(UInt(5))  # 逻辑左移
srl_res = alu_op1 >> alu_op2[0:4].bitcast(UInt(5))  # 逻辑右移

# 算术右移（需要转换为有符号）
sra_res = (op1_signed >> alu_op2[0:4].bitcast(UInt(5))).bitcast(Bits(32))

# 取反加一（求补码）
neg_value = (~value + Bits(32)(1)).bitcast(Bits(32))

# 信号累加（用于查表）
acc_signal |= match.select(signal_value, Bits(32)(0))
```

### 7.7 比较运算符

| 运算符 | 作用 | 示例 |
|--------|------|------|
| `==` | 等于 | `a == b` |
| `!=` | 不等于 | `a != b` |
| `<` | 小于 | `a < b` |
| `<=` | 小于等于 | `a <= b` |
| `>` | 大于 | `a > b` |
| `>=` | 大于等于 | `a >= b` |

**示例**：
```python
# 等于比较
is_zero = (result == Bits(32)(0))
is_x0 = (rd == Bits(5)(0))

# 有符号比较
slt_res = (op1_signed < op2_signed).bitcast(Bits(32))

# 无符号比较
sltu_res = (alu_op1 < alu_op2).bitcast(Bits(32))

# 状态比较
is_idle = (state[0] == IDLE)
```

### 7.8 日志与调试：`log()`

**作用**：在仿真时打印调试信息。

**语法**：
```python
log("format string", arg1, arg2, ...)
```

**格式说明符**：
- `{}`: 十进制
- `{:x}`: 十六进制
- `0x{:x}`: 带前缀的十六进制

**示例**：
```python
# 基本日志
log("EX: ALU Result: 0x{:x}", alu_result)

# 多参数日志
log("ID: Fetched Instruction=0x{:x} at PC=0x{:x}", inst, pc)

# 控制信号日志
log("Control signals: alu_func=0x{:x} op1_sel=0x{:x} op2_sel=0x{:x}",
    acc_alu_func, acc_op1_sel, acc_op2_sel)

# 条件日志
with Condition(is_branch):
    log("EX: Branch Target: 0x{:x}", calc_target)
    log("EX: Branch Taken: {}", is_taken == Bits(1)(1))
```

### 7.9 仿真控制：`finish()`

**作用**：终止仿真。

**示例**：
```python
# 正常结束
with Condition(test_complete == Bits(1)(1)):
    log("Test completed successfully!")
    finish()

# 错误终止
with Condition(ctrl.alu_func == ALUOp.SYS):
    log("EBREAK encountered at PC=0x{:x}, halting simulation.", pc)
    finish()

# 超时终止
with Condition(cycle_count > UInt(32)(1000000)):
    log("Timeout!")
    finish()
```

---

## 8. 时序与通信模型

### 8.1 延迟不敏感设计

Assassyn 采用基于 FIFO 的弹性流水线设计：

- **核心理念**：生产者和消费者通过 FIFO 缓冲区隔离
- **通信协议**：基于 Valid/Ready 握手
- **物理映射**：FIFO 即级间流水线寄存器

### 8.2 数据流动

```
Producer -> FIFO -> Consumer
           (Valid/Ready握手)
```

**流程**：
1. 生产者调用 `async_called()` 将数据放入 FIFO
2. 消费者调用 `pop_all_ports()` 从 FIFO 读取数据
3. 如果 FIFO 满，生产者自动暂停
4. 如果 FIFO 空，消费者等待（阻塞模式）或返回无效（非阻塞模式）

### 8.3 FIFO 深度配置

```python
# 设置 FIFO 深度
call.bind.set_fifo_depth(port1=depth1, port2=depth2, ...)

# 深度为 1：刚性流水线（每级一拍）
call.bind.set_fifo_depth(ctrl=1, data=1)

# 深度大于 1：弹性流水线（允许级间缓冲）
call.bind.set_fifo_depth(ctrl=2, data=2)
```

### 8.4 流水线控制

**Stall（暂停）**：
```python
# 检测需要暂停的条件
stall_if = load_use_hazard | mul_busy | div_busy

# 在 IF 级处理暂停
current_pc = stall_if.select(last_pc, pc_addr)
```

**Flush（冲刷）**：
```python
# 检测需要冲刷的条件
flush_if = branch_target_reg[0] != Bits(32)(0)

# 插入 NOP
final_rd = flush_if.select(Bits(5)(0), rd_addr)
final_alu_func = flush_if.select(ALUOp.NOP, alu_func)
```

### 8.5 旁路（Forwarding）

```python
# 旁路寄存器
ex_bypass_reg = RegArray(Bits(32), 1)
mem_bypass_reg = RegArray(Bits(32), 1)
wb_bypass_reg = RegArray(Bits(32), 1)

# 旁路选择
real_rs1 = rs1_sel.select1hot(
    rs1,              # 原始值
    ex_bypass_reg[0], # EX 旁路
    mem_bypass_reg[0],# MEM 旁路
    wb_bypass_reg[0], # WB 旁路
)

# 更新旁路寄存器
ex_bypass_reg[0] = alu_result
```

---

## 9. 仿真与测试

### 9.1 系统构建

```python
from assassyn.frontend import SysBuilder

# 创建系统
sys = SysBuilder('system_name')

with sys:
    # 实例化模块
    module1 = MyModule()
    module2 = AnotherModule()
    
    # 构建连接
    module1.build(...)
    module2.build(module1, ...)
    
    # 暴露输出（可选）
    sys.expose_on_top(reg_file, kind="Output")
```

### 9.2 编译与仿真

```python
from assassyn.backend import elaborate, config
from assassyn import utils

# 配置
cfg = config(
    verilog=True,           # 是否生成 Verilog
    sim_threshold=600000,   # 仿真周期上限
    idle_threshold=600000,  # 空闲检测阈值
)

# 编译
simulator_path, verilog_path = elaborate(sys, **cfg)

# 构建二进制
binary_path = utils.build_simulator(simulator_path)

# 运行仿真
raw_output = utils.run_simulator(binary_path=binary_path)

# 运行 Verilog 仿真（可选）
# raw_output = utils.run_verilator(verilog_path)
```

### 9.3 测试框架

```python
def run_test_module(sys_builder, check_func):
    """通用测试框架"""
    
    # 编译
    cfg = config(verilog=False, sim_threshold=600000)
    simulator_path, _ = elaborate(sys_builder, **cfg)
    binary_path = utils.build_simulator(simulator_path)
    
    # 运行
    raw = utils.run_simulator(binary_path=binary_path)
    
    # 验证
    check_func(raw)
```

### 9.4 测试驱动模块

```python
class Driver(Module):
    def __init__(self):
        super().__init__(ports={})

    @module.combinational
    def build(self, dut: Module, test_inputs...):
        # 测试向量
        vectors = [
            (input1, expected1),
            (input2, expected2),
            ...
        ]
        
        # 计数器
        cnt = RegArray(UInt(32), 1, initializer=[0])
        (cnt & self)[0] <= cnt[0] + UInt(32)(1)
        idx = cnt[0]
        
        # 发送测试向量
        for i, v in enumerate(vectors):
            match_if = idx == UInt(32)(i)
            with Condition(match_if):
                dut.async_called(input=v[0])
                log("Test[{}]: Input=0x{:x}", i, v[0])
        
        # 结束条件
        with Condition(idx > UInt(32)(len(vectors) + 10)):
            finish()
```

### 9.5 验证函数

```python
def check(raw_output):
    """验证仿真输出"""
    
    expected_values = [...]
    
    # 解析日志
    captured = []
    for line in raw_output.split("\n"):
        if "Output:" in line:
            # 提取数值
            value = int(line.split()[-1], 16)
            captured.append(value)
    
    # 验证
    for i, (act, exp) in enumerate(zip(captured, expected_values)):
        assert act == exp, f"Test {i} failed: got {act}, expected {exp}"
    
    print("All tests passed!")
```

---

## 10. 完整示例

### 10.1 简单计数器

```python
from assassyn.frontend import *
from assassyn.backend import elaborate, config
from assassyn import utils

class Counter(Module):
    def __init__(self):
        super().__init__(ports={})
        self.name = "Counter"

    @module.combinational
    def build(self, max_count):
        # 计数器寄存器
        cnt = RegArray(UInt(32), 1, initializer=[0])
        
        # 读取当前值
        current = cnt[0]
        
        # 计算下一个值
        next_val = (current + UInt(32)(1)).bitcast(UInt(32))
        
        # 检查是否达到最大值
        is_max = current >= max_count
        final_next = is_max.select(UInt(32)(0), next_val)
        
        # 更新寄存器
        (cnt & self)[0] <= final_next
        
        # 日志输出
        log("Counter: {}", current)
        
        # 结束条件
        with Condition(current == max_count):
            finish()


class Driver(Module):
    def __init__(self):
        super().__init__(ports={})

    @module.combinational
    def build(self, counter: Module):
        counter.async_called()


def main():
    sys = SysBuilder('counter_test')
    
    with sys:
        counter = Counter()
        driver = Driver()
        
        counter.build(max_count=UInt(32)(10))
        driver.build(counter)
    
    cfg = config(verilog=False, sim_threshold=100)
    simulator_path, _ = elaborate(sys, **cfg)
    binary_path = utils.build_simulator(simulator_path)
    raw = utils.run_simulator(binary_path=binary_path)
    print(raw)


if __name__ == "__main__":
    main()
```

### 10.2 简单 ALU

```python
from assassyn.frontend import *

# ALU 操作码（独热码）
class ALUOp:
    ADD = Bits(4)(0b0001)
    SUB = Bits(4)(0b0010)
    AND = Bits(4)(0b0100)
    OR  = Bits(4)(0b1000)


class ALU(Module):
    def __init__(self):
        super().__init__(
            ports={
                "op": Port(Bits(4)),
                "a": Port(Bits(32)),
                "b": Port(Bits(32)),
            }
        )
        self.name = "ALU"

    @module.combinational
    def build(self):
        op, a, b = self.pop_all_ports(False)
        
        # 各种运算
        add_res = (a.bitcast(Int(32)) + b.bitcast(Int(32))).bitcast(Bits(32))
        sub_res = (a.bitcast(Int(32)) - b.bitcast(Int(32))).bitcast(Bits(32))
        and_res = a & b
        or_res = a | b
        
        # 结果选择
        result = op.select1hot(add_res, sub_res, and_res, or_res)
        
        log("ALU: a=0x{:x} op=0x{:x} b=0x{:x} = 0x{:x}", a, op, b, result)
        
        return result
```

### 10.3 五级流水线 CPU 结构概览

```python
# main.py 简化示例
def build_cpu():
    sys = SysBuilder("rv32i_cpu")
    
    with sys:
        # 1. 存储资源
        icache = SRAM(width=32, depth=65536, init_file="program.exe")
        dcache = SRAM(width=32, depth=65536, init_file="data.bin")
        reg_file = RegArray(Bits(32), 32)
        
        # 旁路寄存器
        ex_bypass = RegArray(Bits(32), 1)
        mem_bypass = RegArray(Bits(32), 1)
        wb_bypass = RegArray(Bits(32), 1)
        branch_target = RegArray(Bits(32), 1)
        
        # 2. 流水线模块
        fetcher = Fetcher()
        fetcher_impl = FetcherImpl()
        decoder = Decoder()
        decoder_impl = DecoderImpl()
        hazard_unit = DataHazardUnit()
        executor = Execution()
        memory_unit = MemoryAccess()
        writeback = WriteBack()
        driver = Driver()
        
        # 3. 逆序构建（从 WB 到 IF）
        
        # WB 阶段
        wb_rd = writeback.build(reg_file, wb_bypass)
        
        # MEM 阶段
        mem_rd = memory_unit.build(
            writeback, dcache.dout, mem_bypass
        )
        
        # EX 阶段
        ex_rd, ex_is_load, mul_busy, div_busy = executor.build(
            memory_unit, ex_bypass, mem_bypass, wb_bypass,
            branch_target, dcache
        )
        
        # ID 阶段（Shell）
        pre_pkt, rs1, rs2, use1, use2 = decoder.build(
            icache.dout, reg_file
        )
        
        # 冒险检测
        rs1_sel, rs2_sel, stall_if = hazard_unit.build(
            rs1, rs2, use1, use2,
            ex_rd, ex_is_load, mul_busy, div_busy,
            mem_rd, wb_rd
        )
        
        # ID 阶段（Core）
        decoder_impl.build(
            pre_pkt, executor,
            rs1_sel, rs2_sel, stall_if, branch_target
        )
        
        # IF 阶段
        pc_reg, pc_addr, last_pc = fetcher.build()
        fetcher_impl.build(
            pc_reg, pc_addr, last_pc,
            icache, decoder, stall_if, branch_target
        )
        
        # 驱动
        driver.build(fetcher)
    
    return sys
```

---

## 附录 A：常用控制信号定义模式

```python
# 独热码定义
class ALUOp:
    ADD  = Bits(16)(0b0000000000000001)  # Bit 0
    SUB  = Bits(16)(0b0000000000000010)  # Bit 1
    SLL  = Bits(16)(0b0000000000000100)  # Bit 2
    SLT  = Bits(16)(0b0000000000001000)  # Bit 3
    SLTU = Bits(16)(0b0000000000010000)  # Bit 4
    XOR  = Bits(16)(0b0000000000100000)  # Bit 5
    SRL  = Bits(16)(0b0000000001000000)  # Bit 6
    SRA  = Bits(16)(0b0000000010000000)  # Bit 7
    OR   = Bits(16)(0b0000000100000000)  # Bit 8
    AND  = Bits(16)(0b0000001000000000)  # Bit 9
    NOP  = Bits(16)(0b1000000000000000)  # Bit 15

# 二进制编码定义
class MemOp:
    NONE  = Bits(3)(0b001)
    LOAD  = Bits(3)(0b010)
    STORE = Bits(3)(0b100)

# 使用 Record 打包
ctrl_signals = Record(
    alu_func=Bits(16),
    op1_sel=Bits(3),
    op2_sel=Bits(3),
    mem_op=Bits(3),
    rd_addr=Bits(5),
)
```

---

## 附录 B：调试技巧

### B.1 添加日志

```python
# 在关键位置添加日志
log("Stage: Input a=0x{:x} b=0x{:x}", a, b)

# 条件日志（减少输出量）
with Condition(is_valid == Bits(1)(1)):
    log("Valid data: 0x{:x}", data)
```

### B.2 状态机调试

```python
# 打印状态转换
with Condition(state[0] == OLD_STATE):
    with Condition(transition_cond):
        log("State: {} -> {}", OLD_STATE, NEW_STATE)
        state[0] = NEW_STATE
```

### B.3 流水线调试

```python
# 打印每级流水线的输入输出
log("IF: PC=0x{:x}", pc)
log("ID: Inst=0x{:x} rd=x{}", inst, rd)
log("EX: ALU=0x{:x}", result)
log("MEM: Addr=0x{:x} Data=0x{:x}", addr, data)
log("WB: x{} <= 0x{:x}", rd, wdata)
```

---

## 附录 C：最佳实践

### C.1 模块设计

1. **单一职责**：每个模块只做一件事
2. **清晰接口**：使用 Record 定义结构化接口
3. **独热码**：控制信号优先使用独热码
4. **命名规范**：模块名、信号名要有意义

### C.2 流水线设计

1. **逆序构建**：从 WB 向 IF 构建
2. **刚性流水线**：FIFO 深度设为 1
3. **旁路优先**：避免不必要的暂停
4. **冲刷处理**：统一处理分支冲刷

### C.3 测试设计

1. **单元测试**：每个模块独立测试
2. **集成测试**：完整流水线测试
3. **边界条件**：测试极端情况
4. **日志驱动**：通过日志验证正确性

---

*本说明书基于 Assassyn-CPU 项目整理，涵盖了 Assassyn 硬件描述语言的主要语法和功能。*
