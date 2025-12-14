# print(raw) 输出问题诊断报告

## 问题描述

在 `src/main.py` 第 242-244 行：

```python
raw = utils.run_simulator(binary_path=binary_path)
print(raw)
```

**期望行为**：`print(raw)` 应该输出 CPU 运行过程中的所有日志（包括指令执行、寄存器状态等）。

**实际行为**：只输出了一个包含模拟器二进制文件路径的列表：
```
['/home/ming/PythonProjects/cpu_test/workspace/rv32i_cpu/rv32i_cpu_simulator/target/release/rv32i_cpu_simulator']
```

---

## 问题根源分析

### 1. `utils.run_simulator` 函数的行为

根据代码分析和文档（`docs/Assassyn.md` 第 403-410 行），`utils.run_simulator` 应该：

1. **启动编译好的二进制仿真器**
2. **捕获标准输出（stdout）**，包括硬件侧 `log()` 函数打印的内容
3. **返回一个字符串**，包含所有日志输出

**文档示例**：
```python
# 运行二进制仿真器，raw 包含了所有的 log 输出
raw, _, _ = run_quietly(lambda: utils.run_simulator(simulator_path))
```

注意：文档中的用法是 `utils.run_simulator(simulator_path)`（传入路径字符串），而 `main.py` 中使用的是 `utils.run_simulator(binary_path=binary_path)`（使用关键字参数）。

### 2. 可能的问题原因

#### 原因 A：函数签名不匹配

`utils.run_simulator` 可能有两种不同的调用方式：
- **位置参数**：`run_simulator(path)` → 运行仿真器并返回输出
- **关键字参数**：`run_simulator(binary_path=path)` → 可能只是构造命令行参数并返回路径

**证据**：
- `main.py` 使用 `binary_path=binary_path`
- 返回值是一个包含路径的列表 `['/path/to/simulator']`，看起来像命令行参数列表（如 `subprocess` 的 `args` 参数）

**验证方法**：
```python
# 尝试不同的调用方式
raw1 = utils.run_simulator(binary_path)          # 位置参数
raw2 = utils.run_simulator(binary_path=binary_path)  # 关键字参数
print(type(raw1), raw1)
print(type(raw2), raw2)
```

#### 原因 B：未捕获子进程输出

如果 `utils.run_simulator` 内部使用 `subprocess.run` 或 `subprocess.Popen`，可能存在以下问题：

**问题 1：未设置 `capture_output` 或 `stdout`**
```python
# 错误示例：输出直接打印到终端，不返回
result = subprocess.run([binary_path])
return [binary_path]  # 错误：只返回了路径
```

**正确做法**：
```python
result = subprocess.run([binary_path], capture_output=True, text=True)
return result.stdout  # 返回捕获的标准输出
```

**问题 2：只返回了命令参数而非执行结果**
```python
# 错误示例：构造命令但未执行
cmd = [binary_path]
return cmd  # 错误：返回了命令列表而非输出
```

**问题 3：输出被发送到 stderr 而非 stdout**
```python
# 如果仿真器将日志输出到 stderr
result = subprocess.run([binary_path], capture_output=True, text=True)
return result.stdout  # 错误：stderr 未被捕获
```

**正确做法**：
```python
result = subprocess.run([binary_path], capture_output=True, text=True)
return result.stdout + result.stderr  # 合并两个输出流
```

#### 原因 C：`assassyn.utils` 模块版本不兼容

可能当前环境中安装的 `assassyn` 版本与代码预期的版本不一致：
- 旧版本：`run_simulator` 返回路径列表
- 新版本：`run_simulator` 返回输出字符串

**验证方法**：
```bash
pip3 show assassyn  # 查看版本
python3 -c "import assassyn; print(assassyn.__version__)"
```

---

## 诊断步骤

### 步骤 1：检查 `assassyn.utils` 源码

**方法 1：通过 Python 查看源码位置**
```bash
python3 -c "import assassyn.utils; import inspect; print(inspect.getfile(assassyn.utils))"
```

**方法 2：查看函数签名**
```python
import assassyn.utils
import inspect

print("run_simulator signature:")
print(inspect.signature(assassyn.utils.run_simulator))
print("\nDocstring:")
print(assassyn.utils.run_simulator.__doc__)
```

### 步骤 2：测试不同的调用方式

在 `main.py` 中临时添加调试代码：

```python
# 在第 242 行之前添加
print(f"🔍 Testing run_simulator with different approaches...")
print(f"Binary path: {binary_path}")
print(f"Type: {type(binary_path)}")

# 测试 1：使用关键字参数（当前方式）
raw_kwarg = utils.run_simulator(binary_path=binary_path)
print(f"\n[Test 1] With keyword argument:")
print(f"Type: {type(raw_kwarg)}")
print(f"Content: {raw_kwarg}")

# 测试 2：使用位置参数
try:
    raw_pos = utils.run_simulator(binary_path)
    print(f"\n[Test 2] With positional argument:")
    print(f"Type: {type(raw_pos)}")
    print(f"Content: {raw_pos}")
except Exception as e:
    print(f"\n[Test 2] Failed: {e}")

# 测试 3：检查函数签名
import inspect
print(f"\n[Function Signature]")
print(inspect.signature(utils.run_simulator))
```

