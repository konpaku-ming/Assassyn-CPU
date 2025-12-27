# Division Bug Investigation Summary

## Problem

After examining `logs/div1to10.log`, a critical bug was found in the SRT-4 divider where Op1 values became 0x0 or incorrect after the second division operation, causing all subsequent divisions to fail.

## Root Cause

**Bug Location**: `src/divider.py` lines 483-486

The quotient accumulator (Q) update logic when handling negative quotient digits had incorrect carry handling for the case when q=0.

**Original Code** (buggy):
```python
with Condition(neg != Bits(1)(0)):
    # When selecting negative quotient digit
    self.Q[0] = concat(self.QM[0][0:30], Bits(1)(1), q[0:0])
```

**Issue**: The correct formula is `Q = (QM << 2) + (4 - q)`. For different q values:
- q=0: Should add 4 (0b100), which creates a carry into bit 2
- q=1: Should add 3 (0b11), no carry
- q=2: Should add 2 (0b10), no carry

The original code produced:
- q=0: bottom 2 bits = 0b10 (value 2) ❌ - Should be 0b00 with carry
- q=1: bottom 2 bits = 0b11 (value 3) ✓  
- q=2: bottom 2 bits = 0b10 (value 2) ✓

## Fix

**Fixed Code**:
```python
with Condition(neg != Bits(1)(0)):
    # Negative quotient: Q = (QM << 2) + (4 - q)
    # Must handle carry when q=0
    with Condition(q == Bits(2)(0)):
        # q=0: adding 4 creates carry
        # Bottom 2 bits = 0, QM needs +1
        qm_plus_carry = (self.QM[0].bitcast(UInt(33)) + Bits(33)(1)).bitcast(Bits(33))
        self.Q[0] = concat(qm_plus_carry[0:30], Bits(2)(0b00))
    with Condition(q != Bits(2)(0)):
        # q=1 or q=2: no carry
        # Use (~q + 1) to compute (4-q)
        q_inverted_plus_1 = ((~q).bitcast(UInt(2)) + Bits(2)(1)).bitcast(Bits(2))
        self.Q[0] = concat(self.QM[0][0:30], q_inverted_plus_1)
```

## Impact

- First division (÷1): Correct - used fast path (DIV_1 state), bypassed SRT-4 iterations
- Second division (÷2): Failed - entered normal SRT-4 path, triggered the bug
- Subsequent divisions: Continued failing - used incorrect operand from previous result

## Verification Needed

To verify the fix:
1. Re-run the div1to10.exe test case
2. Check that the second division (0x375f00 ÷ 2) produces ~0x1BAF80
3. Verify Op1 values in subsequent divisions use correct accumulated results
4. Verify final results: 10!/1 through 10!/10

## Additional Changes

Added comprehensive debug logging in DIV_END state to help future debugging:
- Q and QM accumulator values
- Remainder sign and adjustment logic
- Quotient and remainder values after sign correction
- Final result selection

---

For complete details in Chinese, see `report/除法问题调查报告.md`.
