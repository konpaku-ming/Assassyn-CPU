# 除法器问题修复总结

## 问题

计算 0x375f00 ÷ 2 时得到错误结果 0x375f00（应该是 0x1BAF80）

## 根本原因

**在 Assassyn 中，不能将中间 wire 变量赋值给 RegArray，必须直接在赋值语句中进行计算。**

## 修复方案

```python
# 错误（之前的"修复"）
temp = concat(self.quotient[0][0:30], Bits(1)(0))
with Condition(cond):
    self.quotient[0] = temp  # 不生效

# 正确（最终修复）
with Condition(cond):
    self.quotient[0] = concat(self.quotient[0][0:30], Bits(1)(0))  # 生效
```

## Assassyn 编程规则

✅ 允许：在 Condition 块内直接计算并赋值  
❌ 禁止：使用中间变量赋值给 RegArray

## 错误分析历程

1. ❌ 第一次：认为是 concat 参数顺序问题 → 反转参数 → 错误
2. ❌ 第二次：认为是条件块内切片限制 → 预计算中间变量 → 错误
3. ✅ 第三次：参考 SRT4 divider → 直接在赋值中计算 → 正确

## 交付内容

- `src/naive_divider.py` - 移除中间变量，恢复原始代码结构
- `report/division_bug_analysis.md` - 详细的三次分析过程
- `report/SOLUTION_SUMMARY.md` - 本文档
