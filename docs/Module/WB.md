# RV32I WB (WriteBack) 模块设计文档

> **依赖**：Assassyn Framework, `control_signals.py`

## 1. 模块概述

**WriteBack** 是流水线的最后一级，职责如下：
1. 接收来自 MEM 阶段的数据
2. 将其写入通用寄存器堆（RegFile）
3. 更新 WB Bypass 寄存器，供 Hazard Unit 使用
4. 检测停机指令并终止仿真

## 2. 数据结构定义

WB 阶段使用的控制包是嵌套结构的最内层：

```python
# control_signals.py

wb_ctrl_signals = Record(
    rd_addr=Bits(5),    # 目标寄存器索引，如果是0拒绝写入
    halt_if=Bits(1),    # 是否触发仿真终止 (ECALL/EBREAK/sb x0, (-1)x0)
)
```

## 3. 模块接口定义

### 3.1 类定义与端口

```python
class WriteBack(Module):
    def __init__(self):
        super().__init__(
            ports={
                # 控制通路：包含 rd_addr 和 halt_if
                "ctrl": Port(wb_ctrl_signals),
                # 数据通路：来自 MEM 级的最终结果
                "wdata": Port(Bits(32)),
            }
        )
        self.name = "WB"
```

### 3.2 构建函数

| 参数名 | 类型 | 描述 |
| :--- | :--- | :--- |
| **reg_file** | `Array` | 全局通用寄存器堆 (32 x 32-bit) |
| **wb_bypass_reg** | `Array` | WB Bypass 寄存器，供 Hazard Unit 使用 |

## 4. 内部实现

WB 的逻辑非常线性：**取包 -> 判零 -> 写入 -> 停机检测 -> 反馈**。

```python
@module.combinational
def build(self, reg_file: Array, wb_bypass_reg: Array):
    
    # 1. 获取输入
    wb_ctrl, wdata = self.pop_all_ports(False)
    rd = wb_ctrl.rd_addr
    halt_if = wb_ctrl.halt_if

    # 2. 写入逻辑 (Write Logic)
    # 当目标寄存器不是 x0 时写入指定寄存器
    with Condition(rd != Bits(5)(0)):
        debug_log("WB: x{} <= 0x{:x}", rd, wdata)
        
        # 驱动寄存器堆
        reg_file[rd] = wdata
        # 更新 WB Bypass 寄存器
        wb_bypass_reg[0] = wdata

    # 3. 仿真终止检测 (Halt Detection)
    with Condition(halt_if == Bits(1)(1)):
        debug_log("WB: HALT!")
        log_register_snapshot(reg_file)
        finish()

    # 4. 引脚暴露 (供 HazardUnit 使用)
    return rd
```

## 5. 停机条件

WB 阶段检测以下指令并终止仿真：

| 指令 | 编码 | 描述 |
| :--- | :--- | :--- |
| `ecall` | `0x00000073` | 环境调用 |
| `ebreak` | `0x00100073` | 断点 |
| `sb x0, -1(x0)` | `0xFE000FA3` | 特殊停机指令 |

停机时会输出所有寄存器的快照，便于调试和验证。

## 6. x0 寄存器保护

RISC-V 规范要求 x0 寄存器始终为 0。WB 阶段通过以下机制保护 x0：

1. **ID 阶段预处理**：将不需要写回的指令的 `rd_addr` 强制设为 0
2. **WB 阶段检查**：当 `rd == 0` 时跳过寄存器写入

这样确保即使有非法指令尝试写入 x0，也不会改变其值。
