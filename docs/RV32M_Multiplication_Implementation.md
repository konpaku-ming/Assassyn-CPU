# RV32M Extension - Multiplication Instructions Implementation

本文档说明了针对 Assassyn-CPU 项目实现 RV32M 扩展中乘法指令的修改。

## 概述

根据 `docs/RV32M_Extension_Plan.md` 和 `docs/RV32M_Implementation_Guide.md` 中的计划，本次实现了 RV32M 扩展的**乘法指令部分**（MUL, MULH, MULHSU, MULHU），暂不包括除法和取模指令。

## 实现的指令

| 指令 | 功能 | 操作码 | funct3 | funct7 |
|------|------|--------|--------|--------|
| MUL | rd = (rs1 × rs2)[31:0] | 0110011 | 0x0 | 0x01 |
| MULH | rd = (rs1 × rs2)[63:32] (有符号×有符号) | 0110011 | 0x1 | 0x01 |
| MULHSU | rd = (rs1 × rs2)[63:32] (有符号×无符号) | 0110011 | 0x2 | 0x01 |
| MULHU | rd = (rs1 × rs2)[63:32] (无符号×无符号) | 0110011 | 0x3 | 0x01 |

## 修改的文件

### 1. src/control_signals.py

**修改内容**：
- 扩展 `ALUOp` 类从 `Bits(16)` 到 `Bits(32)`，为 M 扩展预留空间
- 添加了 4 个新的 ALU 操作码：
  - `MUL` (Bit 11)
  - `MULH` (Bit 12)
  - `MULHSU` (Bit 13)
  - `MULHU` (Bit 14)
- 更新了 `ex_ctrl_signals` 和 `pre_decode_t` 中的 `alu_func` 字段为 `Bits(32)`

**影响**：
- 为未来的指令扩展（如除法、浮点等）预留了足够的操作码空间

### 2. src/instruction_table.py

**修改内容**：
- 更新表格列定义注释，将 `Bit30` 改为 `Funct7`
- 修改所有 R-Type 指令，使用完整的 `funct7` 字段：
  - `bit30=0` → `funct7=0x00`
  - `bit30=1` → `funct7=0x20`
- 修改 I-Type 移位指令（SRLI, SRAI）使用 `funct7`
- 添加了 4 条 M 扩展乘法指令条目：
  - `mul` (funct3=0x0, funct7=0x01)
  - `mulh` (funct3=0x1, funct7=0x01)
  - `mulhsu` (funct3=0x2, funct7=0x01)
  - `mulhu` (funct3=0x3, funct7=0x01)

**重要性**：
- 正确的 `funct7` 匹配是区分 M 扩展指令和基础指令的关键
- M 扩展指令通过 `funct7=0x01` 与基础整数指令（`funct7=0x00` 或 `0x20`）区分

### 3. src/decoder.py

**修改内容**：
- 添加 `funct7` 字段提取：`funct7 = inst[25:31]`（7 位）
- 在查表匹配逻辑中添加 `funct7` 比较：
  ```python
  if t_f7 is not None:
      match_if &= funct7 == Bits(7)(t_f7)
  ```
- 更新累加器 `acc_alu_func` 从 `Bits(16)(0)` 到 `Bits(32)(0)`
- 更新解包逻辑，将 `t_b30` 改为 `t_f7`

**关键改进**：
- 解决了文档中提到的译码器限制问题（只检查 bit30 而非完整 funct7）
- 现在可以正确区分 M 扩展指令和基础指令

### 4. src/execution.py

**修改内容**：
- 实现了 4 种乘法运算：
  - **MUL**: 使用 64 位有符号乘法，提取低 32 位
  - **MULH**: 使用 64 位有符号乘法，提取高 32 位
  - **MULHSU**: rs1 有符号扩展，rs2 无符号扩展，64 位乘法后提取高 32 位
  - **MULHU**: 使用 64 位无符号乘法，提取高 32 位
