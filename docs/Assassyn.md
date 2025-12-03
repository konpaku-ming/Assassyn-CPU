以下是我学习 Assassyn 语言的笔记。

---

# Assassyn 核心类体系

## 一、 基础数据类型 (The Wires)
**物理含义**：电路中的连线，其值为 0/1 位向量，对应线上高低电平。

### 1. `Bits(width)`
*   **作用**：无符号位向量，用于不涉及算术运算（加减乘除）的控制信号、操作码或原始数据。如果只关心位向量 `0` 和 `1` 的模式匹配而不用于算术运算时，使用 `Bits`。
*   **代码示例**：
    ```python
    # 定义了一个 7 位宽的常量，二进制值为 0b0110111
    LUI = Bits(7)(0b0110111)

    # 定义了一根 1 位宽的线
    bits1 = Bits(1)
    ```

### 2. `UInt` / `Int` (SInt)
*   **作用**：赋予数据算术含义。`UInt` 为无符号，`Int` 为有符号（补码）。
*   **代码示例** ：
    ```python
    # 算术运算需要类型转换 (main.py)
    # 将原始的 Bits 转换为 Int(32) 以进行有符号加法
    adder_result = (alu_a.bitcast(Int(32)) + alu_b.bitcast(Int(32))).bitcast(Bits(32))
    
    # 有符号右移 (>>)
    sra_signed_result = (a.bitcast(Int(32)) >> alu_b[0:4].bitcast(Int(5))).bitcast(Bits(32))
    ```
    >   注意 `.bitcast()` 的频繁使用，对于不同类型同一运算符代表电路不同，当心意想不到的算术行为。

## 二、 数据包裹与结构 (The Wrappers)
**物理含义**：对连线的逻辑分组，或处理数据有效性的元数据。

### 1. `Record(fields)`
*   **作用**：硬件结构体定义。将一束宽线切分为有名字的字段。
*   **代码示例** ：
    ```python
    # 定义解码器输出接口
    deocder_signals = Record(
      rs1=Bits(5),       # 5位宽
      rs1_valid=Bits(1), # 1位宽
      imm=Bits(32),      # 32位宽
      # ...
    )
    
    # 使用 Record 打包数据 (instructions.py - decode_logic)
    return deocder_signals.bundle(
        rs1=rs1, 
        rs1_valid=rs1_valid, 
        ...
    )
    ```
*   **实战解析**：`Record` 充当了 `Decoder` 和 `Execution` 之间的协议标准。它避免了手动拼接 100 多位宽的总线，防止了位宽对齐错误。

### 2. `Value`
*   **作用**：包含 `{Data, Valid}` 的对象，用于处理可能无效的数据（空白数据）。
*   **代码示例** ：
    ```python
    class FetcherImpl(Downstream):
        # 这里的 ex_valid 是从上游传来的，类型是 Value
        def build(self, ..., ex_valid: Value, ...):
            
            # 使用 .optional() 处理气泡
            # 含义：如果 ex_valid 无效(bubble)，则返回 Bits(1)(0)
            # 否则返回 ex_valid 携带的数据
            fetch_valid[0] = ex_valid.optional(Bits(1)(0)).select(Bits(1)(1), Bits(1)(0))
    ```
    >   在 `FetcherImpl`（下游模块）中，必须处理上游 `Execution` 可能未产生有效信号的情况。`.optional()` 强制设计者定义了“默认行为”。

## 三、 状态存储 (The Storage)
**物理含义**：具有记忆能力的电路单元。

### 1. `RegArray(type, depth)`
*   **作用**：寄存器或寄存器堆，支持时序赋值与时钟域绑定，是实现时序电路的基础。
*   **代码示例** ：
    ```python
    # 1. 程序计数器 PC
    # 深度为 1 的 32位寄存器
    pc_reg = RegArray(Bits(32), 1)
    
    # 2. 通用寄存器堆 RF
    # 深度为 32 的 32位寄存器组
    reg_file = RegArray(Bits(32), 32)
    
    # 3. 写入逻辑
    # 绑定到 self 时钟域，非阻塞赋值（直接写 = 亦可）
    (cnt & self)[0] <= v
    ```

