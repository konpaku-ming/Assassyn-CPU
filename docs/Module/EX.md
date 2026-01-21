# RV32I EX (Execution) 模块设计文档

> **依赖**：Assassyn Framework, `control_signals.py`, `multiplier.py`, `divider.py`

## 1. 模块概述

**Execution** 模块是 CPU 的运算核心。在此架构中，EX 阶段负责以下任务：

1. **ALU 运算**：执行算术和逻辑运算
2. **旁路处理**：根据 ID 阶段预计算的路由指令选择正确的操作数来源
3. **分支处理**：计算分支条件和跳转目标，更新 BTB 和 Tournament Predictor
4. **M 扩展支持**：处理多周期乘法（3周期 Wallace Tree）和除法（~10周期 Radix-16）

## 2. 接口定义

### 2.1 控制信号包 (`ex_ctrl_signals`)

```python
ex_ctrl_signals = Record(
    alu_func=Bits(16),     # ALU 功能码 (独热码，支持 M 扩展)
    div_op=Bits(5),        # M扩展除法操作 (独热码：NONE/DIV/DIVU/REM/REMU)
    rs1_sel=Bits(4),       # rs1 数据来源选择 (旁路选择)
    rs2_sel=Bits(4),       # rs2 数据来源选择 (旁路选择)
    op1_sel=Bits(3),       # 操作数 1 来源 (RS1/PC/ZERO)
    op2_sel=Bits(3),       # 操作数 2 来源 (RS2/IMM/CONST_4)
    branch_type=Bits(16),  # Branch 指令功能码 (独热码)
    next_pc_addr=Bits(32), # 预测结果：下一条指令的地址
    mem_ctrl=mem_ctrl_signals,  # 【嵌套】携带 MEM/WB 级信号
)
```

### 2.2 端口定义

```python
class Execution(Module):
    def __init__(self):
        super().__init__(
            ports={
                # --- [1] 控制通道 (Control Plane) ---
                "ctrl": Port(ex_ctrl_signals),
                # --- [2] 数据通道群 (Data Plane) ---
                "pc": Port(Bits(32)),        # 当前指令地址
                "rs1_data": Port(Bits(32)),  # 源寄存器 1 数据
                "rs2_data": Port(Bits(32)),  # 源寄存器 2 数据
                "imm": Port(Bits(32)),       # 立即数
            }
        )
        self.name = "Executor"
        
        # M-extension functional units
        self.multiplier = WallaceTreeMul()
        self.divider = Radix16Divider()
```

### 2.3 构建参数

```python
@module.combinational
def build(
    self,
    mem_module: Module,          # 下一级流水线 (MEM)
    ex_bypass: Array,            # EX-MEM 旁路寄存器
    mem_bypass: Array,           # MEM-WB 旁路寄存器
    wb_bypass: Array,            # WB 旁路寄存器
    branch_target_reg: Array,    # 分支目标寄存器 (通知 IF)
    # --- BTB 更新 (可选) ---
    btb_impl: "BTBImpl" = None,
    btb_valid: Array = None,
    btb_tags: Array = None,
    btb_targets: Array = None,
    # --- Tournament Predictor 更新 (可选) ---
    tp_impl: "TournamentPredictorImpl" = None,
    tp_bimodal: Array = None,
    tp_gshare: Array = None,
    tp_ghr: Array = None,
    tp_selector: Array = None,
):
```

## 3. 内部实现

### 3.1 操作数选择 (Operand Muxing)

根据 ID 阶段预计算好的独热码，在多种可能的数据源中选择 ALU 的输入。

```python
# rs1 旁路处理：从 RegFile / EX / MEM / WB 旁路中选择
real_rs1 = ctrl.rs1_sel.select1hot(
    rs1, fwd_from_mem, fwd_from_wb, fwd_from_wb_stage
)

# rs2 旁路处理
real_rs2 = ctrl.rs2_sel.select1hot(
    rs2, fwd_from_mem, fwd_from_wb, fwd_from_wb_stage
)

# 操作数 1 选择：RS1 / PC / 0
alu_op1 = ctrl.op1_sel.select1hot(real_rs1, pc, Bits(32)(0))

# 操作数 2 选择：RS2 / IMM / 4
alu_op2 = ctrl.op2_sel.select1hot(real_rs2, imm, Bits(32)(4))
```

### 3.2 ALU 计算

ALU 支持 RV32I 基础运算和 M 扩展乘法指令：

