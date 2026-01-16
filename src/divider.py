"""
Radix-16 Divider for RV32IM Division Instructions

This module implements a Radix-16 division algorithm that produces 4 bits
of quotient per iteration, using an optimized Quotient Digit Selection (QDS)
approach similar to modern CPU designs.

Architecture Overview:
=====================

The Radix-16 divider uses:
1. Quotient digit set {0, 1, 2, ..., 15}
2. QDS (Quotient Digit Selection) with binary search tree structure
3. 4 bits of quotient per cycle
4. Full-precision comparisons with optimized selection logic

Key Radix-16 Features with QDS Optimization:
- 4 bits of quotient per iteration (vs 2 bits for Radix-4, 3 bits for Radix-8)
- Fixed 8 iterations for 32-bit division
- Binary search tree selection reduces mux depth from 15 to 4 levels
- Critical path optimization for synthesized hardware

QDS (Quotient Digit Selection) Approach:
========================================
Modern CPU dividers optimize the quotient selection critical path. The key insight
is that while we need to compare against all divisor multiples for correctness,
the selection logic can be structured as a binary search tree instead of a
priority encoder.

Old Approach (Priority Encoder):
- Compute: ge_15d, ge_14d, ..., ge_1d (15 comparisons)
- Select: 15-level cascaded mux (deep critical path)
- q = ge_15d ? 15 : (ge_14d ? 14 : ...)

New Approach (Binary Search Tree):
- Compute: Same 15 comparisons (in parallel)
- Select: 4-level binary tree mux structure
- Each quotient bit computed with shallow mux based on higher bits

The comparisons use full-precision 36-bit arithmetic, while the selection
logic is optimized for minimal depth.

Timing:
- 1 cycle: Preprocessing (DIV_PRE)
- 8 cycles: Iterative calculation (DIV_WORKING) - 4 bits per cycle with QDS
- 1 cycle: Post-processing (DIV_END)
- Total: ~10 cycles for normal division

Special cases handled with fast paths:
- DIV_ERROR: Division by zero (1 cycle)
- DIV_1: Divisor = 1 (1 cycle)
"""

from assassyn.frontend import *
from .debug_utils import debug_log


