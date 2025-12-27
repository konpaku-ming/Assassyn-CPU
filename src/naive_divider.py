"""
Naive Divider Module for RV32IM Division Instructions

This module implements the restoring division algorithm in Python/Assassyn.
It provides a native interface compatible with the Assassyn CPU pipeline.

Architecture Overview:
=====================

The restoring divider is a simple division algorithm that computes 1 quotient bit
per clock cycle. It uses a shift-subtract-restore approach to compute quotient
and remainder.

Timing:
- 1 cycle: Preprocessing (DIV_PRE) - convert to unsigned, check special cases
- 32 cycles: Iterative calculation (DIV_WORKING) - 1 bit per cycle
- 1 cycle: Post-processing (DIV_END) - sign correction
- Total: ~34 cycles for normal division

Special cases are handled with fast paths:
- DIV_ERROR: Division by zero (1 cycle)
- DIV_1: Divisor = 1 (1 cycle)

FSM States:
- IDLE: Wait for valid signal
- DIV_PRE: Preprocessing
- DIV_WORKING: Iterative restoring division calculation
- DIV_END: Post-processing
- DIV_1: Fast path for divisor = 1
- DIV_ERROR: Error handling for divisor = 0

Algorithm:
==========
For unsigned division of N-bit numbers:
1. Initialize: R = 0, Q = dividend
2. For i = N-1 down to 0:
   a. Shift R left by 1, shift Q[i] into R[0]
   b. R = R - divisor
   c. If R < 0 (negative):
      - R = R + divisor (restore)
      - Q[i] = 0
   d. Else:
      - Q[i] = 1
3. Final: Q = quotient, R = remainder
"""

from assassyn.frontend import *


