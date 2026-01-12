# vvadd vs multiply 对比分析报告

## 问题

用户提问：为什么 `multiply` 能使CPU正常结束，而 `vvadd` 不能？

## 核心发现

**vvadd 和 multiply 运行在两个完全不同的CPU实现上！**

1. **`src/main.py` 运行 vvadd** - 新版CPU，包含：
   - Tournament 分支预测器（结合局部预测器、全局预测器和选择器）
   - MUL/DIV 扩展支持和相关的冒险检测
   - `rs1_used`/`rs2_used` 指令表字段
   - 完整的 `DataHazardUnit`，包括load-use冒险检测
   - 使用 `funct7` 字段解码（用于M扩展指令）

2. **`upd/main.py` 运行 multiply** - 旧版CPU，包含：
   - 简单的 BTB 分支预测
   - 无 MUL/DIV 扩展支持
   - 无 `rs_used` 跟踪
   - 简化的 `HazardUnit`
   - 使用 `bit30` 字段解码

## 两个程序的结构相同

两个程序都使用相同的启动/停机模式：

```
0x0: auipc x2, 0x1000     ; 设置栈指针
0x4: addi x2, x2, 0
0x8: jal x1, offset       ; 保存返回地址 ra=0xC，跳转到主函数
0xC: sb x0, -1(x0)        ; 停机指令
...
<主函数>
...
ret                       ; 返回到 ra=0xC -> 执行停机指令
```

## 关键差异对比

| 特性 | src/ (vvadd) | upd/ (multiply) |
|------|-------------|-----------------|
| 分支预测 | Tournament Predictor | 简单 BTB |
| MUL/DIV 支持 | 是 | 否 |
| 冒险检测 | DataHazardUnit (复杂) | HazardUnit (简单) |
| Rs1_use/Rs2_use 字段 | 是 | 否 |
| 指令表格式 | 包含 funct7, Rs1_use, Rs2_use | 只有 bit30 |

## 数据冒险检测的差异

### src/data_hazard.py (vvadd使用)
```python
stall_if = load_use_hazard_rs1 | load_use_hazard_rs2 | mul_busy_hazard | div_busy_hazard | ex_is_store_val | mem_is_store_val | ex_is_load_val
```

### upd/hazard_unit.py (multiply使用)
```python
stall_if = ex_is_load_val | ex_is_store_val | mem_is_store_val
```

## 结论

**这个比较是无效的**，因为两个程序运行在完全不同的CPU实现上。

要正确比较，应该：
1. 在同一个CPU实现上运行两个程序
2. 或者识别并修复 `src/` 实现中的具体bug

## 建议的下一步

1. **测试方案A**：修改 `src/main.py` 使其加载 `multiply`，验证新CPU能否正常运行
   ```python
   load_test_case("multiply")  # 替换 "vvadd"
   ```

2. **测试方案B**：修改 `upd/main.py` 使其加载 `vvadd`，验证旧CPU能否运行vvadd

3. **如果新CPU无法运行任何程序**：说明新CPU实现有bug，需要调试

4. **如果新CPU只是无法运行vvadd**：可能是vvadd触发了特定的边界情况

## 程序细节分析

### vvadd 程序
- 循环次数：300次
- 每次迭代：6次load，2次store
- 总指令数：约4500条
- 不使用MUL/DIV指令

### multiply 程序  
- 主循环次数：100次
- 包含软件乘法子程序调用
- 每次迭代调用 multiply 函数
- 不使用硬件MUL/DIV指令

两个程序都不使用M扩展指令，所以新CPU的MUL/DIV支持不应该影响执行。
