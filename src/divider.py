"""
SRT-4 Divider Module for RV32IM Division Instructions

This module implements a true SRT-4 (Sweeney-Robertson-Tocher) division algorithm
that computes 2 quotient bits per clock cycle using redundant digit representation.

Architecture Overview:
=====================

SRT-4 division uses a redundant quotient digit set {-2, -1, 0, 1, 2}, which allows
for simpler quotient digit selection compared to standard radix-4 division. The key
advantage is that the quotient digit can be selected by examining only a few bits
of the partial remainder, without requiring full comparison with divisor multiples.

Key Features:
- Quotient digits: {-2, -1, 0, 1, 2} (encoded in 3 bits)
- On-the-fly conversion from redundant to standard binary representation
- Uses Q and QM registers for on-the-fly conversion
- Partial remainder bounds: -2d <= w < 2d

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
1. Initialize: w = dividend (partial remainder), Q = 0, QM = -1
2. For i = 15 down to 0 (16 iterations):
   a. w_shifted = w << 2 (multiply partial remainder by 4)
   b. Select quotient digit q from {-2, -1, 0, 1, 2} based on top bits of w_shifted
   c. w = w_shifted - q * d
   d. Update Q and QM using on-the-fly conversion
3. Final correction:
   - If final w < 0: quotient = QM, adjust remainder
   - Else: quotient = Q, remainder = w

On-the-fly conversion:
- Q: quotient if next digit is >= 0
- QM: quotient if next digit is < 0 (Q minus 1 at current position)
- For q >= 0: new_Q = 4*Q + q, new_QM = 4*Q + (q-1)
- For q < 0:  new_Q = 4*QM + (4+q), new_QM = 4*QM + (4+q-1)
"""

from assassyn.frontend import *
from .debug_utils import debug_log


