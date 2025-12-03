# RV32I WB (WriteBack) 模块设计文档

> **依赖**：Assassyn Framework, `control_signals.py`

## 1. 模块概述

**WriteBack** 是流水线的最后一级，职责如下：接收来自 MEM 阶段的数据，将其写入通用寄存器堆（RegFile）。

## 2. 数据结构定义

WB 阶段使用的控制包是嵌套结构的最内层。

```python
# control_signals.py

wb_ctrl_t = Record(
    # 对于 Store, Branch 等不需要写回的指令，Decoder 保证 rd_addr == 0
    rd_addr = Bits(5)
)
```

## 3. 模块接口定义

### 3.1 类定义与端口 (`__init__`)

WB 模块定义了两个输入端口，分别接收控制流和数据流。

```python
class WriteBack(Module):
    def __init__(self):
        super().__init__(
            ports={
                # 控制通路：包含 rd_addr
                'ctrl': Port(wb_ctrl_t),
                
                # 数据通路：来自 MEM 级的最终结果 (Mux 后的结果)
                'wdata': Port(Bits(32))
            }
        )
        self.name = 'WB'
```

### 3.2 构建函数 (`build`)

`build` 函数参数负责连接物理资源（寄存器堆）。

| 参数名 | 类型 | 描述 |
| :--- | :--- | :--- |
| **reg_file** | `Array` | 全局通用寄存器堆 (32 x 32-bit)。 |

WB 的逻辑非常线性：**取包 -> 判零 -> 写入 -> 反馈**。

```python
@module.combinational
def build(self, reg_file: Array):
    # 1. 获取输入 (Consume)
    # 从 MEM->WB 的 FIFO 中弹出数据
    # 由于采用刚性流水线（NOP注入），这里假定总是能 pop 到数据
    ctrl, wdata = self.pop_all_ports(False)
    
    rd = ctrl.rd_addr

    # 2. 写入逻辑 (Write Logic)
    # 物理含义：生成寄存器堆的 Write Enable 信号
    # 只有当目标寄存器不是 x0 时，才允许写入
    with Condition(rd != 0):
        # 调试日志：打印写回操作
        log("WB: Write x{} <= 0x{:x}", rd, wdata)
        
        # 驱动寄存器堆的 D 端和 WE 端
        reg_file[rd] = wdata

    # 3. 状态反馈 (Feedback to Hazard Unit)
    # 将当前的 rd 返回，供 DataHazardUnit (Downstream) 使用
    return rd
```