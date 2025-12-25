# RISC-V 32I-M Extension Feasibility Analysis & Implementation Plan

## Executive Summary

**Objective**: Extend the Assassyn-CPU from RV32I (Base Integer Instruction Set) to RV32IM (with Multiply/Divide Extension)

**Conclusion**: ✅ **Fully Feasible** - The current architecture is well-designed and highly modular, allowing seamless integration of M-extension instructions.

**Estimated Effort**: 8.5 hours (1-2 working days)

---

## Current CPU Architecture Overview

### Key Features
- **Pipeline**: 5-stage (IF → ID → EX → MEM → WB)
- **Hazard Handling**: 
  - Data hazards: Full forwarding/bypass mechanism (3 levels)
  - Control hazards: Branch Target Buffer (BTB) + flush mechanism
- **Current ISA Coverage**: Complete RV32I (40 instructions)
  - Arithmetic: ADD, SUB, etc.
  - Logical: AND, OR, XOR, shifts
  - Load/Store: LB, LH, LW, SB, SH, SW (with sign extension)
  - Branches: BEQ, BNE, BLT, BGE, BLTU, BGEU
  - Jumps: JAL, JALR
  - Upper Immediate: LUI, AUIPC
  - System: ECALL, EBREAK

### Technical Stack
- **HDL Framework**: Assassyn (Python-based hardware description)
- **Target Output**: Verilog (for synthesis) + Binary simulator
- **Module Structure**: Clean separation of control signals and datapath

---

## RISC-V M-Extension Specification

### Required Instructions (8 new R-type instructions)

| Instruction | Opcode  | funct3 | funct7  | Operation                              |
|-------------|---------|--------|---------|----------------------------------------|
| MUL         | 0110011 | 000    | 0000001 | rd = (rs1 × rs2)[31:0]                 |
| MULH        | 0110011 | 001    | 0000001 | rd = (rs1 × rs2)[63:32] (signed×signed)|
| MULHSU      | 0110011 | 010    | 0000001 | rd = (rs1 × rs2)[63:32] (signed×unsigned)|
| MULHU       | 0110011 | 011    | 0000001 | rd = (rs1 × rs2)[63:32] (unsigned×unsigned)|
| DIV         | 0110011 | 100    | 0000001 | rd = rs1 ÷ rs2 (signed, round toward 0)|
| DIVU        | 0110011 | 101    | 0000001 | rd = rs1 ÷ rs2 (unsigned)              |
| REM         | 0110011 | 110    | 0000001 | rd = rs1 % rs2 (signed remainder)      |
| REMU        | 0110011 | 111    | 0000001 | rd = rs1 % rs2 (unsigned remainder)    |

### Key Characteristics
- All instructions share R-type format (same as ADD/SUB)
- Distinguished by `funct7=0000001` (vs `0000000` for base instructions)
- Requires 64-bit multiplier and 32-bit divider
- Special case: Division by zero (DIV(x,0) = -1, REM(x,0) = x per RISC-V spec)

---

## Compatibility Assessment

### ✅ Architecture-Level Compatibility

1. **Instruction Format**: R-type format already supported by decoder
2. **Opcode Space**: Current `ALUOp` uses Bits(16) with only 11 bits occupied → 5 bits available
3. **Datapath**: M-extension uses same data flow as ADD/SUB (rs1, rs2 → ALU → rd)
4. **Forwarding**: Results written to rd can reuse existing bypass logic
5. **Pipeline**: Multiplication/division can be treated as single-cycle operations (or multi-cycle with stalls)

### ⚠️ Challenges to Address

1. **Computational Complexity**:
   - Multiplication requires 32×32→64-bit multiplier
   - Division typically requires 32-cycle iteration
   - May impact timing performance (lower max frequency)

2. **Resource Consumption**:
   - Hardware multiplier/divider increases logic resources
   - Generated Verilog may require more LUTs/DSPs

3. **Division-by-Zero Handling**:
   - Requires special case logic per RISC-V specification

---

## Implementation Plan

### Phase 1: Control Signal Extension (1 hour)

**File**: `src/control_signals.py`

**Task**: Extend `ALUOp` class to include M-extension opcodes

**Key Change**: Expand from `Bits(16)` to `Bits(32)` for future-proofing