### 2. `SRAM(width, depth)`
*   **作用**：大容量存储器，构造函数中指定一次读取宽度，深度，用于初始化的文件，build 时添加读写接口连接。每一次读写都需要指定读写使能，地址，写入数据，并等待一个周期获得结果——如为了在 MEM 阶段获取 rdata 需要在 EXE 阶段输入地址。
*   **代码示例** ：
    ```python
    # depth_log = 16 -> 深度 2^16 = 64KB
    icache = SRAM(width=32, depth=1<<depth_log, init_file=f"{workspace}/workload.exe")

    # sram.build(we, re, addr, wdata)：输入读使能、写使能、地址
    icache.build(Bits(1)(0), real_fetch, to_fetch[...], Bits(32)(0))
    ```

## 四、 架构单元 (The Architecture)
**物理含义**：电路板上的逻辑分区。

### 1. `Module`
*   **作用**：标准的时序逻辑容器，拥有端口和时钟域。在__init__ 中定义端口，在 build 中引入接口的连接对象（外界信息）并实现逻辑，可以包含状态（RegArray）。
*   **代码示例**:
    ```python
    class Execution(Module):
        def __init__(self):
            # 定义端口，用于握手
            super().__init__(
                ports={
                    'signals': Port(decoder_signals), # 接收复杂结构体
                    'fetch_addr': Port(Bits(32)),     # 接收简单信号
                })
    
        @module.combinational
        def build(self, ...):
            # 消费端口数据
            signals, fetch_addr = self.pop_all_ports(False)
            # ... 逻辑 ...
            return rd, ex_valid, ...
    ```

### 2. `Downstream`
*   **作用**：纯组合逻辑容器，用于封装复杂的无状态逻辑或反馈回路。
*   **代码示例**:
    ```python
    class Onwrite(Downstream):
        # 注意装饰器不同：@downstream.combinational
        @downstream.combinational
        def build(self, reg_onwrite: Array, exec_rd: Value, writeback_rd: Value):
            # 这里的逻辑是纯组合的 XOR 操作
            # 它在一个周期内完成，用于记分牌更新
            reg_onwrite[0] = reg_onwrite[0] ^ ex_bit ^ wb_bit
    ```
*   **实战解析**：`Onwrite` 模块负责检测 RAW 冒险。这是一个纯逻辑计算，必须即时反馈，不能有寄存器延迟，所以它必须是 `Downstream`。

## 五、 接口与控制 (Interface & Control)
**物理含义**：连线规则与控制逻辑。

### 1. `Port` & `async_called`
*   **作用**：定义接口并自动生成带 FIFO 的连接。
*   **代码示例**:
    ```python
    # Decoder.build 中调用
    # 1. async_called 自动连接：寻找 executor 中名为 'signals' 和 'fetch_addr' 的 Port
    # 2. bind FIFO 接口绑定：深度为 2 的 FIFO
    e_call = executor.async_called(signals=signals, fetch_addr=fetch_addr)
    e_call.bind.set_fifo_depth(signals=2, fetch_addr=2)
    ```
*   **实战解析**：这行代码隐式地实例化了级间寄存器，作为 `Decoder` 和 `Execution` 之间的桥梁。

### 2. `Condition`
*   **作用**：硬件使能控制（Mux / Write Enable）。
*   **代码示例**:
    ```python
    # 分支逻辑
    with Condition(signals.is_branch):
        # 只有在是分支指令时，才计算跳转目标
        # 硬件上：exec_br_dest 的输入端接了一个 Mux
        exec_br_dest[0] = condition[0:0].select(result, pc0)
    ```
*   **实战解析**：`Condition` 控制了副作用发生的范围。如果没有它，`exec_br_dest` 可能会在非分支指令时被错误更新。

以上内容概括了 `Mycpu` 项目中使用的所有 Assassyn 关键对象。

# Assassyn 特殊函数

这些函数独立于 Python 语法，专用于 **操作Assassyn对象**。

**物理含义**：这些函数不产生复杂的控制流或模块实例，它们直接生成 **组合逻辑门 (Gates)** 和 **连线 (Wiring)**。

## 一、 类型转换与解释 (Casting)

在硬件中，一束线就是一束线（0/1），如何解释它（是整数？是地址？是有符号数？）取决于你如何看待它。

### 1. `.bitcast(target_type)`
*   **作用**：重解释与 Assassyn 类型转换。
*   **物理含义**：不生成任何逻辑门，只是告诉编译器“换个方式看这束线”。
*   **示例**：
    ```python
    # 将 32位 原始线 转换为 有符号整数 以进行算术右移
    raw_bits = Bits(32)(0xFFFF0000)
    signed_val = raw_bits.bitcast(SInt(32))
    result = signed_val >> 1
    ```

