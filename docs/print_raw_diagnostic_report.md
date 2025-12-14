# main.py print(raw) 诊断报告

## 执行摘要

本报告分析了 `src/main.py` 第 244 行 `print(raw)` 语句的异常行为：**预期输出应为 CPU 运行过程中的完整日志，但实际只输出了模拟器可执行文件路径的列表**。

---

## 1. 问题描述

### 1.1 预期行为

根据 Assassyn 框架的文档（`docs/Assassyn.md`）和代码注释，`utils.run_simulator()` 应当：

1. 启动编译好的 CPU 模拟器二进制文件
2. 捕获模拟器的标准输出（stdout）
3. 返回包含所有 `log()` 语句输出的字符串

**预期的 `print(raw)` 输出示例**：
```
Cycle 0: PC = 0x00000000
Cycle 1: PC = 0x00000004
Register x10 (a0) = 0x00000064
...
Cycle 1000: PC = 0x80000050
Register x10 (a0) = 0x000013BA (5050)
Program halted successfully.
```

### 1.2 实际行为

**实际的 `print(raw)` 输出**：
```python
['/home/ming/PythonProjects/cpu_test/workspace/rv32i_cpu/rv32i_cpu_simulator/target/release/rv32i_cpu_simulator']
```

这是一个 **Python 列表**，包含单个元素：模拟器二进制文件的完整路径。

---

## 2. 根本原因分析

### 2.1 症状推断

输出 `['/path/to/simulator']` 强烈暗示以下情况之一：

#### 情况 A：`run_simulator` 返回的是命令列表而非输出
```python
# 错误的实现示例
def run_simulator(binary_path):
    cmd = [binary_path]  # 或者 [binary_path, '--some-arg']
    # 忘记捕获 stdout
    subprocess.run(cmd)
    return cmd  # 错误！返回的是命令列表，不是输出
```

#### 情况 B：`run_simulator` 未捕获 stdout
```python
# 不完整的实现示例
def run_simulator(binary_path):
    cmd = [binary_path]
    # 模拟器直接输出到终端，未被捕获
    subprocess.run(cmd)  # 缺少 capture_output=True 或 stdout=PIPE
    return cmd  # 或其他非字符串返回值
```

#### 情况 C：`run_simulator` 捕获了输出但未正确返回
```python
# 返回值错误的实现示例
def run_simulator(binary_path):
    cmd = [binary_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    # 返回了 result.args 而非 result.stdout
    return result.args  # 错误！应该返回 result.stdout
```

### 2.2 Assassyn 框架预期接口

根据 `docs/Assassyn.md` 中的示例代码：

```python
# 正确的用法（文档第 407 行）
raw, _, _ = run_quietly(lambda: utils.run_simulator(simulator_path))

def check(raw):
    expected = 0
    for line in raw.split('\n'):  # raw 应该是字符串，可以用 .split() 分割
        if 'cnt:' in line:
            val = int(line.split()[-1])
            assert val == expected
            expected += 1
```

**关键观察**：
- `raw` 被当作 **字符串** 使用（调用 `.split('\n')`）
- `raw` 应包含模拟器的 **文本日志输出**
- 后续代码通过 **字符串解析** 提取关键信息进行验证

### 2.3 `assassyn.utils` 模块的实际实现（推测）

由于 `assassyn` 包未安装或未在代码库中，无法直接检查源码。但基于症状，可能的实现问题：

1. **模块版本不匹配**：
   - 旧版本的 `utils.run_simulator` 可能返回命令参数
   - 新版本可能改变了接口但 `main.py` 未更新

2. **接口变更未文档化**：
   - `run_simulator` 的返回值定义可能与文档不一致
   - 可能需要额外参数（如 `capture_output=True`）才能捕获日志

3. **日志输出位置错误**：
   - 模拟器可能将日志写入 **stderr** 而非 **stdout**
   - 模拟器可能将日志写入 **文件**（如 `simulator.log`）
   - 日志可能被 `run_quietly()` 包装器抑制

---

## 3. 复现步骤