```python
class ALUOp:
    # Existing operations (0-10)...
    
    # M Extension (11-18)
    MUL    = Bits(32)(0b00000000000000000000100000000000)
    MULH   = Bits(32)(0b00000000000000000001000000000000)
    MULHSU = Bits(32)(0b00000000000000000010000000000000)
    MULHU  = Bits(32)(0b00000000000000000100000000000000)
    DIV    = Bits(32)(0b00000000000000001000000000000000)
    DIVU   = Bits(32)(0b00000000000000010000000000000000)
    REM    = Bits(32)(0b00000000000000100000000000000000)
    REMU   = Bits(32)(0b00000000000001000000000000000000)
```

---

### Phase 2: Instruction Truth Table Update (0.5 hour)

**File**: `src/instruction_table.py`

**Task**: Add 8 entries to `rv32i_table`

**Key Point**: All M-extension instructions share `OP_R_TYPE` opcode, distinguished by `funct3` (0x0-0x7) and `funct7=0x01`

```python
rv32i_table = [
    # ... existing RV32I instructions ...
    
    # --- M Extension ---
    ('mul', OP_R_TYPE, 0x0, 0x01, ImmType.R, ALUOp.MUL, 
     RsUse.YES, RsUse.YES, Op1Sel.RS1, Op2Sel.RS2, MemOp.NONE,
     MemWidth.WORD, Bits(1)(0), WB.YES, BranchType.NO_BRANCH),
    # ... (7 more entries) ...
]
```

---

### Phase 3: Decoder Enhancement (1 hour)

**File**: `src/decoder.py`

**Task**: Add `funct7` field extraction and matching logic

**Current Limitation**: Only parses `bit30`, not full `funct7`

**Enhancement**:
```python
# Physical slicing (add funct7)
opcode = inst[0:6]
rd = inst[7:11]
funct3 = inst[12:14]
rs1 = inst[15:19]
rs2 = inst[20:24]
funct7 = inst[25:31]  # NEW: Extract full funct7 field

# Matching logic (add funct7 check)
for entry in rv32i_table:
    (name, t_op, t_f3, t_f7, ...) = entry  # Add t_f7 parameter
    
    match_if = opcode == t_op
    
    if t_f3 is not None:
        match_if &= funct3 == Bits(3)(t_f3)
    
    # NEW: funct7 matching
    if t_f7 is not None:
        match_if &= funct7 == Bits(7)(t_f7)
    
    # ... existing accumulation logic ...
```

---

### Phase 4: Execution Unit Extension (2 hours)

**File**: `src/execution.py`

**Task**: Implement multiplication and division logic in ALU

#### Multiplication
```python
# MUL: Return lower 32 bits of rs1 × rs2
mul_res = (op1_signed * op2_signed).bitcast(Bits(64))[0:31]

# MULH: Signed×Signed, return upper 32 bits
mulh_full = op1_signed.bitcast(Int(32)) * op2_signed.bitcast(Int(32))
mulh_res = mulh_full.bitcast(Bits(64))[32:63]

# MULHSU: Signed×Unsigned, return upper 32 bits
mulhsu_full = (op1_signed.bitcast(Int(64)) * alu_op2.bitcast(UInt(64)))
mulhsu_res = mulhsu_full.bitcast(Bits(64))[32:63]

# MULHU: Unsigned×Unsigned, return upper 32 bits
mulhu_full = alu_op1.bitcast(UInt(32)) * alu_op2.bitcast(UInt(32))
mulhu_res = mulhu_full.bitcast(Bits(64))[32:63]
```

#### Division (with division-by-zero handling)
```python
# Division-by-zero detection
is_div_zero = alu_op2 == Bits(32)(0)

# DIV: Signed division
div_normal = (op1_signed / op2_signed).bitcast(Bits(32))
div_res = is_div_zero.select(
    Bits(32)(0xFFFFFFFF),  # Div-by-zero → -1
    div_normal
)

# REM: Signed remainder
rem_normal = (op1_signed % op2_signed).bitcast(Bits(32))
rem_res = is_div_zero.select(
    alu_op1,  # Div-by-zero → dividend
    rem_normal
)

# DIVU, REMU: Similar logic with unsigned types
```

#### ALU Result Selector Extension
```python
alu_result = ctrl.alu_func.select1hot(
    add_res,     # 0
    sub_res,     # 1
    # ... (existing 8 operations) ...
    mul_res,     # 11
    mulh_res,    # 12
    mulhsu_res,  # 13
    mulhu_res,   # 14
    div_res,     # 15
    divu_res,    # 16
    rem_res,     # 17
    remu_res,    # 18
    # ... (padding to 32) ...
)
```