## 二、 位操作与拼接 (Bit Manipulation)

对导线进行物理上的拆分和重组。

### 1. `signal[high:low]`
*   **作用**：位截取 (Bit Slicing)。
    > Assassyn 使用 **[高位:低位]** 的闭区间格式（类似 Verilog），与 Python 原生的 `[start:end]`（左闭右开）不同。
*   **物理含义**：从总线中引出部分导线。
*   **示例**：
    ```python
    # 提取低 8 位
    byte = word[7:0] 
    # 提取第 31 位 (符号位)
    sign = word[31:31]
    ```

### 2. `concat(a, b, ...)` 或 `a.concat(b)`
*   **作用**：位拼接 (Concatenation)。
*   **物理含义**：将多束导线并排捆在一起。高位在前，低位在后。
*   **示例**：
    ```python
    # 将 8位 数据扩展为 32位 (高位补0)
    zeros = Bits(24)(0)
    data = Bits(8)(0xFF)
    word = zeros.concat(data) # 或者 concat(zeros, data)
    ```

## 三、 多路选择与逻辑 (Multiplexing)

这是组合逻辑的核心，类似于 `if-else`。

### 1. `cond.select(true_val, false_val)`
*   **作用**：二路选择器 (2-to-1 Mux)，根据 `cond` 的值选择 `true_val` 或 `false_val`。
*   **物理含义**：生成一个 Mux 电路。
*   **示例**：
    ```python
    # 绝对值计算
    is_neg = val < 0
    abs_val = is_neg.select(-val, val)
    ```

### 2. `signal.select1hot(*options)`
*   **作用**：独热码选择器 (One-Hot Mux)，其中 `signal` 为只有一位为 1，余下位为 0 的位向量，其位宽等于 `options` 的数量。根据 `signal` 的值选择 `options` 中对应的值。
*   **物理含义**：生成一组 `AND-OR` 逻辑树。
*   **示例**：
    ```python
    # ALU 结果选择
    # alu_op 是独热码 (0001, 0010, 0100...)
    result = alu_op.select1hot(res_add, res_sub, res_and, res_or)
    ```

## 四、 赋值与状态更新 (Assignment)

### 6. `reg[index] <= value`
*   **作用**：**时序逻辑非阻塞赋值**。
*   **物理含义**：
    *   在当前时钟上升沿，将 `value` 采样。
    *   在生成的 Verilog 中对应 `always @(posedge clk) reg <= value;`。
*   **限制**：只能对 `RegArray` 或 `SRAM` 的端口使用。不能对 `Bits`（线）使用（线是自动连接的）。
*   **示例**：
    ```python
    (cnt & self)[0] <= cnt[0] + 1
    ```

# Assassyn 时序与通信模型：基于 FIFO 的延迟不敏感设计

## 1. 顶层抽象：延迟不敏感 (Latency-Insensitive)

在传统的硬件设计（如 Verilog）中，模块间的通信通常是**严格同步**的：模块 A 在 Cycle $T$ 发出数据，模块 B 必须在 Cycle $T+1$ 接收。这种强耦合导致了复杂的全局时序对齐和流水线气泡管理问题。

Assassyn 引入了一种更高级的抽象：**基于 FIFO 的弹性流水线 (Elastic Pipelining)**。

*   **核心理念**：**生产者（Producer）**和**消费者（Consumer）**彼此不需要知道对方的时序特性。它们之间通过一个**自动生成的 FIFO 缓冲区**隔离。
*   **通信协议**：基于 **Valid/Ready 握手协议**。
    *   上游有数据 -> `Valid = 1`。
    *   下游有空位 -> `Ready = 1`。
    *   只有当两者同时为 1 时，数据才传输。
*   **物理映射**：这个 FIFO 实际上就是**级间流水线寄存器**。FIFO 的深度决定了流水线级的深度。

但可惜的是，在 MyCPU 中所有的 FIFO **深度均为1**且输入信息与否完全由上游包裹一个布尔值**flag**决定，即我们只使用最基本的刚性级间寄存器（为了更好的把握电信号的流动）。

## 2. 电路结构衔接：构建静态通道

