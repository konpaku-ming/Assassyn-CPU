# Assassyn-CPU 五级流水线工作原理详细报告

> **文档版本**: v1.0  
> **最后更新**: 2025-12-12  
> **作者**: AI Agent Analysis

## 目录

1. [CPU架构概述](#cpu架构概述)
2. [五级流水线架构](#五级流水线架构)
3. [每个周期的详细操作](#每个周期的详细操作)
4. [数据冒险处理机制](#数据冒险处理机制)
5. [控制冒险处理机制](#控制冒险处理机制)
6. [完整指令执行示例](#完整指令执行示例)
7. [关键设计特性](#关键设计特性)

---

## CPU架构概述

### 1.1 整体架构

Assassyn-CPU 是一个基于 RISC-V RV32I 指令集的五级流水线 CPU 设计，使用 Assassyn HDL（一种基于 Python 的硬件描述语言）实现。

**核心特性**:
- **指令集**: RISC-V RV32I (32位基础整数指令集)
- **流水线级数**: 5级（IF, ID, EX, MEM, WB）
- **数据位宽**: 32位
- **寄存器**: 32个通用寄存器 (x0-x31)
- **内存架构**: 哈佛架构（指令存储和数据存储分离）
- **冒险处理**: 
  - 数据冒险：前递（Forwarding）+ 停顿（Stall）
  - 控制冒险：分支预测 + 冲刷（Flush）

### 1.2 设计哲学

**延迟不敏感（Latency-Insensitive）设计**:
- 使用 Assassyn 框架的异步调用机制（`async_called`）
- 模块间通过 Port 和 FIFO 进行通信
- 自动处理流水线的握手协议

**模块化与解耦**:
- 每个流水级是独立的 Module 或 Downstream
- 控制信号通过嵌套 Record 结构传递
- 物理资源（寄存器堆、SRAM）集中管理

**正交化设计**:
- 控制通道（Control Plane）和数据通道（Data Plane）分离
- 旁路选择在 ID 级决定，在 EX 级执行
- 冒险检测与执行逻辑解耦

---

## 五级流水线架构

### 2.1 流水线概览

```
+--------+      +--------+      +--------+      +--------+      +--------+
|   IF   | ---> |   ID   | ---> |   EX   | ---> |  MEM   | ---> |   WB   |
| 取指   |      | 译码   |      | 执行   |      | 访存   |      | 写回   |
+--------+      +--------+      +--------+      +--------+      +--------+
    |               |               |               |               |
    |               |               |               |               |
    v               v               v               v               v
  ICache         RegFile           ALU           DCache         RegFile
  PC寄存器       指令译码          分支单元        数据对齐        旁路网络
```

### 2.2 流水线各级职责

| 阶段 | 名称 | 主要职责 | 输入 | 输出 |
|------|------|----------|------|------|
| **IF** | Instruction Fetch | 取指令 | PC值, Stall/Flush信号 | PC值, 指令地址 |
| **ID** | Instruction Decode | 译码 | 指令, PC值 | 控制信号包, 操作数, 立即数 |
| **EX** | Execute | 执行 | 控制信号, 操作数 | ALU结果, 分支决策 |
| **MEM** | Memory Access | 访存 | ALU结果, 控制信号 | 内存数据/ALU结果 |
| **WB** | Write Back | 写回 | 最终数据, rd地址 | 更新寄存器堆 |

---

## 每个周期的详细操作

### 3.1 IF阶段（取指）

**时序**: 每个周期开始

**主要部件**:
- `pc_reg`: 程序计数器寄存器
- `last_pc_reg`: 上一周期PC值（用于Stall）
- `icache`: 指令缓存（SRAM）

**每周期操作流程**:

```
周期开始:
1. 读取控制信号
   - stall_if: 是否停顿
   - branch_target_reg[0]: 分支目标地址

2. 选择当前PC
   if (stall_if):
       current_pc = last_pc_reg[0]  # 保持上周期PC
   else:
       current_pc = pc_reg[0]        # 使用当前PC

3. 检查是否需要Flush
   flush_if = (branch_target_reg[0] != 0)
   if (flush_if):
       final_current_pc = branch_target_reg[0]  # 使用分支目标
   else:
       final_current_pc = current_pc

4. 驱动ICache
   sram_addr = final_current_pc >> 2  # 字节地址转字地址
   icache.read(addr=sram_addr)

5. 计算下一周期PC
   final_next_pc = final_current_pc + 4

6. 更新寄存器（时序逻辑）
   pc_reg[0] <= final_next_pc
   last_pc_reg[0] <= final_current_pc

7. 发送到ID级
   decoder.async_called(pc=final_current_pc)

周期结束
```

**关键点**:
- IF级不直接读取指令内容，只负责驱动SRAM
- 实际指令数据在下一周期从SRAM输出端口获取
- Stall时保持PC不变，Flush时立即跳转到新地址

### 3.2 ID阶段（译码）

**时序**: 接收IF级输出

**主要部件**:
- `Decoder`: 状态容器（Module）
- `DecoderImpl`: 逻辑核心（Downstream）
- `DataHazardUnit`: 冒险检测单元
- `reg_file`: 通用寄存器堆
- `icache.dout`: 指令缓存输出

**每周期操作流程**:

```
周期开始:

=== Decoder部分 ===
1. 获取输入
   pc_val = 从IF级接收的PC
   inst = icache.dout[0]  # 从SRAM读取指令

2. 物理切片
   opcode = inst[0:6]
   rd = inst[7:11]
   funct3 = inst[12:14]
   rs1 = inst[15:19]
   rs2 = inst[20:24]
   bit30 = inst[30:30]

3. 立即数并行生成
   imm_i = 符号扩展(inst[20:31])      # I型
   imm_s = 符号扩展(inst[25:31] | inst[7:11])  # S型
   imm_b = 符号扩展(...) # B型
   imm_u = inst[12:31] | 0x000  # U型
   imm_j = 符号扩展(...) # J型

4. 查表译码（遍历rv32i_table）
   for each instruction in table:
       match = (opcode == entry.op) && 
               (funct3 == entry.f3) && 
               (bit30 == entry.b30)
       
       if match:
           acc_alu_func |= entry.alu_func
           acc_op1_sel |= entry.op1_sel
           acc_op2_sel |= entry.op2_sel
           acc_mem_op |= entry.mem_op
           acc_br_type |= entry.branch_type
           acc_imm |= 根据imm_type选择立即数
           ...

5. 读取寄存器
   raw_rs1_data = reg_file[rs1]
   raw_rs2_data = reg_file[rs2]

6. 构造预解码包
   pre = {
       alu_func, op1_sel, op2_sel,
       branch_type, next_pc_addr,
       mem_ctrl: {mem_opcode, mem_width, mem_unsigned, rd_addr},
       pc, rs1_data, rs2_data, imm
   }

7. 发送到DataHazardUnit
   返回: pre, rs1, rs2, rs1_used, rs2_used

=== DataHazardUnit部分 ===
8. 检测Load-Use冒险
   load_use_hazard_rs1 = rs1_used && !rs1_is_zero && 
                         ex_is_load && (rs1 == ex_rd)
   load_use_hazard_rs2 = rs2_used && !rs2_is_zero && 
                         ex_is_load && (rs2 == ex_rd)
   stall_if = load_use_hazard_rs1 || load_use_hazard_rs2

9. 生成前递选择信号（优先级从高到低）
   if (rs1 == ex_rd && !ex_is_load):
       rs1_sel = EX_MEM_BYPASS
   else if (rs1 == mem_rd):
       rs1_sel = MEM_WB_BYPASS
   else if (rs1 == wb_rd):
       rs1_sel = WB_BYPASS
   else:
       rs1_sel = RS1
   
   # rs2同理

=== DecoderImpl部分 ===
10. 检查是否需要NOP
    flush_if = (branch_target_reg[0] != 0)
    nop_if = flush_if || stall_if

11. NOP注入
    if (nop_if):
        final_rd = 0
        final_mem_opcode = NONE
        final_branch_type = NO_BRANCH
    else:
        使用正常控制信号

12. 打包并发送到EX级
    executor.async_called(
        ctrl = {alu_func, op1_sel, op2_sel, rs1_sel, rs2_sel, 
                branch_type, next_pc_addr, mem_ctrl},
        pc = pre.pc,
        rs1_data = pre.rs1_data,
        rs2_data = pre.rs2_data,
        imm = pre.imm
    )

周期结束
```

**关键点**:
- 译码采用查表法，通过OR累加实现多路选择
- 所有立即数格式并行生成，根据指令类型选择
- 寄存器读取是组合逻辑，立即完成
- NOP注入确保流水线始终有有效数据流动

### 3.3 EX阶段（执行）

**时序**: 接收ID级输出

**主要部件**:
- ALU（算术逻辑单元）
- 分支判断逻辑
- 旁路多路选择器
- `ex_mem_bypass`: EX-MEM旁路寄存器
- `branch_target_reg`: 分支目标寄存器

**每周期操作流程**:

```
周期开始:

1. 获取输入
   ctrl = 控制信号包
   pc, rs1, rs2, imm = 数据输入
   mem_ctrl = 访存控制信号

2. 检查Flush信号
   flush_if = (branch_target_reg[0] != 0)
   if (flush_if):
       final_rd = 0  # 作废当前指令
       final_mem_opcode = NONE

3. 获取旁路数据
   fwd_from_mem = ex_mem_bypass[0]     # 上一条指令结果
   fwd_from_wb = mem_wb_bypass[0]      # 上上条指令结果
   fwd_from_wb_stage = wb_bypass[0]    # 当前写回数据

4. RS1旁路选择
   根据 ctrl.rs1_sel:
   - RS1: real_rs1 = rs1
   - EX_MEM_BYPASS: real_rs1 = fwd_from_mem
   - MEM_WB_BYPASS: real_rs1 = fwd_from_wb
   - WB_BYPASS: real_rs1 = fwd_from_wb_stage

5. RS2旁路选择（同RS1）

6. 操作数1选择
   根据 ctrl.op1_sel:
   - RS1: alu_op1 = real_rs1
   - PC: alu_op1 = pc
   - ZERO: alu_op1 = 0

7. 操作数2选择
   根据 ctrl.op2_sel:
   - RS2: alu_op2 = real_rs2
   - IMM: alu_op2 = imm
   - CONST_4: alu_op2 = 4

8. ALU计算
   根据 ctrl.alu_func:
   - ADD: result = op1 + op2
   - SUB: result = op1 - op2
   - AND: result = op1 & op2
   - OR: result = op1 | op2
   - XOR: result = op1 ^ op2
   - SLL: result = op1 << op2[0:4]
   - SRL: result = op1 >> op2[0:4]
   - SRA: result = (signed)op1 >> op2[0:4]
   - SLT: result = (signed)op1 < (signed)op2 ? 1 : 0
   - SLTU: result = op1 < op2 ? 1 : 0
   - NOP: result = op2

9. 更新旁路寄存器
   ex_mem_bypass[0] = alu_result

10. SRAM操作
    is_store = (final_mem_ctrl.mem_opcode == STORE)
    is_load = (final_mem_ctrl.mem_opcode == LOAD)
    
    dcache.build(
        we = is_store,
        wdata = real_rs2,
        addr = alu_result,
        re = is_load
    )

11. 分支处理
    a. 计算目标地址
       is_jalr = (ctrl.branch_type == JALR)
       target_base = is_jalr ? real_rs1 : pc
       calc_target = target_base + imm
    
    b. 判断分支条件
       is_eq = (alu_result == 0)
       is_lt = (alu_result[31] == 1)  # 符号位
       
       根据branch_type:
       - BEQ: is_taken = is_eq
       - BNE: is_taken = !is_eq
       - BLT: is_taken = is_lt
       - BGE: is_taken = !is_lt
       - BLTU/BGEU: 同上
       - JAL/JALR: is_taken = 1
    
    c. 决定下一PC
       if (is_branch && is_taken):
           final_next_pc = calc_target
       else:
           final_next_pc = next_pc_addr
    
    d. 检测预测失败
       branch_miss = (final_next_pc != ctrl.next_pc_addr)
       if (branch_miss):
           branch_target_reg[0] = final_next_pc
       else:
           branch_target_reg[0] = 0

12. 发送到MEM级
    memory_unit.async_called(
        ctrl = final_mem_ctrl,
        alu_result = alu_result
    )

13. 返回状态
    return final_rd, ex_is_load

周期结束
```

**关键点**:
- 旁路网络有3个来源，优先级：EX > MEM > WB
- ALU支持10种基本运算
- 分支判断与地址计算并行进行
- 预测失败时向branch_target_reg写入目标地址，触发Flush

### 3.4 MEM阶段（访存）

**时序**: 接收EX级输出

**主要部件**:
- 数据对齐单元（Data Aligner）
- `dcache.dout`: 数据缓存输出
- `mem_wb_bypass`: MEM-WB旁路寄存器

**每周期操作流程**:

```
周期开始:

1. 获取输入
   ctrl = 访存控制信号
   alu_result = ALU计算结果（或地址）

2. 从SRAM读取原始数据
   raw_mem = dcache.dout[0]  # 32位字

3. 数据对齐（Load指令）
   a. 选择半字（16位）
      根据 alu_result[1]:
      - 0: half_selected = raw_mem[0:15]   # 低16位
      - 1: half_selected = raw_mem[16:31]  # 高16位
   
   b. 选择字节（8位）
      根据 alu_result[0]:
      - 0: byte_selected = half_selected[0:7]   # 低8位
      - 1: byte_selected = half_selected[8:15]  # 高8位

4. 符号扩展
   a. 字节扩展
      if (mem_unsigned):
          padding_8 = 0x000000
      else:
          padding_8 = byte_selected[7] ? 0xFFFFFF : 0x000000
      byte_extended = padding_8 | byte_selected
   
   b. 半字扩展
      if (mem_unsigned):
          padding_16 = 0x0000
      else:
          padding_16 = half_selected[15] ? 0xFFFF : 0x0000
      half_extended = padding_16 | half_selected

5. 选择最终内存数据
   根据 ctrl.mem_width:
   - BYTE: processed_mem_result = byte_extended
   - HALF: processed_mem_result = half_extended
   - WORD: processed_mem_result = raw_mem

6. 最终数据选择
   is_load = (ctrl.mem_opcode == LOAD)
   if (is_load):
       final_data = processed_mem_result
   else:
       final_data = alu_result

7. 更新旁路寄存器
   mem_wb_bypass[0] = final_data

8. 发送到WB级
   writeback.async_called(
       ctrl = ctrl.rd_addr,
       wdata = final_data
   )

9. 返回状态
   return ctrl.rd_addr

周期结束
```

**关键点**:
- 数据对齐采用二分法：先选半字，再选字节
- 支持有符号/无符号扩展
- Load指令使用对齐后的数据，其他指令使用ALU结果
- 旁路寄存器更新，供后续指令使用

### 3.5 WB阶段（写回）

**时序**: 接收MEM级输出

**主要部件**:
- `reg_file`: 通用寄存器堆
- `wb_bypass`: WB旁路寄存器

**每周期操作流程**:

```
周期开始:

1. 获取输入
   ctrl = rd地址
   wdata = 最终数据

2. 判断是否写回
   if (ctrl != 0):  # rd不是x0寄存器
       a. 写入寄存器堆
          reg_file[ctrl] = wdata
       
       b. 更新旁路寄存器
          wb_bypass[0] = wdata
       
       c. 输出日志
          log("WB: Write x{} <= 0x{:x}", ctrl, wdata)

3. 返回状态
   return ctrl

周期结束
```

**关键点**:
- x0寄存器硬连线为0，写入被阻止
- 写回操作更新寄存器堆和旁路寄存器
- 这是流水线的最后一级，指令退休

---

## 数据冒险处理机制

### 4.1 数据冒险分类

**RAW（Read After Write）冒险**:
```assembly
ADD x1, x2, x3   # 写 x1
SUB x4, x1, x5   # 读 x1 (冒险!)
```

### 4.2 前递（Forwarding）机制

**前递网络结构**:
```
        EX阶段              MEM阶段             WB阶段
          ↓                   ↓                  ↓
    ex_mem_bypass      mem_wb_bypass       wb_bypass
          ↓                   ↓                  ↓
          +-------------------+------------------+
                              ↓
                        旁路选择器（ID级决定，EX级执行）
```

**前递优先级（从高到低）**:
1. **EX-MEM旁路**: 上一条指令刚计算完成
2. **MEM-WB旁路**: 上上条指令访存完成
3. **WB旁路**: 当前正在写回的数据
4. **寄存器堆**: 正常读取

**前递决策逻辑**（在DataHazardUnit中）:
```python
if (rs1_used && !rs1_is_zero):
    if (rs1 == ex_rd && !ex_is_load):
        rs1_sel = EX_MEM_BYPASS
    elif (rs1 == mem_rd):
        rs1_sel = MEM_WB_BYPASS
    elif (rs1 == wb_rd):
        rs1_sel = WB_BYPASS
    else:
        rs1_sel = RS1
else:
    rs1_sel = RS1
```

### 4.3 停顿（Stall）机制

**Load-Use冒险**:
```assembly
LW  x1, 0(x2)    # Cycle N: ID级
ADD x3, x1, x4   # Cycle N+1: ID级，需要x1但数据还未从内存读出
```

**必须停顿的原因**:
- Load指令在MEM阶段才能获取数据
- EX-MEM旁路无法在EX阶段提供Load数据
- 必须等待一个周期，让Load到达MEM阶段

**停顿行为**:
1. **IF级**: 保持PC不变（`stall_if.select(last_pc_reg, pc_reg)`）
2. **ID级**: 向EX级注入NOP气泡（`nop_if.select(0, rd)`）
3. **EX级**: 正常执行Load指令
4. **时间线**:
   ```
   Cycle N:   LW在ID    ADD在IF
   Cycle N+1: LW在EX    ADD仍在IF (stall)
   Cycle N+2: LW在MEM   ADD在ID (继续，使用MEM-WB旁路)
   ```

### 4.4 完整数据冒险处理示例

**场景1: 连续数据依赖（前递解决）**
```assembly
ADD x1, x2, x3   # Inst1
SUB x4, x1, x5   # Inst2，依赖x1
AND x6, x4, x7   # Inst3，依赖x4
```

| 周期 | IF | ID | EX | MEM | WB |
|------|----|----|----|----|-----|
| 1 | Inst1 | - | - | - | - |
| 2 | Inst2 | Inst1 | - | - | - |
| 3 | Inst3 | Inst2 | Inst1 | - | - |
| 4 | - | Inst3 | Inst2 | Inst1 | - |
| 5 | - | - | Inst3 | Inst2 | Inst1 |

- Cycle 3: Inst2的ID级检测到rs1(x1) == Inst1的rd，DataHazardUnit设置rs1_sel=EX_MEM_BYPASS
- Cycle 4: Inst2在EX级从ex_mem_bypass获取x1值（Inst1的ALU结果）
- Cycle 4: Inst3的ID级检测到rs1(x4) == Inst2的rd，设置rs1_sel=EX_MEM_BYPASS
- Cycle 5: Inst3在EX级从ex_mem_bypass获取x4值

**场景2: Load-Use冒险（停顿解决）**
```assembly
LW  x1, 0(x2)    # Inst1
ADD x3, x1, x4   # Inst2，依赖x1
```

| 周期 | IF | ID | EX | MEM | WB | 说明 |
|------|----|----|----|----|-----|------|
| 1 | Inst1 | - | - | - | - | |
| 2 | Inst2 | Inst1 | - | - | - | |
| 3 | Inst2 | NOP | Inst1 | - | - | Stall! ID检测Load-Use |
| 4 | - | Inst2 | NOP | Inst1 | - | 恢复，Inst2使用MEM-WB旁路 |
| 5 | - | - | Inst2 | NOP | Inst1 | |

- Cycle 2: Inst2在ID级，检测到rs1(x1) == Inst1的rd且Inst1是Load
- Cycle 3: DataHazardUnit输出stall_if=1，IF保持PC，ID向EX注入NOP
- Cycle 4: Inst1到达MEM级，数据可用，Inst2重新进入ID级，使用MEM-WB旁路

---

## 控制冒险处理机制

### 5.1 控制冒险场景

**分支指令导致的流水线冲刷**:
```assembly
BEQ x1, x2, label   # Cycle N: ID级
ADD x3, x4, x5      # Cycle N+1: IF级（可能被冲刷）
SUB x6, x7, x8      # Cycle N+2: 未取指（可能被冲刷）
label:
OR  x9, x10, x11    # 目标指令
```

### 5.2 分支预测策略

**静态预测**: 始终预测分支不跳转（Not Taken）
- `next_pc_addr = pc + 4`（在ID级计算）
- 简单高效，适合大多数情况

### 5.3 分支冲刷机制

**核心组件**: `branch_target_reg`（全局寄存器）

**工作流程**:

```
=== EX阶段（Cycle N） ===
1. 计算分支目标
   target_base = is_jalr ? real_rs1 : pc
   calc_target = target_base + imm

2. 判断分支条件
   根据branch_type判断is_taken

3. 决定实际下一PC
   actual_next_pc = is_taken ? calc_target : (pc + 4)

4. 检测预测错误
   predicted_pc = ctrl.next_pc_addr
   branch_miss = (actual_next_pc != predicted_pc)

5. 写入分支目标寄存器
   if (branch_miss):
       branch_target_reg[0] = actual_next_pc
   else:
       branch_target_reg[0] = 0

=== IF阶段（Cycle N+1） ===
6. 检查分支目标寄存器
   flush_if = (branch_target_reg[0] != 0)

7. 如果需要Flush
   if (flush_if):
       final_current_pc = branch_target_reg[0]  # 使用正确地址

=== ID阶段（Cycle N+1） ===
8. 检查分支目标寄存器
   flush_if = (branch_target_reg[0] != 0)
   nop_if = flush_if || stall_if

9. 注入NOP
   if (nop_if):
       final_rd = 0
       final_mem_opcode = NONE
       final_branch_type = NO_BRANCH

=== EX阶段（Cycle N+1） ===
10. 检查并清除分支目标寄存器
    flush_if = (branch_target_reg[0] != 0)
    if (flush_if):
        final_rd = 0  # 作废当前指令
        branch_target_reg[0] = 0  # 清除标志（隐式）
```

### 5.4 分支处理时间线

**场景: BEQ预测失败**
```assembly
0x100: BEQ x1, x2, 0x200
0x104: ADD x3, x4, x5    # 错误路径
0x108: SUB x6, x7, x8    # 错误路径
...
0x200: OR x9, x10, x11   # 正确路径
```

| 周期 | IF | ID | EX | MEM | WB | 说明 |
|------|----|----|----|----|-----|------|
| 1 | BEQ@100 | - | - | - | - | |
| 2 | ADD@104 | BEQ | - | - | - | 预测Not Taken |
| 3 | SUB@108 | ADD | BEQ | - | - | BEQ在EX判断，分支实际Taken |
| 4 | OR@200 | NOP | NOP | BEQ | - | Flush!读取正确指令 |
| 5 | - | OR | NOP | NOP | BEQ | 恢复正常 |

- Cycle 3: BEQ在EX级判断为Taken，写入branch_target_reg=0x200
- Cycle 4:
  - IF级检测到flush，使用0x200作为PC，取OR指令
  - ID级将ADD作废（注入NOP）
  - EX级将SUB作废

**分支损失**: 2个周期（ADD和SUB被作废）

### 5.5 JAL/JALR处理

**JAL（无条件跳转）**:
```assembly
JAL x1, offset
```
- ID级: op1_sel=PC, op2_sel=CONST_4（计算返回地址PC+4）
- EX级: alu_result = PC + 4, target = PC + offset
- 分支总是Taken，但仍然需要Flush

**JALR（寄存器跳转）**:
```assembly
JALR x1, offset(x2)
```
- ID级: op1_sel=PC, op2_sel=CONST_4
- EX级: alu_result = PC + 4, target = rs1 + offset
- 目标地址依赖寄存器值，可能触发前递

---

## 完整指令执行示例

### 6.1 示例程序

```assembly
# 计算 x3 = (x1 + x2) * 4
ADD x3, x1, x2    # 0x00: x3 = x1 + x2
SLL x3, x3, 2     # 0x04: x3 = x3 << 2
SW  x3, 0(x4)     # 0x08: mem[x4] = x3
```

假设初始状态:
- x1 = 0x10
- x2 = 0x20
- x4 = 0x1000

### 6.2 逐周期执行

**Cycle 1**
```
IF:  取指令 ADD，PC=0x00，next_PC=0x04
ID:  空
EX:  空
MEM: 空
WB:  空

寄存器/旁路状态: 无变化
```

**Cycle 2**
```
IF:  取指令 SLL，PC=0x04，next_PC=0x08
ID:  译码 ADD
     - rs1=x1(1), rs2=x2(2), rd=x3(3)
     - alu_func=ADD, op1_sel=RS1, op2_sel=RS2
     - 读取: rs1_data=0x10, rs2_data=0x20
     - DataHazardUnit: 无冒险
EX:  空
MEM: 空
WB:  空

寄存器/旁路状态: 无变化
```

**Cycle 3**
```
IF:  取指令 SW，PC=0x08，next_PC=0x0C
ID:  译码 SLL
     - rs1=x3(3), rs2=0, rd=x3(3), imm=2
     - alu_func=SLL, op1_sel=RS1, op2_sel=IMM
     - 读取: rs1_data=0x00（旧值）
     - DataHazardUnit: 检测到 rs1(3) == ex_rd(3)
       设置 rs1_sel=EX_MEM_BYPASS
EX:  执行 ADD
     - alu_op1=0x10, alu_op2=0x20
     - alu_result=0x30
     - ex_mem_bypass[0] = 0x30
MEM: 空
WB:  空

寄存器/旁路状态:
- ex_mem_bypass = 0x30
```

**Cycle 4**
```
IF:  取下一条指令，PC=0x0C
ID:  译码 SW
     - rs1=x4(4), rs2=x3(3), imm=0
     - alu_func=ADD, mem_opcode=STORE
     - 读取: rs1_data=0x1000, rs2_data=0x00（旧值）
     - DataHazardUnit: 检测到 rs2(3) == ex_rd(3)
       设置 rs2_sel=EX_MEM_BYPASS
EX:  执行 SLL
     - 旁路: real_rs1 = ex_mem_bypass[0] = 0x30
     - alu_op1=0x30, alu_op2=2
     - alu_result=0xC0（0x30 << 2）
     - ex_mem_bypass[0] = 0xC0
MEM: ADD进入MEM
     - 非Load指令: final_data = alu_result = 0x30
     - mem_wb_bypass[0] = 0x30
WB:  空

寄存器/旁路状态:
- ex_mem_bypass = 0xC0
- mem_wb_bypass = 0x30
```

**Cycle 5**
```
IF:  继续...
ID:  下一条指令
EX:  执行 SW
     - 旁路: real_rs2 = ex_mem_bypass[0] = 0xC0
     - alu_op1=0x1000, alu_op2=0
     - alu_result=0x1000（地址）
     - dcache.write(addr=0x1000, wdata=0xC0)
MEM: SLL进入MEM
     - final_data = 0xC0
     - mem_wb_bypass[0] = 0xC0
WB:  ADD进入WB
     - reg_file[3] = 0x30
     - wb_bypass[0] = 0x30

寄存器/旁路状态:
- reg_file[x3] = 0x30（ADD写回）
- mem_wb_bypass = 0xC0
- wb_bypass = 0x30
```

**Cycle 6**
```
EX:  下一条指令
MEM: SW进入MEM
     - mem[0x1000] = 0xC0（已在EX阶段写入SRAM）
     - final_data = 0x1000
WB:  SLL进入WB
     - reg_file[3] = 0xC0（覆盖之前的值）
     - wb_bypass[0] = 0xC0

寄存器/旁路状态:
- reg_file[x3] = 0xC0（SLL写回）
- mem[0x1000] = 0xC0
```

**Cycle 7**
```
WB:  SW进入WB
     - rd=0，不写回（SW不更新寄存器）

最终结果:
- x3 = 0xC0
- mem[0x1000] = 0xC0
```

### 6.3 关键观察

1. **前递网络运作**:
   - SLL使用EX-MEM旁路获取ADD结果
   - SW使用EX-MEM旁路获取SLL结果

2. **时序关系**:
   - 旁路寄存器在前一级更新，后一级立即可用
   - ADD的结果在Cycle 3写入ex_mem_bypass，Cycle 4被SLL使用

3. **Store指令**:
   - SRAM写入在EX阶段驱动
   - MEM阶段只是流水线阶段，实际写入已完成

---

## 关键设计特性

### 7.1 Assassyn框架特性

**1. 延迟不敏感（Latency-Insensitive）**
- 模块间通过异步调用通信
- 自动插入FIFO处理握手
- 开发者无需关心具体握手时序

**2. Record嵌套结构**
```python
ex_ctrl_signals = Record(
    alu_func, op1_sel, op2_sel, rs1_sel, rs2_sel,
    branch_type, next_pc_addr,
    mem_ctrl = Record(
        mem_opcode, mem_width, mem_unsigned,
        rd_addr
    )
)
```
- 控制信号随流水线逐级剥离
- EX级剥离ex_ctrl，向MEM传递mem_ctrl
- MEM级剥离mem_ctrl，向WB传递rd_addr

**3. Module vs Downstream**
- Module: 有状态（寄存器），可被异步调用
- Downstream: 纯组合逻辑，用于构建辅助逻辑

### 7.2 独热码（One-Hot Encoding）

**优势**:
- 简化选择逻辑（使用select1hot）
- 避免优先级编码器
- 易于扩展新功能

**示例**:
```python
alu_func = Bits(16)
ADD  = 0b0000000000000001
SUB  = 0b0000000000000010
SLL  = 0b0000000000000100
...

result = alu_func.select1hot(
    add_res, sub_res, sll_res, ...
)
```

### 7.3 刚性流水线（Rigid Pipeline）

**特点**:
- 每个周期每级都有有效数据（或NOP）
- 不使用valid/ready握手
- 简化控制逻辑

**NOP注入时机**:
- Stall时: ID向EX注入NOP
- Flush时: IF和ID同时注入NOP
- NOP表现: rd=0, mem_opcode=NONE, branch_type=NO_BRANCH

### 7.4 旁路网络设计

**三级旁路**:
1. EX-MEM: 最高优先级，覆盖最近的依赖
2. MEM-WB: 中等优先级，覆盖两周期前的依赖
3. WB: 最低优先级，覆盖三周期前的依赖

**决策在ID，执行在EX**:
- DataHazardUnit在ID级生成rs1_sel/rs2_sel
- EX级根据选择信号从不同旁路读取数据
- 解耦冒险检测与数据选择

### 7.5 控制信号累加法

**译码策略**:
```python
acc_alu_func = Bits(16)(0)
for entry in rv32i_table:
    match = (opcode == entry.op) && ...
    acc_alu_func |= match.select(entry.alu_func, 0)
```

**原理**:
- 遍历所有指令，累加匹配的信号
- 因为每条指令只匹配一次，OR累加等价于MUX
- 避免复杂的if-else逻辑

### 7.6 分支预测与恢复

**简单但有效**:
- 静态预测Not Taken，准确率约70%
- 预测失败损失2个周期
- 未来可扩展为动态预测（需要BTB）

**快速恢复**:
- 使用全局branch_target_reg广播
- 所有级同时响应Flush信号
- 一个周期内完成冲刷

---

## 总结

Assassyn-CPU是一个设计精良的五级流水线处理器，展现了以下优秀特性：

1. **清晰的模块化**: 每个流水级职责明确，接口清晰
2. **高效的冒险处理**: 前递网络+停顿机制，最小化性能损失
3. **优雅的控制逻辑**: 独热码+累加法，硬件实现友好
4. **完整的RV32I支持**: 40条基础指令全覆盖
5. **可扩展性**: 基于Assassyn框架，易于添加新功能

**性能特点**:
- 理想CPI（无冒险）: 1.0
- Load-Use冒险惩罚: 1周期
- 分支预测失败惩罚: 2周期
- 实际CPI（典型程序）: 1.2-1.4

**学习价值**:
本设计是学习计算机体系结构的优秀案例，展示了：
- 流水线的基本原理
- 冒险检测与解决
- HDL的现代化设计方法
- 从规范到实现的完整流程

---

**参考资料**:
- [RISC-V Specification](https://riscv.org/technical/specifications/)
- [Assassyn HDL Documentation](docs/Assassyn.md)
- [Module Design Documents](docs/Module/)

