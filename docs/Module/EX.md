# RV32I EX (Execution) 模块设计文档

> **依赖**：Assassyn, `control_signals.py` (自定义控制信号包)

## 1. 模块概述
**Execution** 模块是 CPU 的运算核心。
在此架构中，EX 阶段不“检测”数据冒险，而是直接“执行” ID 阶段下达的路由指令（即从哪里拿数据）。
同时，它负责驱动 SRAM 的写入端口（Store），计算分支结果并向 IF 阶段反馈重定向/冲刷信号。

## 2. 接口定义

### 2.1 控制信号包 (`control_signals.py`)

EX 阶段的控制信号包定义如下：

```python
ex_ctrl_signals = Record(
    alu_func  = Bits(16),   # ALU 功能码 (独热码)

    rs1_sel   = Bits(3),     # rs1 数据来源选择 (旁路选择)
    rs2_sel   = Bits(3),     # rs2 数据来源选择 (旁路选择)
    
    # 操作数来源选择 (语义选择)
    # 0: 来自级间寄存器的 RS 数据
    # 1: 来自级间寄存器的 PC/Imm
    # 2: 常数 0 - op1_sel 用于 LUI等 / 常数 4 - op2_sel 用于 JAL/JALR Link
    op1_sel   = Bits(3),    
    op2_sel   = Bits(3),    
    
    is_branch = Bits(1),      # 是否是 Branch 指令
    is_jtype = Bits(1),       # 是否是直接跳转指令
    is_jalr = Bits(1),        # 是否是 JALR 指令
    next_pc_addr = Bits(32),  # 预测结果：下一条指令的地址

    mem_ctrl  = mem_ctrl_signals # 【嵌套】携带 MEM/WB 级信号
)
```

### 2.2 端口定义 (`__init__`)

输入端口接收来自 ID 阶段的打包数据，控制信号来自

```python
class Execution(Module):
    def __init__(self):
        super().__init__(
            ports={
                # --- [1] 控制通道 (Control Plane) ---
                # 包含 alu_func, op1_sel, op2_sel, is_branch, is_write
                # 以及嵌套的 mem_ctrl
                'ctrl': Port(ex_ctrl_signals),

                # --- [2] 数据通道群 (Data Plane) ---
                # 当前指令地址 (用于 Branch/AUIPC/JAL)
                'pc': Port(Bits(32)),
                
                # 源寄存器 1 数据 (来自 RegFile)
                'rs1_data': Port(Bits(32)),
                
                # 源寄存器 2 数据 (来自 RegFile)
                'rs2_data': Port(Bits(32)),
                
                # 立即数 (在 ID 级已完成符号扩展)
                'imm': Port(Bits(32))
            }
        )
        self.name = 'EX'
```

### 2.3 构建参数 (`build`)

`build` 函数接收物理资源引用和下一级模块。

```python
@module.combinational
def build(self, 
          mem_module: Module,          # 下一级流水线 (MEM)
          dcache: SRAM,                # SRAM 模块引用
          # --- 旁路数据源 (Forwarding Sources) ---
          ex_mem_bypass: Array,     # 来自 EX-MEM 旁路寄存器的数据（上条指令结果）
          mem_wb_bypass: Array,      # 来自 MEM-WB 旁路寄存器的数据 (上上条指令结果)
          # --- 分支反馈 ---
          branch_target_reg: Array,    # 用于通知 IF 跳转目标的全局寄存器
          ):
    # 实现见下文
    pass
```

## 3. build()实现

### 3.1 获取输入与解包

```python
    # 1. 弹出所有端口数据
    # 根据 __init__ 定义顺序解包
    ctrl = self.ctrl.pop()
    pc   = self.pc.pop()
    rs1  = self.rs1_data.pop()
    rs2  = self.rs2_data.pop()
    imm  = self.imm.pop()
    
    # 获取旁路数据
    fwd_from_mem = ex_mem_bypass[0]
    fwd_from_wb  = mem_wb_bypass[0]
```

### 3.2 操作数选择 (Operand Muxing)

根据 ID 阶段预计算好的独热码 `op_sel`，在多种可能的数据源中选择 ALU 的输入。

```python
    # --- rs1 旁路处理 ---
    real_rs1 = ctrl.rs1_sel.select1hot (
        rs1, fwd_from_mem, fwd_from_wb
    )

    # --- rs2 旁路处理 ---
    real_rs2 = ctrl.op2_sel.select1hot(
        rs2, Bits(32)(0), fwd_from_mem, fwd_from_wb, Bits(32)(0)
    )

    # --- 操作数 1 选择 ---
    alu_op1 = ctrl.op1_sel.select1hot(
        real_rs1,       # 0
        pc,             # 1 (AUIPC/JAL/Branch)
        Bits(32)(0)     # 2 (LUI Link)
    )

    # --- 操作数 2 选择 ---
    alu_op2 = ctrl.op2_sel.select1hot(
        rs2,            # 0
        imm,            # 1
        Bits(32)(4)     # 2 (JAL/JALR Link)
    )
```