class NaiveDivider:
    """
    Pure Python/Assassyn implementation of restoring division for 32-bit operands.
    
    The divider is a multi-cycle functional unit that takes ~34 cycles:
    - 1 cycle: Preprocessing (convert to unsigned, detect special cases)
    - 32 cycles: Iterative calculation (1 bit per cycle)
    - 1 cycle: Post-processing (sign correction)
    
    Pipeline Integration:
    - When a division instruction enters EX stage, the divider is started
    - The pipeline stalls (IF/ID/EX) until divider completes
    - Result is written back to register file through normal WB path
    
    Implementation Notes:
    - Implements restoring division: 1 bit per cycle
    - Uses shift-subtract-restore approach
    - Handles signed/unsigned division and remainder operations
    - Detects and handles special cases (div-by-zero, signed overflow)
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
        self.div_cnt = RegArray(Bits(6), 1, initializer=[0])  # Iteration counter (32 iterations)

        # Internal working registers for restoring division
        self.dividend_r = RegArray(Bits(32), 1, initializer=[0])  # Unsigned dividend
        self.divisor_r = RegArray(Bits(32), 1, initializer=[0])  # Unsigned divisor
        self.quotient = RegArray(Bits(32), 1, initializer=[0])  # Quotient accumulator
        self.remainder = RegArray(Bits(33), 1, initializer=[0])  # Remainder (33 bits to detect sign)
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

        log("NaiveDivider: Start division, dividend=0x{:x}, divisor=0x{:x}, signed={}",
            dividend,
            divisor,
            is_signed)

    def tick(self):
        """
        Execute one cycle of the restoring division state machine.
        Should be called every clock cycle.

        This implements the main FSM, including:
        - IDLE: Wait for valid signal, detect special cases
        - DIV_PRE: Preprocessing (convert to unsigned)
        - DIV_WORKING: Iterative restoring division (32 cycles)
        - DIV_END: Post-processing (sign correction)
        - DIV_1: Fast path for divisor = 1
        - DIV_ERROR: Handle division by zero
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
                    log("NaiveDivider: Division by zero detected")

                with Condition(~div_by_zero & div_by_one):
                    # Fast path for divisor = 1
                    self.state[0] = self.DIV_1
                    self.valid_in[0] = Bits(1)(0)
                    log("NaiveDivider: Fast path (divisor=1)")

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

                    log("NaiveDivider: Starting normal division (DIV_PRE)")

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
            log("NaiveDivider: Completed with division by zero error")

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
            log("NaiveDivider: Completed via fast path (divisor=1)")

        # State: DIV_PRE - Preprocessing
        with Condition(self.state[0] == self.DIV_PRE):
            # Initialize for restoring division
            # quotient starts as dividend, remainder starts as 0
            self.quotient[0] = self.dividend_r[0]
            self.remainder[0] = Bits(33)(0)
            
            # Initialize iteration counter (32 iterations for 32-bit)
            self.div_cnt[0] = Bits(6)(32)
            
            # Transition to DIV_WORKING
            self.state[0] = self.DIV_WORKING
            
            log("NaiveDivider: Preprocessing complete, starting 32 iterations")

        # State: DIV_WORKING - Iterative restoring division
        with Condition(self.state[0] == self.DIV_WORKING):
            # Restoring division algorithm:
            # 1. Shift remainder left by 1 and bring in next bit from quotient
            # 2. Subtract divisor from remainder
            # 3. If remainder is negative, restore it and set quotient bit to 0
            # 4. Otherwise, keep remainder and set quotient bit to 1
            
            # Step 1: Shift remainder left and bring in MSB of quotient
            # remainder = (remainder << 1) | (quotient >> 31)
            quotient_msb = self.quotient[0][31:31]
            # Shift remainder left by 1: remainder[0:31] become bits [1:32]
            # Then bring in quotient MSB at bit 0
            shifted_remainder = concat(self.remainder[0][0:31], quotient_msb)

            # Step 2: Subtract divisor from remainder
            # remainder = remainder - divisor (with sign extension for divisor)
            divisor_extended = concat(Bits(1)(0), self.divisor_r[0])
            temp_remainder = (shifted_remainder.bitcast(UInt(33)) - divisor_extended.bitcast(UInt(33))).bitcast(Bits(33))

            # Step 3: Check if result is negative (MSB = 1)
            is_negative = temp_remainder[32:32]

            # Pre-compute quotient updates outside conditional blocks
            # This avoids issues with slice operations inside Condition blocks
            quotient_lower_bits = self.quotient[0][0:30]
            new_quotient_if_neg = concat(quotient_lower_bits, Bits(1)(0))
            new_quotient_if_pos = concat(quotient_lower_bits, Bits(1)(1))

            with Condition(is_negative == Bits(1)(1)):
                # Restore: add divisor back
                self.remainder[0] = shifted_remainder
                # Shift quotient left and insert 0: quotient = (quotient << 1) | 0
                self.quotient[0] = new_quotient_if_neg

            with Condition(is_negative != Bits(1)(1)):
                # Keep subtraction result
                self.remainder[0] = temp_remainder
                # Shift quotient left and insert 1: quotient = (quotient << 1) | 1
                self.quotient[0] = new_quotient_if_pos

            # Decrement counter
            self.div_cnt[0] = (self.div_cnt[0].bitcast(UInt(6)) - Bits(6)(1)).bitcast(Bits(6))

            # Check if done (counter reaches 0)
            with Condition(self.div_cnt[0] == Bits(6)(0)):
                self.state[0] = self.DIV_END
                log("NaiveDivider: Iterations complete, entering post-processing")

        # State: DIV_END - Post-processing
        with Condition(self.state[0] == self.DIV_END):
            log("NaiveDivider: DIV_END - quotient=0x{:x}, remainder=0x{:x}",
                self.quotient[0], self.remainder[0][0:31])

            # Apply sign correction
            # For quotient: if signs differ, negate
            # For remainder: same sign as dividend
            q_needs_neg = (self.div_sign[0] == Bits(2)(0b01)) | (self.div_sign[0] == Bits(2)(0b10))
            rem_needs_neg = self.div_sign[0][1:1]  # Dividend sign

            log("NaiveDivider: div_sign=0x{:x}, q_needs_neg={}", self.div_sign[0], q_needs_neg)

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
                log("NaiveDivider: Signed overflow detected (-2^31 / -1)")

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

                log("NaiveDivider: q_signed=0x{:x}, rem_signed=0x{:x}, is_rem={}",
                    q_signed, rem_signed, self.is_rem[0])

                # Select quotient or remainder
                self.result[0] = self.is_rem[0].select(rem_signed, q_signed)

            self.ready[0] = Bits(1)(1)
            self.busy[0] = Bits(1)(0)
            self.state[0] = self.IDLE
            log("NaiveDivider: Completed, result=0x{:x}", self.result[0])

    def get_result_if_ready(self):
        """
        Get result if division is complete.
        Returns: (ready, result, error)
        """
        return (self.ready[0], self.result[0], self.error[0])

    def clear_result(self):
        """Clear result and reset ready flag"""
        self.ready[0] = Bits(1)(0)