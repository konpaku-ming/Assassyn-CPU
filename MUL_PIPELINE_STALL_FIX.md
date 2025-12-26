# MUL Pipeline Stall Fix - Implementation Report

## Problem Description

The multiplication instruction (MUL) uses a 3-cycle Wallace Tree multiplier, but the pipeline did not properly handle this multi-cycle operation:

1. **Issue 1**: The EX stage did not stall the pipeline when MUL was executing
2. **Issue 2**: Subsequent instructions could enter EX and overwrite the MUL result in the bypass register before the multiplication completed
3. **Requirement**: MUL should occupy the EX stage for 3 cycles, stalling the entire pipeline until completion

## Root Cause Analysis

The multiplier has three pipeline stages (m1, m2, m3) that take 3 cycles to complete:
- Cycle 1 (EX_M1): Partial product generation
- Cycle 2 (EX_M2): Wallace Tree compression (32 → 6-8 rows)
- Cycle 3 (EX_M3): Final compression + CPA, result ready

However, the hazard detection unit only checked for Load-Use hazards, not for multi-cycle MUL operations. This allowed new instructions to enter the EX stage while the multiplier was still processing, causing the ALU to overwrite the bypass register.

## Solution Overview

The fix introduces MUL busy detection into the pipeline stall logic:

1. **Execution Stage** (`execution.py`): Exposes the multiplier's busy status
2. **Data Hazard Unit** (`data_hazard.py`): Uses the busy status to stall the pipeline
3. **Main Pipeline** (`main.py`): Connects the signals between modules

## Implementation Details

### 1. Execution Stage Changes (`src/execution.py`)

```python
# At the end of build() method, return mul_busy status
mul_busy = multiplier.is_busy()
return final_mem_ctrl.rd_addr, is_load, mul_busy
```

The `multiplier.is_busy()` method checks if any of the three pipeline stages are active:
```python
def is_busy(self):
    """Check if multiplier has operations in flight"""
    return (self.m1_valid[0] | self.m2_valid[0] | self.m3_valid[0])
```

### 2. Data Hazard Unit Changes (`src/data_hazard.py`)

Added `ex_mul_busy` parameter and MUL stall logic:

```python
@downstream.combinational
def build(
    self,
    ...
    ex_mul_busy: Value,  # EX 级乘法器是否忙碌 (多周期 MUL 指令占用)
    ...
):
    ...
    # MUL 多周期占用检测
    mul_busy_stall = ex_mul_busy_val
    
    # 组合 Load-Use 和 MUL busy 停顿条件
    stall_if = load_use_hazard_rs1 | load_use_hazard_rs2 | mul_busy_stall
```

### 3. Main Pipeline Changes (`src/main.py`)

Connected the mul_busy signal:

```python
# EX 阶段返回 rd, is_load, mul_busy
ex_rd, ex_is_load, ex_mul_busy = executor.build(...)

# 传递给 Hazard Unit
rs1_sel, rs2_sel, stall_if = hazard_unit.build(
    ...
    ex_mul_busy=ex_mul_busy,
    ...
)
```

## Verification Plan

### Unit Tests
- Updated `test_datahazard.py` to include MUL busy test case
- Test case 6: Verifies that `ex_mul_busy=1` causes `stall_if=1`

### Integration Tests
To verify the complete fix:
1. Run mul1to10 workload
2. Check that MUL instructions cause 3-cycle stalls
3. Verify that subsequent instructions don't overwrite MUL results
4. Confirm that MUL results are correct

## Expected Behavior

### Cycle-by-Cycle Timeline (Example)

**Cycle N**: MUL instruction enters EX
- `start_multiply()` called, m1_valid=1
- `is_busy()` returns 1
- Pipeline begins to stall

**Cycle N+1**: Pipeline stalled
- NOP inserted into EX (due to stall)
- `cycle_m1()` advances: m1→m2, m2_valid=1, m1_valid=0
- `is_busy()` returns 1 (m2_valid=1)
- Pipeline continues to stall

**Cycle N+2**: Pipeline stalled
- NOP in EX
- `cycle_m2()` advances: m2→m3, m3_valid=1, m2_valid=0
- `is_busy()` returns 1 (m3_valid=1)
- Pipeline continues to stall

**Cycle N+3**: Pipeline stalled
- NOP in EX
- `cycle_m3()` completes, result ready
- `clear_result()` called, m3_valid=0
- `is_busy()` returns 0
- Pipeline stall released

**Cycle N+4**: Pipeline resumes
- Next instruction can enter EX
- MUL result has been safely computed and stored

## Benefits

1. **Correctness**: MUL results are no longer overwritten by subsequent instructions
2. **Simplicity**: Clean integration with existing hazard detection logic
3. **Safety**: Conservative approach ensures all MUL operations complete properly
4. **Consistency**: Follows the same pattern as Load-Use hazard detection

## Edge Cases Handled

1. **Branch Flush During MUL**: If a branch occurs while MUL is executing, the multiplier continues but the result is not written (rd_addr=0). The pipeline still stalls to completion.

2. **Back-to-Back MUL**: Second MUL instruction waits until first completes before starting.

3. **Combined Hazards**: If both Load-Use and MUL busy occur, the OR logic ensures proper stalling.

## Testing Status

- [x] Code changes implemented
- [x] Unit test updated with MUL busy test case
- [ ] Integration test with mul1to10 workload
- [ ] Verify cycle count matches expectation (3 stall cycles per MUL)
- [ ] Confirm MUL result correctness

## Conclusion

This fix ensures that MUL instructions properly occupy the EX stage for 3 cycles, preventing pipeline hazards and ensuring correct multiplication results. The implementation is minimal, focused, and integrates cleanly with the existing hazard detection infrastructure.