### 3.1 最小复现环境

1. **文件准备**：
   ```bash
   cd /home/runner/work/Assassyn-CPU/Assassyn-CPU
   # 确保 workloads 目录存在且包含测试文件
   ls -l workloads/my0to100.exe workloads/my0to100.data
   ```

2. **运行 main.py**：
   ```bash
   cd src
   python3 main.py
   ```

3. **观察输出**：
   ```
   [*] Source Dir: /path/to/workloads
   [*] Workspace : /path/to/src/.workspace
     -> Copied Instruction: my0to100.exe ==> workload.exe
     -> Copied Memory Data: my0to100.data ==> workload.data
   [*] Data Path: /path/to/.workspace/workload.data
   [*] Ins Path: /path/to/.workspace/workload.exe
   🚀 Compiling system: rv32i_cpu...
   🔨 Building binary from: /path/to/simulator
   🏃 Running simulation (Direct Output Mode)...
   ['/path/to/simulator']  # <- 问题出现在这里
   🔍 Verifying output...
   ```

### 3.2 故障注入测试

为了验证根本原因，可以在 `main.py` 中添加调试代码：

```python
# 在第 242 行之后插入
raw = utils.run_simulator(binary_path=binary_path)

# === 调试代码开始 ===
print(f"[DEBUG] Type of raw: {type(raw)}")
print(f"[DEBUG] Content of raw: {repr(raw)}")

if isinstance(raw, list):
    print("[ERROR] run_simulator returned a list (command args) instead of string output!")
    print("[ERROR] This suggests the simulator output was not captured.")
elif isinstance(raw, str):
    print(f"[DEBUG] raw is a string with {len(raw)} characters")
    if len(raw) == 0:
        print("[WARNING] raw is empty - no output captured")
else:
    print(f"[ERROR] Unexpected type: {type(raw)}")
# === 调试代码结束 ===

print(raw)
```

**预期诊断结果**：
- 如果输出 `Type of raw: <class 'list'>`，则证实 **情况 A/B**
- 如果输出 `Type of raw: <class 'str'>` 但 `len(raw) == 0`，则 stdout 未捕获
- 如果输出 `Type of raw: <class 'subprocess.CompletedProcess'>`，则返回值未正确提取

---

## 4. 修复方案

### 方案 1：修改 `utils.run_simulator` 调用（如果可以访问 assassyn 源码）

**前提**：能够修改或替换 `assassyn.utils` 模块

**步骤**：

1. **定位 `run_simulator` 函数定义**：
   ```bash
   # 查找 assassyn 包的安装位置
   python3 -c "import assassyn.utils as u; import inspect; print(inspect.getsourcefile(u.run_simulator))"
   ```

2. **修正实现**：
   ```python
   # assassyn/utils.py （推测路径）
   import subprocess
   
   def run_simulator(binary_path, timeout=60):
       """
       运行 CPU 模拟器并捕获标准输出
       
       参数：
           binary_path (str): 模拟器二进制文件的完整路径
           timeout (int): 超时时间（秒）
       
       返回：
           str: 模拟器的标准输出日志（所有 log() 语句的输出）
       """
       cmd = [binary_path]
       
       try:
           # 关键修复：添加 capture_output=True 和 text=True
           result = subprocess.run(
               cmd,
               capture_output=True,  # 捕获 stdout 和 stderr
               text=True,            # 以文本模式返回（而非字节流）
               timeout=timeout,      # 防止挂起
               check=False           # 允许非零退出码
           )
           
           # 返回标准输出（而非命令列表）
           output = result.stdout
           
           # 如果 stdout 为空，检查 stderr
           if not output.strip() and result.stderr.strip():
               print("[WARNING] No stdout, but stderr contains:")
               print(result.stderr)
               output = result.stderr  # 某些模拟器可能输出到 stderr
           
           return output
       
       except subprocess.TimeoutExpired:
           print(f"[ERROR] Simulator timed out after {timeout} seconds")
           return ""
       except Exception as e:
           print(f"[ERROR] Failed to run simulator: {e}")
           return ""
   ```

