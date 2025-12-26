# Pure Wallace Tree Multiplier Implementation

## Overview

This document describes the implementation of a 32×32-bit multiplier using **pure Wallace Tree** reduction without Booth encoding, replacing the previous Radix-4 Booth + Wallace Tree implementation.

## Key Changes

### Previous Implementation (Radix-4 Booth + Wallace Tree)
- Used Radix-4 Booth encoding to reduce 32 partial products to 17
- 3 pipeline stages: EX1, EX2, EX3
- More complex encoding logic in first stage

### New Implementation (Pure Wallace Tree)
- **No Booth encoding** - uses simple AND-based partial product generation
- Generates all 32 partial products directly
- 3 pipeline stages: **EX_M1**, **EX_M2**, **EX_M3**
- Simpler first stage, more compression work in later stages

## Architecture Details

### Stage 1: EX_M1 - Partial Product Generation

**Hardware Implementation:**
```
For i = 0 to 31:
    pp[i] = A & {32{B[i]}}
    // Where {32{B[i]}} means replicate bit B[i] 32 times
    pp[i] = pp[i] << i  // Left-shift by i positions
```

**Key Points:**
- Generates 32 partial products (instead of 17 with Booth)
- Each `pp[i]` is either all zeros or equals `A`, depending on bit `B[i]`
- Each partial product is left-shifted by `i` positions for proper alignment
- Results in 32 rows, each 64 bits wide (to accommodate shifts)
- Sign extension handled for signed multiplication

**Example:**
```
A = 0xABCD1234 (multiplicand)
B = 0x00000005 (multiplier = 0b...00000101)

pp[0] = A & {32{B[0]}} << 0 = A & 0xFFFFFFFF = 0xABCD1234
pp[1] = A & {32{B[1]}} << 1 = 0 << 1 = 0x00000000
pp[2] = A & {32{B[2]}} << 2 = A << 2 = 0xABCD1234 << 2
pp[3..31] = all zeros (since B[3..31] = 0)
```

### Stage 2: EX_M2 - Wallace Tree First Compression Layers

**Hardware Implementation:**

Uses multiple levels of 3:2 compressors (full adders) and 2:2 compressors (half adders) to reduce rows:

**3:2 Compressor (Full Adder):**
```
For each bit position i:
    sum[i] = a[i] ⊕ b[i] ⊕ c[i]
    carry[i+1] = (a[i] & b[i]) | (b[i] & c[i]) | (a[i] & c[i])
```

**2:2 Compressor (Half Adder):**
```
For each bit position i:
    sum[i] = a[i] ⊕ b[i]
    carry[i+1] = a[i] & b[i]
```

**Compression Levels in EX_M2:**
```
Level 0: 32 rows (input from EX_M1)
Level 1: 22 rows (10 full adders reduce 30 → 20, keep 2)
Level 2: 15 rows (7 full adders reduce 21 → 14, keep 1)
Level 3: 10 rows (5 full adders reduce 15 → 10)
Level 4:  7 rows (3 full adders reduce 9 → 6, keep 1)
Level 5:  5 rows (2 full adders reduce 6 → 4, keep 1)

Output: 5-7 rows
```

**Key Points:**
- Most of the Wallace Tree compression happens in this stage
- Reduces 32 rows down to 5-7 rows
- Uses approximately 27 full adders (3:2 compressors)
- Critical path through multiple levels of logic

### Stage 3: EX_M3 - Wallace Tree Final Compression + CPA

**Hardware Implementation:**

1. **Final Wallace Tree Compression:**
```
Level 6: 5 → 4 rows (1 full adder, keep 1)
Level 7: 4 → 3 rows (1 full adder, keep 1)  
Level 8: 3 → 2 rows (1 full adder)

Output: 2 rows (sum and carry)
```

2. **Carry-Propagate Adder (CPA):**
```
final_product[63:0] = sum_row[63:0] + carry_row[63:0]
```

**Key Points:**
- Completes final compression to 2 rows
- Uses approximately 3 full adders for final compression
- CPA performs final 64-bit addition
- CPA can use various architectures:
  - Ripple-Carry Adder (simple, slower)
  - Carry-Lookahead Adder (faster, more area)
  - Carry-Select Adder (balanced)
  - Kogge-Stone Adder (fastest, most area)
- Extracts high or low 32 bits based on operation type

## Comparison: Booth vs Pure Wallace Tree

| Aspect | Radix-4 Booth + Wallace | Pure Wallace Tree |
|--------|-------------------------|-------------------|
| Partial Products | 17 | 32 |
| PP Generation | Complex (Booth encoding) | Simple (AND gates) |
| PP Gen Hardware | Multiplexers, shifters | AND gates only |
| Wallace Tree Levels | ~6 levels | ~8 levels |
| Stage 1 Complexity | High | Low |
| Stage 2 Complexity | Medium | High |
| Total Compressors | ~40-50 | ~30 (due to more levels) |
| Critical Path | Booth + 6 levels + CPA | PP gen + 8 levels + CPA |

