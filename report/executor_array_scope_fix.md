# Executor Array Scope Issue Fix

## Problem Description

When compiling the generated Rust code, the following error occurred:

```
error[E0425]: cannot find value `Executor_array_22_wt_1` in this scope
    --> src/modules/Executor.rs:1512:38
     |
1512 |         | ValueCastTo::<bool>::cast(&Executor_array_22_wt_1)
     |                                      ^^^^^^^^^^^^^^^^^^^^^^ help: a local variable with a similar name exists: `Executor_array_21_rd_1`
```

This error appeared in the generated Rust code for the Executor module, specifically related to the naive divider implementation in `src/naive_divider.py`.

## Root Cause

The issue was caused by intermediate variable declarations in the DIV_WORKING state:

```python
# Original problematic code
quotient_lower_bits = self.quotient[0][0:30]
new_quotient_if_neg = concat(quotient_lower_bits, Bits(1)(0))
new_quotient_if_pos = concat(quotient_lower_bits, Bits(1)(1))

with Condition(is_negative == Bits(1)(1)):
    self.quotient[0] = new_quotient_if_neg

with Condition(is_negative != Bits(1)(1)):
    self.quotient[0] = new_quotient_if_pos
```

These intermediate variables (`quotient_lower_bits`, `new_quotient_if_neg`, `new_quotient_if_pos`) were:
1. Defined in an outer scope (within the DIV_WORKING condition)
2. Used across multiple sibling conditional branches

When the Assassyn framework generated Rust code, it created array variables with names like `Executor_array_22_wt_1` for these intermediate values. However, when these variables were referenced in the nested condition blocks, the generated code had scope issues where the variables were not accessible.

## Solution

The fix eliminates the intermediate variables by computing the quotient values directly within each conditional branch:

```python
# Fixed code
with Condition(is_negative == Bits(1)(1)):
    # Restore: add divisor back
    self.remainder[0] = shifted_remainder
    # Shift quotient left and insert 0: quotient = (quotient << 1) | 0
    # Compute new quotient value directly within this branch
    self.quotient[0] = concat(self.quotient[0][0:30], Bits(1)(0))

with Condition(is_negative != Bits(1)(1)):
    # Keep subtraction result
    self.remainder[0] = temp_remainder
    # Shift quotient left and insert 1: quotient = (quotient << 1) | 1
    # Compute new quotient value directly within this branch
    self.quotient[0] = concat(self.quotient[0][0:30], Bits(1)(1))
```

### Why This Works

1. **No intermediate variables**: Each branch directly computes the value it needs
2. **Clear scope**: All operations are within the branch where they're used
3. **Hardware semantics**: In hardware, mutually exclusive branches reading the same value is perfectly valid
4. **Register stability**: Register values are stable during a clock cycle, so reading `self.quotient[0][0:30]` in each branch gets the same value

### Trade-offs

- **Original approach**: Tried to optimize by computing common sub-expressions once
- **Current approach**: Slightly more verbose, but avoids code generation scope issues
- **Performance**: No impact on hardware performance - both branches are mutually exclusive, only one executes per cycle

## Technical Background

### Assassyn Code Generation

The Assassyn framework translates Python hardware descriptions into Rust code. When intermediate variables are created, the framework generates array storage with auto-generated names. The scope rules for these generated variables can be complex, especially with nested conditional blocks.

### Hardware Semantics

In hardware design:
- Conditional blocks (like `with Condition`) are translated to multiplexers
- Only one branch of mutually exclusive conditions executes
- Register reads are stable within a clock cycle
- Duplicate reads in different branches don't cause functional issues

## Verification

The fix should be verified by:
1. Successfully generating Rust code without compilation errors
2. Running division test cases to ensure correct functional behavior
3. Checking that the generated hardware matches the intended design

## Related Issues

This fix addresses the scope issue while maintaining the correctness of the restoring division algorithm. Previous fixes addressed computational correctness; this fix addresses code generation issues.
