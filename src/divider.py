"""
Radix-8 Divider for RV32IM Division Instructions

This module implements a Radix-8 division algorithm that produces 3 bits
of quotient per iteration.

Architecture Overview:
=====================

The Radix-8 divider uses:
1. Quotient digit set {0, 1, 2, 3, 4, 5, 6, 7}
2. Comparison against 7d, 6d, 5d, 4d, 3d, 2d, d for quotient selection
3. 3 bits of quotient per cycle

Key Radix-8 Features:
- 3 bits of quotient per iteration (vs 2 bits for Radix-4)
- Fixed 11 iterations for 32-bit division
- Simple comparison-based quotient selection

Timing:
- 1 cycle: Preprocessing (DIV_PRE)
- 11 cycles: Iterative calculation (DIV_WORKING) - 3 bits per cycle
- 1 cycle: Post-processing (DIV_END)
- Total: ~13 cycles for normal division

Special cases handled with fast paths:
- DIV_ERROR: Division by zero (1 cycle)
- DIV_1: Divisor = 1 (1 cycle)
"""

from assassyn.frontend import *
from .debug_utils import debug_log


class Radix8Divider:
    """
    Radix-8 division implementation that produces 3 bits of quotient per iteration.

    The divider is a multi-cycle functional unit that takes ~13 cycles:
    - 1 cycle: Preprocessing
    - 11 cycles: Iterative calculation (3 bits per cycle)
    - 1 cycle: Post-processing

    Key Radix-8 features:
    - Quotient digit set {0, 1, 2, 3, 4, 5, 6, 7}
    - Comparison against 7d, 6d, 5d, 4d, 3d, 2d, d
    - 3 bits of quotient per iteration
    - Fixed 11 iterations for 32-bit division

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
        
        # Radix-8 specific registers
        self.quotient = RegArray(Bits(32), 1, initializer=[0])  # Quotient accumulator
        self.remainder = RegArray(Bits(35), 1, initializer=[0])  # Partial remainder (35 bits)
        
        # Divisor multiples (computed in DIV_PRE)
        self.d1 = RegArray(Bits(35), 1, initializer=[0])  # 1*d
        self.d2 = RegArray(Bits(35), 1, initializer=[0])  # 2*d
        self.d3 = RegArray(Bits(35), 1, initializer=[0])  # 3*d
        self.d4 = RegArray(Bits(35), 1, initializer=[0])  # 4*d
        self.d5 = RegArray(Bits(35), 1, initializer=[0])  # 5*d
        self.d6 = RegArray(Bits(35), 1, initializer=[0])  # 6*d
        self.d7 = RegArray(Bits(35), 1, initializer=[0])  # 7*d

        # Sign tracking for final correction
        self.div_sign = RegArray(Bits(2), 1, initializer=[0])  # Sign bits {dividend[31], divisor[31]}
        self.sign_r = RegArray(Bits(1), 1, initializer=[0])  # Sign flag for result
        
        # Compatibility registers for tests
        self.div_shift = RegArray(Bits(6), 1, initializer=[0])  # Not used in Radix-8
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

    def quotient_select(self, shifted_rem, d1, d2, d3, d4, d5, d6, d7):
        """
        Radix-8 quotient digit selection.
        Compare shifted remainder against multiples of divisor.
        Returns quotient digit from {0, 1, 2, 3, 4, 5, 6, 7}.
        """
        # Compare shifted_rem >= 7d, 6d, 5d, 4d, 3d, 2d, d
        ge_7d = (shifted_rem.bitcast(UInt(35)) >= d7.bitcast(UInt(35)))
        ge_6d = (shifted_rem.bitcast(UInt(35)) >= d6.bitcast(UInt(35)))
        ge_5d = (shifted_rem.bitcast(UInt(35)) >= d5.bitcast(UInt(35)))
        ge_4d = (shifted_rem.bitcast(UInt(35)) >= d4.bitcast(UInt(35)))
        ge_3d = (shifted_rem.bitcast(UInt(35)) >= d3.bitcast(UInt(35)))
        ge_2d = (shifted_rem.bitcast(UInt(35)) >= d2.bitcast(UInt(35)))
        ge_1d = (shifted_rem.bitcast(UInt(35)) >= d1.bitcast(UInt(35)))
        
        # Select quotient digit based on comparison results
        q = ge_7d.select(
            Bits(3)(7),
            ge_6d.select(
                Bits(3)(6),
                ge_5d.select(
                    Bits(3)(5),
                    ge_4d.select(
                        Bits(3)(4),
                        ge_3d.select(
                            Bits(3)(3),
                            ge_2d.select(
                                Bits(3)(2),
                                ge_1d.select(
                                    Bits(3)(1),
                                    Bits(3)(0)
                                )
                            )
                        )
                    )
                )
            )
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

        debug_log("Radix8Divider: Start division, dividend=0x{:x}, divisor=0x{:x}, signed={}",
            dividend,
            divisor,
            is_signed)

    def tick(self):
        """
        Execute one cycle of the Radix-8 state machine.
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
                    debug_log("Radix8Divider: Division by zero detected")

                with Condition(~div_by_zero & div_by_one):
                    # Fast path for divisor = 1
                    self.state[0] = self.DIV_1
                    self.valid_in[0] = Bits(1)(0)
                    debug_log("Radix8Divider: Fast path (divisor=1)")

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

                    debug_log("Radix8Divider: Starting normal division (DIV_PRE)")

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
            debug_log("Radix8Divider: Completed with division by zero error")

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
            debug_log("Radix8Divider: Completed via fast path (divisor=1)")

        # State: DIV_PRE - Preprocessing for Radix-8 division
        with Condition(self.state[0] == self.DIV_PRE):
            divisor = self.divisor_r[0]
            dividend = self.dividend_r[0]
            
            # Compute divisor multiples (35 bits to handle 7*d overflow)
            d_35 = concat(Bits(3)(0), divisor)  # 35-bit divisor
            
            # Compute 1d through 7d
            d1_val = d_35
            d2_val = (d_35.bitcast(UInt(35)) << UInt(35)(1)).bitcast(Bits(35))  # 2*d
            d3_val = (d_35.bitcast(UInt(35)) + d2_val.bitcast(UInt(35))).bitcast(Bits(35))  # 3*d
            d4_val = (d_35.bitcast(UInt(35)) << UInt(35)(2)).bitcast(Bits(35))  # 4*d
            d5_val = (d4_val.bitcast(UInt(35)) + d_35.bitcast(UInt(35))).bitcast(Bits(35))  # 5*d
            d6_val = (d4_val.bitcast(UInt(35)) + d2_val.bitcast(UInt(35))).bitcast(Bits(35))  # 6*d
            d7_val = (d4_val.bitcast(UInt(35)) + d3_val.bitcast(UInt(35))).bitcast(Bits(35))  # 7*d
            
            # Store divisor multiples
            self.d1[0] = d1_val
            self.d2[0] = d2_val
            self.d3[0] = d3_val
            self.d4[0] = d4_val
            self.d5[0] = d5_val
            self.d6[0] = d6_val
            self.d7[0] = d7_val
            
            # Initialize quotient to 0, remainder to 0
            self.quotient[0] = Bits(32)(0)
            self.remainder[0] = Bits(35)(0)
            
            # Initialize Q/QM for compatibility
            self.Q[0] = Bits(32)(0)
            self.QM[0] = Bits(32)(0)
            
            # For 32-bit division with 3 bits per iteration: ceil(32/3) = 11 iterations
            self.div_cnt[0] = Bits(5)(11)
            
            # Store dividend for iteration
            self.dividend_r[0] = dividend
            
            # Transition to DIV_WORKING
            self.state[0] = self.DIV_WORKING
            
            debug_log("Radix8Divider: Preprocessing complete, d1=0x{:x}, d7=0x{:x}",
                d1_val, d7_val)

        # State: DIV_WORKING - Radix-8 iteration
        with Condition(self.state[0] == self.DIV_WORKING):
            # Get current values
            rem_cur = self.remainder[0]  # 35-bit partial remainder
            quot_cur = self.quotient[0]  # 32-bit quotient so far
            dividend_cur = self.dividend_r[0]  # Remaining dividend bits
            
            # Shift remainder left by 3 and bring in next 3 dividend bits
            # Bits come from MSB of dividend_cur
            next_bits = dividend_cur[29:31]  # Top 3 bits of dividend
            shifted_rem = concat(rem_cur[0:31], next_bits)  # (rem << 3) | next_bits
            
            # Shift dividend left by 3 (move next bits into position)
            new_dividend = concat(dividend_cur[0:28], Bits(3)(0))
            
            # Quotient digit selection
            q_digit = self.quotient_select(
                shifted_rem,
                self.d1[0], self.d2[0], self.d3[0], self.d4[0],
                self.d5[0], self.d6[0], self.d7[0]
            )
            
            # Compute new remainder based on quotient digit
            # rem = shifted_rem - q * d
            q_times_d = (q_digit == Bits(3)(0)).select(
                Bits(35)(0),
                (q_digit == Bits(3)(1)).select(
                    self.d1[0],
                    (q_digit == Bits(3)(2)).select(
                        self.d2[0],
                        (q_digit == Bits(3)(3)).select(
                            self.d3[0],
                            (q_digit == Bits(3)(4)).select(
                                self.d4[0],
                                (q_digit == Bits(3)(5)).select(
                                    self.d5[0],
                                    (q_digit == Bits(3)(6)).select(
                                        self.d6[0],
                                        self.d7[0]  # q=7
                                    )
                                )
                            )
                        )
                    )
                )
            )
            
            new_rem = (shifted_rem.bitcast(UInt(35)) - q_times_d.bitcast(UInt(35))).bitcast(Bits(35))
            
            # Update quotient: shift left by 3 and add new digit
            new_quot = concat(quot_cur[0:28], q_digit)
            
            # Store updated values
            self.remainder[0] = new_rem
            self.quotient[0] = new_quot
            self.dividend_r[0] = new_dividend
            self.Q[0] = new_quot  # For compatibility
            
            # Update shift_rem for compatibility
            self.shift_rem[0] = concat(Bits(1)(0), shifted_rem)
            
            # Decrement counter
            self.div_cnt[0] = (self.div_cnt[0].bitcast(UInt(5)) - UInt(5)(1)).bitcast(Bits(5))
            
            debug_log("Radix8Divider: iter, shifted_rem=0x{:x}, q={}, new_rem=0x{:x}, new_quot=0x{:x}",
                shifted_rem, q_digit, new_rem, new_quot)
            
            # Check if done
            is_last = (self.div_cnt[0] == Bits(5)(1))
            with Condition(is_last):
                self.state[0] = self.DIV_END
                debug_log("Radix8Divider: Last iteration complete")

        # State: DIV_END - Post-processing
        with Condition(self.state[0] == self.DIV_END):
            q_out = self.quotient[0]
            rem_out = self.remainder[0][0:31]  # Take lower 32 bits of remainder
            
            debug_log("Radix8Divider: DIV_END - quotient=0x{:x}, remainder=0x{:x}",
                q_out, rem_out)

            # Apply sign correction
            q_needs_neg = (self.div_sign[0] == Bits(2)(0b01)) | (self.div_sign[0] == Bits(2)(0b10))
            rem_needs_neg = self.div_sign[0][1:1]

            debug_log("Radix8Divider: div_sign=0x{:x}, q_needs_neg={}", self.div_sign[0], q_needs_neg)

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
                debug_log("Radix8Divider: Signed overflow detected (-2^31 / -1)")

            with Condition(~signed_overflow):
                q_signed = (self.sign_r[0] & q_needs_neg).select(
                    (~q_out + Bits(32)(1)).bitcast(Bits(32)),
                    q_out
                )
                rem_signed = (self.sign_r[0] & rem_needs_neg).select(
                    (~rem_out + Bits(32)(1)).bitcast(Bits(32)),
                    rem_out
                )

                debug_log("Radix8Divider: q_signed=0x{:x}, rem_signed=0x{:x}, is_rem={}",
                    q_signed, rem_signed, self.is_rem[0])

                self.result[0] = self.is_rem[0].select(rem_signed, q_signed)

            self.ready[0] = Bits(1)(1)
            self.rd_out[0] = self.rd_in[0]
            self.busy[0] = Bits(1)(0)
            self.state[0] = self.IDLE
            debug_log("Radix8Divider: Completed, result=0x{:x}", self.result[0])

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
SRT4Divider = Radix8Divider