# 内存字节/半字指令支持情况

## 指令表覆盖情况
- `instruction_table.py` 明确定义了 `lb`/`lh`/`lbu`/`lhu`（行 54-63）和 `sb`/`sh`/`sw`（行 67-72）的译码入口，其中加载类指令携带 `MemWidth.BYTE/HALF/WORD` 与符号扩展标志。

## Load（B/H）实现情况
- 在 EX 阶段，加载/存储地址由 `rs1 + imm` 的 ALU 加法得到（`execution.py` 第 156 行的 `add_res`），并随控制信号传递到访存处理（同文件第 466-486 行）。
- MEM 阶段读取 32 位原始数据后，根据 `mem_width` 进行对齐与扩展：
  - `half_selected` 依据地址 bit1 选取高/低 16 位（`memory.py` 第 62 行），`byte_selected` 依据地址 bit0 选取高/低 8 位（第 68 行）。
  - `mem_unsigned` 控制符号填充：字节扩展在第 72-76 行，半字扩展在第 79-83 行。
  - `mem_width.select1hot` 在 BYTE/HALF/WORD 间选择最终返回的数据（第 87-91 行）。
- 结论：`lb/lbu`、`lh/lhu` 已实现，包含按地址低位选择字节/半字并做符号/零扩展。

## Store（B/H）实现情况
- 虽然译码表存在 `sb/sh`，但 EX 阶段对存储的处理只在 `is_store = final_mem_ctrl.mem_opcode == MemOp.STORE`（`execution.py` 第 469 行）为真时打开写使能，并通过 `dcache.build(...)` 将 32 位 `rs2` 写入 SRAM（同文件第 481-486 行，`wdata=real_rs2`），未基于 `mem_width` 进行字节/半字掩码。
- 写入时未参考 `mem_width`，也没有字节/半字掩码或对齐切片逻辑，等效于始终执行整字写入。
- 结论：`sb/sh` 尚未真正实现；存储路径目前只有整字写（行为与 `sw` 相同）。

## `lw` 与 `sw` 的当前行为
- `lw`：译码为 `MemWidth.WORD`（`instruction_table.py` 行 58-59）。EX 阶段地址为 `rs1 + imm`，传递到 MEM；MEM 直接返回 32 位原始 SRAM 数据（`memory.py` 第 87-91 行），该路径不涉及符号扩展字段。测试桩 `MockSRAM`（`tests/test_mock.py` 第 25-39 行）对非对齐访问打印警告，反映对齐假设。
- `sw`：译码为 `MemWidth.WORD`（`instruction_table.py` 行 71-72）。EX 阶段在 `mem_opcode == STORE` 时将 32 位 `rs2` 写入目标地址，未做字节掩码处理（`execution.py` 第 469、481-486 行）。因此当前存储路径实际只支持整字写。
