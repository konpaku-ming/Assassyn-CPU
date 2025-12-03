# RV32I ID (Instruction Decode) 模块设计文档

> **依赖**：Assassyn Framework
> **组成**：`ID.py` (主流水线模块), `control_signals.py` (包含 Record 定义)

## 1. 模块概述

ID 模块是流水线的**控制中心**。它的核心职责是将从取指阶段（IF）获取的原始二进制指令流，翻译为后续流水线阶段（EX, MEM, WB）所需的结构化控制信号和数据操作数。

该设计采用 **解耦（Decoupled）** 思想，将复杂的指令解析逻辑收敛在 ID 阶段，向后传递正交化的控制信号包，并采用嵌套 Record 结构实现信号在流水线各级的逐层剥离。

## 2. 接口定义

### 2.1 类定义与端口 (`__init__`)

ID 模块作为标准的 `Module`，通过端口接收来自 IF 阶段的流式数据（主要是 PC，指令通常通过共享 SRAM 接口获取）。

```python
class Decoder(Module):
    def __init__(self):
        super().__init__(
            ports={
                # 来自 IF 阶段的 PC 值（用于 JAL/Branch 计算或传递给 EX 级）
                'pc': Port(Bits(32)),
            }
        )
        self.name = 'ID'
```

### 2.2 构建参数 (`build`)

`build` 函数描述了 ID 模块与其他组件的物理连接。

| 参数名          | 类型         | 描述                                                |
| :-------------- | :----------- | :-------------------------------------------------- |
| **executor**    | `Module`     | 下一级流水线（EX），用于发送打包好的控制/数据包。   |
| **hazard_unit** | `Downstream` | 数据冒险检测单元，用于处理 Stall 和记分牌更新。     |
| **icache_data** | `Array`   | SRAM (ICache) 的输出端口 (`dout`)，即原始指令数据。 |
| **reg_file**    | `Array`   | 通用寄存器堆，用于读取 `rs1` 和 `rs2` 的源数据。    |

```python
@module.combinational
def build(self, executor: Module, hazard_unit: Downstream, icache_data: Array, reg_file: Array):
    # 实现逻辑见下文
```

---

## 3. 数据结构：控制信号包 (Control Packets)

采用 **嵌套 Record** 结构，实现控制信号的分层管理。以下定义置于 `control_signals.py`。

### 3.1 写回域 (`WbCtrl`)
```python
wb_ctrl_signals = Record(
    rd_addr    = Bits(5)   # 目标寄存器索引，如果是0拒绝写入。
)
```

### 3.2 访存域 (`MemCtrl`)
```python
mem_ctrl_signals = Record(
    is_load      = Bits(1), # 是否读内存
    mem_width    = Bits(3), # 访问宽度，独热码 (0:Byte, 1:Half, 2:Word)
    mem_unsigned = Bits(1), # 是否无符号扩展 (LBU/LHU)
    wb_ctrl      = wb_ctrl_signals # 【嵌套】携带 WB 级信号
)
```

### 3.3 执行域 (`ExCtrl`)
```python
ex_ctrl_signals = Record(
    alu_func = Bits(16),   # ALU 功能码 (独热码)
    op1_sel  = Bits(4),    # 操作数1来源，独热码 (0:RS1, 1:PC, 2: exe_bypass_reg, 3: mem_bypass_reg)
    op2_sel  = Bits(5),    # 操作数2来源，独热码 (0:RS2, 1:imm, 2: exe_bypass_reg, 3: mem_bypass_reg, 4: Constant_4)
    is_write = Bits(1),    # 是否写入SRAM (Store 指令)
    is_branch= Bits(1),    # 是否跳转 (Branch 指令)
    mem_ctrl = mem_ctrl_signals  # 【嵌套】携带 MEM 级信号
)
```

## 4. 内部实现逻辑 (`build` 流程)

### 1. 切片与预处理 (Physical Slicing)

把 32 位 `inst` 拆解为所有可能的零件。

```python
# 1. 基础字段
opcode = inst[0:6]
rd     = inst[7:11]
funct3 = inst[12:14]
rs1    = inst[15:19]
rs2    = inst[20:24]
funct7 = inst[25:31]

# 2. 特殊位 (用于区分 SRAI/SRLI 等)
# 移位指令的区分位通常在 inst[30]
func7_bit30 = inst[30:30]

# 3. 立即数并行生成 (全部算好)
imm_i, imm_s, imm_b, imm_u, imm_j = gen_all_immediates(inst)
```

#### 2. 查表与控制包生成 (The Loop & `|=`)

利用预定义的指令真值表 `instructions_table`，对每条指令进行匹配，并累加生成控制信号包。这一步利用 Python 的循环来生成巨大的 Mux 逻辑。

```python
# 初始化累加器 (默认全 0)
alu_func_acc  = Bits(16)(0)
op1_sel_acc   = Bits(4)(0) # 独热码
op2_sel_acc   = Bits(5)(0) # 独热码
imm_val_acc   = Bits(32)(0)
is_load_acc   = Bits(1)(0)
# ... 其他信号 ...

# 遍历真值表
for entry in instructions_table:
    # A. 匹配逻辑 (包含对 shift 特殊位的处理)
    # 如果 entry 指定了 func7_bit30，也要纳入匹配
    match = (opcode == entry.op) & ... 
    
    # B. 信号累加 (你的核心思路)
    # 利用 Select + Or 实现 Mux
    alu_func_acc |= match.select(entry.alu_func, 0)
    op1_sel_acc  |= match.select(entry.op1_sel, 0)
    
    # C. 立即数选择
    # 如果匹配，把对应的立即数 (如 imm_i) 累加进来
    imm_val_acc  |= match.select(entry.imm_src, 0)
```

#### 3. 冒险检测 (Hazard Interaction)

在数据打包发送之前，先解决“能不能发”和“怎么发”的问题。

```python
# 1. 调用 Hazard Unit
# 输入：当前指令的 rs1, rs2 (物理切片得到的)
#       以及回传回来的 EX/MEM/WB 状态
stall_req, fwd_op1, fwd_op2 = hazard_unit.build(rs1, rs2, ...)

# 2. 执行流控 (Rigid Pipeline)
# 如果 stall_req 为真，冻结 ID 级 (不 pop FIFO，不更新内部状态)
wait_until(~stall_req)

# 3. 处理 NOP 注入
# 如果 Stall，向 EX 发送 NOP 包；否则发送正常包
packet_valid = ~stall_req
```

#### 4. 打包与分发 (Dispatch)
最后，将计算好的 **“控制语义”** 和 **“前瞻决策”** 一起发给 EX。

```python
# 构造发送给 EX 的控制包 (ex_ctrl_t)
ex_ctrl_payload = ex_ctrl_signals.bundle(
    # 语义控制
    alu_func = alu_func_acc,
    op1_sel = fwd_op1,
    op2_sel = fwd_op2,
    
    # 下级控制
    mem_ctrl = ...
)

# 物理发送 (接口分离)
executor.async_called(
    ctrl = packet_valid.select(ex_ctrl_payload, NOP_CTRL), # NOP 注入，对应一个常量控制包，对应指令 ADD，向x0写入。
    pc   = current_pc,
    rs1_data = reg_file[rs1],
    rs2_data = reg_file[rs2],
    imm  = imm_val_acc
)
```