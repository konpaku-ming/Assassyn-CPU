"""
SRT-4 Divider Module for RV32IM Division Instructions

This module implements a true SRT-4 (Sweeney-Robertson-Tocher) division algorithm
that computes 2 quotient bits per clock cycle using a redundant digit set.

Architecture Overview:
=====================

SRT-4 division uses a redundant quotient digit set {-2, -1, 0, 1, 2}, which allows
for simpler hardware compared to Radix-4 restoring division because:
1. No need to compute 3×divisor (only need d and 2d)
2. Quotient selection based on partial remainder estimate (no full comparison)

The key difference from Radix-4 restoring:
- Radix-4 restoring: digits {0, 1, 2, 3}, requires computing 3d
- SRT-4: digits {-2, -1, 0, 1, 2}, requires only d and 2d

Since the quotient can have negative digits, we use on-the-fly conversion
to accumulate the final binary quotient using Q and QM registers.

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
1. Initialize: w = 0 (partial remainder), Q = 0, QM = -1, bring in dividend bits
2. For i = 15 down to 0 (16 iterations):
   a. w_shifted = (w << 2) | next 2 bits from dividend
   b. Select quotient digit q from {-2, -1, 0, 1, 2} based on w_shifted vs d, 2d
   c. w = w_shifted - q * d
   d. Update Q and QM using on-the-fly conversion
3. Final: If w < 0, quotient = QM, else quotient = Q

On-the-fly conversion:
- Q: quotient if all remaining digits are >= 0
- QM: quotient if current digit were decremented by 1
- For q >= 0: new_Q = 4*Q + q, new_QM = 4*Q + (q-1)
- For q < 0:  new_Q = 4*QM + (4+q), new_QM = 4*QM + (4+q-1)
"""

from assassyn.frontend import *
from .debug_utils import debug_log


