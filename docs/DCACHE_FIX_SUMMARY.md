# DCache Index Out-of-Bounds Fix Summary

## Issue Description

The CPU simulator panicked with the following error when running the "my0to100" program:

```
thread 'main' panicked at src/modules/dcache.rs:78:27:
index out of bounds: the len is 65536 but the index is 262120
```

## Root Cause

The SRAM dcache module expects **word indices** (0-65535) as addresses, but the execution module was passing **byte addresses** (0-262140) directly without conversion.

### Technical Details

1. **SRAM Configuration** (main.py:103)
   - `dcache = SRAM(width=32, depth=1 << 16)`
   - Depth: 2^16 = 65536 words
   - Each word: 32 bits = 4 bytes
   - Valid word indices: 0 to 65535
   - Valid byte addresses: 0x0 to 0x3FFFC (0 to 262140)

2. **Stack Pointer Initialization** (main.py:115)
   - `reg_init[2] = ((1 << 16) - 1) * 4`
   - SP = 65535 * 4 = 262140 (0x3FFFC)
   - This is CORRECT: SP points to the last valid byte address

3. **The Bug** (execution.py:240, before fix)
   ```python
   dcache.build(
       we=is_store,
       wdata=real_rs2,
       addr=alu_result,  # BUG: byte address used as word index!
       re=is_load,
   )
   ```

4. **Why It Panicked**
   - When program accesses memory near SP (e.g., SP-20 = 262120)
   - Byte address 262120 used directly as word index
   - dcache.rs tries to access index 262120 in array of length 65536
   - Panic: index out of bounds!

## The Fix

Convert byte addresses to word indices by dividing by 4 (right shift by 2 bits).

### Code Change (execution.py lines 237-242)

```python
# 直接调用 dcache.build 处理 SRAM 操作
# 将字节地址转换为字索引（除以4或右移2位）
word_addr = alu_result >> UInt(32)(2)
dcache.build(
    we=is_store,  # 写使能信号（对于Store指令）
    wdata=real_rs2,  # 写入数据（经过Forwarding的rs2）
    addr=word_addr,  # 地址（字索引，字节地址除以4）
    re=is_load,  # 读使能信号（对于Load指令）
)
```

### Why This Works

| Address (bytes) | Word Index (addr >> 2) | Valid? |
|-----------------|------------------------|--------|
| 262140 (0x3FFFC) | 65535 (0xFFFF) | ✅ Yes |
| 262136 (0x3FFF8) | 65534 (0xFFFE) | ✅ Yes |
| 262120 (0x3FFE8) | 65530 (0xFFFA) | ✅ Yes |
| 0 (0x0) | 0 (0x0) | ✅ Yes |

## Pattern Consistency

This fix aligns dcache access with the existing icache access pattern:

**ICache (fetch.py:67)** - Already correct:
```python
sram_addr = (final_current_pc) >> UInt(32)(2)
icache.build(we=Bits(1)(0), re=Bits(1)(1), addr=sram_addr, wdata=Bits(32)(0))
```

**DCache (execution.py:238-242)** - Now fixed:
```python
word_addr = alu_result >> UInt(32)(2)
dcache.build(we=is_store, wdata=real_rs2, addr=word_addr, re=is_load)
```

## Memory Module Compatibility

The memory.py module correctly uses the low 2 bits of `alu_result` for byte/halfword selection within a word:
- `alu_result[1:1]` - selects halfword (bits 16-31 or 0-15)
- `alu_result[0:0]` - selects byte within halfword

This is compatible with our fix because:
- Bits [31:2] → word address (for SRAM indexing)
- Bits [1:0] → byte offset within word (for data alignment)

## Testing

Without the fix:
```
❌ Panic: index 262120 out of bounds (len=65536)
```

With the fix:
```
✅ Address 262120 → word_idx 65530 → Valid access
✅ All stack operations work correctly
✅ my0to100 program can run without panic
```

## Key Takeaway

**Convention**: When accessing SRAM modules in Assassyn CPU:
- CPU operates with **byte addresses** (word-aligned)
- SRAM requires **word indices**
- Always convert: `word_index = byte_address >> 2`

## Related Files

- **Fix Applied**: `src/execution.py` (lines 237-242)
- **Reference Pattern**: `src/fetch.py` (line 67)
- **Memory Alignment**: `src/memory.py` (lines 62, 68)
- **SP Initialization**: `src/main.py` (line 115)

## Commit

- **Branch**: copilot/fix-dcache-index-out-of-bounds
- **Commit**: bc25b05 - "Fix dcache byte-to-word address conversion in execution.py"

---

**Date**: 2025-12-15  
**Issue**: Index out-of-bounds panic in dcache during bare-metal CPU simulator run  
**Status**: ✅ Fixed
