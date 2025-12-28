# 乘法器与除法器计算方法说明

本文基于仓库中的 `multiplier.py`、`divider.py` 与 `naive_divider.py`，按周期梳理各功能单元的运算流程与时序行为。

## WallaceTreeMul（三周期纯 Wallace Tree 乘法器）
- **启动**：`start_multiply` 在 EX 入口锁存 `op1/op2`、符号位与高/低半选择标志，并置 `m1_valid`，表示 EX_M1 将在下个周期工作。
- **周期 1（EX_M1：部分积（partial products）生成）**
  - `cycle_m1` 触发：当 `m1_valid=1`。
  - 对两个 32 位操作数按符号位进行 64 位符号/零扩展（`sign_zero_extend`）。
  - 在硬件含义上生成 32 组部分积：`pp[i] = (A & {32{B[i]}}) << i`； 当前仿真实现直接做 64 位乘法得到等价总和，不逐层展开/压缩部分积（后续阶段只搬运与选择结果）。
  - 将 64 位乘积拆分为 `partial_low`（0~31 位）与 `partial_high`（32~63 位）送入 M2 寄存器，设置 `m2_valid`，清空 `m1_valid`。
- **周期 2（EX_M2：压缩层）**
  - `cycle_m2` 在 `m2_valid=1` 时执行。
  - 硬件对应 Wallace Tree 前几层（32→6~8 行）的 3:2/2:2 压缩； 仿真中不再做压缩，只转发并准备最终高/低 32 位选择。
  - 根据 `result_high` 选择返回高 32 位（MULH*）或低 32 位（MUL），写入 `m3_result`，置 `m3_valid`，清空 `m2_valid`。
- **周期 3（EX_M3：最终压缩与 CPA）**
  - `cycle_m3` 在 `m3_valid=1` 时仅保持结果，不再进行数值计算； 硬件含义为剩余压缩（至 2 行）并通过 CPA 完成 64 位进位传递加法。
  - 结果在本周期末可被 EX/WB 读取，读取后上层调用 `clear_result` 清除 `m3_valid`。
- **时序概览**：周期 N 指令进入 → 周期 N+1：M1 → 周期 N+2：M2 → 周期 N+3：M3 → 周期 N+4：结果对外可读； `is_busy` 在任意阶段有效时阻塞后续 EX。
- **示例（无符号 MUL，op1=0x0000000A，op2=0x0000000C）**
  - 周期 N：`start_multiply` 锁存，`m1_valid=1`。
  - 周期 N+1（M1）：符号/零扩展为 64 位：`op1_ext=0x000000000000000A`，`op2_ext=0x000000000000000C`；直接乘得 64 位结果 `0x0000000000000078`，拆成 `partial_low=0x00000078`、`partial_high=0x00000000`。
  - 周期 N+2（M2）：根据 `result_high=0` 选择 `partial_low` 写入 `m3_result`。
  - 周期 N+3（M3）：保持 `m3_result=0x78`，可被 EX/WB 读取；若 `result_high=1` 则读取 0。
  - 可视化（关键寄存器）：
  
    | 周期 | 阶段 | m1_op1 / m1_op2 | m2_partial_high / m2_partial_low | m3_result |
    | --- | --- | --- | --- | --- |
    | N   | start | 0x0000000A / 0x0000000C | — | — |
    | N+1 | M1 | 0x0000000A / 0x0000000C | high=0x00000000 / low=0x00000078 | — |
    | N+2 | M2 | — | high=0x00000000 / low=0x00000078 | — |
    | N+3 | M3 | — | — | 0x00000078 |

## SRT4Divider（radix-4 恢复算法，约 18 周期）
- **启动**：`start_divide` 锁存被除数/除数、符号与余数选择位，置 `valid_in`、`busy`。
- **周期 1（IDLE → 特判分流）**
  - `tick` 在 `state=IDLE` 且 `valid_in=1` 时检查：
    - `divisor=0` → 进入 `DIV_ERROR`。
    - `divisor=1` → 进入 `DIV_1`。
    - 其他情况：进入 `DIV_PRE`，同时若为有符号除法提取操作数符号、取绝对值并记录 `div_sign`（被除数/除数符号位拼接，用于商符号判定）、`sign_r`（标记当前是否为有符号除法）。
- **周期 2（DIV_PRE：预处理）**
  - 初始化：`quotient=dividend_abs`，`remainder=0`（34 位），`div_cnt=16`（每次 2bit，共 16 次），状态转 `DIV_WORKING`。
- **周期 3~18（DIV_WORKING：迭代 16 次，每次求 2 位商）**
  - 每个周期完成一轮：
    1. `remainder` 左移 2 位并引入当前 `quotient` 的最高 2 位；`quotient` 低位腾空。
    2. 计算 `d, 2d, 3d`（34 位对齐），比较 `remainder` 与这些倍数。
    3. 按优先级选择最大可减倍数，更新 `remainder`，生成本轮商位 `q_bits`（00/01/10/11 分别表示商值 0/1/2/3），合并回 `quotient` 低 2 位。
    4. `div_cnt` 递减；当计数减到 1 时本轮结束后状态置 `DIV_END`（下一周期生效）。
- **周期 19（DIV_END：符号/溢出处理）**
  - 检测 `(-2^31)/(-1)` 溢出：商强制为 `0x80000000`，余数为 0。
  - 正常情况下：若商符号需取反则对 `quotient` 求补；余数符号跟随被除数。根据 `is_rem` 选择输出商或余数。
  - 置 `ready=1`，清 `busy`，状态回 `IDLE`。
