# Main Test - CPU 内存初始化与测试

本目录包含用于 Assassyn CPU 内存初始化和测试的程序、工具和文档。

## 📚 文档导航

### 🚀 新手入门
- **[快速使用指南.md](快速使用指南.md)** - 5分钟快速上手
  - 最简单的使用步骤
  - 常用命令
  - 常见问题解答

### 📖 详细文档
- **[初始化报告.md](初始化报告.md)** - 完整技术文档
  - 文件格式详解
  - 转换原理说明
  - 内存初始化机制
  - 故障排除指南

### ✅ 验证报告
- **[初始化验证报告.md](初始化验证报告.md)** - 详细验证结果
  - 文件完整性验证
  - 指令内容分析
  - 功能预期说明

---

## 🎯 当前测试程序

### Accumulate 程序
- **功能**: 计算 1+2+3+...+100 = 5050
- **指令数**: 22条 RISC-V 指令
- **数据段**: 无需静态数据
- **测试覆盖**: 算术、内存、循环、分支、函数调用

### 文件说明
- `accumulate_data.bin` - 数据段二进制文件（0字节）
- `accumulate_text.bin` - 指令段二进制文件（88字节）

---

## 🛠️ 工具和脚本

### convert_bin_to_exe.py
将二进制文件转换为 Assassyn SRAM 初始化格式。

**用法**:
```bash
python3 convert_bin_to_exe.py
```

**输入**:
- `accumulate_data.bin`
- `accumulate_text.bin`

**输出** (生成在 `.workspace/`):
- `workload_mem.exe` - 数据内存初始化文件
- `workload_ins.exe` - 指令内存初始化文件
- `workload.init` - 偏移量初始化文件

### verify_conversion.py
验证转换结果的正确性。

**用法**:
```bash
python3 verify_conversion.py
```

### test_initialization.py
全面测试初始化系统的完整性。

**用法**:
```bash
python3 test_initialization.py
```

**测试项目**:
- ✅ 目录结构验证
- ✅ 文件格式验证
- ✅ 指令内容验证
- ✅ CPU 配置验证

---

## ⚡ 快速开始

### 1️⃣ 转换二进制文件
```bash
cd main_test
python3 convert_bin_to_exe.py
```

### 2️⃣ 验证转换结果
```bash
python3 verify_conversion.py
```

### 3️⃣ 全面测试（推荐）
```bash
python3 test_initialization.py
```

### 4️⃣ 运行 CPU 仿真
```bash
cd ..
python src/main.py
```

---

## 📊 文件结构

```
main_test/
├── README.md                    # 本文档
├── 快速使用指南.md               # 快速入门指南
├── 初始化报告.md                 # 详细技术文档
├── 初始化验证报告.md             # 验证结果报告
│
├── accumulate_data.bin          # 测试程序数据段
├── accumulate_text.bin          # 测试程序指令段
│
├── convert_bin_to_exe.py        # 转换工具
├── verify_conversion.py         # 验证工具
└── test_initialization.py       # 全面测试工具
```

生成的文件（在 `.workspace/`）:
```
.workspace/
├── workload_mem.exe             # 数据内存初始化
├── workload_ins.exe             # 指令内存初始化
└── workload.init                # 偏移量初始化
```

---

## 🔄 工作流程

1. **准备**: 准备 `.bin` 格式的程序文件
2. **转换**: 运行 `convert_bin_to_exe.py`
3. **验证**: 运行 `verify_conversion.py`
4. **使用**: CPU 自动从 `.workspace/` 加载初始化文件

---

## 📋 初始化状态

| 项目 | 状态 | 说明 |
|------|------|------|
| 二进制文件 | ✅ | accumulate_data.bin, accumulate_text.bin |
| 转换脚本 | ✅ | convert_bin_to_exe.py |
| 验证脚本 | ✅ | verify_conversion.py |
| 初始化文件 | ✅ | .workspace/*.exe 已生成 |
| 文档 | ✅ | 完整的中文文档 |

**状态**: ✅ **已完成初始化，可以开始测试**

---

## 🧪 测试建议

### 基础测试
```bash
pytest tests/test_fetch.py -v       # 指令获取
pytest tests/test_decoder.py -v     # 指令解码
pytest tests/test_memory.py -v      # 内存访问
```

### 执行测试
```bash
pytest tests/test_execute_part1.py -v
pytest tests/test_execute_part2.py -v
pytest tests/test_execute_part3.py -v
```

### 完整测试套件
```bash
pytest tests/ -v
```

---

## 🎓 技术规格

### 文件格式
- **输入**: 原始二进制（小端序，32位对齐）
- **输出**: ASCII 十六进制文本（每行8位十六进制数）

### 字节序
- 小端序（Little-Endian）
- RISC-V 标准字节序

### 数据宽度
- 32位字宽
- 每条指令4字节

### 内存容量
- 默认: 2^16 = 65536 字
- 可配置: 修改 `src/main.py` 中的 `depth_log` 参数

---

## 📞 获取帮助

### 查看详细说明
- 转换原理: 阅读 `初始化报告.md`
- 使用示例: 阅读 `快速使用指南.md`
- 验证结果: 阅读 `初始化验证报告.md`

### 常见问题
请参考 `快速使用指南.md` 中的"常见问题"部分。

---

## 🔗 相关链接

- [CPU 工作原理详细报告](../CPU工作原理详细报告.md)
- [项目 README](../README.md)
- [快速入门指南](../QUICKSTART.md)

---

**最后更新**: 2025-12-13  
**版本**: 1.0  
**维护者**: GitHub Copilot  
**状态**: ✅ 可用