在代码构建阶段（Elaboration），我们需要建立模块之间的物理连接。这一过程涉及 `__init__` (定义)、`build`参数(感知)、`async_called` (连接) 和 `bind` (配置)。

### 2.1 接口定义：`Port`
在 Module 的 `__init__` 中声明“该级流水线接收什么样的数据”，相当于在芯片上凿出物理插孔。

```python
class Execution(Module):
    def __init__(self):
        super().__init__(
            ports={
                # 定义一个名为 'signals' 的输入端口
                # 数据类型为复杂的 Record 结构
                'signals': Port(decorder_signals), 
                
                # 定义一个名为 'fetch_addr' 的输入端口
                # 数据类型为 32位 宽线
                'fetch_addr': Port(Bits(32)),
            })
```

### 2.2 感知：`build` 参数

在 `build` 方法中，模块通过参数接收外部传入的连接对象。一般将会传入消费产生数据的流水线下游模块实例 x ，之后 x 使用 `async_called` 进行连接。

### 2.2 连接与实例化：`async_called`
这是 Assassyn 的**自动布线机**。当生产者调用此函数时，它完成三件事：
1.  **查找**：根据参数名（如 `signals`）在消费者中寻找对应的 `Port`。
2.  **生成**：在两者之间实例化一个硬件 FIFO 模块。
3.  **连线**：连接 `Producer -> FIFO -> Consumer` 的 Valid/Ready/Data 信号。

```python
# 在 Decoder (生产者) 中
# executor 是消费者模块的实例
e_call = executor.async_called(signals=signals, fetch_addr=fetch_addr)
```

### 2.3 属性配置：`bind`
返回的 `e_call` 对象代表了这次连接（Call Site）。我们可以通过它来配置中间 FIFO 的属性。

```python
# 设置两个级间寄存器 FIFO 深度为 2
# 物理含义：在 Decoder 和 Execution 之间插入两级流水线寄存器
e_call.bind.set_fifo_depth(signals=2, fetch_addr=2)
```

## 3. 数据协议传输：运行时的动态握手

电路连好后，数据如何在时钟驱动下流动？这依赖于消费者端的三个核心操作：`push` (隐含), `peek`, `pop`。

### 3.1 推送 (Push): `async_called`
上游调用 `async_called` 时，实际上是在驱动 FIFO 的写端口。
*   **行为**：将数据放入 FIFO 入口，并拉高写使能（Valid）。
*   **反压**：如果 FIFO 满了，Assassyn 自动生成的逻辑会拉低上游模块的 `Ready`，导致上游模块 **Stall（暂停）**。

### 3.2 偷看 (Peek): `peek()`
这是实现复杂流水线控制（如处理 RAW 冒险）的关键。
*   **行为**：读取 FIFO 队头的数据，但 **不消耗** 它。
*   **信号**：直接读取 `FIFO.dout`，但不驱动 `FIFO.read_en`。
*   **作用**：允许消费者在决定是否处理该数据前，先检查数据的依赖关系。

### 3.3 消费 (Pop): `pop_all_ports`
这是数据传输的终点。
*   **行为**：读取数据，并 **移除** FIFO 队头元素。
*   **信号**：驱动 `FIFO.read_en` (Ready) 拉高。
*   **模式**：
    *   **`pop_all_ports(True)` (Blocking)**: 如果 FIFO 为空，消费者模块 Stall，不执行后续逻辑。
    *   **`pop_all_ports(False)` (Non-blocking)**: 无论 FIFO 是否为空都返回。返回的是 `Value` 对象（需用 `.optional()` 处理无效数据）。
  
### 3.4 等待条件：`wait_until(cond)`
这是暂停流水线，注入气泡的方式。
*   **行为**：在 `wait_until(cond)` 之后，对应作用域内的所有副作用操作（如寄存器写入、FIFO 消费）都会被 `cond` 条件控制。
*   **信号**：
    *   如果 `cond=0`，所有副作用操作被屏蔽，如pop_all_ports()停止。
    *   如果 `cond=1`，正常执行副作用操作。
*   **模式及作用**：实现该级流水线暂停，等待特定条件满足后继续执行，由于流水线之间存在**反压（Back-pressure）**机制，上游模块会自动暂停，形成气泡。

# Assassyn 电路实例化与测试