3. **重新安装 assassyn 包**（如果是本地开发包）：
   ```bash
   cd /path/to/assassyn
   pip install -e .
   ```

---

### 方案 2：在 main.py 中添加临时包装器（如果不能修改 assassyn）

**前提**：无法或不想修改 `assassyn` 包源码

**步骤**：

1. **在 `main.py` 顶部添加包装函数**：
   ```python
   import subprocess
   
   def run_simulator_with_capture(binary_path):
       """
       包装 utils.run_simulator 以确保正确捕获输出
       """
       cmd = [binary_path]
       
       try:
           result = subprocess.run(
               cmd,
               capture_output=True,
               text=True,
               timeout=60,
               check=False
           )
           
           output = result.stdout
           if not output.strip() and result.stderr.strip():
               output = result.stderr
           
           return output
       
       except subprocess.TimeoutExpired:
           print("[ERROR] Simulator timeout")
           return ""
       except Exception as e:
           print(f"[ERROR] Simulator failed: {e}")
           return ""
   ```

2. **修改第 242 行的调用**：
   ```python
   # 原代码：
   # raw = utils.run_simulator(binary_path=binary_path)
   
   # 修改为：
   raw = run_simulator_with_capture(binary_path)
   ```

---

### 方案 3：检查模拟器日志文件（如果日志被写入文件）

**前提**：模拟器可能将日志写入 `.workspace` 目录下的文件

**步骤**：

1. **运行模拟器后检查工作目录**：
   ```bash
   cd src/.workspace
   ls -ltr  # 查找最近修改的文件
   ```

2. **查找可能的日志文件**：
   ```bash
   find .workspace -name "*.log" -o -name "*.txt" -o -name "output*"
   ```

3. **如果找到日志文件（如 `simulator.log`），修改 main.py**：
   ```python
   # 在第 242 行之后添加
   raw = utils.run_simulator(binary_path=binary_path)
   
   # 尝试从文件读取日志
   log_file = os.path.join(workspace, "simulator.log")  # 假设的日志文件名
   if os.path.exists(log_file):
       with open(log_file, 'r') as f:
           raw = f.read()
       print(f"[INFO] Read {len(raw)} bytes from {log_file}")
   else:
       print(f"[WARNING] Log file not found: {log_file}")
   ```

---

### 方案 4：验证模拟器本身是否生成日志

**前提**：确认模拟器二进制文件是否被正确配置以输出日志

**步骤**：

1. **手动运行模拟器**：
   ```bash
   cd src
   # 首先运行 main.py 生成模拟器
   python3 -c "
   from main import *
   load_test_case('my0to100')
   sys_builder = build_cpu(depth_log=16)
   cfg = config(verilog=False, sim_threshold=600000, resource_base='', idle_threshold=600000)
   simulator_path, _ = elaborate(sys_builder, **cfg)
   binary_path = utils.build_simulator(simulator_path)
   print(binary_path)
   "
   
   # 然后手动执行模拟器
   /path/to/simulator  # 直接运行，观察是否有输出
   ```

2. **检查模拟器是否需要参数**：
   ```bash
   /path/to/simulator --help
   /path/to/simulator -v  # verbose mode
   /path/to/simulator --log-level debug
   ```

3. **如果模拟器需要特殊参数才输出日志**，修改 `run_simulator` 调用：
   ```python
   # 假设需要 --verbose 参数
   raw = utils.run_simulator(binary_path=binary_path, args=["--verbose"])
   ```

---

## 5. 推荐的诊断流程

### 第 1 步：确认 `raw` 的类型和内容

```bash
cd /home/runner/work/Assassyn-CPU/Assassyn-CPU/src
python3 -c "
from main import *
load_test_case('my0to100')
sys_builder = build_cpu(depth_log=16)
cfg = config(verilog=False, sim_threshold=600000, resource_base='', idle_threshold=600000)
simulator_path, _ = elaborate(sys_builder, **cfg)
binary_path = utils.build_simulator(simulator_path)
raw = utils.run_simulator(binary_path=binary_path)

print('=== Type ===')
print(type(raw))
print('=== Content ===')
print(repr(raw))
print('=== Length ===')
print(len(raw) if hasattr(raw, '__len__') else 'N/A')
"
```

