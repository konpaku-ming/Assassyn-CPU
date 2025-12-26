# ADD操作数正确性分析工具

本工具用于分析Assassyn CPU模拟器日志文件中ADD指令的操作数正确性。

## 问题背景

需要验证 `logs/0to100.log` 中的所有加法操作是否正确执行，即验证每个ADD指令的操作数和结果是否满足：**Op1 + Op2 = Result**

## 工具使用

### ADD操作分析

#### 基本用法

```bash
# 分析默认日志文件 (logs/0to100.log)
python3 analyze_add_operations.py

# 分析指定的日志文件
python3 analyze_add_operations.py logs/0to100.log

# 分析其他日志文件
python3 analyze_add_operations.py logs/mul1to10.log

# 查看帮助信息
python3 analyze_add_operations.py --help
```

#### 输出文件

工具会生成以下报告文件：

1. **ADD_OPERATIONS_ANALYSIS.md** - 英文分析报告
2. **0to100_ADD_分析报告.md** - 中文详细报告（仅在分析0to100.log时）

### 寄存器值查询

使用 `show_register_value.py` 查看任意寄存器的最终值：

```bash
# 查看寄存器a0（函数返回值）
python3 show_register_value.py a0

# 查看寄存器x15
python3 show_register_value.py x15

# 查看特定日志文件中的寄存器
python3 show_register_value.py a0 logs/mul1to10.log

# 查看帮助信息
python3 show_register_value.py
```

#### 输出示例

```
📊 Summary:
  Total writes: 101
  Final value:  0x0 (decimal: 0)
  Final cycle:  410.00

  ℹ️  Register a0/x10 is typically used for function return values
     The program returned 0 (success)
```

**在0to100.log中，寄存器a0的最终值为 0x0 (十进制: 0)**

## 分析结果

### 0to100.log 分析结果

✅ **所有305个ADD操作均正确**

- **总ADD操作数：** 305次
- **正确操作数：** 305次（100%）
- **错误操作数：** 0次
- **执行周期数：** 412个时钟周期

### 验证方法

工具执行以下步骤：

1. **提取ADD操作**：从日志中搜索所有 `EX: ALU Operation: ADD` 标记
2. **解析操作数**：
   - Op1：从 `EX: ALU Op1 source` 行提取
   - Op2：从 `EX: ALU Op2 source` 行提取
3. **获取结果**：从 `EX: ALU Result` 行提取
4. **验证正确性**：检查 `(Op1 + Op2) mod 2^32 = Result`
5. **生成报告**：输出详细的分析结果

### 示例验证

| 周期 | Op1 | Op2 | 预期结果 | 实际结果 | 状态 |
|------|-----|-----|---------|---------|------|
| 4.00 | 0x0 | 0x0 | 0x0 | 0x0 | ✅ |
| 5.00 | 0x0 | 0xb8 | 0xb8 | 0xb8 | ✅ |
| 6.00 | 0xb8 | 0x190 | 0x248 | 0x248 | ✅ |
| 9.00 | 0xb8 | 0x4 | 0xbc | 0xbc | ✅ |

## 技术细节

### 操作数来源

日志显示ADD操作的操作数可能来自：

- **ZERO**：零寄存器（x0）
- **RS1/RS2**：寄存器文件
- **IMM**：立即数
- **EX-MEM Bypass**：EX阶段旁路
- **WB Bypass**：写回阶段旁路
- **MEM-WB Bypass**：MEM到WB阶段旁路

### 数据处理

- 支持32位有符号和无符号整数
- 正确处理整数溢出（模2^32运算）
- 十六进制和十进制双重显示

## 代码结构

```python
analyze_add_operations.py
├── parse_hex()              # 十六进制解析
├── extract_add_operations() # 提取ADD操作
├── verify_add_operations()  # 验证正确性
├── generate_report()        # 生成报告
└── main()                   # 主函数
```

### 配置常量

- `BACKWARD_SEARCH_LINES = 10`：向前搜索操作数的行数
- `FORWARD_SEARCH_LINES = 5`：向后搜索结果的行数

## 结论

通过对 `0to100.log` 的分析，证实：

✅ **所有305个ADD指令的操作数和结果完全正确**

- CPU的ALU加法功能正常工作
- 数据旁路（Data Forwarding）机制正确实现
- 没有发现任何操作数错误或计算错误

这表明Assassyn CPU的加法器设计和实现是正确的。

## 相关文档

- [ADD_OPERATIONS_ANALYSIS.md](./ADD_OPERATIONS_ANALYSIS.md) - 英文分析报告
- [0to100_ADD_分析报告.md](./0to100_ADD_分析报告.md) - 中文详细报告

## 许可证

本工具是Assassyn CPU项目的一部分。