- **特殊通路**
  - `DIV_ERROR`：1 周期内输出 RISC-V 规定的除零结果（商全 1，余数=被除数），清 `busy/ready`。
  - `DIV_1`：1 周期内返回商=被除数、余数=0。
- **示例（无符号 DIV，dividend=0x0000002A=42，divisor=0x00000006=6）**
  - 周期 N：`start_divide`，状态在下一周期进入 `DIV_PRE`。
  - 周期 N+1（DIV_PRE）：`quotient=0x2A`，`remainder=0`，`div_cnt=16`。
  - 周期 N+2（第 1 轮）：`remainder` 左移 2 并带入商顶 2 位 `0b10` → `remainder=0b10=2`；`d=6`，`2d=12`，`3d=18`，均大于 2，故 `q_bits=00`，`remainder` 保持 2，工作寄存器 `quotient` 左移 2 位填入 00（工作值变大，用于腾出最低 2 位存放新数字）。
  - 周期 N+3（第 2 轮）：`remainder`=2 左移 2 带入商顶 2 位（此时顶两位为 `0b10`）→ `remainder=0b1010=10`；10≥`d`(6) 但 <`2d`，选 `q_bits=01`，`remainder=10-6=4`，`quotient` 左移 2 位再填入 01。此时工作寄存器最低两位已写入“01”（代表当前迭代的商位），高位继续为后续轮次腾空间。
  - 继续迭代，其余轮次依次在低位写入 2-bit 商数字。虽然中间工作寄存器数值会临时变大，但 16 轮结束后，寄存器串行写入的 32 位正好对应真实商，得到 `quotient=7`、`remainder=0`（42 / 6 = 7）。
  - 可视化（前两轮，显示 remainder/quotient_work/q_bits）：
  
    | 周期 | remainder（低 8 位，hex） | q_bits | quotient 工作寄存器低 8 位（hex） |
    | --- | --- | --- | --- |
    | N+1（预处理后） | 0x00 | —   | 0x2A |
    | N+2（第 1 轮后） | 0x02 | 00  | 0xA8 （左移 2，填 00） |
    | N+3（第 2 轮后） | 0x04 | 01  | 0xA9 （左移 2，填 01） |

## NaiveDivider（逐位恢复除法，约 34 周期）
- **启动与特判**：`start_divide`/`IDLE` 流程与 SRT4 相同，零/一特判分别进入 `DIV_ERROR`、`DIV_1`，正常进入 `DIV_PRE`。
- **周期 2（DIV_PRE）**
  - 预置 `quotient=dividend_abs`，`remainder=0`（33 位），`div_cnt=32`（逐位计算），状态转 `DIV_WORKING`。
- **周期 3~34（DIV_WORKING：32 次，1 位/周期）**
  - 每周期执行：
    1. `remainder` 左移 1 位并带入当前 `quotient` 最高位。
    2. 以符号扩展的 `divisor` 相减得到 `temp_remainder`。
    3. 若结果为负则恢复（加回除数）、当前商位写 0；否则保留差值、商位写 1。商寄存器通过左移 + 低位插入 0/1 更新。
    4. `div_cnt` 递减；减到 1 时本轮后转 `DIV_END`。
- **周期 35（DIV_END）**
  - 同 SRT4：处理 `(-2^31)/(-1)` 溢出，否则依据操作数符号对商/余数做补码反转，并据 `is_rem` 选择输出；置 `ready=1`、清 `busy`、回 `IDLE`。
- **特殊通路**：`DIV_ERROR` 与 `DIV_1` 行为同上，但整体时延较长的正常路径为 1（预处理）+32（迭代）+1（后处理）≈34 周期。
- **示例（无符号 DIV，dividend=0x0000002A=42，divisor=0x00000006=6，展示前 3 个周期）**
  - 周期 N：`start_divide` 后下周期进入 `DIV_PRE`。
  - 周期 N+1（DIV_PRE）：`quotient=0x2A`，`remainder=0`，`div_cnt=32`。
  - 周期 N+2（第 1 轮）：`remainder` 左移带入商 MSB=1 → `remainder=1`；减去 6 得负，恢复为 1，商左移写 0（工作值从 0b101010 变为 0b1010100）。`div_cnt=31`。
  - 周期 N+3（第 2 轮）：`remainder` 左移带入新 MSB=0 → `remainder=2`；减 6 仍负，恢复为 2，商左移写 0（工作值 0b1010100 → 0b10101000）。`div_cnt=30`。
  - 周期 N+4（第 3 轮）：`remainder` 左移带入新 MSB=1 → `remainder=5`；5<6，恢复为 5，商左移写 0（工作值 0b10101000 → 0b101010000）。后续继续 29 轮，始终左移并在 LSB 写入 0/1，32 轮结束后寄存器比特串即为最终商 7（0b000...0111），余数 0。
  - 可视化（前三轮 remainder/quotient 工作值）：
  
    | 周期 | remainder (33b) | quotient 工作值（二进制示意） |
    | --- | --- | --- |
    | N+1（预处理后） | 0b0 | 0b101010 |
    | N+2（第 1 轮后） | 0b1 | 0b1010100 |
    | N+3（第 2 轮后） | 0b10 | 0b10101000 |
    | N+4（第 3 轮后） | 0b101 | 0b101010000 |