### 第 2 步：手动运行模拟器

```bash
# 获取模拟器路径（从上一步输出中提取）
SIMULATOR_PATH="/path/to/simulator"

# 直接运行
$SIMULATOR_PATH

# 或者通过 strace 检查文件 I/O
strace -e openat,write $SIMULATOR_PATH 2>&1 | grep -E "(log|output|stdout)"
```

### 第 3 步：检查工作目录

```bash
cd src/.workspace
ls -la
cat *.log 2>/dev/null || echo "No log files found"
```

### 第 4 步：根据结果选择修复方案

| 症状 | 根本原因 | 推荐方案 |
|------|----------|----------|
| `raw` 是列表 `[path]` | `run_simulator` 返回命令而非输出 | 方案 1 或 2 |
| `raw` 是空字符串 | stdout 未捕获或模拟器无输出 | 方案 4，然后方案 1/2 |
| 找到 `.log` 文件 | 日志被写入文件而非 stdout | 方案 3 |
| 手动运行有输出，但代码中无 | subprocess 调用有问题 | 方案 1 或 2 |

---

## 6. 预防措施与最佳实践

### 6.1 确保接口一致性

在 `main.py` 中添加类型检查和断言：

```python
raw = utils.run_simulator(binary_path=binary_path)

# 添加防御性检查
assert isinstance(raw, str), f"Expected string, got {type(raw).__name__}"
assert len(raw) > 0, "Simulator produced no output"
assert '\n' in raw or len(raw) > 100, "Output suspiciously short"

print(raw)
```

### 6.2 日志记录

添加详细的日志输出：

```python
import logging
logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)

# 在调用 run_simulator 前后
logger.info(f"Running simulator: {binary_path}")
raw = utils.run_simulator(binary_path=binary_path)
logger.info(f"Simulator output: {len(raw)} chars")
logger.debug(f"First 200 chars: {raw[:200]}")
```

### 6.3 错误处理

```python
try:
    raw = utils.run_simulator(binary_path=binary_path)
    if not isinstance(raw, str):
        raise TypeError(f"run_simulator returned {type(raw)}, expected str")
    if len(raw) == 0:
        raise RuntimeError("Simulator produced no output")
except Exception as e:
    print(f"❌ Simulation failed: {e}")
    # 尝试备用方案
    import subprocess
    result = subprocess.run([binary_path], capture_output=True, text=True)
    raw = result.stdout or result.stderr
    print(f"Fallback capture: {len(raw)} chars")
```

---

## 7. 已知兼容性问题

### 7.1 Assassyn 框架版本

- **0.x 版本**：可能使用旧的接口，返回值为 `(stdout, stderr, returncode)` 元组
- **1.x 版本**：可能改为返回 `CompletedProcess` 对象
- **2.x 版本**：可能直接返回字符串

**解决方案**：检查 `assassyn` 的 `__version__`：

```python
import assassyn
print(f"Assassyn version: {assassyn.__version__}")
```

### 7.2 Python subprocess 模块

- Python < 3.7：`capture_output` 参数不可用，需要手动指定 `stdout=PIPE, stderr=PIPE`
- Python < 3.5：`run()` 函数不存在，需要使用 `Popen` 或 `check_output`

**兼容写法**：

```python
import sys
import subprocess

if sys.version_info >= (3, 7):
    result = subprocess.run(cmd, capture_output=True, text=True)
else:
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
```

---

## 8. 总结与建议

### 8.1 根本原因

`print(raw)` 只输出模拟器路径列表的根本原因是：**`utils.run_simulator()` 函数返回的是命令参数列表（或其他非字符串类型），而非捕获的模拟器标准输出**。

### 8.2 直接原因