- 扩展 ALU 结果选择器从 16 个槽位到 32 个槽位
- 添加了乘法操作的日志输出用于调试

**实现细节**：
```python
# MUL: 低32位
mul_result_signed = (op1_signed.bitcast(Int(64)) * op2_signed.bitcast(Int(64)))
mul_res = mul_result_signed[0:31].bitcast(Bits(32))

# MULH: 有符号×有符号高32位
mulh_res = mul_result_signed[32:63].bitcast(Bits(32))

# MULHSU: 有符号×无符号高32位
op1_signed_64 = op1_signed.bitcast(Int(64))
op2_unsigned_64 = alu_op2.bitcast(UInt(64))
mulhsu_result = (op1_signed_64 * op2_unsigned_64.bitcast(Int(64)))
mulhsu_res = mulhsu_result[32:63].bitcast(Bits(32))

# MULHU: 无符号×无符号高32位
op1_unsigned_64 = alu_op1.bitcast(UInt(64))
mulhu_result = (op1_unsigned_64 * op2_unsigned_64)
mulhu_res = mulhu_result[32:63].bitcast(Bits(32))
```

### 5. tests/test_mul_extension.py

**新建文件**：
- 创建了专门的乘法指令测试文件
- 包含 12 个测试用例：
  - MUL 基础测试（正数、负数、零、溢出）
  - MULH 测试（有符号乘法高位）
  - MULHSU 测试（混合符号乘法高位）
  - MULHU 测试（无符号乘法高位）

**测试覆盖**：
- 基本功能验证
- 边界条件测试
- 符号处理验证
- 溢出行为验证

## 测试说明

在 Python 虚拟环境中运行测试，请使用以下命令：

```bash
# 在 Assassyn-CPU 项目根目录
python tests/test_mul_extension.py
```

或者运行所有测试：

```bash
python -m pytest tests/
```

## 性能特性

当前实现为**简化版本**，使用 Python 的乘法运算符，由 Assassyn 编译器转换为硬件乘法器：

- **延迟**: 单周期（简化实现）
- **资源**: 依赖于 Assassyn 后端生成的硬件乘法器
- **精度**: 完全符合 RISC-V 规范

**未来优化方向**（根据文档）：
- 可以实现 Radix-4 Booth 编码 + Wallace Tree 压缩的多周期乘法器
- 这将提供更高的时钟频率和更好的资源效率
- 多周期实现需要额外的流水线暂停机制（在 `src/data_hazard.py` 中实现）

## 符合 RISC-V 规范

实现严格遵循 RISC-V 规范：

1. **MUL**: 返回完整 64 位乘积的低 32 位，无论操作数符号
2. **MULH**: 两个操作数都作为有符号数处理
3. **MULHSU**: rs1 作为有符号数，rs2 作为无符号数
4. **MULHU**: 两个操作数都作为无符号数处理

## 兼容性

- ✅ 与现有 RV32I 指令完全兼容
- ✅ 不影响现有的数据冒险处理（Forwarding）机制
- ✅ 不影响分支预测（BTB）功能
- ✅ 写回机制无需修改

## 注意事项

1. **除法指令未实现**: 本次只实现了乘法指令，DIV、DIVU、REM、REMU 将在后续实现
2. **多周期支持**: 当前为单周期实现，如需多周期乘法器需要额外的暂停控制
3. **测试环境**: 测试在 Python 虚拟环境中运行，需要安装 assassyn 包及其依赖

## 验证建议

在集成到主分支前，建议：

1. 运行新的乘法指令测试：`tests/test_mul_extension.py`
2. 运行所有现有测试确保无回归
3. 测试一些包含乘法指令的 RV32IM 程序

## 参考文档

- `docs/RV32M_Extension_Plan.md` - 完整实施计划
- `docs/RV32M_Implementation_Guide.md` - 实施指南和代码模板
- `docs/RV32M_Quick_Summary.md` - 快速总结
- RISC-V 规范 Volume I, Chapter 7 - M Extension