class SRT4Divider:
    """
    SRT-4 division for 32-bit operands using redundant quotient representation.

    The divider is a multi-cycle functional unit that takes ~18 cycles:
    - 1 cycle: Preprocessing (convert to unsigned, detect special cases)
    - 16 cycles: Iterative calculation (2 bits per cycle)
    - 1 cycle: Post-processing (sign correction, final quotient selection)

    SRT-4 Key Features:
    - Uses redundant digit set {-2, -1, 0, 1, 2}
    - On-the-fly conversion to binary using Q/QM registers
    - Quotient digit selection based on partial remainder estimate

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

        # Internal working registers for SRT-4
        self.dividend_r = RegArray(Bits(32), 1, initializer=[0])  # Unsigned dividend
        self.divisor_r = RegArray(Bits(32), 1, initializer=[0])   # Unsigned divisor
        
        # Partial remainder: 35 bits to handle signed operations and overflow
        # The partial remainder w satisfies: -2*d <= w < 2*d
        self.shift_rem = RegArray(Bits(35), 1, initializer=[0])
        # Alias for compatibility
        self.partial_rem = self.shift_rem
        
        # div_shift is not used in our non-normalizing SRT-4, but kept for compatibility
        self.div_shift = RegArray(Bits(6), 1, initializer=[0])
        
        # On-the-fly conversion registers
        # Q holds the quotient assuming the final/next digit is non-negative
        # QM holds Q-1 (quotient minus 1 at the current bit position)
        self.Q = RegArray(Bits(32), 1, initializer=[0])
        self.QM = RegArray(Bits(32), 1, initializer=[0])
        
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
    
    def find_leading_one(self, value):
        """
        Find the position of the leading 1 bit in a 32-bit value.
        Returns a 6-bit shift amount (0-31, or 32 if value is 0).
        
        This is a helper function kept for compatibility, not used in our
        non-normalizing SRT-4 implementation.
        """
        # Build a priority encoder using cascaded conditions
        result = Bits(6)(32)  # Default: no leading 1 found
        
        for i in range(31, -1, -1):
            bit_set = value[i:i] == Bits(1)(1)
            shift_amt = Bits(6)(31 - i)
            result = bit_set.select(shift_amt, result)
        
        return result
    
    def power_of_2(self, shift_amt):
        """
        Generate 2^shift_amt as a 32-bit value.
        Helper function kept for compatibility.
        """
        result = Bits(32)(1)
        for i in range(32):
            is_this_shift = (shift_amt == Bits(6)(i))
            result = is_this_shift.select(Bits(32)(1 << i), result)
        return result
    
    def quotient_select(self, w_high):
        """Alias for quotient_digit_select for compatibility"""
        return self.quotient_digit_select(w_high)

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

    def quotient_digit_select(self, w_high):
        """
        SRT-4 Quotient Digit Selection (QDS) function.
        
        This function selects a quotient digit from {-2, -1, 0, 1, 2} based on
        the high bits of the partial remainder. The selection uses simple
        comparison thresholds.
        
        For SRT-4 with redundancy parameter a=2 and radix r=4:
        - If w >= 2d: q = 2
        - If w >= d:  q = 1  
        - If w >= 0:  q = 0
        - If w >= -d: q = -1
        - Else:       q = -2
        
        However, to avoid comparing with full d, we use an approximation based
        on the top bits of w. The selection uses a simplified Robertson diagram.
        
        Args:
            w_high: Top 6 bits of partial remainder (signed, 2's complement)
        
        Returns:
            q: Quotient digit encoded as 3-bit value
               010 = +2, 001 = +1, 000 = 0, 111 = -1, 110 = -2
        """
        # Interpret w_high as a signed 6-bit value
        # We select q based on the magnitude of w_high
        # 
        # For a well-designed SRT-4 divider without normalization,
        # we compare w_high (representing w/d approximately) against thresholds:
        # q=+2: w_high >= 4 (very positive)
        # q=+1: w_high >= 2 (moderately positive)  
        # q=0:  -2 < w_high < 2 (near zero)
        # q=-1: w_high <= -2 (moderately negative)
        # q=-2: w_high <= -4 (very negative)
        
        # Check sign bit (bit 5)
        w_sign = w_high[5:5]
        
        # Thresholds for positive partial remainders
        # +4 in 6-bit = 000100
        # +2 in 6-bit = 000010
        THRESH_POS_4 = Bits(6)(4)
        THRESH_POS_2 = Bits(6)(2)
        
        # Thresholds for negative partial remainders (2's complement)
        # -2 in 6-bit = 111110
        # -4 in 6-bit = 111100
        THRESH_NEG_2 = Bits(6)(0b111110)
        THRESH_NEG_4 = Bits(6)(0b111100)
        
        # For positive w_high (sign = 0)
        is_positive = (w_sign == Bits(1)(0))
        ge_pos4 = is_positive & (w_high >= THRESH_POS_4)
        ge_pos2 = is_positive & (w_high >= THRESH_POS_2)
        
        # For negative w_high (sign = 1)  
        is_negative = (w_sign == Bits(1)(1))
        # In 2's complement, more negative values have smaller bit patterns
        le_neg4 = is_negative & (w_high <= THRESH_NEG_4)
        le_neg2 = is_negative & (w_high <= THRESH_NEG_2)
        
        # Select quotient digit
        # Priority: +2 > +1 > 0 > -1 > -2
        q = ge_pos4.select(
            Bits(3)(0b010),  # q = +2
            ge_pos2.select(
                Bits(3)(0b001),  # q = +1
                le_neg4.select(
                    Bits(3)(0b110),  # q = -2
                    le_neg2.select(
                        Bits(3)(0b111),  # q = -1
                        Bits(3)(0b000)   # q = 0
                    )
                )
            )
        )
        
        return q

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

        # State: DIV_PRE - Preprocessing
        with Condition(self.state[0] == self.DIV_PRE):
            # Initialize for SRT-4 division
            # Partial remainder starts at 0 (will shift in dividend bits)
            # We use a combined approach: partial_rem holds shifted partial remainder
            # and Q/QM are used for on-the-fly conversion
            
            # Initialize partial remainder to 0 extended to 35 bits
            self.partial_rem[0] = concat(Bits(3)(0), self.dividend_r[0])
            
            # Initialize on-the-fly conversion registers
            # Q starts at 0, QM starts at all 1s (representing -1 at each position)
            self.Q[0] = Bits(32)(0)
            self.QM[0] = Bits(32)(0xFFFFFFFF)
            
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
            # 1. Shift partial remainder left by 2 (multiply by 4)
            # 2. Select quotient digit q from {-2, -1, 0, 1, 2}
            # 3. Compute new partial remainder: w_new = 4*w - q*d
            # 4. Update Q and QM for on-the-fly conversion

            # Step 1: Shift partial remainder left by 2
            # Take the lower 33 bits and shift left by 2
            w_shifted = concat(self.partial_rem[0][0:32], Bits(2)(0))

            # Step 2: Quotient digit selection
            # Use the top 6 bits of the shifted partial remainder for selection
            # These bits represent w/d approximately after scaling
            w_high = w_shifted[29:34]  # Top 6 bits of 35-bit value
            q_digit = self.quotient_digit_select(w_high)
            
            # Decode the quotient digit for arithmetic
            # q encoding: 010 = +2, 001 = +1, 000 = 0, 111 = -1, 110 = -2
            is_q_pos2 = (q_digit == Bits(3)(0b010))
            is_q_pos1 = (q_digit == Bits(3)(0b001))
            is_q_zero = (q_digit == Bits(3)(0b000))
            is_q_neg1 = (q_digit == Bits(3)(0b111))
            is_q_neg2 = (q_digit == Bits(3)(0b110))

            # Step 3: Compute new partial remainder: w_new = 4*w - q*d
            # Extend divisor to 35 bits
            d_ext = concat(Bits(3)(0), self.divisor_r[0])
            d_2x = concat(Bits(2)(0), self.divisor_r[0], Bits(1)(0))  # 2*d
            
            # Compute q*d for each case
            # For q = +2: subtract 2*d
            # For q = +1: subtract d
            # For q = 0:  no change
            # For q = -1: add d
            # For q = -2: add 2*d
            
            w_minus_2d = (w_shifted.bitcast(UInt(35)) - d_2x.bitcast(UInt(35))).bitcast(Bits(35))
            w_minus_d = (w_shifted.bitcast(UInt(35)) - d_ext.bitcast(UInt(35))).bitcast(Bits(35))
            w_plus_d = (w_shifted.bitcast(UInt(35)) + d_ext.bitcast(UInt(35))).bitcast(Bits(35))
            w_plus_2d = (w_shifted.bitcast(UInt(35)) + d_2x.bitcast(UInt(35))).bitcast(Bits(35))
            
            # Select new partial remainder based on q
            new_w = is_q_pos2.select(
                w_minus_2d,
                is_q_pos1.select(
                    w_minus_d,
                    is_q_neg2.select(
                        w_plus_2d,
                        is_q_neg1.select(
                            w_plus_d,
                            w_shifted  # q = 0
                        )
                    )
                )
            )

            # Step 4: On-the-fly quotient conversion
            # The on-the-fly algorithm maintains Q and QM such that:
            # - Q is the quotient if the remaining digits are non-negative
            # - QM is Q-1 (quotient minus 1 at the current bit position)
            #
            # For q >= 0: new_Q = 4*Q + q, new_QM = 4*Q + (q-1)
            # For q < 0:  new_Q = 4*QM + (4+q), new_QM = 4*QM + (4+q-1)
            
            Q_shifted = concat(self.Q[0][0:29], Bits(2)(0))  # Q << 2 (multiply by 4)
            QM_shifted = concat(self.QM[0][0:29], Bits(2)(0))  # QM << 2
            
            # Compute new Q and QM for each case
            # q=+2: new_Q = 4*Q + 2, new_QM = 4*Q + 1
            new_Q_pos2 = (Q_shifted.bitcast(UInt(32)) + Bits(32)(2).bitcast(UInt(32))).bitcast(Bits(32))
            new_QM_pos2 = (Q_shifted.bitcast(UInt(32)) + Bits(32)(1).bitcast(UInt(32))).bitcast(Bits(32))
            
            # q=+1: new_Q = 4*Q + 1, new_QM = 4*Q + 0
            new_Q_pos1 = (Q_shifted.bitcast(UInt(32)) + Bits(32)(1).bitcast(UInt(32))).bitcast(Bits(32))
            new_QM_pos1 = Q_shifted
            
            # q=0: new_Q = 4*Q + 0, new_QM = 4*Q + (-1) = 4*Q - 1 = 4*QM + 3
            new_Q_zero = Q_shifted
            new_QM_zero = (QM_shifted.bitcast(UInt(32)) + Bits(32)(3).bitcast(UInt(32))).bitcast(Bits(32))
            
            # q=-1: new_Q = 4*QM + 3, new_QM = 4*QM + 2
            new_Q_neg1 = (QM_shifted.bitcast(UInt(32)) + Bits(32)(3).bitcast(UInt(32))).bitcast(Bits(32))
            new_QM_neg1 = (QM_shifted.bitcast(UInt(32)) + Bits(32)(2).bitcast(UInt(32))).bitcast(Bits(32))
            
            # q=-2: new_Q = 4*QM + 2, new_QM = 4*QM + 1
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
                            new_Q_neg2  # q = -2
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
                            new_QM_neg2  # q = -2
                        )
                    )
                )
            )

            # Update registers
            self.partial_rem[0] = new_w
            self.Q[0] = new_Q
            self.QM[0] = new_QM

            # Decrement counter
            self.div_cnt[0] = (self.div_cnt[0].bitcast(UInt(5)) - Bits(5)(1)).bitcast(Bits(5))

        # State: DIV_END - Post-processing
        with Condition(self.state[0] == self.DIV_END):
            debug_log("SRT4Divider: DIV_END - Q=0x{:x}, QM=0x{:x}, partial_rem=0x{:x}",
                self.Q[0], self.QM[0], self.partial_rem[0])

            # Final quotient selection based on sign of partial remainder
            # If partial remainder is negative, use QM (which is Q-1)
            # Otherwise use Q
            rem_sign = self.partial_rem[0][34:34]  # Sign bit of partial remainder
            
            # Select quotient based on remainder sign
            raw_quotient = rem_sign.select(self.QM[0], self.Q[0])
            
            # Compute remainder
            # If rem_sign is 1 (negative), we need to add divisor to get positive remainder
            d_ext = concat(Bits(3)(0), self.divisor_r[0])
            corrected_rem = rem_sign.select(
                (self.partial_rem[0].bitcast(UInt(35)) + d_ext.bitcast(UInt(35))).bitcast(Bits(35)),
                self.partial_rem[0]
            )
            raw_remainder = corrected_rem[0:31]  # Take lower 32 bits

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