```python
# 基础运算
add_res = (op1_signed + op2_signed).bitcast(Bits(32))
sub_res = (op1_signed - op2_signed).bitcast(Bits(32))
and_res = alu_op1 & alu_op2
or_res = alu_op1 | alu_op2
xor_res = alu_op1 ^ alu_op2
sll_res = alu_op1 << shamt
srl_res = alu_op1 >> shamt
sra_res = op1_signed >> shamt
slt_res = (op1_signed < op2_signed).bitcast(Bits(32))
sltu_res = (alu_op1 < alu_op2).bitcast(Bits(32))

# ALU 结果选择 (独热码)
alu_result = ctrl.alu_func.select1hot(
    add_res,   # ADD (bit 0)
    sub_res,   # SUB (bit 1)
    sll_res,   # SLL (bit 2)
    slt_res,   # SLT (bit 3)
    sltu_res,  # SLTU (bit 4)
    xor_res,   # XOR (bit 5)
    srl_res,   # SRL (bit 6)
    sra_res,   # SRA (bit 7)
    or_res,    # OR (bit 8)
    and_res,   # AND (bit 9)
    alu_op2,   # SYS (bit 10)
    Bits(32)(0),  # MUL placeholder (bit 11)
    Bits(32)(0),  # MULH placeholder (bit 12)
    Bits(32)(0),  # MULHSU placeholder (bit 13)
    Bits(32)(0),  # MULHU placeholder (bit 14)
    Bits(32)(0),  # NOP (bit 15)
)
```

### 3.3 M 扩展：乘法处理

使用 3 周期 Wallace Tree 乘法器处理 MUL/MULH/MULHSU/MULHU：

```python
# 检测乘法指令
is_mul_op = is_mul | is_mulh | is_mulhsu | is_mulhu

# 启动乘法器
with Condition((is_mul_op == Bits(1)(1)) & (mul_busy == Bits(1)(0)) & (flush_if == Bits(1)(0))):
    self.multiplier.start_multiply(
        op1=real_rs1,
        op2=real_rs2,
        op1_signed=op1_signed_flag,
        op2_signed=op2_signed_flag,
        result_high=result_high_flag,
        rd=wb_ctrl.rd_addr
    )

# 执行流水线阶段
self.multiplier.cycle_m1()  # 部分积生成 + 2 级压缩
self.multiplier.cycle_m2()  # Wallace Tree 压缩 (15→2)
self.multiplier.cycle_m3()  # CLA 最终加法
```

### 3.4 M 扩展：除法处理

使用 ~10 周期 Radix-16 除法器处理 DIV/DIVU/REM/REMU：

```python
# 启动除法器
with Condition((is_div_op == Bits(1)(1)) & (div_busy == Bits(1)(0)) & (flush_if == Bits(1)(0))):
    self.divider.start_divide(
        dividend=real_rs1,
        divisor=real_rs2,
        is_signed=is_signed_div,
        is_rem=is_rem_op,
        rd=wb_ctrl.rd_addr
    )

# 执行状态机
self.divider.tick()
```

### 3.5 分支处理

```python
# 计算跳转目标
is_jalr = ctrl.branch_type == BranchType.JALR
target_base = is_jalr.select(real_rs1, pc)
calc_target = target_base + imm

# JALR: 目标地址最低位清0
calc_target = is_jalr.select(
    concat(raw_calc_target[1:31], Bits(1)(0)),
    raw_calc_target,
)

# 分支条件判断
is_taken = (
    is_taken_eq | is_taken_ne | is_taken_lt | is_taken_ge |
    is_taken_ltu | is_taken_geu |
    (ctrl.branch_type == BranchType.JAL) | is_jalr
)

# 检测分支预测错误
branch_miss = final_next_pc != ctrl.next_pc_addr
branch_target_reg[0] = branch_miss.select(final_next_pc, Bits(32)(0))
```

### 3.6 BTB 和 Tournament Predictor 更新

```python
# 更新 BTB (分支 taken 时)
if btb_impl is not None:
    should_update_btb = is_branch & is_taken & ~flush_if
    btb_impl.update(pc=pc, target=calc_target, should_update=should_update_btb, ...)

# 更新 Tournament Predictor (所有分支)
if tp_impl is not None:
    tp_should_update = is_branch & ~flush_if
    tp_impl.update(pc=pc, actual_taken=is_taken, is_branch=tp_should_update, ...)
```

### 3.7 输出与返回值

```python
# 更新 Bypass 寄存器
ex_bypass[0] = final_result

# 发送到 MEM 级
mem_call = mem_module.async_called(ctrl=final_mem_ctrl, alu_result=final_result)

# 返回引脚供 HazardUnit 和 SingleMemory 使用
return final_rd, final_result, is_load, is_store, mem_width, real_rs2, mul_busy, div_busy
```

## 4. 资源调度表

| 指令类型 | PC Adder | Main ALU | 说明 |
| :--- | :--- | :--- | :--- |
| **Branch** | PC + Imm (Target) | rs1 vs rs2 (Compare) | 并行计算目标与条件 |
| **JAL** | PC + Imm (Target) | PC + 4 (Link) | 并行计算目标与链接地址 |
| **JALR** | rs1 + Imm (Target) | PC + 4 (Link) | 并行计算目标与链接地址 |
| **ALU** | (Idle) | 计算 Result | 常规操作 |
| **Load/Store** | (Idle) | rs1 + Imm (Addr) | 地址计算 |
| **MUL** | (Idle) | (Idle) | 乘法器处理 |
| **DIV** | (Idle) | (Idle) | 除法器处理 |