### 步骤 3：查看 `tests/common.py` 的用法

`tests/common.py` 第 28 行也使用了 `utils.run_simulator`：
```python
raw = utils.run_simulator(binary_path=binary_path)
```

**检查是否有其他测试文件使用了不同的调用方式**：
```bash
cd /home/runner/work/Assassyn-CPU/Assassyn-CPU
grep -r "run_simulator" tests/ --include="*.py"
```

### 步骤 4：直接运行模拟器二进制文件

绕过 `utils.run_simulator`，直接使用 Python 的 `subprocess` 运行仿真器：

```python
import subprocess

# 在 main.py 第 242 行替换为：
print(f"🏃 Running simulation directly with subprocess...")
result = subprocess.run(
    [binary_path],
    capture_output=True,
    text=True,
    timeout=60  # 防止无限运行
)

print("=== STDOUT ===")
print(result.stdout)
print("\n=== STDERR ===")
print(result.stderr)
print(f"\n=== Return Code: {result.returncode} ===")

# 合并输出（如果需要）
raw = result.stdout + result.stderr
print(raw)
```

---

## 推荐解决方案

### 方案 1：修正 `utils.run_simulator` 调用方式（首选）

**前提**：假设 `utils.run_simulator` 支持位置参数返回输出，关键字参数只返回路径。

**修改 `main.py` 第 242 行**：
```python
# 原代码
raw = utils.run_simulator(binary_path=binary_path)

# 修改为
raw = utils.run_simulator(binary_path)  # 使用位置参数
```

**优点**：
- ✅ 符合文档示例的用法
- ✅ 最小改动
- ✅ 可能是设计意图

**缺点**：
- ❌ 需要确认 `utils.run_simulator` 的实际签名

---

### 方案 2：直接使用 `subprocess` 运行仿真器（次优）

**前提**：如果 `utils.run_simulator` 确实有问题或不可用。

**修改 `main.py` 第 240-244 行**：
```python
import subprocess

# 运行模拟器，捕获输出
print(f"🏃 Running simulation (Direct Output Mode)...")
try:
    result = subprocess.run(
        [binary_path],
        capture_output=True,
        text=True,
        timeout=600,  # 10 分钟超时
        check=True    # 如果返回码非零则抛出异常
    )
    raw = result.stdout
    if result.stderr:
        # 如果 stderr 也有内容，合并输出
        raw += "\n=== STDERR ===\n" + result.stderr
except subprocess.TimeoutExpired:
    print("❌ Simulation timeout after 600 seconds")
    raise
except subprocess.CalledProcessError as e:
    print(f"❌ Simulation failed with return code {e.returncode}")
    print(f"stdout: {e.stdout}")
    print(f"stderr: {e.stderr}")
    raise

print(raw)
print("🔍 Verifying output...")
```

**优点**：
- ✅ 完全控制子进程调用
- ✅ 明确捕获 stdout 和 stderr
- ✅ 添加了超时和错误处理

**缺点**：
- ❌ 绕过了 `assassyn.utils` 的封装（可能丢失额外功能）
- ❌ 违反了"不修改 main.py"的约束（但这是必要的修复）

---

### 方案 3：包装器函数（最灵活）

**前提**：需要保持 `main.py` 逻辑不变，但修复 `utils.run_simulator` 的行为。

**在 `src/` 目录下创建 `utils_wrapper.py`**：
```python
"""
utils_wrapper.py - 包装 assassyn.utils 以修复 run_simulator 的行为
"""
import subprocess
from assassyn import utils as original_utils

def run_simulator(binary_path_or_kwarg=None, binary_path=None):
    """
    修复版的 run_simulator，确保返回仿真器输出而非路径
    
    参数：
        binary_path_or_kwarg: 位置参数（路径字符串）
        binary_path: 关键字参数（路径字符串）
    
    返回：
        str: 仿真器的标准输出和标准错误
    """
    # 处理两种调用方式
    if binary_path is not None:
        path = binary_path
    elif binary_path_or_kwarg is not None:
        path = binary_path_or_kwarg
    else:
        raise ValueError("Must provide binary path as positional or keyword argument")
    
    # 尝试调用原始函数（如果它正常工作）
    try:
        result = original_utils.run_simulator(path)
        # 如果返回的是字符串（正常情况），直接返回
        if isinstance(result, str):
            return result
        # 如果返回的是列表（bug 情况），说明未执行，我们自己执行
        elif isinstance(result, list):
            print(f"⚠️  Warning: run_simulator returned list, falling back to subprocess")
    except Exception as e:
        print(f"⚠️  Warning: run_simulator failed ({e}), falling back to subprocess")
    
    # 回退方案：直接使用 subprocess
    result = subprocess.run(
        [path],
        capture_output=True,
        text=True,
        timeout=600
    )
    return result.stdout + ("\n=== STDERR ===\n" + result.stderr if result.stderr else "")

# 导出其他原始函数
build_simulator = original_utils.build_simulator
```

