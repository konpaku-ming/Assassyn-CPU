"""
Radix-4 Restoring Divider Module for RV32IM Division Instructions

This module implements a radix-4 restoring division algorithm that computes
2 quotient bits per clock cycle. It's simpler than SRT-4 because it doesn't
require complex quotient selection tables.

Architecture Overview:
=====================

The radix-4 divider works similarly to the standard restoring divider but
processes 2 bits per cycle by comparing the partial remainder against
multiples of the divisor (0, d, 2d, 3d).

Timing:
- 1 cycle: Preprocessing (DIV_PRE) - convert to unsigned, detect special cases
- 16 cycles: Iterative calculation (DIV_WORKING) - 2 bits per cycle
- 1 cycle: Post-processing (DIV_END) - sign correction
- Total: ~18 cycles for normal division

Special cases handled with fast paths:
- DIV_ERROR: Division by zero (1 cycle)
- DIV_1: Divisor = 1 (1 cycle)

Algorithm:
==========
For unsigned division of 32-bit numbers:
1. Initialize: R = 0, Q = dividend
2. For i = 15 down to 0 (16 iterations):
   a. Shift R left by 2, bring in 2 MSBs from Q
   b. Q = Q << 2
   c. Compare R with 3*d, 2*d, d:
      - If R >= 3*d: R = R - 3*d, Q[1:0] = 11
      - Elif R >= 2*d: R = R - 2*d, Q[1:0] = 10
      - Elif R >= d: R = R - d, Q[1:0] = 01
      - Else: Q[1:0] = 00
3. Final: Q = quotient, R = remainder
"""

from assassyn.frontend import *