可能的直接原因包括：
1. `run_simulator` 实现错误，返回了 `cmd` 而非 `result.stdout`
2. `subprocess.run()` 调用缺少 `capture_output=True` 参数
3. 模拟器日志被输出到 stderr 或文件，而代码只读取 stdout
4. `assassyn` 版本与 `main.py` 期望的接口不匹配

### 8.3 推荐的修复优先级

1. **立即修复**（方案 2）：在 `main.py` 中添加包装函数，直接调用 `subprocess.run` 并捕获输出
2. **短期修复**（方案 1）：修改 `assassyn.utils.run_simulator` 源码，确保正确捕获和返回 stdout
3. **长期修复**：
   - 为 `utils.run_simulator` 编写单元测试
   - 在文档中明确接口契约（参数、返回值、异常）
   - 添加类型注解（Type Hints）

### 8.4 后续验证步骤

修复后，应确认以下行为：

1. `print(raw)` 输出包含 CPU 运行日志（多行文本）
2. 日志包含关键信息（如 PC 值、寄存器状态）
3. 日志可以被 `split('\n')` 正常解析
4. 程序执行结果正确（如 accumulate(100) = 5050）

---

## 9. 附录：参考代码片段

### A. 完整的包装函数实现

```python
# main.py 顶部添加
import subprocess
import os

def run_simulator_robust(binary_path, timeout=60, check_stderr=True):
    """
    健壮的模拟器运行包装函数
    
    参数：
        binary_path (str): 模拟器二进制文件路径
        timeout (int): 超时时间（秒）
        check_stderr (bool): 如果 stdout 为空，是否检查 stderr
    
    返回：
        str: 捕获的模拟器输出
    
    异常：
        RuntimeError: 如果模拟器崩溃或无输出
    """
    if not os.path.exists(binary_path):
        raise FileNotFoundError(f"Simulator not found: {binary_path}")
    
    if not os.access(binary_path, os.X_OK):
        raise PermissionError(f"Simulator not executable: {binary_path}")
    
    cmd = [binary_path]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )
        
        output = result.stdout
        
        # 如果 stdout 为空但 stderr 有内容
        if not output.strip() and check_stderr and result.stderr.strip():
            print("[INFO] Using stderr as output (stdout was empty)")
            output = result.stderr
        
        # 检查返回码
        if result.returncode != 0:
            print(f"[WARNING] Simulator exited with code {result.returncode}")
            if result.stderr.strip():
                print(f"[STDERR] {result.stderr}")
        
        return output
    
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Simulator timed out after {timeout}s")
    except Exception as e:
        raise RuntimeError(f"Failed to run simulator: {e}")
```

### B. 调试版本的 main.py 关键部分

```python
# 第 240-250 行修改

print(f"🏃 Running simulation (Direct Output Mode)...")

# 使用健壮的包装函数
try:
    raw = run_simulator_robust(binary_path=binary_path)
    
    # 验证输出
    print(f"[DEBUG] Captured {len(raw)} characters")
    if len(raw) < 50:
        print(f"[WARNING] Output seems too short: {repr(raw)}")
    
    # 显示前 500 个字符（如果有）
    if raw:
        preview = raw[:500] if len(raw) > 500 else raw
        print("=== Simulator Output (Preview) ===")
        print(preview)
        if len(raw) > 500:
            print(f"... (truncated, total {len(raw)} chars)")
        print("=== End of Preview ===")
    else:
        print("[ERROR] No output captured!")
    
except Exception as e:
    print(f"❌ Simulation failed: {e}")
    raise

print("🔍 Verifying output...")
```

---

## 10. 联系与支持

如果在实施修复后仍遇到问题，请提供以下信息：

1. Python 版本：`python3 --version`
2. Assassyn 版本：`python3 -c "import assassyn; print(assassyn.__version__)"`
3. 操作系统：`uname -a`
4. 完整的错误堆栈跟踪
5. `main.py` 的完整输出（包括所有打印语句）
6. 手动运行模拟器的输出：`/path/to/simulator`

---

**报告生成日期**：2025-12-14  
**报告版本**：1.0  
**作者**：GitHub Copilot Agent  
**状态**：待验证