**修改 `main.py` 第 6 行**：
```python
# 原代码
from assassyn import utils

# 修改为
import utils_wrapper as utils
```

**优点**：
- ✅ 兼容两种调用方式
- ✅ 自动回退到可靠的实现
- ✅ 不影响其他使用 `utils` 的地方

**缺点**：
- ❌ 引入了额外的文件
- ❌ 仍然需要修改 `main.py` 的 import

---

## 验证清单

完成修复后，确认以下行为：

- [ ] `print(raw)` 输出包含 CPU 指令执行日志
- [ ] 输出包含寄存器状态信息
- [ ] 输出包含 `log()` 函数打印的调试信息
- [ ] 程序正常退出（无超时或错误）
- [ ] 输出格式与 `tests/common.py` 中的预期一致

**示例输出**（期望看到类似内容）：
```
Cycle 0: PC=0x00000000, Inst=0xfe010113 (addi sp, sp, -32)
Cycle 1: PC=0x00000004, Inst=0x00812e23 (sw s0, 28(sp))
Cycle 2: PC=0x00000008, Inst=0x02010413 (addi s0, sp, 32)
...
Register x10 (a0) = 0x000013BA (5050 decimal)
Simulation completed in 1234 cycles
```

---

## 后续行动

### 如果方案 1 有效：
1. 确认 `assassyn.utils.run_simulator` 的签名和文档
2. 更新 `docs/Assassyn.md` 说明正确用法
3. 检查其他文件（如 `tests/common.py`）是否也需要修复

### 如果方案 2 有效：
1. 考虑向 `assassyn` 项目报告 bug
2. 在项目中添加注释说明为何绕过 `utils`
3. 监控 `assassyn` 更新，未来可能恢复使用

### 如果方案 3 有效：
1. 将 `utils_wrapper.py` 作为项目的标准实践
2. 文档化包装器的存在和原因
3. 在 CI/CD 中确保包装器被正确使用

---

## 附录 A：调试信息收集脚本

创建 `debug_run_simulator.py` 用于诊断：

```python
#!/usr/bin/env python3
"""
调试脚本：诊断 utils.run_simulator 的行为
"""
import sys
import inspect
from assassyn import utils

def diagnose():
    print("=" * 70)
    print("Diagnosing assassyn.utils.run_simulator")
    print("=" * 70)
    
    # 1. 检查函数签名
    print("\n[1] Function Signature:")
    try:
        sig = inspect.signature(utils.run_simulator)
        print(f"    {sig}")
    except Exception as e:
        print(f"    Error: {e}")
    
    # 2. 检查文档字符串
    print("\n[2] Docstring:")
    doc = utils.run_simulator.__doc__
    if doc:
        for line in doc.split('\n')[:10]:  # 前 10 行
            print(f"    {line}")
    else:
        print("    No docstring available")
    
    # 3. 检查源码位置
    print("\n[3] Source Location:")
    try:
        file_path = inspect.getfile(utils.run_simulator)
        print(f"    {file_path}")
    except Exception as e:
        print(f"    Error: {e}")
    
    # 4. 测试不同的调用方式（使用假路径）
    print("\n[4] Testing Calls (dry run):")
    test_path = "/tmp/fake_simulator"
    
    print("    a) Positional argument:")
    try:
        result = utils.run_simulator(test_path)
        print(f"       Type: {type(result)}")
        print(f"       Value: {result}")
    except Exception as e:
        print(f"       Error: {e}")
    
    print("    b) Keyword argument:")
    try:
        result = utils.run_simulator(binary_path=test_path)
        print(f"       Type: {type(result)}")
        print(f"       Value: {result}")
    except Exception as e:
        print(f"       Error: {e}")
    
    print("\n" + "=" * 70)

if __name__ == "__main__":
    diagnose()
```

**运行方法**：
```bash
python3 debug_run_simulator.py
```

---

## 附录 B：相关文件清单

| 文件                  | 行号      | 相关代码                                           |
|-----------------------|-----------|---------------------------------------------------|
| `src/main.py`         | 242       | `raw = utils.run_simulator(binary_path=binary_path)` |
| `src/main.py`         | 244       | `print(raw)`                                      |
| `tests/common.py`     | 28        | `raw = utils.run_simulator(binary_path=binary_path)` |
| `docs/Assassyn.md`    | 403-410   | 文档示例（使用位置参数）                            |

---

## 总结

**根本问题**：`utils.run_simulator(binary_path=binary_path)` 返回的是模拟器路径列表，而非执行输出。

**推荐解决方案**：
1. **首选**：将 `main.py` 第 242 行改为 `raw = utils.run_simulator(binary_path)`（使用位置参数）
2. **备选**：使用 `subprocess.run` 直接运行仿真器并捕获输出
3. **最灵活**：创建包装器函数兼容两种调用方式

**下一步**：
- 执行诊断步骤 1-4
- 根据诊断结果选择合适的方案
- 测试修复后的输出是否包含 CPU 日志
- 更新文档说明正确用法

---

**生成时间**：2025-12-14  
**诊断对象**：`src/main.py` 第 244 行的 `print(raw)` 输出问题  
**状态**：待验证并实施修复方案