class SRT4Divider:
    """
    Radix-4 restoring division for 32-bit operands.

    The divider is a multi-cycle functional unit that takes ~18 cycles:
    - 1 cycle: Preprocessing (convert to unsigned, detect special cases)
    - 16 cycles: Iterative calculation (2 bits per cycle)
    - 1 cycle: Post-processing (sign correction)

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

        # Output results
        self.result = RegArray(Bits(32), 1, initializer=[0])
        self.ready = RegArray(Bits(1), 1, initializer=[0])
        self.error = RegArray(Bits(1), 1, initializer=[0])  # Division by zero

        # State machine registers
        self.state = RegArray(Bits(3), 1, initializer=[0])  # FSM state
        self.div_cnt = RegArray(Bits(5), 1, initializer=[0])  # Iteration counter

        # Internal working registers
        self.dividend_r = RegArray(Bits(32), 1, initializer=[0])  # Unsigned dividend
        self.divisor_r = RegArray(Bits(32), 1, initializer=[0])  # Unsigned divisor
        self.quotient = RegArray(Bits(32), 1, initializer=[0])  # Quotient accumulator
        self.remainder = RegArray(Bits(34), 1, initializer=[0])  # Remainder (34 bits for comparison)
        self.div_sign = RegArray(Bits(2), 1, initializer=[0])  # Sign bits {dividend[31], divisor[31]}
        self.sign_r = RegArray(Bits(1), 1, initializer=[0])  # Sign flag for result

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

    def start_divide(self, dividend, divisor, is_signed, is_rem):
        """
        Start a division operation.

        Args:
            dividend: 32-bit dividend (rs1)
            divisor: 32-bit divisor (rs2)
            is_signed: 1 for signed (DIV/REM), 0 for unsigned (DIVU/REMU)
            is_rem: 1 to return remainder, 0 to return quotient
        """
        self.dividend_in[0] = dividend
        self.divisor_in[0] = divisor
        self.is_signed[0] = is_signed
        self.is_rem[0] = is_rem
        self.valid_in[0] = Bits(1)(1)
        self.busy[0] = Bits(1)(1)
        self.ready[0] = Bits(1)(0)
        self.error[0] = Bits(1)(0)

        log("Divider: Start division, dividend=0x{:x}, divisor=0x{:x}, signed={}",
            dividend,
            divisor,
            is_signed)

    def tick(self):
        """
        Execute one cycle of the radix-4 state machine.
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
                    log("Divider: Division by zero detected")

                with Condition(~div_by_zero & div_by_one):
                    # Fast path for divisor = 1
                    self.state[0] = self.DIV_1
                    self.valid_in[0] = Bits(1)(0)
                    log("Divider: Fast path (divisor=1)")

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

                    log("Divider: Starting normal division (DIV_PRE)")

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
            self.error[0] = Bits(1)(1)
            self.busy[0] = Bits(1)(0)
            self.state[0] = self.IDLE
            log("Divider: Completed with division by zero error")

        # State: DIV_1 - Fast path for divisor = 1
        with Condition(self.state[0] == self.DIV_1):
            # Fast path: quotient is dividend, remainder is 0
            self.result[0] = self.is_rem[0].select(
                Bits(32)(0),  # Remainder = 0
                self.dividend_in[0]  # Quotient = dividend
            )
            self.ready[0] = Bits(1)(1)
            self.busy[0] = Bits(1)(0)
            self.state[0] = self.IDLE
            log("Divider: Completed via fast path (divisor=1)")

        # State: DIV_PRE - Preprocessing
        with Condition(self.state[0] == self.DIV_PRE):
            # Initialize for radix-4 restoring division
            # quotient starts as dividend (will be shifted out as we compute)
            # remainder starts as 0
            self.quotient[0] = self.dividend_r[0]
            self.remainder[0] = Bits(34)(0)

            # Initialize iteration counter (16 iterations for 32-bit / 2 bits per iteration)
            self.div_cnt[0] = Bits(5)(16)

            # Transition to DIV_WORKING
            self.state[0] = self.DIV_WORKING

            log("Divider: Preprocessing complete, starting 16 iterations")

        # State: DIV_WORKING - Iterative radix-4 restoring division
        with Condition(self.state[0] == self.DIV_WORKING):
            # Check if done FIRST (counter reaches 1, meaning this is the last iteration)
            # This must be checked before the iteration work so that the final iteration
            # is performed and then we transition to DIV_END
            with Condition(self.div_cnt[0] == Bits(5)(1)):
                self.state[0] = self.DIV_END
                log("Divider: Iterations complete, entering post-processing")

            # Radix-4 restoring division algorithm:
            # 1. Shift remainder left by 2 and bring in 2 MSBs from quotient
            # 2. Shift quotient left by 2
            # 3. Compare remainder with 3*d, 2*d, d and subtract the largest
            # 4. Set corresponding quotient bits

            # Step 1 & 2: Shift operations
            # Get 2 MSBs from quotient (bits 31 and 30)
            quotient_msbs = self.quotient[0][30:31]

            # Shift remainder left by 2 and bring in quotient MSBs
            # remainder = (remainder << 2) | quotient_msbs
            shifted_remainder = concat(self.remainder[0][0:31], quotient_msbs)

            # Shift quotient left by 2 (make room for new quotient bits)
            shifted_quotient = concat(self.quotient[0][0:29], Bits(2)(0))

            # Step 3: Compute divisor multiples (as 34-bit values for safe comparison)
            d1 = concat(Bits(2)(0), self.divisor_r[0])  # 1 * divisor
            d2 = concat(Bits(1)(0), self.divisor_r[0], Bits(1)(0))  # 2 * divisor (left shift by 1)
            d3 = (d1.bitcast(UInt(34)) + d2.bitcast(UInt(34))).bitcast(Bits(34))  # 3 * divisor

            # Step 4: Compare and select quotient digit
            # Check R >= 3*d, R >= 2*d, R >= d
            ge_3d = shifted_remainder >= d3
            ge_2d = shifted_remainder >= d2
            ge_1d = shifted_remainder >= d1

            # Compute new remainder and quotient bits for each case
            # Case: R >= 3*d
            rem_minus_3d = (shifted_remainder.bitcast(UInt(34)) - d3.bitcast(UInt(34))).bitcast(Bits(34))
            # Case: R >= 2*d
            rem_minus_2d = (shifted_remainder.bitcast(UInt(34)) - d2.bitcast(UInt(34))).bitcast(Bits(34))
            # Case: R >= d
            rem_minus_1d = (shifted_remainder.bitcast(UInt(34)) - d1.bitcast(UInt(34))).bitcast(Bits(34))

            # Select new remainder and quotient bits
            # Priority: 3d > 2d > d > 0
            new_remainder = ge_3d.select(
                rem_minus_3d,
                ge_2d.select(
                    rem_minus_2d,
                    ge_1d.select(
                        rem_minus_1d,
                        shifted_remainder  # No subtraction
                    )
                )
            )

            # Quotient bits: 11 if >= 3d, 10 if >= 2d, 01 if >= d, 00 otherwise
            q_bits = ge_3d.select(
                Bits(2)(0b11),
                ge_2d.select(
                    Bits(2)(0b10),
                    ge_1d.select(
                        Bits(2)(0b01),
                        Bits(2)(0b00)
                    )
                )
            )

            # Update registers
            self.remainder[0] = new_remainder
            self.quotient[0] = (shifted_quotient.bitcast(UInt(32)) | q_bits.bitcast(UInt(32))).bitcast(Bits(32))

            # Decrement counter LAST
            self.div_cnt[0] = (self.div_cnt[0].bitcast(UInt(5)) - Bits(5)(1)).bitcast(Bits(5))

        # State: DIV_END - Post-processing
        with Condition(self.state[0] == self.DIV_END):
            log("Divider: DIV_END - quotient=0x{:x}, remainder=0x{:x}",
                self.quotient[0], self.remainder[0][0:31])

            # Apply sign correction
            # For quotient: if signs differ, negate
            # For remainder: same sign as dividend
            q_needs_neg = (self.div_sign[0] == Bits(2)(0b01)) | (self.div_sign[0] == Bits(2)(0b10))
            rem_needs_neg = self.div_sign[0][1:1]  # Dividend sign

            log("Divider: div_sign=0x{:x}, q_needs_neg={}", self.div_sign[0], q_needs_neg)

            # Check for signed overflow: (-2^31) / (-1)
            min_int = Bits(32)(0x80000000)
            neg_one = Bits(32)(0xFFFFFFFF)
            signed_overflow = (self.sign_r[0] == Bits(1)(1)) & \
                              (self.dividend_in[0] == min_int) & \
                              (self.divisor_in[0] == neg_one)

            with Condition(signed_overflow):
                # Handle signed overflow per RISC-V spec
                self.result[0] = self.is_rem[0].select(
                    Bits(32)(0),  # Remainder = 0
                    Bits(32)(0x80000000)  # Quotient = -2^31 (no change)
                )
                log("Divider: Signed overflow detected (-2^31 / -1)")

            with Condition(~signed_overflow):
                # Normal result with sign correction
                q_signed = (self.sign_r[0] & q_needs_neg).select(
                    (~self.quotient[0] + Bits(32)(1)).bitcast(Bits(32)),
                    self.quotient[0]
                )
                rem_signed = (self.sign_r[0] & rem_needs_neg).select(
                    (~self.remainder[0][0:31] + Bits(32)(1)).bitcast(Bits(32)),
                    self.remainder[0][0:31]
                )

                log("Divider: q_signed=0x{:x}, rem_signed=0x{:x}, is_rem={}",
                    q_signed, rem_signed, self.is_rem[0])

                # Select quotient or remainder
                self.result[0] = self.is_rem[0].select(rem_signed, q_signed)

            self.ready[0] = Bits(1)(1)
            self.busy[0] = Bits(1)(0)
            self.state[0] = self.IDLE
            log("Divider: Completed, result=0x{:x}", self.result[0])

    def get_result_if_ready(self):
        """
        Get result if division is complete.
        Returns: (ready, result, error)
        """
        return (self.ready[0], self.result[0], self.error[0])

    def clear_result(self):
        """Clear result and reset ready flag"""
        self.ready[0] = Bits(1)(0)