`Assassyn` 将**电路设计**（Module编写）与**工程流**（测试、实例化、仿真）进行了严格分离，在 Assassyn 中进行电路的实例化与测试主要包含以下四个步骤：

### 1. 系统构建与实例化 (System Instantiation)

这是将 Python 类定义转化为可被编译器识别的硬件系统图（Graph）的过程。核心工具是 **`SysBuilder`**。

*   **上下文管理**：使用 `SysBuilder` 作为上下文管理器（`with` 语句）。
*   **注册机制**：在 `with sys:` 代码块内部实例化的所有 `Module` 对象，会自动注册到这个 `sys` 系统名下。
*   **顶层入口**：通常需要实例化一个顶层模块（如教程中的 `Driver`）并调用其 `build()` 方法来触发布线逻辑。`Driver` 模块负责进行电路复位、部分 SRAM 偏移值初始化以及生成测试激励。

**代码映射：**
```python
# 创建一个名为 'driver' 的系统环境
sys = SysBuilder('driver') 
with sys:
    # 实例化顶层模块（测试激励发生器）
    driver = Driver()
    # 执行构建，生成内部连线
    driver.build()
```

### 2. 仿真器生成 (Elaboration / Compilation)

这是将 Python 描述的硬件图转换为可执行的二进制文件或 Verilog 代码的过程。核心函数是 **`elaborate`**。

*   **输入**：上一步构建好的 `sys` 对象。
*   **后端选择**：可以通过参数（如 `verilog=True`）指示是否生成 Verilog 代码以便使用 Verilator 进行仿真。
*   **输出**：返回生成的仿真器可执行文件的路径（`simulator_path`）。

**代码映射：**
```python
# 将 Python 对象 sys 编译为二进制仿真器
# run_quietly 用于屏蔽编译过程中的 Rust/C++ 编译器输出
(simulator_path, verilator_path), _, _ = run_quietly(
    lambda: elaborate(sys, verilog=utils.has_verilator())
)
```

### 3. 仿真运行与交互 (Execution & Interaction)

这一步是实际运行电路，并获取运行时的状态数据。Assassyn 提供了**硬件侧**和**软件侧**两种交互手段。

#### A. 硬件侧：内嵌的仿真原语 (In-Circuit Primitives)
在编写 `Module` 时，可以嵌入专门用于仿真的指令，这些指令不影响电路逻辑，只服务于测试：
*   **`log(fmt, args)`**：相当于 Verilog 的 `$display`，用于在仿真运行时向标准输出打印信号值。这是后续验证的基础。
*   **`finish()`**：用于在满足特定条件时（如测试完成或出错）主动终止仿真。
*   **`assume/assert`**：用于形式化验证或运行时断言。

#### B. 软件侧：仿真器调用
使用 **`utils.run_simulator`** 启动编译好的二进制文件。
*   **捕获输出**：仿真器运行后的标准输出（stdout），包括硬件侧 `log()` 打印的内容，会被捕获并作为一个长字符串返回。

**代码映射：**
```python
# 运行二进制仿真器，raw 包含了所有的 log 输出
raw, _, _ = run_quietly(lambda: utils.run_simulator(simulator_path))
```

### 4. 结果验证 (Verification)

这是纯 Python 的后处理步骤。Assassyn 的测试哲学倾向于 **“日志解析流” (Log Parsing)**。

*   **机制**：编写 Python 函数（如 `check`）来解析仿真器返回的字符串数据 (`raw`)。
*   **逻辑**：
    1.  按行分割日志。
    2.  提取关键字（如 `cnt:`）。
    3.  将提取的数值与 Python 计算的预期值（Expected Value）进行比对。
*   **断言**：使用 Python 的 `assert` 语句，如果比对失败则抛出异常，标记测试失败。

**代码映射：**
```python
def check(raw):
    expected = 0
    for line in raw.split('\n'):
        if 'cnt:' in line:
            # 解析 log 输出
            val = int(line.split()[-1])
            # 验证正确性
            assert val == expected
            expected += 1
```

---

### 总结

在 Assassyn 中，建立一个测试环境的流程如下：

1.  **SysBuilder**：把模块“装箱”。
2.  **Elaborate**：把箱子“编译”成机器码。
3.  **Run Simulator**：运行机器码，利用硬件内的 `log()` 吐出数据。
4.  **Check Function**：用 Python 脚本分析吐出的数据，判断 Pass/Fail。