### 3.3 ALU 计算 (Calculation)

```python
    # 1. 基础运算
    sum_res = (alu_op1.bitcast(SInt) + alu_op2.bitcast(SInt)).bitcast(Bits)
    # ... 其他运算 (AND, OR, SLL, SLT...)
    
    # 2. 结果选择
    alu_result = ctrl.alu_func.select1hot(
        sum_res, 
        # ...
    )
    
    # 3. 驱动本级 Bypass 寄存器 (向 ID 级提供数据)
    # 这样下一拍 ID 级就能看到这条指令的结果了
    exe_mem_bypas[0] = alu_result
```

### 3.4 访存操作 (Store Handling)

将 Store 指令的写入请求与 Load 指令的读取请求发送到 SRAM。

```python
    # 仅在 is_write (Store) 为真时驱动 SRAM 的 WE
    # 地址是 ALU 计算结果，数据是经过 Forwarding 的 rs2
    dcache.build(
        we    = ctrl.is_write,
        wdata = real_rs2, 
        addr  = alu_result,
        re    = ctrl.mem_ctrl.is_load # 读使能来自 mem_ctrl
    )
```

### 3.5 分支处理 (Branch Handling)

### 3.5.1 资源调度表 (Resource Scheduling)

首先明确主ALU与专用PC加法器在不同指令下的分工，这是 ID 阶段生成控制信号的依据。

| 指令类型   | **PC Adder (输入: PC, Mux)**  | **Main ALU (输入: Mux, Mux)**     | **说明**                   |
| :--------- | :---------------------------- | :-------------------------------- | :------------------------- |
| **Branch** | 计算 **Target** (`PC + Imm`)  | 计算 **Compare** (`rs1` vs `rs2`) | 并行计算目标与条件         |
| **JAL**    | 计算 **Target** (`PC + Imm`)  | 计算 **Link** (`PC + 4`)          | 并行计算向后传递结果与PC值 |
| **JALR**   | 计算 **Target** (`rs1 + Imm`) | 计算 **Link** (`PC + 4`)          | 并行计算向后传递结果与PC值 |
| **其他**   | (Idle / Dont Care)            | 计算 **Result**                   | 常规操作                   |

### 3.5.2 相关控制信号

* 用于处理主ALU操作数选择的 `op1_sel` 和 `op2_sel`。
*   `is_branch` (1-bit): 启动分支部分逻辑。
*   `is_jalr` (1-bit): 控制 PC Adder 的第一个操作数。
    *   `0`: 选择 `PC` (用于 Branch, JAL)
    *   `1`: 选择 `rs1` (用于JALR)

```python
  # 假设已完成 Forwarding，拿到了 real_rs1, real_rs2, imm, pc
   
  # 1. 使用专用加法器计算跳转地址，对于 JALR，基址是 rs1；对于 JAL/Branch，基址是 PC
    
  target_base = ctrl.is_jalr.select(
        pc,          # 0: Branch / JAL
        real_rs1     # 1: JALR
  )
    
  # 专用加法器永远做 Base + Imm
  calc_target = target_base + imm

  # 2. 计算分支条件
  is_taken = is_jtype & (alu_result[0:0] == Bits(1)(1))

  # 3. 根据指令类型决定最终的下一 PC 地址
  final_next_pc = ctrl.is_branch.select(
        is_taken.select(
            calc_target        # Taken
            pc + Bits(32)(4),  # Not Taken
        ), next_pc_addr
  )

  # 4. 写入分支目标寄存器，供 IF 级使用
  branch_miss = final_next_pc != ctrl.next_pc_addr
  branch_target_reg[0] = branch_miss.select(
      Bits(32)(0),    # 不跳转，写 0 表示顺序执行
      final_next_pc   # 跳转，写入目标地址
  )
```

### 3.6 下一级绑定与状态反馈

```python
    # 构造发送给 MEM 的包
    # 只有两个参数：控制 + 统一数据
    mem_call = mem_module.async_called(
        mem_ctrl_signals = ctrl.mem_ctrl,
        alu_result = alu_result
    )
    mem_call.bind.set_fifo_depth(ctrl=1, alu_result=1)

    # 3. 返回状态 (供 HazardUnit 窃听)
    # rd_addr 用于记分牌/依赖检测
    # is_load 用于检测 Load-Use 冒险
    return ctrl.mem_ctrl.wb_ctrl.rd_addr, ctrl.mem_ctrl.is_load
```