## Hardware Resource Estimates

### Stage 1 (EX_M1):
- 32 × 32-bit AND gates = 1,024 AND gates
- Left-shift logic (wiring, no gates)
- Sign extension logic

### Stage 2 (EX_M2):
- ~27 full adders (3:2 compressors)
- Each full adder = 2 XOR + 3 AND + 1 OR per bit
- For 64-bit width: ~27 × 64 = 1,728 gate equivalents

### Stage 3 (EX_M3):
- ~3 full adders for final compression
- 64-bit CPA (varies by architecture)
  - Ripple-Carry: ~64 full adders
  - Other architectures: more complex

### Total Resource Estimate:
- **AND gates:** ~1,024 (Stage 1) + ~5,184 (Stages 2-3) = ~6,200
- **XOR gates:** ~3,840 (Stages 2-3)
- **OR gates:** ~1,920 (Stages 2-3)
- **Total:** ~12,000 gate equivalents (approximate)

## Timing Characteristics

### Critical Path per Stage:

**Stage 1 (EX_M1):**
- 1 AND gate delay
- Sign extension logic
- **Estimated:** 1-2 gate delays

**Stage 2 (EX_M2):**
- 5 levels of 3:2 compressors
- Each level: ~2-3 gate delays (XOR + majority logic)
- **Estimated:** 10-15 gate delays

**Stage 3 (EX_M3):**
- 3 levels of 3:2 compressors: ~6-9 gate delays
- 64-bit CPA: varies by architecture
  - Ripple-Carry: ~64 gate delays
  - Carry-Lookahead: ~log₂(64) = 6 levels
  - Kogge-Stone: ~log₂(64) = 6 levels
- **Estimated:** 12-20 gate delays (with fast CPA)

### Total Latency:
- **3 clock cycles** (pipelined)
- **Clock frequency limited by:** Stage 2 or Stage 3 (whichever is slower)

## Supported Operations

All RISC-V RV32M extension multiplication instructions are supported:

| Instruction | Operation | Signedness | Result |
|-------------|-----------|------------|--------|
| **MUL** | rs1 × rs2 | Both signed | Low 32 bits |
| **MULH** | rs1 × rs2 | Both signed | High 32 bits |
| **MULHSU** | rs1 × rs2 | rs1 signed, rs2 unsigned | High 32 bits |
| **MULHU** | rs1 × rs2 | Both unsigned | High 32 bits |

## Code Changes Summary

### Files Modified:

1. **`src/multiplier.py`:**
   - Renamed class: `BoothWallaceMul` → `WallaceTreeMul`
   - Renamed pipeline stages: `ex1/ex2/ex3` → `m1/m2/m3`
   - Updated `cycle_m1()`: Simple partial product generation
   - Updated `cycle_m2()`: Wallace tree compression (32 → 6-8 rows)
   - Updated `cycle_m3()`: Final compression + CPA
   - Updated all documentation and comments

2. **`src/execution.py`:**
   - Updated import: `BoothWallaceMul` → `WallaceTreeMul`
   - Updated instantiation and method calls
   - Updated comments to reflect Pure Wallace Tree architecture
   - Changed logging messages

## Benefits of Pure Wallace Tree

### Advantages:
1. **Simpler first stage:** No complex Booth encoding logic
2. **Regular structure:** Easier to layout and verify
3. **Predictable timing:** No special cases from Booth encoding
4. **Easier to understand:** Simpler conceptual model

### Trade-offs:
1. **More partial products:** 32 instead of 17
2. **More compression levels:** 8 instead of ~6
3. **Potentially longer critical path:** More levels to traverse

## Testing

The existing multiplication tests in `tests/test_mul_extension.py` continue to work without modification, as the external interface remains the same:

- Same input/output interface
- Same 3-cycle latency
- Same supported operations (MUL, MULH, MULHSU, MULHU)
- Mathematically equivalent results

## Conclusion

This implementation successfully replaces the Booth-encoded multiplier with a pure Wallace Tree multiplier, meeting the requirements:

✅ **No Booth encoding** - uses simple AND-based partial product generation  
✅ **3-stage pipeline** - EX_M1, EX_M2, EX_M3  
✅ **EX_M1:** Generate 32 partial products with `pp[i] = A & {32{B[i]}}`  
✅ **EX_M2:** Wallace tree compression (32 → 6-8 rows)  
✅ **EX_M3:** Final compression (6-8 → 2 rows) + CPA  
✅ **Maintains compatibility** with existing code and tests

The new implementation provides a simpler, more regular multiplier structure while maintaining the same functional behavior and performance characteristics.