---

### Phase 5: Test Case Development (3 hours)

#### 5.1 Unit Tests
**File**: `tests/test_m_extension.py`

Test vectors:
- Basic multiplication: `10 × 20 = 200`
- Signed overflow: `0x80000000 × 2` (MULH test)
- Division: `100 ÷ 10 = 10`
- Division by zero: `10 ÷ 0 = -1`
- Remainder: `105 % 10 = 5`

#### 5.2 Integration Tests
**Files**: `workloads/mul_test.s`, `workloads/div_test.s`

Assembly programs covering:
- All 8 M-extension instructions
- Edge cases (overflow, division by zero)
- Mixed operations with RV32I instructions

#### 5.3 Performance Tests
Compare existing software multiply (`workloads/multiply.exe`) with hardware MUL instruction:
- Expected speedup: 10x for multiplication, 5x for division

---

### Phase 6: Documentation Update (1 hour)

#### Update Module Documentation
- `docs/Module/EX.md`: Add M-extension ALU operations
- `docs/Module/ID.md`: Explain funct7 decoding logic

#### Create M-Extension Guide
**File**: `docs/RV32M_Extension_Guide.md`

Contents:
- Supported instructions and their semantics
- Performance characteristics
- Usage examples
- Known limitations

---

## Timeline

| Phase                        | Time   | Deliverable                          |
|------------------------------|--------|--------------------------------------|
| Phase 1: Control Signals     | 1h     | Updated `control_signals.py`         |
| Phase 2: Instruction Table   | 0.5h   | 8 new entries in `instruction_table.py` |
| Phase 3: Decoder Enhancement | 1h     | funct7 matching in `decoder.py`      |
| Phase 4: Execution Unit      | 2h     | Multiply/divide logic in `execution.py` |
| Phase 5: Test Development    | 3h     | Unit + integration + performance tests |
| Phase 6: Documentation       | 1h     | Updated module docs + M-ext guide    |
| **Total**                    | **8.5h** | **Complete RV32IM support**        |

---

## Risk Assessment & Mitigation

### Risk 1: Divider Latency
**Impact**: May reduce max CPU frequency or require pipeline stalls  
**Mitigation**:
- Option A: Multi-cycle divider with stall mechanism
- Option B: Fast division algorithm (Newton-Raphson)
- Option C: Accept lower frequency in initial implementation

### Risk 2: Resource Consumption
**Impact**: FPGA synthesis failure or slow simulation  
**Mitigation**:
- Monitor Verilog code quality from Assassyn
- Use shared multiply/divide unit (time-multiplexed)
- Consider DSP primitives if target FPGA supports

### Risk 3: Assassyn Language Limitations
**Impact**: Cannot express complex multiply/divide circuits  
**Mitigation**:
- Rely on Python operator mapping to hardware
- Consult Assassyn documentation for type conversion support
- Contact framework developers if necessary

---

## Success Criteria

✅ **Functional Correctness**
- [ ] All 8 M-extension instructions pass unit tests
- [ ] Division-by-zero handling complies with RISC-V spec
- [ ] Edge cases pass (e.g., 0x80000000 ÷ -1)

✅ **Integration Integrity**
- [ ] No conflicts with existing RV32I instructions
- [ ] Forwarding mechanism works for multiply/divide results
- [ ] BTB prediction unaffected

✅ **Performance Metrics**
- [ ] Multiply instructions: 10x speedup vs software
- [ ] Divide instructions: 5x speedup vs software

✅ **Documentation Quality**
- [ ] All module changes have corresponding documentation
- [ ] Runnable example programs provided

---

## Future Optimization Directions

1. **Multi-Cycle Divider**: Extend division to 32-cycle iteration to improve frequency
2. **F/D Extensions**: Further support floating-point operations
3. **Performance Counters**: Add instruction statistics to evaluate M-extension usage
4. **Toolchain Support**: Ensure GCC/LLVM-generated RV32IM code executes correctly

---

## Conclusion

RV32M extension implementation on Assassyn-CPU is **fully feasible**, thanks to:
1. Clean modular design
2. Flexible control signal mechanism
3. High expressiveness of Python/Assassyn

**Estimated timeline**: 1-2 working days from design to testing.

**Recommendation**: Follow this plan in incremental phases, with regression testing after each phase to ensure stable incremental development.

---

**Document Version**: v1.0  
**Date**: 2025-12-24  
**Author**: Copilot AI Assistant  
**Status**: Ready for Review
