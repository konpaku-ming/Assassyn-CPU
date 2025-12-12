# 贡献指南

感谢您对 Assassyn-CPU 项目的关注！我们欢迎任何形式的贡献。

## 目录

- [行为准则](#行为准则)
- [如何贡献](#如何贡献)
- [开发流程](#开发流程)
- [代码规范](#代码规范)
- [提交规范](#提交规范)
- [测试要求](#测试要求)
- [文档贡献](#文档贡献)
- [问题报告](#问题报告)

## 行为准则

### 我们的承诺

为了营造一个开放和友好的环境，我们承诺让所有人都能自由地参与到本项目中，无论其经验水平、性别、性别认同和表达、性取向、残疾、外貌、体型、种族、年龄或宗教信仰。

### 我们的标准

**积极行为包括**:
- 使用友好和包容的语言
- 尊重不同的观点和经验
- 优雅地接受建设性批评
- 关注对社区最有利的事情
- 对其他社区成员表示同理心

**不可接受的行为包括**:
- 使用性化的语言或图像，以及不受欢迎的性关注或示好
- 挑衅、侮辱/贬损性评论，以及人身或政治攻击
- 公开或私下骚扰
- 未经明确许可，发布他人的私人信息，如物理或电子地址
- 其他在专业环境中可以合理认为不适当的行为

## 如何贡献

### 贡献类型

我们欢迎以下类型的贡献：

1. **代码贡献**
   - 新功能实现
   - Bug 修复
   - 性能优化
   - 代码重构

2. **文档贡献**
   - 改进现有文档
   - 添加新的教程或指南
   - 翻译文档
   - 修正拼写或语法错误

3. **测试贡献**
   - 添加新的测试用例
   - 改进测试覆盖率
   - 修复失败的测试

4. **问题报告**
   - Bug 报告
   - 功能请求
   - 性能问题

5. **设计贡献**
   - 架构设计建议
   - 接口设计改进
   - 文档图表制作

## 开发流程

### 1. Fork 仓库

```bash
# 在 GitHub 上点击 Fork 按钮
# 然后克隆您的 fork
git clone https://github.com/YOUR_USERNAME/Assassyn-CPU.git
cd Assassyn-CPU

# 添加上游仓库
git remote add upstream https://github.com/konpaku-ming/Assassyn-CPU.git
```

### 2. 创建开发分支

```bash
# 更新主分支
git checkout main
git pull upstream main

# 创建功能分支
git checkout -b feature/your-feature-name

# 或者修复分支
git checkout -b fix/bug-description
```

分支命名规范：
- `feature/xxx` - 新功能
- `fix/xxx` - Bug 修复
- `docs/xxx` - 文档更新
- `refactor/xxx` - 代码重构
- `test/xxx` - 测试相关

### 3. 设置开发环境

```bash
# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# 或
.\.venv\Scripts\Activate.ps1  # Windows

# 安装依赖（包括开发依赖）
pip install -r requirements.txt

# 安装代码检查工具
pip install black flake8 mypy pytest-cov
```

### 4. 进行更改

- 遵循[代码规范](#代码规范)
- 编写清晰的代码注释
- 为新功能添加测试
- 更新相关文档

### 5. 运行测试

```bash
# 运行所有测试
make test

# 运行特定测试
make test-fetch
make test-decoder

# 检查测试覆盖率
pytest tests/ --cov=src --cov-report=html
```

### 6. 代码质量检查

```bash
# 格式化代码
make format

# 运行 linter
make lint

# 类型检查
make typecheck
```

### 7. 提交更改

```bash
# 添加更改
git add .

# 提交（遵循提交规范）
git commit -m "feat: add new feature"

# 推送到您的 fork
git push origin feature/your-feature-name
```

### 8. 创建 Pull Request

1. 访问您的 fork 在 GitHub 上的页面
2. 点击 "New Pull Request"
3. 选择您的功能分支
4. 填写 PR 模板（见下文）
5. 提交 Pull Request

## 代码规范

### Python 代码规范

我们遵循 [PEP 8](https://www.python.org/dev/peps/pep-0008/) 风格指南，并有以下额外要求：

#### 1. 格式化

使用 `black` 进行自动格式化：

```bash
black src/ tests/
```

#### 2. 命名规范

```python
# 模块名：小写字母，下划线分隔
# 文件名: decoder.py, data_hazard.py

# 类名：大驼峰（PascalCase）
class Decoder(Module):
    pass

class DataHazardUnit(Module):
    pass

# 函数名：小写字母，下划线分隔
def get_pad(width, hex_mask, sign):
    pass

# 常量：大写字母，下划线分隔
ALU_OP_ADD = 0b0000
MEM_OP_LOAD = 0b01

# 变量名：小写字母，下划线分隔
pc_reg = RegArray(Bits(32), 1)
branch_target = Bits(32)(0)
```

#### 3. 注释规范

```python
# 模块级文档字符串（中英文均可）
"""
Decoder Module - 译码器模块

实现 RV32I 指令的译码功能，包括：
- 指令解析
- 立即数扩展
- 控制信号生成
"""

# 函数文档字符串
def decode_instruction(inst: Bits) -> Record:
    """
    解码 32 位 RISC-V 指令
    
    参数:
        inst: 32 位指令编码
        
    返回:
        包含所有控制信号的 Record 对象
    """
    pass

# 行内注释：解释复杂逻辑
# 注意：RISC-V 的立即数需要符号扩展
imm = sign_extend(raw_imm, 32)
```

#### 4. 导入规范

```python
# 标准库导入
import os
import sys

# 第三方库导入
from assassyn.frontend import *
from assassyn.backend import elaborate, config

# 本地导入
from .control_signals import *
from .decoder import Decoder
```

### Assassyn 代码规范

#### 1. 模块定义

```python
class MyModule(Module):
    def __init__(self):
        # 定义端口
        super().__init__(
            ports={
                'input_signal': Port(Bits(32)),
                'control': Port(my_ctrl_record),
            }
        )
        self.name = "MyModule"  # 可选：设置模块名称

    @module.combinational
    def build(self, downstream_module: Module, global_reg: Array):
        # 获取输入
        input_signal, control = self.pop_all_ports(False)
        
        # 实现逻辑
        result = process(input_signal, control)
        
        # 调用下游模块
        downstream_module.async_called(data=result)
        
        # 返回必要的输出
        return result
```

#### 2. 类型使用

```python
# 明确使用类型转换
alu_result = (a.bitcast(Int(32)) + b.bitcast(Int(32))).bitcast(Bits(32))

# 避免隐式类型转换
# Bad:
result = a + b  # 不清楚是有符号还是无符号

# Good:
result = (a.bitcast(UInt(32)) + b.bitcast(UInt(32))).bitcast(Bits(32))
```

#### 3. 信号命名

```python
# 寄存器：使用 _reg 后缀
pc_reg = RegArray(Bits(32), 1)
data_reg = RegArray(Bits(32), 32)

# 立即数：使用 imm 前缀
imm_i = extract_imm_i(inst)
imm_s = extract_imm_s(inst)

# 控制信号：描述性名称
alu_op = extract_alu_op(inst)
mem_write_enable = control.mem_we
```

## 提交规范

我们使用 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

### 提交消息格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type 类型

- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档更新
- `style`: 代码格式（不影响代码含义）
- `refactor`: 重构（既不是新功能也不是修复）
- `perf`: 性能优化
- `test`: 添加或修改测试
- `chore`: 构建过程或辅助工具的变动

### Scope 范围（可选）

- `fetch`: IF 阶段
- `decoder`: ID 阶段
- `execute`: EX 阶段
- `memory`: MEM 阶段
- `writeback`: WB 阶段
- `hazard`: 冒险处理
- `test`: 测试相关
- `docs`: 文档相关

### 示例

```bash
# 添加新功能
git commit -m "feat(decoder): add support for M extension instructions"

# 修复 Bug
git commit -m "fix(execute): correct ALU shift operation logic"

# 更新文档
git commit -m "docs: add installation guide for macOS"

# 重构代码
git commit -m "refactor(memory): simplify load/store logic"

# 添加测试
git commit -m "test(hazard): add tests for RAW hazard detection"
```

## 测试要求

### 1. 测试覆盖率

- 新功能必须包含测试
- 目标覆盖率：≥ 80%
- 关键路径覆盖率：100%

### 2. 测试文件组织

```python
# tests/test_module_name.py
import pytest
from tests.common import run_test_module
from src.module_name import MyModule

def test_basic_functionality():
    """测试基本功能"""
    # 设置测试环境
    sys = setup_test()
    
    # 定义验证函数
    def check(output):
        assert "expected" in output
    
    # 运行测试
    run_test_module(sys, check)

def test_edge_cases():
    """测试边界情况"""
    # ...
```

### 3. 测试命名

```python
# 描述性测试名称
def test_decoder_handles_r_type_instruction():
    pass

def test_hazard_unit_detects_raw_dependency():
    pass

def test_memory_access_with_unaligned_address():
    pass
```

## 文档贡献

### 1. 文档类型

- **代码注释**: 解释复杂逻辑
- **模块文档**: `docs/Module/` 中的详细设计文档
- **教程**: 使用指南和示例
- **API 文档**: 函数和类的说明

### 2. 文档格式

- 使用 Markdown 格式
- 提供代码示例
- 包含图表（如需要）
- 中英文均可，建议中文

### 3. 文档结构

```markdown
# 模块名称

## 概述
简要说明模块功能

## 接口定义
列出输入输出端口

## 实现细节
详细说明实现逻辑

## 使用示例
提供代码示例

## 注意事项
特殊情况和限制
```

## 问题报告

### Bug 报告

使用以下模板报告 Bug：

```markdown
**Bug 描述**
简要描述问题

**复现步骤**
1. 执行 '...'
2. 运行 '...'
3. 观察错误 '...'

**期望行为**
应该发生什么

**实际行为**
实际发生了什么

**环境信息**
- OS: [e.g. Ubuntu 22.04]
- Python 版本: [e.g. 3.11.0]
- Rust 版本: [e.g. 1.70.0]

**额外信息**
其他相关信息
```

### 功能请求

```markdown
**功能描述**
描述您想要的功能

**使用场景**
为什么需要这个功能

**建议实现**
（可选）您认为应该如何实现

**替代方案**
（可选）是否考虑过其他方案
```

## Pull Request 模板

创建 PR 时，请包含以下信息：

```markdown
## 更改说明
简要描述此 PR 的更改

## 更改类型
- [ ] 新功能
- [ ] Bug 修复
- [ ] 文档更新
- [ ] 代码重构
- [ ] 性能优化
- [ ] 测试改进

## 相关 Issue
Closes #issue_number

## 测试
- [ ] 已添加新测试
- [ ] 所有测试通过
- [ ] 代码覆盖率符合要求

## 检查清单
- [ ] 代码遵循项目规范
- [ ] 已运行 `make format`
- [ ] 已运行 `make lint`
- [ ] 已更新相关文档
- [ ] 提交消息遵循规范

## 额外说明
其他需要说明的信息
```

## 获取帮助

如果您在贡献过程中遇到问题：

1. 查看 [README.md](README.md) 和 [INSTALL.md](INSTALL.md)
2. 搜索现有的 [Issues](https://github.com/konpaku-ming/Assassyn-CPU/issues)
3. 在 [Discussions](https://github.com/konpaku-ming/Assassyn-CPU/discussions) 中提问
4. 联系项目维护者

## 致谢

感谢所有贡献者的付出！您的贡献让 Assassyn-CPU 变得更好。

---

再次感谢您的贡献！🎉