class SRT4Divider:
    """
    SRT-4 division for 32-bit operands with redundant quotient digits.

    The divider is a multi-cycle functional unit that takes ~18 cycles:
    - 1 cycle: Preprocessing (convert to unsigned, detect special cases)
    - 16 cycles: Iterative calculation (2 bits per cycle)
    - 1 cycle: Post-processing (sign correction, quotient finalization)

    Key differences from Radix-4 restoring:
    - Uses redundant digit set {-2, -1, 0, 1, 2}
    - Only needs d and 2d (not 3d)
    - Uses on-the-fly conversion for quotient accumulation
    - Partial remainder can be negative (uses signed arithmetic)

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
        self.div_cnt = RegArray(Bits(5), 1, initializer=[0])  # Iteration counter

        # Internal working registers
        self.dividend_r = RegArray(Bits(32), 1, initializer=[0])  # Unsigned dividend (for shifting in)
        self.divisor_r = RegArray(Bits(32), 1, initializer=[0])  # Unsigned divisor
        
        # SRT-4 specific registers
        # Partial remainder: 35 bits signed to handle range [-2d, 2d)
        self.shift_rem = RegArray(Bits(35), 1, initializer=[0])
        self.partial_rem = self.shift_rem  # Alias for compatibility
        
        # On-the-fly conversion registers
        self.Q = RegArray(Bits(32), 1, initializer=[0])   # Quotient (assuming remaining digits >= 0)
        self.QM = RegArray(Bits(32), 1, initializer=[0])  # Quotient minus 1
        
        # For test compatibility
        self.div_shift = RegArray(Bits(6), 1, initializer=[0])
        
        # Legacy compatibility (kept but not used in SRT-4)
        self.quotient = self.Q      # Alias
        self.remainder = self.shift_rem  # Alias (will use lower bits)
        
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
    
    # Helper methods for test compatibility
    def find_leading_one(self, value):
        """Find position of leading 1 bit (for test compatibility)"""
        result = Bits(6)(32)
        for i in range(31, -1, -1):
            bit_set = value[i:i] == Bits(1)(1)
            result = bit_set.select(Bits(6)(i), result)
        return result
    
    def power_of_2(self, shift_amt):
        """Generate 2^shift_amt (for test compatibility)"""
        result = Bits(32)(1)
        for i in range(32):
            is_this_shift = (shift_amt == Bits(6)(i))
            result = is_this_shift.select(Bits(32)(1 << i), result)
        return result
    
    def quotient_select(self, w_high):
        """Alias for quotient_digit_select (for test compatibility)"""
        return self.quotient_digit_select(w_high)
    
    def quotient_digit_select(self, shifted_rem, d1, d2):
        """
        SRT-4 Quotient Digit Selection.
        
        Selects quotient digit q from {-2, -1, 0, 1, 2} based on comparing
        the shifted partial remainder with multiples of divisor.
        
        Selection logic:
        - If shifted_rem >= 2d: q = +2
        - Elif shifted_rem >= d: q = +1
        - Elif shifted_rem >= 0: q = 0
        - Elif shifted_rem >= -d: q = -1 (i.e., shifted_rem + d >= 0)
        - Else: q = -2
        
        Returns:
        - q_digit: 3-bit encoded digit (010=+2, 001=+1, 000=0, 111=-1, 110=-2)
        - is_q_pos2, is_q_pos1, is_q_zero, is_q_neg1, is_q_neg2: individual flags
        """
        # Check sign of partial remainder
        rem_sign = shifted_rem[34:34]  # Sign bit
        is_negative = (rem_sign == Bits(1)(1))
        is_non_negative = (rem_sign == Bits(1)(0))
        
        # Comparisons for non-negative remainder
        ge_2d = is_non_negative & (shifted_rem >= d2)
        ge_d = is_non_negative & (shifted_rem >= d1)
        
        # For negative remainder, check if adding d makes it non-negative
        # shifted_rem + d >= 0  means shifted_rem >= -d
        rem_plus_d = (shifted_rem.bitcast(UInt(35)) + d1.bitcast(UInt(35))).bitcast(Bits(35))
        rem_plus_d_sign = rem_plus_d[34:34]
        ge_neg_d = is_negative & (rem_plus_d_sign == Bits(1)(0))  # shifted_rem >= -d
        
        # Select quotient digit
        is_q_pos2 = ge_2d
        is_q_pos1 = ~ge_2d & ge_d
        is_q_zero = is_non_negative & ~ge_d
        is_q_neg1 = is_negative & ge_neg_d
        is_q_neg2 = is_negative & ~ge_neg_d
        
        return (is_q_pos2, is_q_pos1, is_q_zero, is_q_neg1, is_q_neg2)

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

        debug_log("SRT4Divider: Start division, dividend=0x{:x}, divisor=0x{:x}, signed={}",
            dividend,
            divisor,
            is_signed)

    def tick(self):
        """
        Execute one cycle of the SRT-4 state machine.
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
                    debug_log("SRT4Divider: Division by zero detected")

                with Condition(~div_by_zero & div_by_one):
                    # Fast path for divisor = 1
                    self.state[0] = self.DIV_1
                    self.valid_in[0] = Bits(1)(0)
                    debug_log("SRT4Divider: Fast path (divisor=1)")

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

                    debug_log("SRT4Divider: Starting normal division (DIV_PRE)")

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
            debug_log("SRT4Divider: Completed with division by zero error")

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
            debug_log("SRT4Divider: Completed via fast path (divisor=1)")

        # State: DIV_PRE - Preprocessing for SRT-4
        with Condition(self.state[0] == self.DIV_PRE):
            # Initialize for SRT-4 division
            # Partial remainder starts as 0, dividend bits will be shifted in
            self.partial_rem[0] = Bits(35)(0)
            
            # On-the-fly conversion: Q starts at 0, QM starts at -1 (all 1s)
            self.Q[0] = Bits(32)(0)
            self.QM[0] = Bits(32)(0xFFFFFFFF)
            
            # Dividend will be shifted in 2 bits at a time
            # No change to dividend_r needed, we read from it during iterations
            
            # Initialize iteration counter (16 iterations for 32-bit / 2 bits per iteration)
            self.div_cnt[0] = Bits(5)(16)

            # Transition to DIV_WORKING
            self.state[0] = self.DIV_WORKING

            debug_log("SRT4Divider: Preprocessing complete, starting 16 iterations")

        # State: DIV_WORKING - Iterative SRT-4 division
        with Condition(self.state[0] == self.DIV_WORKING):
            # Check if done (counter reaches 1, meaning this is the last iteration)
            with Condition(self.div_cnt[0] == Bits(5)(1)):
                self.state[0] = self.DIV_END
                debug_log("SRT4Divider: Iterations complete, entering post-processing")

            # SRT-4 algorithm per iteration:
            # 1. Shift partial remainder left by 2, bring in next 2 dividend bits
            # 2. Select quotient digit q from {-2, -1, 0, 1, 2}
            # 3. Compute new partial remainder: w = 4*w + next_bits - q*d
            # 4. Update Q and QM using on-the-fly conversion

            # Step 1: Shift partial remainder left by 2 and bring in dividend bits
            # Get 2 MSBs from dividend (bits 31 and 30)
            dividend_msbs = self.dividend_r[0][30:31]
            
            # Shift partial remainder left by 2 and add dividend bits
            # shifted_rem = (partial_rem << 2) | dividend_msbs
            shifted_rem = concat(self.partial_rem[0][0:32], dividend_msbs)
            
            # Shift dividend left by 2 for next iteration
            shifted_dividend = concat(self.dividend_r[0][0:29], Bits(2)(0))

            # Step 2 & 3: Quotient digit selection and partial remainder update
            # Compute divisor multiples (as 35-bit values for signed comparison)
            d1 = concat(Bits(3)(0), self.divisor_r[0])  # 1 * divisor, positive
            d2 = concat(Bits(2)(0), self.divisor_r[0], Bits(1)(0))  # 2 * divisor
            
            # Get quotient digit selection flags
            (is_q_pos2, is_q_pos1, is_q_zero, is_q_neg1, is_q_neg2) = \
                self.quotient_digit_select(shifted_rem, d1, d2)
            
            # Compute new partial remainder based on selected digit
            # For q = +2: new_rem = shifted_rem - 2d
            # For q = +1: new_rem = shifted_rem - d
            # For q = 0:  new_rem = shifted_rem
            # For q = -1: new_rem = shifted_rem + d
            # For q = -2: new_rem = shifted_rem + 2d
            
            rem_minus_2d = (shifted_rem.bitcast(UInt(35)) - d2.bitcast(UInt(35))).bitcast(Bits(35))
            rem_minus_d = (shifted_rem.bitcast(UInt(35)) - d1.bitcast(UInt(35))).bitcast(Bits(35))
            rem_plus_d = (shifted_rem.bitcast(UInt(35)) + d1.bitcast(UInt(35))).bitcast(Bits(35))
            rem_plus_2d = (shifted_rem.bitcast(UInt(35)) + d2.bitcast(UInt(35))).bitcast(Bits(35))
            
            new_rem = is_q_pos2.select(
                rem_minus_2d,
                is_q_pos1.select(
                    rem_minus_d,
                    is_q_neg2.select(
                        rem_plus_2d,
                        is_q_neg1.select(
                            rem_plus_d,
                            shifted_rem  # q = 0
                        )
                    )
                )
            )

            # Step 4: On-the-fly quotient conversion
            # Q and QM are updated based on the selected digit
            Q_shifted = concat(self.Q[0][0:29], Bits(2)(0))  # Q << 2
            QM_shifted = concat(self.QM[0][0:29], Bits(2)(0))  # QM << 2
            
            # For q >= 0: new_Q = 4*Q + q, new_QM = 4*Q + (q-1)
            # For q < 0:  new_Q = 4*QM + (4+q), new_QM = 4*QM + (4+q-1)
            
            # q = +2: new_Q = 4*Q + 2, new_QM = 4*Q + 1
            new_Q_pos2 = (Q_shifted.bitcast(UInt(32)) + Bits(32)(2).bitcast(UInt(32))).bitcast(Bits(32))
            new_QM_pos2 = (Q_shifted.bitcast(UInt(32)) + Bits(32)(1).bitcast(UInt(32))).bitcast(Bits(32))
            
            # q = +1: new_Q = 4*Q + 1, new_QM = 4*Q + 0
            new_Q_pos1 = (Q_shifted.bitcast(UInt(32)) + Bits(32)(1).bitcast(UInt(32))).bitcast(Bits(32))
            new_QM_pos1 = Q_shifted
            
            # q = 0: new_Q = 4*Q + 0, new_QM = 4*Q - 1 = 4*QM + 3
            new_Q_zero = Q_shifted
            new_QM_zero = (QM_shifted.bitcast(UInt(32)) + Bits(32)(3).bitcast(UInt(32))).bitcast(Bits(32))
            
            # q = -1: new_Q = 4*QM + 3, new_QM = 4*QM + 2
            new_Q_neg1 = (QM_shifted.bitcast(UInt(32)) + Bits(32)(3).bitcast(UInt(32))).bitcast(Bits(32))
            new_QM_neg1 = (QM_shifted.bitcast(UInt(32)) + Bits(32)(2).bitcast(UInt(32))).bitcast(Bits(32))
            
            # q = -2: new_Q = 4*QM + 2, new_QM = 4*QM + 1
            new_Q_neg2 = (QM_shifted.bitcast(UInt(32)) + Bits(32)(2).bitcast(UInt(32))).bitcast(Bits(32))
            new_QM_neg2 = (QM_shifted.bitcast(UInt(32)) + Bits(32)(1).bitcast(UInt(32))).bitcast(Bits(32))
            
            # Select new Q
            new_Q = is_q_pos2.select(
                new_Q_pos2,
                is_q_pos1.select(
                    new_Q_pos1,
                    is_q_zero.select(
                        new_Q_zero,
                        is_q_neg1.select(
                            new_Q_neg1,
                            new_Q_neg2
                        )
                    )
                )
            )
            
            # Select new QM
            new_QM = is_q_pos2.select(
                new_QM_pos2,
                is_q_pos1.select(
                    new_QM_pos1,
                    is_q_zero.select(
                        new_QM_zero,
                        is_q_neg1.select(
                            new_QM_neg1,
                            new_QM_neg2
                        )
                    )
                )
            )

            # Update registers
            self.partial_rem[0] = new_rem
            self.dividend_r[0] = shifted_dividend
            self.Q[0] = new_Q
            self.QM[0] = new_QM

            # Decrement counter
            self.div_cnt[0] = (self.div_cnt[0].bitcast(UInt(5)) - Bits(5)(1)).bitcast(Bits(5))

        # State: DIV_END - Post-processing
        with Condition(self.state[0] == self.DIV_END):
            debug_log("SRT4Divider: DIV_END - Q=0x{:x}, QM=0x{:x}, partial_rem=0x{:x}",
                self.Q[0], self.QM[0], self.partial_rem[0])

            # Final quotient selection
            # If partial remainder is negative, use QM, else use Q
            rem_sign = self.partial_rem[0][34:34]
            raw_quotient = rem_sign.select(self.QM[0], self.Q[0])
            
            # Compute remainder
            # If rem_sign is 1 (negative), add divisor to get positive remainder
            d_ext = concat(Bits(3)(0), self.divisor_r[0])
            corrected_rem = rem_sign.select(
                (self.partial_rem[0].bitcast(UInt(35)) + d_ext.bitcast(UInt(35))).bitcast(Bits(35)),
                self.partial_rem[0]
            )
            raw_remainder = corrected_rem[0:31]  # Lower 32 bits

            debug_log("SRT4Divider: raw_quotient=0x{:x}, raw_remainder=0x{:x}", raw_quotient, raw_remainder)

            # Apply sign correction
            # For quotient: if signs differ, negate
            # For remainder: same sign as dividend
            q_needs_neg = (self.div_sign[0] == Bits(2)(0b01)) | (self.div_sign[0] == Bits(2)(0b10))
            rem_needs_neg = self.div_sign[0][1:1]  # Dividend sign

            debug_log("SRT4Divider: div_sign=0x{:x}, q_needs_neg={}", self.div_sign[0], q_needs_neg)

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
                debug_log("SRT4Divider: Signed overflow detected (-2^31 / -1)")

            with Condition(~signed_overflow):
                # Normal result with sign correction
                q_signed = (self.sign_r[0] & q_needs_neg).select(
                    (~raw_quotient + Bits(32)(1)).bitcast(Bits(32)),
                    raw_quotient
                )
                rem_signed = (self.sign_r[0] & rem_needs_neg).select(
                    (~raw_remainder + Bits(32)(1)).bitcast(Bits(32)),
                    raw_remainder
                )

                debug_log("SRT4Divider: q_signed=0x{:x}, rem_signed=0x{:x}, is_rem={}",
                    q_signed, rem_signed, self.is_rem[0])

                # Select quotient or remainder
                self.result[0] = self.is_rem[0].select(rem_signed, q_signed)

            self.ready[0] = Bits(1)(1)
            self.rd_out[0] = self.rd_in[0]
            self.busy[0] = Bits(1)(0)
            self.state[0] = self.IDLE
            debug_log("SRT4Divider: Completed, result=0x{:x}", self.result[0])

    def get_result_if_ready(self):
        """
        Get result if division is complete.
        Returns: (ready, result, rd, error)
        """
        return (self.ready[0], self.result[0], self.rd_out[0], self.error[0])

    def clear_result(self):
        """Clear result and reset ready flag"""
        self.ready[0] = Bits(1)(0)