class Radix16Divider:
    """
    Radix-16 division implementation that produces 4 bits of quotient per iteration,
    using an optimized QDS (Quotient Digit Selection) approach.

    The divider is a multi-cycle functional unit that takes ~10 cycles:
    - 1 cycle: Preprocessing
    - 8 cycles: Iterative calculation (4 bits per cycle with QDS)
    - 1 cycle: Post-processing

    Key Radix-16 features with QDS optimization:
    - Quotient digit set {0, 1, 2, ..., 15}
    - Binary search tree selection structure (4 mux levels vs 15)
    - Full-precision 36-bit comparisons for correctness
    - Optimized critical path through selection logic
    - 4 bits of quotient per iteration
    - Fixed 8 iterations for 32-bit division

    QDS Selection Logic:
    The quotient digit selection uses a binary search tree structure:
    - q[3] (MSB) determined by comparing with 8d
    - q[2] determined by comparing with 4d or 12d based on q[3]
    - q[1] determined by comparing with 2d/6d/10d/14d based on q[3:2]
    - q[0] (LSB) determined by comparing with odd multiples based on q[3:1]

    This reduces the mux depth from 15 levels (priority encoder) to 4 levels,
    significantly improving the critical path in synthesized hardware.

    Pipeline Integration:
    - When a division instruction enters EX stage, the divider is started
    - The pipeline stalls (IF/ID/EX) until divider completes
    - Result is written back to register file through normal WB path
    """

    def __init__(self):
        # Control and status registers
        self.busy = RegArray(Bits(1), 1, initializer=[0])
        self.valid_in = RegArray(Bits(1), 1, initializer=[0])

        # Input operands (captured when valid)
        self.dividend_in = RegArray(Bits(32), 1, initializer=[0])
        self.divisor_in = RegArray(Bits(32), 1, initializer=[0])
        self.is_signed = RegArray(Bits(1), 1, initializer=[0])
        self.is_rem = RegArray(Bits(1), 1, initializer=[0])  # 1=remainder, 0=quotient
        self.rd_in = RegArray(Bits(5), 1, initializer=[0])  # Destination register

        # Output results
        self.result = RegArray(Bits(32), 1, initializer=[0])
        self.ready = RegArray(Bits(1), 1, initializer=[0])
        self.error = RegArray(Bits(1), 1, initializer=[0])  # Division by zero
        self.rd_out = RegArray(Bits(5), 1, initializer=[0])  # Output destination register

        # State machine registers
        self.state = RegArray(Bits(3), 1, initializer=[0])  # FSM state
        self.div_cnt = RegArray(Bits(5), 1, initializer=[0])  # Iteration counter (counts down)

        # Internal working registers
        self.dividend_r = RegArray(Bits(32), 1, initializer=[0])  # Unsigned dividend
        self.divisor_r = RegArray(Bits(32), 1, initializer=[0])  # Unsigned divisor

        # Radix-16 specific registers
        self.quotient = RegArray(Bits(32), 1, initializer=[0])  # Quotient accumulator
        self.remainder = RegArray(Bits(36), 1,
                                  initializer=[0])  # Partial remainder (36 bits for 4-bit shift + 15*d overflow)

        # QDS-optimized divisor multiples - only need d, 2d, 4d, 8d for binary search
        # These are stored as normalized (shifted) values for efficient QDS lookup
        self.d1 = RegArray(Bits(36), 1, initializer=[0])  # 1*d (normalized)
        self.d2 = RegArray(Bits(36), 1, initializer=[0])  # 2*d (normalized)
        self.d3 = RegArray(Bits(36), 1, initializer=[0])  # 3*d (for QDS refinement)
        self.d4 = RegArray(Bits(36), 1, initializer=[0])  # 4*d (normalized)
        self.d5 = RegArray(Bits(36), 1, initializer=[0])  # 5*d (for QDS refinement)
        self.d6 = RegArray(Bits(36), 1, initializer=[0])  # 6*d (for QDS refinement)
        self.d7 = RegArray(Bits(36), 1, initializer=[0])  # 7*d (for QDS refinement)
        self.d8 = RegArray(Bits(36), 1, initializer=[0])  # 8*d (normalized)
        self.d9 = RegArray(Bits(36), 1, initializer=[0])  # 9*d (for QDS level 4)
        self.d10 = RegArray(Bits(36), 1, initializer=[0])  # 10*d (for QDS level 3)
        self.d11 = RegArray(Bits(36), 1, initializer=[0])  # 11*d (for QDS level 4)
        self.d12 = RegArray(Bits(36), 1, initializer=[0])  # 12*d (for QDS level 2)
        self.d13 = RegArray(Bits(36), 1, initializer=[0])  # 13*d (for QDS level 4)
        self.d14 = RegArray(Bits(36), 1, initializer=[0])  # 14*d (for QDS level 3)
        self.d15 = RegArray(Bits(36), 1, initializer=[0])  # 15*d (for QDS level 4)

        # Sign tracking for final correction
        self.div_sign = RegArray(Bits(2), 1, initializer=[0])  # Sign bits {dividend[31], divisor[31]}
        self.sign_r = RegArray(Bits(1), 1, initializer=[0])  # Sign flag for result

        # Compatibility registers for tests (preserved for backward compatibility)
        self.norm_shift = RegArray(Bits(6), 1, initializer=[0])  # Reserved for future normalization
        self.div_shift = RegArray(Bits(6), 1, initializer=[0])  # Reserved for future optimization
        self.shift_rem = RegArray(Bits(36), 1, initializer=[0])  # For compatibility
        self.Q = RegArray(Bits(32), 1, initializer=[0])  # For compatibility
        self.QM = RegArray(Bits(32), 1, initializer=[0])  # For compatibility

        # FSM states
        self.IDLE = Bits(3)(0)
        self.DIV_PRE = Bits(3)(1)
        self.DIV_WORKING = Bits(3)(2)
        self.DIV_END = Bits(3)(3)
        self.DIV_1 = Bits(3)(4)
        self.DIV_ERROR = Bits(3)(5)

    def is_busy(self):
        """Check if divider is currently processing"""
        return self.busy[0]

    def find_leading_one(self, value):
        """
        Find position of leading 1 bit.
        Returns the bit position (0-31) of the most significant 1 bit.
        Returns 32 if value is 0.
        """
        result = Bits(6)(32)
        for i in range(31, -1, -1):
            bit_set = value[i:i] == Bits(1)(1)
            result = bit_set.select(Bits(6)(i), result)
        return result

    def power_of_2(self, shift_amt):
        """Generate 2^shift_amt (for shifts 0-31)"""
        result = Bits(32)(1)
        for i in range(32):
            is_this_shift = (shift_amt == Bits(6)(i))
            result = is_this_shift.select(Bits(32)(1 << i), result)
        return result

    def quotient_select(self, shifted_rem, d1, d2, d3, d4, d5, d6, d7, d8, d9, d10, d11, d12, d13, d14, d15):
        """
        QDS (Quotient Digit Selection) for Radix-16 division.

        This implementation uses a binary search tree structure for the selection
        logic, which reduces the critical path from 15 levels of cascaded muxes
        (in a priority encoder) to only 4 levels of muxes.

        Hardware Implementation Note:
        ============================
        In synthesized hardware, all 15 comparisons are computed in parallel
        (they are independent operations). The key optimization is in how the
        results are combined:

        - Old approach: 15-deep cascaded mux chain (priority encoder)
          - Critical path: 15 mux levels
          - q = ge_15d ? 15 : (ge_14d ? 14 : (ge_13d ? 13 : ...))

        - New approach: Binary search tree selection
          - Critical path: 4 mux levels
          - Each quotient bit computed with 2-level mux based on higher bits

        QDS Binary Search Tree:
        ======================
        Level 1: Compare with 8d (determines q[3] - MSB)
        Level 2: Compare with 4d or 12d (determines q[2])
        Level 3: Compare with 2d/6d/10d/14d (determines q[1])
        Level 4: Compare with odd multiples (determines q[0] - LSB)

        The comparisons themselves still use full-precision 36-bit values for
        correctness. The optimization is in the selection logic depth.

        Returns quotient digit from {0, 1, 2, ..., 15}.
        """
        # All comparisons computed in parallel (in hardware)
        # Level 1: MSB selection - compare with 8d
        ge_8d = (shifted_rem.bitcast(UInt(36)) >= d8.bitcast(UInt(36)))

        # Level 2: Second bit selection
        # If >= 8d, compare with 12d; else compare with 4d
        ge_12d = (shifted_rem.bitcast(UInt(36)) >= d12.bitcast(UInt(36)))
        ge_4d = (shifted_rem.bitcast(UInt(36)) >= d4.bitcast(UInt(36)))

        # Level 3: Third bit selection (6 comparisons total here for all paths)
        ge_14d = (shifted_rem.bitcast(UInt(36)) >= d14.bitcast(UInt(36)))
        ge_10d = (shifted_rem.bitcast(UInt(36)) >= d10.bitcast(UInt(36)))
        ge_6d = (shifted_rem.bitcast(UInt(36)) >= d6.bitcast(UInt(36)))
        ge_2d = (shifted_rem.bitcast(UInt(36)) >= d2.bitcast(UInt(36)))

        # Level 4: LSB selection (8 comparisons total here for precision)
        ge_15d = (shifted_rem.bitcast(UInt(36)) >= d15.bitcast(UInt(36)))
        ge_13d = (shifted_rem.bitcast(UInt(36)) >= d13.bitcast(UInt(36)))
        ge_11d = (shifted_rem.bitcast(UInt(36)) >= d11.bitcast(UInt(36)))
        ge_9d = (shifted_rem.bitcast(UInt(36)) >= d9.bitcast(UInt(36)))
        ge_7d = (shifted_rem.bitcast(UInt(36)) >= d7.bitcast(UInt(36)))
        ge_5d = (shifted_rem.bitcast(UInt(36)) >= d5.bitcast(UInt(36)))
        ge_3d = (shifted_rem.bitcast(UInt(36)) >= d3.bitcast(UInt(36)))
        ge_1d = (shifted_rem.bitcast(UInt(36)) >= d1.bitcast(UInt(36)))

        # Build quotient using binary search tree structure
        # q[3] = ge_8d
        q3 = ge_8d

        # q[2] depends on q[3]:
        # - If q[3]=1 (q>=8): q[2] = (q>=12), so q[2] = ge_12d
        # - If q[3]=0 (q<8):  q[2] = (q>=4), so q[2] = ge_4d
        q2 = ge_8d.select(ge_12d, ge_4d)

        # q[1] depends on (q[3], q[2]):
        # - q>=12: q[1] = (q>=14), so ge_14d
        # - 8<=q<12: q[1] = (q>=10), so ge_10d
        # - 4<=q<8: q[1] = (q>=6), so ge_6d
        # - q<4: q[1] = (q>=2), so ge_2d
        q1_high = ge_12d.select(ge_14d, ge_10d)  # For q >= 8
        q1_low = ge_4d.select(ge_6d, ge_2d)  # For q < 8
        q1 = ge_8d.select(q1_high, q1_low)

        # q[0] depends on (q[3], q[2], q[1]) - 8 cases:
        # Range 14-15: q[0] = ge_15d
        # Range 12-13: q[0] = ge_13d
        # Range 10-11: q[0] = ge_11d
        # Range 8-9:   q[0] = ge_9d
        # Range 6-7:   q[0] = ge_7d
        # Range 4-5:   q[0] = ge_5d
        # Range 2-3:   q[0] = ge_3d
        # Range 0-1:   q[0] = ge_1d

        # Build q0 using hierarchical selection
        # Upper half (q >= 8)
        q0_14_15 = ge_15d  # Range 14-15
        q0_12_13 = ge_13d  # Range 12-13
        q0_10_11 = ge_11d  # Range 10-11
        q0_8_9 = ge_9d  # Range 8-9

        # Lower half (q < 8)
        q0_6_7 = ge_7d  # Range 6-7
        q0_4_5 = ge_5d  # Range 4-5
        q0_2_3 = ge_3d  # Range 2-3
        q0_0_1 = ge_1d  # Range 0-1

        # Select within upper half (q >= 8)
        q0_upper_upper = ge_12d.select(
            ge_14d.select(q0_14_15, q0_12_13),  # q >= 12
            ge_10d.select(q0_10_11, q0_8_9)  # 8 <= q < 12
        )

        # Select within lower half (q < 8)
        q0_lower_upper = ge_4d.select(
            ge_6d.select(q0_6_7, q0_4_5),  # 4 <= q < 8
            ge_2d.select(q0_2_3, q0_0_1)  # q < 4
        )

        q0 = ge_8d.select(q0_upper_upper, q0_lower_upper)

        # Combine bits into 4-bit quotient digit
        # Using proper bit concatenation: q = {q3, q2, q1, q0}
        q = concat(
            concat(
                concat(
                    q3.select(Bits(1)(1), Bits(1)(0)),
                    q2.select(Bits(1)(1), Bits(1)(0))
                ),
                q1.select(Bits(1)(1), Bits(1)(0))
            ),
            q0.select(Bits(1)(1), Bits(1)(0))
        )

        return q

    def start_divide(self, dividend, divisor, is_signed, is_rem, rd=Bits(5)(0)):
        """
        Start a division operation.

        Args:
            dividend: 32-bit dividend (rs1)
            divisor: 32-bit divisor (rs2)
            is_signed: 1 for signed (DIV/REM), 0 for unsigned (DIVU/REMU)
            is_rem: 1 to return remainder, 0 to return quotient
            rd: Destination register (5-bit), defaults to 0
        """
        self.dividend_in[0] = dividend
        self.divisor_in[0] = divisor
        self.is_signed[0] = is_signed
        self.is_rem[0] = is_rem
        self.rd_in[0] = rd
        self.valid_in[0] = Bits(1)(1)
        self.busy[0] = Bits(1)(1)
        self.ready[0] = Bits(1)(0)
        self.error[0] = Bits(1)(0)

        debug_log("Radix16Divider: Start division, dividend=0x{:x}, divisor=0x{:x}, signed={}",
                  dividend,
                  divisor,
                  is_signed)

    def tick(self):
        """
        Execute one cycle of the Radix-16 state machine.
        Should be called every clock cycle.
        """

        # State: IDLE - Wait for valid signal and check for special cases
        with Condition(self.state[0] == self.IDLE):
            with Condition(self.valid_in[0] == Bits(1)(1)):
                # Check for special cases
                div_by_zero = (self.divisor_in[0] == Bits(32)(0))
                div_by_one = (self.divisor_in[0] == Bits(32)(1))

                with Condition(div_by_zero):
                    # Handle division by zero per RISC-V spec
                    self.state[0] = self.DIV_ERROR
                    self.valid_in[0] = Bits(1)(0)
                    debug_log("Radix16Divider: Division by zero detected")

                with Condition(~div_by_zero & div_by_one):
                    # Fast path for divisor = 1
                    self.state[0] = self.DIV_1
                    self.valid_in[0] = Bits(1)(0)
                    debug_log("Radix16Divider: Fast path (divisor=1)")

                with Condition(~div_by_zero & ~div_by_one):
                    # Normal division path - go to preprocessing
                    self.state[0] = self.DIV_PRE
                    self.valid_in[0] = Bits(1)(0)

                    # Convert to unsigned if signed
                    dividend_is_neg = self.is_signed[0] & self.dividend_in[0][31:31]
                    divisor_is_neg = self.is_signed[0] & self.divisor_in[0][31:31]

                    # Take absolute value if negative
                    dividend_abs = dividend_is_neg.select(
                        (~self.dividend_in[0] + Bits(32)(1)).bitcast(Bits(32)),
                        self.dividend_in[0]
                    )
                    divisor_abs = divisor_is_neg.select(
                        (~self.divisor_in[0] + Bits(32)(1)).bitcast(Bits(32)),
                        self.divisor_in[0]
                    )

                    self.dividend_r[0] = dividend_abs
                    self.divisor_r[0] = divisor_abs
                    self.div_sign[0] = concat(self.dividend_in[0][31:31], self.divisor_in[0][31:31])
                    self.sign_r[0] = self.is_signed[0]

                    debug_log("Radix16Divider: Starting normal division (DIV_PRE)")

        # State: DIV_ERROR - Handle division by zero
        with Condition(self.state[0] == self.DIV_ERROR):
            # Return RISC-V specified error values
            quotient_on_div0 = self.is_signed[0].select(
                Bits(32)(0xFFFFFFFF),  # -1 for signed
                Bits(32)(0xFFFFFFFF)  # 2^32-1 for unsigned (same bit pattern)
            )
            self.result[0] = self.is_rem[0].select(
                self.dividend_in[0],  # Remainder = dividend
                quotient_on_div0  # Quotient = -1 or 2^32-1
            )
            self.ready[0] = Bits(1)(1)
            self.rd_out[0] = self.rd_in[0]
            self.error[0] = Bits(1)(1)
            self.busy[0] = Bits(1)(0)
            self.state[0] = self.IDLE
            debug_log("Radix16Divider: Completed with division by zero error")

        # State: DIV_1 - Fast path for divisor = 1
        with Condition(self.state[0] == self.DIV_1):
            # Fast path: quotient is dividend, remainder is 0
            self.result[0] = self.is_rem[0].select(
                Bits(32)(0),  # Remainder = 0
                self.dividend_in[0]  # Quotient = dividend
            )
            self.ready[0] = Bits(1)(1)
            self.rd_out[0] = self.rd_in[0]
            self.busy[0] = Bits(1)(0)
            self.state[0] = self.IDLE
            debug_log("Radix16Divider: Completed via fast path (divisor=1)")

        # State: DIV_PRE - Preprocessing for Radix-16 division
        with Condition(self.state[0] == self.DIV_PRE):
            divisor = self.divisor_r[0]
            dividend = self.dividend_r[0]

            # Compute divisor multiples (36 bits to handle 15*d overflow)
            d_36 = concat(Bits(4)(0), divisor)  # 36-bit divisor

            # Compute 1d through 15d using efficient combinations
            d1_val = d_36
            d2_val = (d_36.bitcast(UInt(36)) << UInt(36)(1)).bitcast(Bits(36))  # 2*d
            d3_val = (d2_val.bitcast(UInt(36)) + d_36.bitcast(UInt(36))).bitcast(Bits(36))  # 3*d = 2d + d
            d4_val = (d_36.bitcast(UInt(36)) << UInt(36)(2)).bitcast(Bits(36))  # 4*d
            d5_val = (d4_val.bitcast(UInt(36)) + d_36.bitcast(UInt(36))).bitcast(Bits(36))  # 5*d = 4d + d
            d6_val = (d4_val.bitcast(UInt(36)) + d2_val.bitcast(UInt(36))).bitcast(Bits(36))  # 6*d = 4d + 2d
            d7_val = (d4_val.bitcast(UInt(36)) + d3_val.bitcast(UInt(36))).bitcast(Bits(36))  # 7*d = 4d + 3d
            d8_val = (d_36.bitcast(UInt(36)) << UInt(36)(3)).bitcast(Bits(36))  # 8*d
            d9_val = (d8_val.bitcast(UInt(36)) + d_36.bitcast(UInt(36))).bitcast(Bits(36))  # 9*d = 8d + d
            d10_val = (d8_val.bitcast(UInt(36)) + d2_val.bitcast(UInt(36))).bitcast(Bits(36))  # 10*d = 8d + 2d
            d11_val = (d8_val.bitcast(UInt(36)) + d3_val.bitcast(UInt(36))).bitcast(Bits(36))  # 11*d = 8d + 3d
            d12_val = (d8_val.bitcast(UInt(36)) + d4_val.bitcast(UInt(36))).bitcast(Bits(36))  # 12*d = 8d + 4d
            d13_val = (d8_val.bitcast(UInt(36)) + d5_val.bitcast(UInt(36))).bitcast(Bits(36))  # 13*d = 8d + 5d
            d14_val = (d8_val.bitcast(UInt(36)) + d6_val.bitcast(UInt(36))).bitcast(Bits(36))  # 14*d = 8d + 6d
            d15_val = (d8_val.bitcast(UInt(36)) + d7_val.bitcast(UInt(36))).bitcast(Bits(36))  # 15*d = 8d + 7d

            # Store divisor multiples
            self.d1[0] = d1_val
            self.d2[0] = d2_val
            self.d3[0] = d3_val
            self.d4[0] = d4_val
            self.d5[0] = d5_val
            self.d6[0] = d6_val
            self.d7[0] = d7_val
            self.d8[0] = d8_val
            self.d9[0] = d9_val
            self.d10[0] = d10_val
            self.d11[0] = d11_val
            self.d12[0] = d12_val
            self.d13[0] = d13_val
            self.d14[0] = d14_val
            self.d15[0] = d15_val

            # Initialize quotient to 0, remainder to 0
            self.quotient[0] = Bits(32)(0)
            self.remainder[0] = Bits(36)(0)

            # Initialize Q/QM for compatibility
            self.Q[0] = Bits(32)(0)
            self.QM[0] = Bits(32)(0)

            # For 32-bit division with 4 bits per iteration: ceil(32/4) = 8 iterations
            self.div_cnt[0] = Bits(5)(8)

            # Store dividend for iteration
            self.dividend_r[0] = dividend

            # Transition to DIV_WORKING
            self.state[0] = self.DIV_WORKING

            debug_log("Radix16Divider: Preprocessing complete, d1=0x{:x}, d15=0x{:x}",
                      d1_val, d15_val)

        # State: DIV_WORKING - Radix-16 iteration
        with Condition(self.state[0] == self.DIV_WORKING):
            # Get current values
            rem_cur = self.remainder[0]  # 36-bit partial remainder
            quot_cur = self.quotient[0]  # 32-bit quotient so far
            dividend_cur = self.dividend_r[0]  # Remaining dividend bits

            # Shift remainder left by 4 and bring in next 4 dividend bits
            # Bits come from MSB of dividend_cur
            next_bits = dividend_cur[28:31]  # Top 4 bits of dividend
            shifted_rem = concat(rem_cur[0:31], next_bits)  # (rem << 4) | next_bits

            # Shift dividend left by 4 (move next bits into position)
            new_dividend = concat(dividend_cur[0:27], Bits(4)(0))

            # Quotient digit selection using Radix-16 comparison
            q_digit = self.quotient_select(
                shifted_rem,
                self.d1[0], self.d2[0], self.d3[0], self.d4[0],
                self.d5[0], self.d6[0], self.d7[0], self.d8[0],
                self.d9[0], self.d10[0], self.d11[0], self.d12[0],
                self.d13[0], self.d14[0], self.d15[0]
            )

            # Compute new remainder based on quotient digit: rem = shifted_rem - q * d
            q_times_d = (q_digit == Bits(4)(0)).select(
                Bits(36)(0),
                (q_digit == Bits(4)(1)).select(
                    self.d1[0],
                    (q_digit == Bits(4)(2)).select(
                        self.d2[0],
                        (q_digit == Bits(4)(3)).select(
                            self.d3[0],
                            (q_digit == Bits(4)(4)).select(
                                self.d4[0],
                                (q_digit == Bits(4)(5)).select(
                                    self.d5[0],
                                    (q_digit == Bits(4)(6)).select(
                                        self.d6[0],
                                        (q_digit == Bits(4)(7)).select(
                                            self.d7[0],
                                            (q_digit == Bits(4)(8)).select(
                                                self.d8[0],
                                                (q_digit == Bits(4)(9)).select(
                                                    self.d9[0],
                                                    (q_digit == Bits(4)(10)).select(
                                                        self.d10[0],
                                                        (q_digit == Bits(4)(11)).select(
                                                            self.d11[0],
                                                            (q_digit == Bits(4)(12)).select(
                                                                self.d12[0],
                                                                (q_digit == Bits(4)(13)).select(
                                                                    self.d13[0],
                                                                    (q_digit == Bits(4)(14)).select(
                                                                        self.d14[0],
                                                                        self.d15[0]  # q=15
                                                                    )
                                                                )
                                                            )
                                                        )
                                                    )
                                                )
                                            )
                                        )
                                    )
                                )
                            )
                        )
                    )
                )
            )

            new_rem = (shifted_rem.bitcast(UInt(36)) - q_times_d.bitcast(UInt(36))).bitcast(Bits(36))

            # Update quotient: shift left by 4 and add new digit
            new_quot = concat(quot_cur[0:27], q_digit)

            # Store updated values
            self.remainder[0] = new_rem
            self.quotient[0] = new_quot
            self.dividend_r[0] = new_dividend
            self.Q[0] = new_quot  # For compatibility

            # Update shift_rem for compatibility
            self.shift_rem[0] = shifted_rem

            # Decrement counter
            self.div_cnt[0] = (self.div_cnt[0].bitcast(UInt(5)) - UInt(5)(1)).bitcast(Bits(5))

            debug_log("Radix16Divider: iter, shifted_rem=0x{:x}, q={}, new_rem=0x{:x}, new_quot=0x{:x}",
                      shifted_rem, q_digit, new_rem, new_quot)

            # Check if done
            is_last = (self.div_cnt[0] == Bits(5)(1))
            with Condition(is_last):
                self.state[0] = self.DIV_END
                debug_log("Radix16Divider: Last iteration complete")

        # State: DIV_END - Post-processing
        with Condition(self.state[0] == self.DIV_END):
            q_out = self.quotient[0]
            rem_out = self.remainder[0][0:31]  # Take lower 32 bits of remainder

            debug_log("Radix16Divider: DIV_END - quotient=0x{:x}, remainder=0x{:x}",
                      q_out, rem_out)

            # Apply sign correction
            q_needs_neg = (self.div_sign[0] == Bits(2)(0b01)) | (self.div_sign[0] == Bits(2)(0b10))
            rem_needs_neg = self.div_sign[0][1:1]

            debug_log("Radix16Divider: div_sign=0x{:x}, q_needs_neg={}", self.div_sign[0], q_needs_neg)

            # Check for signed overflow: (-2^31) / (-1)
            min_int = Bits(32)(0x80000000)
            neg_one = Bits(32)(0xFFFFFFFF)
            signed_overflow = (self.sign_r[0] == Bits(1)(1)) & \
                              (self.dividend_in[0] == min_int) & \
                              (self.divisor_in[0] == neg_one)

            with Condition(signed_overflow):
                self.result[0] = self.is_rem[0].select(
                    Bits(32)(0),
                    Bits(32)(0x80000000)
                )
                debug_log("Radix16Divider: Signed overflow detected (-2^31 / -1)")

            with Condition(~signed_overflow):
                q_signed = (self.sign_r[0] & q_needs_neg).select(
                    (~q_out + Bits(32)(1)).bitcast(Bits(32)),
                    q_out
                )
                rem_signed = (self.sign_r[0] & rem_needs_neg).select(
                    (~rem_out + Bits(32)(1)).bitcast(Bits(32)),
                    rem_out
                )

                debug_log("Radix16Divider: q_signed=0x{:x}, rem_signed=0x{:x}, is_rem={}",
                          q_signed, rem_signed, self.is_rem[0])

                self.result[0] = self.is_rem[0].select(rem_signed, q_signed)

            self.ready[0] = Bits(1)(1)
            self.rd_out[0] = self.rd_in[0]
            self.busy[0] = Bits(1)(0)
            self.state[0] = self.IDLE
            debug_log("Radix16Divider: Completed, result=0x{:x}", self.result[0])

    def get_result_if_ready(self):
        """
        Get result if division is complete.
        Returns: (ready, result, rd, error)
        """
        return (self.ready[0], self.result[0], self.rd_out[0], self.error[0])

    def clear_result(self):
        """Clear result and reset ready flag"""
        self.ready[0] = Bits(1)(0)


# Alias for backward compatibility
SRT4Divider = Radix16Divider