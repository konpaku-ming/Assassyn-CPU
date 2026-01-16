# FAQ: Assassyn 组件间通信机制

## 问题

> 在 Assassyn 中，一个组件向另一个组件传递信息，是不是只能用寄存器，然后会造成一个周期的延时？

## 答案

**不是的。** Assassyn 提供了两种组件间通信机制，分别适用于不同场景：

### 1. 时序传递（通过 FIFO/寄存器）—— 有一个周期延时

当使用 `Module` 和 `async_called()` 进行跨模块通信时，数据会经过 FIFO 缓冲区（本质上是流水线级间寄存器），这确实会造成 **一个时钟周期的延时**。

**示例代码**：
```python
# 在 Decoder 中向 Executor 发送数据
call = executor.async_called(ctrl=ctrl_data, pc=pc_value)
call.bind.set_fifo_depth(ctrl=1, pc=1)  # FIFO 深度为 1
```

**特点**：
- 数据在当前周期被"推入"FIFO
- 下游模块在下一周期通过 `pop_all_ports()` 读取
- 这是流水线级间的标准通信方式
- 物理实现上对应级间寄存器

### 2. 组合逻辑传递（通过 Downstream 和返回值）—— 无延时

当使用 `Downstream` 模块或直接传递 `build()` 函数的返回值时，数据传递是 **纯组合逻辑**，在 **同一个时钟周期内** 完成，**没有延时**。

**示例代码**：

#### 方式 A：使用 Downstream 组合逻辑模块
```python
class DataHazardUnit(Downstream):
    """纯组合逻辑模块 - 无状态、无延时"""
    
    @downstream.combinational
    def build(self, rs1_idx: Value, ex_rd: Value, ...):
        # 冒险检测逻辑 - 在同一周期内完成
        stall_if = (rs1_idx == ex_rd) & ex_is_load
        return rs1_sel, rs2_sel, stall_if  # 立即可用
```

#### 方式 B：通过 build() 返回值传递
```python
# 在 main.py 中的数据流
class Decoder(Module):
    def build(self, ...):
        # ... 译码逻辑 ...
        return pre, rs1, rs2  # 返回值在同一周期立即可用

# 调用方直接使用返回值
pre, rs1, rs2 = decoder.build(icache_dout, reg_file)

# DataHazardUnit 在同一周期内使用这些值
rs1_sel, rs2_sel, stall_if = hazard_unit.build(
    rs1_idx=rs1,  # 直接使用，无延时
    rs2_idx=rs2,
    ...
)
```

### 对比总结

| 通信方式 | 实现机制 | 延时 | 适用场景 |
|---------|---------|------|---------|
| `async_called()` + FIFO | 时序逻辑（寄存器） | 1 个周期 | 流水线级间通信 |
| `Downstream` + 返回值 | 组合逻辑（直接连线） | 0 个周期 | 同级反馈、冒险检测 |

### 本项目中的实际应用

在本 RV32IM CPU 项目中，两种机制都有使用：

1. **时序传递**（有延时）：
   - `Fetcher` → `Decoder`：通过 `async_called()` 传递 PC 和指令
   - `Decoder` → `Execution`：通过 `async_called()` 传递控制信号和数据
   - `Execution` → `Memory`：流水线级间通信
   - `Memory` → `WriteBack`：流水线级间通信

2. **组合逻辑传递**（无延时）：
   - `Decoder.build()` 返回 `rs1`, `rs2` → `DataHazardUnit.build()` 使用
   - `DataHazardUnit.build()` 返回 `stall_if` → `FetcherImpl.build()` 使用
   - `Execution.build()` 返回 `ex_rd`, `ex_is_load` → `DataHazardUnit` 使用
   - 所有 `Downstream` 模块（如 `FetcherImpl`, `DecoderImpl`, `DataHazardUnit`）内部的逻辑

### 设计建议

- **需要流水线隔离时**：使用 `Module` + `async_called()`，接受一个周期延时
- **需要即时反馈时**：使用 `Downstream` + 返回值，实现同周期响应
- **冒险检测、旁路选择等**：必须使用组合逻辑，否则无法及时响应

### 参考文档

- [Assassyn 语言完整说明书](./Assassyn_语言完整说明书.md) - 第 5 节"架构单元"
- [Assassyn 笔记](./Assassyn.md) - "Assassyn 时序与通信模型"部分
